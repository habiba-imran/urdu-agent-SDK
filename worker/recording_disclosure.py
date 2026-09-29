"""F-C4 Phase C: spoken recording disclosure + stay-on-line consent grant.

Platform-owned disclosure text (not tenant greeting). Spoken with
``allow_interruptions=False`` before the normal session opening. After playout
completes without interruption, consent becomes ``granted`` (persist may upload).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from worker.recording_policy import (
    CONSENT_GRANTED,
    CONSENT_PENDING,
)

logger = logging.getLogger("worker.recording_disclosure")

# Stay-on-line v1 (plan D2). Keep plain — do not Cartesia-enrich (legal clarity).
_DISCLOSURE_EN = (
    "This call may be recorded for quality and training. Continuing means you agree."
)
_DISCLOSURE_UR = (
    "یہ کال معیار اور تربیت کے لیے ریکارڈ کی جا سکتی ہے۔ "
    "جاری رکھنے کا مطلب ہے کہ آپ متفق ہیں۔"
)

# None = not probed; True/False after first check (Ehsan migration may lag).
_sessions_has_consent_cols: bool | None = None


def reset_consent_column_probe() -> None:
    """Test helper."""
    global _sessions_has_consent_cols
    _sessions_has_consent_cols = None


def recording_disclosure_text(agent_language: str | None) -> str:
    lang = (agent_language or "").strip().lower()
    if lang in ("ur", "urdu"):
        return _DISCLOSURE_UR
    return _DISCLOSURE_EN


def _consent_columns_exist(conn: Any) -> bool:
    global _sessions_has_consent_cols
    if _sessions_has_consent_cols is not None:
        return _sessions_has_consent_cols
    row = conn.execute(
        """
        select 1
          from information_schema.columns
         where table_schema = 'public'
           and table_name = 'sessions'
           and column_name = 'recording_consent_status'
         limit 1
        """
    ).fetchone()
    _sessions_has_consent_cols = row is not None
    return _sessions_has_consent_cols


def persist_recording_consent(
    *,
    room_name: str,
    status: str,
    consented_at: datetime | None = None,
) -> bool:
    """Write consent fields on ``sessions`` when columns exist. Returns True if written."""
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "scripts"))
    try:
        from scripts.dbconn import conn_kwargs
    except ImportError:
        from dbconn import conn_kwargs  # type: ignore

    import psycopg

    at = consented_at or datetime.now(timezone.utc)
    try:
        with psycopg.connect(**conn_kwargs(), connect_timeout=5, autocommit=True) as conn:
            if not _consent_columns_exist(conn):
                logger.info(
                    "recording consent DB skip room=%s — columns not migrated yet",
                    room_name,
                )
                return False
            conn.execute(
                """
                update sessions
                   set recording_consent_status = %s,
                       recording_consent_at = %s
                 where room_name = %s
                """,
                (status, at, room_name),
            )
        logger.info(
            "recording consent persisted room=%s status=%s",
            room_name,
            status,
        )
        return True
    except Exception as exc:
        logger.warning(
            "recording consent persist failed room=%s: %s",
            room_name,
            exc,
        )
        return False


async def speak_recording_disclosure_if_needed(
    session: Any,
    *,
    agent_language: str | None,
    room_name: str,
    logger: Any | None = None,
) -> bool:
    """Speak non-interruptible disclosure when recording may start.

    Returns True when stay-on-line consent was granted (playout finished, not interrupted).
    """
    log = logger or globals()["logger"]
    userdata = getattr(session, "userdata", None)
    if userdata is None or not getattr(userdata, "recording_may_start", False):
        return False

    # Ensure pending until playout completes.
    userdata.recording_consent_status = CONSENT_PENDING
    text = recording_disclosure_text(agent_language)
    log.info(
        "recording disclosure speaking room=%s chars=%s allow_interruptions=False",
        room_name,
        len(text),
    )

    # Same shield as greeting: telephony force barge-in flush skips when opening_active.
    userdata.opening_active = True
    handle = None
    try:
        handle = session.say(text, allow_interruptions=False)
        if handle is not None and hasattr(handle, "wait_for_playout"):
            try:
                await handle.wait_for_playout()
            except Exception as exc:
                log.warning(
                    "recording disclosure playout failed room=%s: %s",
                    room_name,
                    exc,
                )
                return False
    finally:
        userdata.opening_active = False

    if handle is not None and getattr(handle, "interrupted", False):
        log.info(
            "recording disclosure interrupted room=%s — consent stays pending",
            room_name,
        )
        return False

    granted_at = datetime.now(timezone.utc)
    userdata.recording_consent_status = CONSENT_GRANTED
    userdata.recording_consent_at = granted_at.isoformat()

    # DB write off the event loop (same pattern as other worker sync DB touches).
    import asyncio

    await asyncio.to_thread(
        persist_recording_consent,
        room_name=room_name,
        status=CONSENT_GRANTED,
        consented_at=granted_at,
    )
    log.info("recording consent granted room=%s (stay-on-line)", room_name)
    return True
