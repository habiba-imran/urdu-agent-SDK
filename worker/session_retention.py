"""F-C4 Phase D: session media retention helpers (set retention_until on close)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("worker.session_retention")

_DEFAULT_RETENTION_DAYS = 30

# Column probes (None = not checked yet). Sessions/escalations may lack cols until A.3.
_sessions_has_retention: bool | None = None
_escalations_has_retention: bool | None = None


def reset_retention_column_probes() -> None:
    """Test helper."""
    global _sessions_has_retention, _escalations_has_retention
    _sessions_has_retention = None
    _escalations_has_retention = None


def retention_days_from_env() -> int:
    raw = (os.environ.get("UVA_RECORDING_RETENTION_DAYS") or str(_DEFAULT_RETENTION_DAYS)).strip()
    try:
        days = int(raw)
    except ValueError:
        logger.warning(
            "invalid UVA_RECORDING_RETENTION_DAYS=%r — using %s",
            raw,
            _DEFAULT_RETENTION_DAYS,
        )
        return _DEFAULT_RETENTION_DAYS
    if days < 1:
        logger.warning(
            "UVA_RECORDING_RETENTION_DAYS=%s < 1 — using %s",
            days,
            _DEFAULT_RETENTION_DAYS,
        )
        return _DEFAULT_RETENTION_DAYS
    return days


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        select 1
          from information_schema.columns
         where table_schema = 'public'
           and table_name = %s
           and column_name = %s
         limit 1
        """,
        (table, column),
    ).fetchone()
    return row is not None


def _sessions_retention_ready(conn: Any) -> bool:
    global _sessions_has_retention
    if _sessions_has_retention is True:
        return True
    # Do not cache False — A.3 may land without worker restart.
    ready = _column_exists(conn, "sessions", "retention_until")
    if ready:
        _sessions_has_retention = True
    return ready


def _escalations_retention_ready(conn: Any) -> bool:
    global _escalations_has_retention
    if _escalations_has_retention is True:
        return True
    ready = _column_exists(conn, "escalations", "retention_until")
    if ready:
        _escalations_has_retention = True
    return ready


def apply_retention_on_session_close(
    conn: Any,
    *,
    room_name: str,
    session_id: str | None,
    retention_days: int | None = None,
) -> None:
    """Set retention_until on session / telephony_calls / escalations when columns exist.

    ``telephony_calls.retention_until`` already exists (migration 0014).
    ``sessions`` / ``escalations`` columns land with Ehsan A.3 — skipped until then.
    """
    days = retention_days if retention_days is not None else retention_days_from_env()

    # telephony_calls — always attempt (column exists since 0014).
    try:
        conn.execute(
            """
            update telephony_calls
               set retention_until = now() + (%s || ' days')::interval,
                   updated_at = now()
             where room_name = %s
               and retention_until is null
               and deleted_at is null
            """,
            (str(days), room_name),
        )
    except Exception as exc:
        logger.warning(
            "session retention: telephony_calls update failed room=%s: %s",
            room_name,
            exc,
        )

    if session_id and _sessions_retention_ready(conn):
        try:
            conn.execute(
                """
                update sessions
                   set retention_until = now() + (%s || ' days')::interval
                 where id = %s
                   and retention_until is null
                """,
                (str(days), session_id),
            )
        except Exception as exc:
            logger.warning(
                "session retention: sessions update failed id=%s: %s",
                session_id,
                exc,
            )
    elif session_id:
        logger.info(
            "session retention: sessions.retention_until not migrated yet — skip room=%s",
            room_name,
        )

    if session_id and _escalations_retention_ready(conn):
        try:
            conn.execute(
                """
                update escalations
                   set retention_until = now() + (%s || ' days')::interval
                 where session_id = %s
                   and retention_until is null
                """,
                (str(days), session_id),
            )
        except Exception as exc:
            logger.warning(
                "session retention: escalations update failed session_id=%s: %s",
                session_id,
                exc,
            )
