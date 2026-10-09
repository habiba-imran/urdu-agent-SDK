"""Worker-side ``telephony_calls.platform_status`` tracking from LiveKit SIP state.

A-01.6: outbound rows are inserted as ``dialing`` and, until now, only a Telnyx
``call.*`` webhook (which needs ``webhook_event_url`` on the Telnyx connection) or the
2h sweep in ``telephony_reconcile.py`` ever moved them — so call history showed every
outbound call as ``failed / provider_timeout``.

The worker is in the room and LiveKit publishes the SIP leg's state on the participant:

* attribute ``sip.callStatus`` — ``dialing`` → ``ringing`` → ``active`` (answered;
  ``automation`` means DTMF automation on an answered call) → ``hangup``
* a disconnect reason when a dial never connects — ``USER_REJECTED`` (busy/declined),
  ``USER_UNAVAILABLE`` (no answer / unreachable), ``SIP_TRUNK_FAILURE``

This module mirrors those onto the call row, independent of provider webhooks:

* non-terminal transitions go through ``transition_call_status(only_from=...)`` so a
  late or duplicate event can never downgrade a call or overwrite a terminal status;
* a dial that fails to connect is finalized immediately (``busy`` / ``no_answer`` /
  ``failed``) through ``finalize_call`` — the same ``quota_released_at`` ledger the
  webhook, worker shutdown and reconciler use, so nothing double-releases;
* an answered call is left for ``worker/session_close`` to complete at shutdown.

DB writes run off the event loop (``run_blocking``); each uses a short-lived autocommit
connection. Row lookups are retried on every event because the outbound row is
committed by the portal API a moment *after* the agent is dispatched.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("worker.telephony_call_status")

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

SIP_CALL_STATUS_ATTR = "sip.callStatus"

# LiveKit sip.callStatus -> telephony_calls.platform_status (non-terminal only).
SIP_CALL_STATUS_MAP: dict[str, str] = {
    "dialing": "dialing",
    "ringing": "ringing",
    "active": "in_progress",
    "automation": "in_progress",
}

# Order matters: a transition is applied only from a strictly lower rank.
STATUS_RANK: dict[str, int] = {"queued": 0, "dialing": 1, "ringing": 2, "in_progress": 3}

# LiveKit DisconnectReason for a SIP participant that never connected -> terminal status.
DISCONNECT_REASON_MAP: dict[str, tuple[str, str]] = {
    "USER_REJECTED": ("busy", "callee_rejected"),
    "USER_UNAVAILABLE": ("no_answer", "callee_unavailable"),
    "SIP_TRUNK_FAILURE": ("failed", "sip_trunk_failure"),
}


def _open_conn() -> Any:
    try:
        from scripts.dbconn import conn_kwargs
    except ImportError:
        from dbconn import conn_kwargs  # type: ignore # noqa: E402

    import psycopg

    return psycopg.connect(**conn_kwargs(), connect_timeout=5, autocommit=True)


def _default_run_blocking(fn: Callable[[], None]) -> None:
    """Run ``fn`` off the event loop when one is running, else inline (tests/scripts)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        fn()
        return

    def _guarded() -> None:
        try:
            fn()
        except Exception as e:  # pragma: no cover - logged, never raised into the loop
            logger.error("telephony_call_status write failed: %s", e)

    loop.run_in_executor(None, _guarded)


def _attrs_of(participant: Any) -> dict[str, Any]:
    raw = getattr(participant, "attributes", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _is_sip_participant(participant: Any, attrs: dict[str, Any] | None = None) -> bool:
    attrs = attrs if attrs is not None else _attrs_of(participant)
    if any(str(k).startswith("sip.") for k in attrs):
        return True
    kind = str(getattr(participant, "kind", "") or "").lower()
    identity = str(getattr(participant, "identity", "") or "").lower()
    return "sip" in kind or identity.startswith("sip")


def disconnect_reason_name(value: Any) -> str:
    """Normalize LiveKit's DisconnectReason (enum / int / str) to its upper-case name."""
    if value is None:
        return ""
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name.upper()
    if isinstance(value, int):
        try:  # pragma: no cover - requires livekit protocol package
            from livekit.protocol.models import DisconnectReason

            return str(DisconnectReason.Name(value)).upper()
        except Exception:
            return str(value)
    return str(value).upper()


class TelephonyCallStatusTracker:
    """Mirror LiveKit SIP participant state onto the room's ``telephony_calls`` row."""

    def __init__(
        self,
        *,
        room_name: str,
        telephony_call_id: str | None = None,
        tenant_id: str = "",
        conn_factory: Callable[[], Any] | None = None,
        run_blocking: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self.room_name = room_name
        self.telephony_call_id = (telephony_call_id or "").strip() or None
        self.tenant_id = (tenant_id or "").strip()
        self._conn_factory = conn_factory or _open_conn
        self._run_blocking = run_blocking or _default_run_blocking
        self._last_rank = -1
        self.answered = False
        self.finalized = False
        self._call: dict[str, Any] | None = None

    # ------------------------------------------------------------------ wiring
    def attach(self, room: Any) -> "TelephonyCallStatusTracker":
        room.on("participant_attributes_changed", self._on_attributes_changed)
        room.on("participant_connected", self._on_participant_connected)
        room.on("participant_disconnected", self._on_participant_disconnected)
        # Outbound: the SIP participant may already be in the room when the agent joins.
        remotes = getattr(room, "remote_participants", None) or {}
        for participant in list(remotes.values()):
            attrs = _attrs_of(participant)
            if SIP_CALL_STATUS_ATTR in attrs:
                self.on_sip_call_status(attrs[SIP_CALL_STATUS_ATTR])
        return self

    def _on_attributes_changed(self, changed: Any, participant: Any = None) -> None:
        if not isinstance(changed, dict):
            return
        if SIP_CALL_STATUS_ATTR in changed:
            self.on_sip_call_status(changed[SIP_CALL_STATUS_ATTR])

    def _on_participant_connected(self, participant: Any) -> None:
        attrs = _attrs_of(participant)
        if SIP_CALL_STATUS_ATTR in attrs:
            self.on_sip_call_status(attrs[SIP_CALL_STATUS_ATTR])

    def _on_participant_disconnected(self, participant: Any) -> None:
        attrs = _attrs_of(participant)
        if not _is_sip_participant(participant, attrs):
            return
        reason = disconnect_reason_name(getattr(participant, "disconnect_reason", None))
        self.on_sip_participant_disconnected(reason)

    # ------------------------------------------------------------------ events
    def on_sip_call_status(self, raw_status: Any) -> None:
        raw = str(raw_status or "").strip().lower()
        mapped = SIP_CALL_STATUS_MAP.get(raw)
        if mapped is None:
            # ``hangup`` and unknown values: terminal handling belongs to disconnect /
            # session shutdown, which know *why* the call ended.
            return
        rank = STATUS_RANK[mapped]
        if rank <= self._last_rank:
            return
        self._last_rank = rank
        if mapped == "in_progress":
            self.answered = True
        lower = [s for s, r in STATUS_RANK.items() if r < rank]
        self._run_blocking(
            lambda: self._write_transition(mapped, raw_participant_status=f"sip.callStatus:{raw}", only_from=lower)
        )

    def on_sip_participant_disconnected(self, reason: str) -> None:
        if self.answered or self.finalized:
            # Answered calls are completed by worker/session_close at shutdown.
            return
        reason = (reason or "").upper()
        mapped = DISCONNECT_REASON_MAP.get(reason)
        if mapped is None:
            # e.g. CLIENT_INITIATED / ROOM_DELETED before answer: the shutdown path will
            # record no_answer from the row's dialing/ringing status.
            logger.info(
                "telephony_call_status room=%s sip participant left before answer reason=%s "
                "(left to session_close)",
                self.room_name,
                reason or "-",
            )
            return
        status, error_code = mapped
        self.finalized = True
        self._run_blocking(
            lambda: self._write_finalize(status, error_code=error_code, raw_participant_status=f"disconnect:{reason}")
        )

    # --------------------------------------------------------------------- db
    def _resolve_call(self, conn: Any) -> dict[str, Any] | None:
        if self._call is not None:
            return self._call
        from tenant_portal_api import telephony_queries as queries

        call = queries.find_open_call_by_room(conn, self.room_name)
        if call is None and self.telephony_call_id:
            row = conn.execute(
                "select id, tenant_id, platform_status from telephony_calls where id = %s",
                (self.telephony_call_id,),
            ).fetchone()
            if row:
                call = {"id": str(row[0]), "tenant_id": str(row[1]), "platform_status": row[2]}
        if call is not None:
            self._call = {"id": call["id"], "tenant_id": call["tenant_id"] or self.tenant_id}
        return self._call

    def _write_transition(self, status: str, *, raw_participant_status: str, only_from: list[str]) -> None:
        from tenant_portal_api import telephony_queries as queries

        conn = self._conn_factory()
        try:
            call = self._resolve_call(conn)
            if call is None:
                logger.info(
                    "telephony_call_status room=%s no telephony_calls row yet; skipped status=%s",
                    self.room_name,
                    status,
                )
                return
            changed = queries.transition_call_status(
                conn,
                call["id"],
                status,
                raw_participant_status=raw_participant_status,
                answered=(status == "in_progress"),
                only_from=only_from,
            )
            logger.info(
                "telephony_call_status room=%s call=%s status=%s applied=%s",
                self.room_name,
                call["id"],
                status,
                bool(changed),
            )
        finally:
            _close_quietly(conn)

    def _write_finalize(self, status: str, *, error_code: str, raw_participant_status: str) -> None:
        from tenant_portal_api import telephony_queries as queries

        conn = self._conn_factory()
        try:
            call = self._resolve_call(conn)
            if call is None:
                logger.warning(
                    "telephony_call_status room=%s dial failed (%s) but no telephony_calls row found",
                    self.room_name,
                    status,
                )
                return
            outcome = queries.finalize_call(
                conn,
                call["id"],
                call["tenant_id"],
                status,
                error_code=error_code,
                error_message=f"Dial did not connect: {raw_participant_status}",
                raw_participant_status=raw_participant_status,
            )
            logger.info(
                "telephony_call_status room=%s call=%s finalized status=%s status_changed=%s quota_released=%s",
                self.room_name,
                call["id"],
                status,
                outcome["status_changed"],
                outcome["quota_released"],
            )
        finally:
            _close_quietly(conn)


def _close_quietly(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # pragma: no cover
            pass


def attach_call_status_tracker(
    room: Any,
    *,
    room_name: str,
    telephony_call_id: str | None = None,
    tenant_id: str = "",
) -> TelephonyCallStatusTracker | None:
    """Best-effort attach for ``worker/main.py``; never raises into the entrypoint."""
    try:
        return TelephonyCallStatusTracker(
            room_name=room_name,
            telephony_call_id=telephony_call_id,
            tenant_id=tenant_id,
        ).attach(room)
    except Exception as e:
        logger.warning("telephony_call_status attach failed room=%s: %s", room_name, e)
        return None
