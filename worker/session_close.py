"""F-H18 Phase B: resilient session close + quota/usage on clean shutdown.

Called from ``worker/main.py`` shutdown callback. Crash/OOM still needs scheduled
``scripts/reconcile_sessions.py`` (Ehsan) — this module only hardens the clean path.

Order (plan D3 / B.2):
1. Mark session ended if still open
2. Decrement concurrent quota if we closed an open row and have tenant_id
   (telephony rooms release through ``telephony_calls.quota_released_at`` instead)
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
    # A-01.2: set when the room belonged to a telephony call (no ``sessions`` row) and
    # the close was applied to ``telephony_calls`` instead.
    telephony_call_id: str | None = None


_TELEPHONY_FAILURE_REASONS = ("stale", "error", "fail", "timeout", "abandon")


def _telephony_end_status(current_status: str | None, end_reason: str) -> str:
    """Pick a terminal ``telephony_calls.platform_status`` for a worker-side close.

    ``in_progress`` (answered — set by worker/telephony_call_status from LiveKit's
    ``sip.callStatus=active``, by the Telnyx webhook, or at insert for inbound) ends as
    ``completed``. A call still ``queued/dialing/ringing`` when the job shuts down was
    never answered: ``failed`` if the shutdown reason is an error, else ``no_answer``.
    """
    if current_status == "in_progress":
        return "completed"
    reason = (end_reason or "").lower()
    if any(tok in reason for tok in _TELEPHONY_FAILURE_REASONS):
        return "failed"
    if current_status in ("queued", "dialing", "ringing"):
        return "no_answer"
    return "completed"


def _finalize_telephony_call(
    conn: Any,
    *,
    room_name: str,
    tenant_id: str,
    end_reason: str,
) -> tuple[str | None, bool, str | None]:
    """Close the ``telephony_calls`` row for ``room_name`` and release its quota once.

    Returns ``(call_id, quota_released, call_tenant_id)``; ``(None, False, None)`` when
    the room is not a telephony room. The release is ledgered on
    ``telephony_calls.quota_released_at`` so it cannot double-decrement against the
    Telnyx webhook or the reconciler.
    """
    try:
        from tenant_portal_api import telephony_queries as queries
    except Exception as e:  # pragma: no cover - import environment issue
        logger.error("session_close stage=telephony_lookup import failed err=%s", e)
        return None, False, None

    try:
        call = queries.find_open_call_by_room(conn, room_name)
    except Exception as e:
        logger.error(
            "session_close stage=telephony_lookup failed room=%s tenant_id=%s err=%s",
            room_name,
            tenant_id or "-",
            e,
        )
        return None, False, None
    if not call:
        return None, False, None

    call_id = call["id"]
    call_tenant = call["tenant_id"] or tenant_id
    if tenant_id and call_tenant != tenant_id:
        logger.error(
            "session_close stage=telephony_close tenant mismatch room=%s call=%s "
            "md_tenant=%s row_tenant=%s (using row tenant)",
            room_name,
            call_id,
            tenant_id,
            call_tenant,
        )
    status = _telephony_end_status(call.get("platform_status"), end_reason)
    try:
        outcome = queries.finalize_call(
            conn,
            call_id,
            call_tenant,
            status,
            error_code="worker_shutdown" if status == "failed" else None,
            error_message=f"Closed by worker: {end_reason}" if status == "failed" else None,
            raw_participant_status=f"worker_shutdown:{end_reason}",
        )
    except Exception as e:
        logger.error(
            "session_close stage=telephony_close failed room=%s call=%s tenant_id=%s err=%s",
            room_name,
            call_id,
            call_tenant,
            e,
        )
        return call_id, False, call_tenant
    logger.info(
        "session_close stage=telephony_close ok room=%s call=%s tenant_id=%s status=%s "
        "status_changed=%s quota_released=%s",
        room_name,
        call_id,
        call_tenant,
        status,
        outcome["status_changed"],
        outcome["quota_released"],
    )
    return call_id, bool(outcome["quota_released"]), call_tenant


def build_transcript(session_obj: Any) -> list[dict[str, Any]]:
    """Best-effort full audit transcript; legacy sessions fall back to session history."""
    try:
        from worker.humanization.history import plain_text_for_history

        audit = getattr(getattr(session_obj, "userdata", None), "audit_transcript", None)
        if audit is not None and audit.turns():
            return audit.turns()

        turns = [
            {
                "role": m.role,
                "text": plain_text_for_history(m.text_content or ""),
                "at": m.created_at,
            }
            for m in session_obj.history.messages()
            if m.role in ("user", "assistant") and (m.text_content or "").strip()
        ]
        return turns
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
        # No open ``sessions`` row. Either a browser room that is already closed, or a
        # telephony call whose session is missing / was closed by reconcile_sessions.
        # Telephony slots are reserved on ``telephony_calls`` and must be released there.
        tele_call_id, tele_released, _ = _finalize_telephony_call(
            conn,
            room_name=room_name,
            tenant_id=tenant_id,
            end_reason=end_reason,
        )
        if tele_call_id is None:
            logger.info(
                "session_close stage=close_session noop room=%s tenant_id=%s "
                "(already closed or unknown room)",
                room_name,
                tenant_id or "-",
            )
        else:
            # Retention on telephony_calls is keyed by room_name and idempotent; usage
            # is deliberately skipped here (no open session to attribute it to — the
            # reconcile_sessions P3-H4 backfill owns usage for stale-closed sessions).
            _apply_retention(conn, room_name=room_name, tenant_id=tenant_id, session_id=None)
        return SessionCloseResult(
            closed=False,
            session_id=None,
            quota_decremented=tele_released,
            usage_events=0,
            transcript_attached=False,
            telephony_call_id=tele_call_id,
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
    # A-01.3: outbound calls now carry a sessions row *and* a telephony_calls
    # reservation. The reservation is the ledger (quota_released_at), so release
    # through it instead of the blind decrement — the Telnyx webhook and the telephony
    # reconciler share that ledger and cannot double-decrement with us.
    telephony_call_id, tele_released, tele_tenant = _finalize_telephony_call(
        conn,
        room_name=room_name,
        tenant_id=tenant_id,
        end_reason=end_reason,
    )
    if telephony_call_id is not None:
        quota_decremented = tele_released
        # Dispatch metadata can lack tenant_id; the call row is authoritative.
        tenant_id = tenant_id or tele_tenant or ""
    elif tenant_id:
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
        telephony_call_id=telephony_call_id,
    )

    return SessionCloseResult(
        closed=closed,
        session_id=session_id,
        quota_decremented=quota_decremented,
        usage_events=usage_events,
        transcript_attached=transcript_attached,
        telephony_call_id=telephony_call_id,
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
        from worker.humanization.history import sanitize_transcript_turns

        # Defense in depth: strip provider TTS markup even if caller passed raw turns.
        cleaned = sanitize_transcript_turns(transcript) or []

        conn.execute(
            "update sessions set transcript = %s where room_name = %s",
            (Jsonb(cleaned), room_name),
        )
        logger.info(
            "session_close stage=transcript ok room=%s tenant_id=%s turns=%s",
            room_name,
            tenant_id or "-",
            len(cleaned),
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
    telephony_call_id: str | None = None,
) -> int:
    if not tenant_id:
        return 0
    try:
        from worker.usage import collect_model_usage, record_usage_many

        items = collect_model_usage(session_obj) if session_obj is not None else {}
        items["agent_sec"] = float(elapsed_sec)
        n = record_usage_many(conn, tenant_id, session_id, items)

        if telephony_call_id:
            # Mark the call as billed so audits can find calls whose usage never landed.
            conn.execute(
                "update telephony_calls set usage_recorded_at = now(), updated_at = now() "
                "where id = %s and usage_recorded_at is null",
                (telephony_call_id,),
            )

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
