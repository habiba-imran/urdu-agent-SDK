"""Correlate Telnyx ``call.*`` webhook events with ``telephony_calls`` rows (A-01.1).

Why this exists
---------------
LiveKit's ``CreateSIPParticipant`` returns LiveKit's own ``sip_call_id`` (``SCL_…``).
Telnyx webhooks carry Telnyx's ``call_control_id`` / ``call_session_id`` / ``call_leg_id``.
Neither side knows the other's id at dial time, so matching ``call_control_id`` against
``livekit_sip_call_id`` (the previous behaviour) never succeeded.

Strategy
--------
1. Exact: ``provider_call_control_id`` (then ``provider_call_session_id``) once bound.
2. Legacy: ``livekit_sip_call_id`` / ``_full`` — kept so environments where the ids happen
   to coincide (mocks) and pre-0039 databases keep working.
3. First-event bind: an unbound, still-active call with the same direction and the same
   from/to digits, created within ``BIND_WINDOW_MINUTES``, tenant-scoped via Telnyx
   ``connection_id`` when the payload has one. Exactly one candidate binds atomically.
   Several candidates: prefer the one created nearest the event's ``start_time``; without a
   usable timestamp refuse to bind (fail safe — the reconciler's timeout still applies).

Column availability is probed once per process so a service deployed before migration
0039 degrades to (1b)+(2) with a warning instead of aborting the webhook transaction.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("tenant_portal_api.telephony_call_correlation")

BIND_WINDOW_MINUTES = 15
ACTIVE_STATUSES = ("queued", "dialing", "ringing", "in_progress")

_provider_cols_present: bool | None = None  # None = not probed yet


def reset_column_probe() -> None:
    """Test helper."""
    global _provider_cols_present
    _provider_cols_present = None


def provider_call_columns_exist(conn: Any) -> bool:
    """Probe once whether migration 0039 has been applied."""
    global _provider_cols_present
    if _provider_cols_present is not None:
        return _provider_cols_present
    try:
        row = conn.execute(
            """
            select 1
              from information_schema.columns
             where table_schema = 'public'
               and table_name = 'telephony_calls'
               and column_name = 'provider_call_control_id'
             limit 1
            """
        ).fetchone()
        present = row is not None
    except Exception as exc:  # fake connections in tests may not know this query
        logger.debug("provider column probe failed, assuming present: %s", exc)
        present = True
    if not present:
        logger.warning(
            "telephony_calls.provider_call_control_id missing — apply migration 0039; "
            "Telnyx call events can only be correlated by legacy LiveKit sip id"
        )
    _provider_cols_present = present
    return present


_SIP_URI_RE = re.compile(r"^(?:sips?|tel):", re.IGNORECASE)


def normalize_phone_digits(raw: Any) -> str:
    """Return digits only from ``+1415…``, ``sip:+1415…@host``, ``tel:…`` forms."""
    s = str(raw or "").strip()
    if not s:
        return ""
    s = _SIP_URI_RE.sub("", s)
    s = s.split("@", 1)[0]
    s = s.split(";", 1)[0]
    return "".join(c for c in s if c.isdigit())


def map_provider_direction(raw: Any) -> str | None:
    d = str(raw or "").strip().lower()
    if d in {"outgoing", "outbound"}:
        return "outbound"
    if d in {"incoming", "inbound"}:
        return "inbound"
    return None


def _parse_ts(raw: Any) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass(frozen=True)
class CallEventIdentity:
    call_control_id: str | None
    call_session_id: str | None
    call_leg_id: str | None
    connection_id: str | None
    from_digits: str
    to_digits: str
    direction: str | None
    started_at: datetime | None

    @property
    def has_provider_id(self) -> bool:
        return bool(self.call_control_id or self.call_session_id)


def extract_call_identity(payload: dict[str, Any]) -> CallEventIdentity:
    """Pull correlation fields from a Telnyx webhook body (or just its ``data.payload``)."""
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}
    inner = data.get("payload") if isinstance(data.get("payload"), dict) else data

    def _s(key: str) -> str | None:
        v = inner.get(key)
        if v is None:
            return None
        text = str(v).strip()
        return text or None

    return CallEventIdentity(
        call_control_id=_s("call_control_id"),
        call_session_id=_s("call_session_id"),
        call_leg_id=_s("call_leg_id"),
        connection_id=_s("connection_id"),
        from_digits=normalize_phone_digits(inner.get("from")),
        to_digits=normalize_phone_digits(inner.get("to")),
        direction=map_provider_direction(inner.get("direction")),
        started_at=_parse_ts(inner.get("start_time") or data.get("occurred_at")),
    )


def _exact_by_provider_ids(conn: Any, ident: CallEventIdentity) -> tuple[str, str] | None:
    if ident.call_control_id:
        row = conn.execute(
            """
            select id, tenant_id from telephony_calls
            where provider_call_control_id = %s
            order by created_at desc limit 1
            """,
            (ident.call_control_id,),
        ).fetchone()
        if row:
            return str(row[0]), str(row[1])
    if ident.call_session_id:
        row = conn.execute(
            """
            select id, tenant_id from telephony_calls
            where provider_call_session_id = %s
            order by created_at desc limit 1
            """,
            (ident.call_session_id,),
        ).fetchone()
        if row:
            return str(row[0]), str(row[1])
    return None


def _legacy_by_livekit_sip_id(conn: Any, ident: CallEventIdentity) -> tuple[str, str] | None:
    key = ident.call_control_id or ident.call_session_id
    if not key:
        return None
    row = conn.execute(
        """
        select id, tenant_id from telephony_calls
        where livekit_sip_call_id = %s or livekit_sip_call_id_full = %s
        order by created_at desc limit 1
        """,
        (key, key),
    ).fetchone()
    if row:
        return str(row[0]), str(row[1])
    return None


def _tenant_for_connection(conn: Any, connection_id: str | None) -> str | None:
    if not connection_id:
        return None
    try:
        row = conn.execute(
            """
            select tenant_id from telnyx_sip_connections
            where provider_sip_connection_id = %s and disabled_at is null
            order by created_at desc limit 1
            """,
            (connection_id,),
        ).fetchone()
    except Exception as exc:
        logger.debug("connection_id → tenant lookup failed: %s", exc)
        return None
    return str(row[0]) if row else None


def _candidates_by_numbers(
    conn: Any, ident: CallEventIdentity, tenant_id: str | None
) -> list[tuple[str, str, datetime | None]]:
    """Unbound active calls whose from/to digits match, newest first."""
    if not ident.from_digits or not ident.to_digits:
        return []
    sql = """
        select id, tenant_id, created_at
        from telephony_calls
        where provider_call_control_id is null
          and platform_status in ('queued', 'dialing', 'ringing', 'in_progress')
          and created_at > now() - (%s * interval '1 minute')
          and regexp_replace(coalesce(from_number, ''), '[^0-9]', '', 'g') = %s
          and regexp_replace(coalesce(to_number, ''), '[^0-9]', '', 'g') = %s
    """
    params: list[Any] = [BIND_WINDOW_MINUTES, ident.from_digits, ident.to_digits]
    if ident.direction:
        sql += " and direction = %s"
        params.append(ident.direction)
    if tenant_id:
        sql += " and tenant_id = %s"
        params.append(tenant_id)
    sql += " order by created_at desc limit 5"
    rows = conn.execute(sql, tuple(params)).fetchall() or []
    return [(str(r[0]), str(r[1]), r[2] if len(r) > 2 else None) for r in rows]


def _pick_candidate(
    cands: list[tuple[str, str, datetime | None]], started_at: datetime | None
) -> tuple[str, str] | None:
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0][0], cands[0][1]
    if started_at is None:
        return None
    best: tuple[str, str] | None = None
    best_gap: float | None = None
    for call_id, tenant_id, created_at in cands:
        if not isinstance(created_at, datetime):
            continue
        created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        gap = abs((started_at - created).total_seconds())
        if best_gap is None or gap < best_gap:
            best, best_gap = (call_id, tenant_id), gap
    return best


def bind_provider_ids(conn: Any, call_id: str, ident: CallEventIdentity) -> bool:
    """Atomically attach Telnyx ids to an unbound row. False if another event won the race."""
    row = conn.execute(
        """
        update telephony_calls
        set provider_call_control_id = %s,
            provider_call_session_id = coalesce(%s, provider_call_session_id),
            provider_call_leg_id = coalesce(%s, provider_call_leg_id),
            provider_call_bound_at = now(),
            updated_at = now()
        where id = %s and provider_call_control_id is null
        returning id
        """,
        (ident.call_control_id, ident.call_session_id, ident.call_leg_id, call_id),
    ).fetchone()
    return row is not None


def resolve_call_for_event(
    conn: Any, ident: CallEventIdentity, *, bind: bool = True
) -> tuple[str, str] | None:
    """Return ``(call_id, tenant_id)`` for this event, binding provider ids on first contact."""
    if not ident.has_provider_id and not (ident.from_digits and ident.to_digits):
        return None

    cols_ok = provider_call_columns_exist(conn)

    if cols_ok:
        found = _exact_by_provider_ids(conn, ident)
        if found:
            return found

    found = _legacy_by_livekit_sip_id(conn, ident)
    if found:
        return found

    if not cols_ok or not ident.call_control_id:
        return None

    tenant_id = _tenant_for_connection(conn, ident.connection_id)
    cands = _candidates_by_numbers(conn, ident, tenant_id)
    if len(cands) > 1:
        logger.warning(
            "ambiguous Telnyx call correlation: %s candidates direction=%s tenant=%s",
            len(cands),
            ident.direction or "-",
            tenant_id or "-",
        )
    picked = _pick_candidate(cands, ident.started_at)
    if not picked:
        return None
    if not bind:
        return picked

    call_id, tenant = picked
    if bind_provider_ids(conn, call_id, ident):
        logger.info(
            "bound Telnyx call ids to telephony_call=%s tenant=%s direction=%s",
            call_id,
            tenant,
            ident.direction or "-",
        )
        return call_id, tenant
    # Lost a race with a concurrent event for the same call — the exact lookup now resolves.
    return _exact_by_provider_ids(conn, ident)
