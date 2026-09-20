"""F-H18 Phase B: resilient session close + quota/usage on clean shutdown.

Called from ``worker/main.py`` shutdown callback. Crash/OOM still needs scheduled
``scripts/reconcile_sessions.py`` (Ehsan) — this module only hardens the clean path.

Order (plan D3 / B.2):
1. Mark session ended if still open
2. Decrement concurrent quota if we closed an open row and have tenant_id
3. Best-effort: transcript, retention, usage / minutes
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("worker.session_close")

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@dataclass(frozen=True)
class SessionCloseResult:
    """Outcome of one close attempt (idempotent on already-closed rooms)."""

    closed: bool
    session_id: str | None
    quota_decremented: bool
    usage_events: int
    transcript_attached: bool


def build_transcript(session_obj: Any) -> list[dict[str, Any]]:
    """Best-effort transcript from AgentSession history. Empty on any failure."""
    try:
        from worker.humanization.history import plain_text_for_history

        return [
            {
                "role": m.role,
                "text": plain_text_for_history(m.text_content or ""),
                "at": m.created_at,
            }
            for m in session_obj.history.messages()
            if m.role in ("user", "assistant") and (m.text_content or "").strip()
        ]
    except Exception as e:
        logger.warning(
            "session_close stage=transcript_build failed (using empty) err=%s",
            e,
        )
        return []


def _open_conn() -> Any:
    try:
        from scripts.dbconn import conn_kwargs
    except ImportError:
        from dbconn import conn_kwargs  # type: ignore # noqa: E402

    import psycopg

    return psycopg.connect(**conn_kwargs(), connect_timeout=5, autocommit=True)


def release_session_quota_slot(
    *,
    room_name: str,
    tenant_id: str,
    elapsed_sec: int,
    end_reason: str,
    session_obj: Any | None = None,
    transcript: list[dict[str, Any]] | None = None,
    conn: Any | None = None,
) -> SessionCloseResult:
    """Close open session row, release concurrency, then best-effort billing extras.

    If ``conn`` is provided (tests), it is used and not closed by this function.
    Otherwise a short-lived autocommit connection is opened.
    """
    owns_conn = conn is None
    if owns_conn:
        try:
            conn = _open_conn()
        except Exception as e:
            logger.error(
                "session_close stage=connect failed room=%s tenant_id=%s err=%s",
                room_name,
                tenant_id or "-",
                e,
            )
            return SessionCloseResult(
                closed=False,
                session_id=None,
                quota_decremented=False,
                usage_events=0,
                transcript_attached=False,
            )

    try:
        return _release_on_conn(
            conn,
            room_name=room_name,
            tenant_id=tenant_id,
            elapsed_sec=elapsed_sec,
            end_reason=end_reason,
            session_obj=session_obj,
            transcript=transcript,
        )
    finally:
        if owns_conn and conn is not None:
            try:
                conn.close()
            except Exception as e:
                # Best-effort close after close stages already logged ERROR/OK.
                logger.warning("stage=conn_close failed room=%s err=%s", room_name, e)


def _release_on_conn(
    conn: Any,
    *,
    room_name: str,
    tenant_id: str,
    elapsed_sec: int,
    end_reason: str,
    session_obj: Any | None,
    transcript: list[dict[str, Any]] | None,
) -> SessionCloseResult:
    session_id: str | None = None
    closed = False
    quota_decremented = False
    usage_events = 0
    transcript_attached = False

    # --- Stage 1: mark session ended (no transcript yet — isolation) ---
    try:
        updated = conn.execute(
            "update sessions set ended_at = now(), duration_sec = %s, end_reason = %s "
            "where room_name = %s and ended_at is null returning id",
            (elapsed_sec, end_reason, room_name),
        ).fetchone()
    except Exception as e:
        logger.error(
            "session_close stage=close_session failed room=%s tenant_id=%s err=%s",
            room_name,
            tenant_id or "-",
            e,
        )
        return SessionCloseResult(
            closed=False,
            session_id=None,
            quota_decremented=False,
            usage_events=0,
            transcript_attached=False,
        )

    if not updated:
        logger.info(
            "session_close stage=close_session noop room=%s tenant_id=%s "
            "(already closed or unknown room)",
            room_name,
            tenant_id or "-",
        )
        return SessionCloseResult(
            closed=False,
            session_id=None,
            quota_decremented=False,
            usage_events=0,
            transcript_attached=False,
        )

    closed = True
    session_id = str(updated[0])
    logger.info(
        "session_close stage=close_session ok room=%s tenant_id=%s session_id=%s "
        "duration_sec=%s end_reason=%s",
        room_name,
        tenant_id or "-",
        session_id,
        elapsed_sec,
        end_reason,
    )

    # --- Stage 2: quota (only if we just closed an open row) ---
    if tenant_id:
        try:
            conn.execute(
                "update quota_state set concurrent_now = greatest(concurrent_now - 1, 0) "
                "where tenant_id = %s",
                (tenant_id,),
            )
            quota_decremented = True
            logger.info(
                "session_close stage=quota_decrement ok room=%s tenant_id=%s",
                room_name,
                tenant_id,
            )
        except Exception as e:
            logger.error(
                "session_close stage=quota_decrement failed room=%s tenant_id=%s err=%s",
                room_name,
                tenant_id,
                e,
            )
    else:
        logger.error(
            "session_close stage=quota_decrement skipped room=%s tenant_id=- "
            "(no tenant_id; reconcile_sessions.py must correct concurrent_now)",
            room_name,
        )

    # --- Stage 3+: best-effort extras (must not undo close/quota) ---
    if transcript is None:
        transcript = build_transcript(session_obj) if session_obj is not None else []

    transcript_attached = _attach_transcript(
        conn, room_name=room_name, tenant_id=tenant_id, transcript=transcript
    )
    _apply_retention(conn, room_name=room_name, tenant_id=tenant_id, session_id=session_id)
    usage_events = _record_usage_and_minutes(
        conn,
        room_name=room_name,
        tenant_id=tenant_id,
        session_id=session_id,
        session_obj=session_obj,
        elapsed_sec=elapsed_sec,
    )

    return SessionCloseResult(
        closed=closed,
        session_id=session_id,
        quota_decremented=quota_decremented,
        usage_events=usage_events,
        transcript_attached=transcript_attached,
    )


def _attach_transcript(
    conn: Any,
    *,
    room_name: str,
    tenant_id: str,
    transcript: list[dict[str, Any]],
) -> bool:
    try:
        from psycopg.types.json import Jsonb

        conn.execute(
            "update sessions set transcript = %s where room_name = %s",
            (Jsonb(transcript), room_name),
        )
        logger.info(
            "session_close stage=transcript ok room=%s tenant_id=%s turns=%s",
            room_name,
            tenant_id or "-",
            len(transcript),
        )
        return True
    except Exception as e:
        logger.error(
            "session_close stage=transcript failed room=%s tenant_id=%s err=%s",
            room_name,
            tenant_id or "-",
            e,
        )
        return False


def _apply_retention(
    conn: Any, *, room_name: str, tenant_id: str, session_id: str
) -> None:
    try:
        from worker.session_retention import apply_retention_on_session_close

        apply_retention_on_session_close(
            conn,
            room_name=room_name,
            session_id=session_id,
        )
    except Exception as e:
        logger.error(
            "session_close stage=retention failed room=%s tenant_id=%s session_id=%s err=%s",
            room_name,
            tenant_id or "-",
            session_id,
            e,
        )


def _record_usage_and_minutes(
    conn: Any,
    *,
    room_name: str,
    tenant_id: str,
    session_id: str,
    session_obj: Any | None,
    elapsed_sec: int,
) -> int:
    if not tenant_id:
        return 0
    try:
        from worker.usage import collect_model_usage, record_usage_many

        items = collect_model_usage(session_obj) if session_obj is not None else {}
        items["agent_sec"] = float(elapsed_sec)
        n = record_usage_many(conn, tenant_id, session_id, items)

        conn.execute(
            """
            insert into quota_state (tenant_id, minutes_this_month, period_start)
            values (%s, %s, date_trunc('month', now())::date)
            on conflict (tenant_id) do update set
              minutes_this_month = case
                when quota_state.period_start < date_trunc('month', now())::date
                  then excluded.minutes_this_month
                else quota_state.minutes_this_month + excluded.minutes_this_month
              end,
              period_start = date_trunc('month', now())::date
            """,
            (tenant_id, elapsed_sec / 60.0),
        )
        logger.info(
            "session_close stage=usage ok room=%s tenant_id=%s events=%s minutes=%.2f",
            room_name,
            tenant_id,
            n,
            elapsed_sec / 60.0,
        )
        return n
    except Exception as e:
        logger.error(
            "session_close stage=usage failed room=%s tenant_id=%s session_id=%s err=%s",
            room_name,
            tenant_id,
            session_id,
            e,
        )
        return 0
