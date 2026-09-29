"""Resolve verified caller phone for F-C7 ownership (D10).

Sources (priority):
1. Mint / dispatch / participant metadata ``verified_caller_phone``
2. LiveKit SIP participant attribute ``sip.phoneNumber`` (caller ANI)
3. ``telephony_calls`` remote party for this room (inbound → from_number, outbound → to_number)

Never use trunk / job ``e164_number`` / ``sip.trunkPhoneNumber`` as verified caller.
"""

from __future__ import annotations

import logging
from typing import Any

from worker.telephony_runtime import extract_sip_participant_attributes
from worker.write_tool_gate import normalize_phone

logger = logging.getLogger(__name__)


def remote_party_from_telephony_call(
    *,
    direction: str | None,
    from_number: str | None,
    to_number: str | None,
) -> str | None:
    """Pick the remote (human) party — never the platform trunk side alone."""
    d = (direction or "").strip().lower()
    if d == "inbound":
        return normalize_phone(from_number) or None
    if d == "outbound":
        return normalize_phone(to_number) or None
    return None


def load_remote_party_from_telephony_calls(
    db_conn: Any,
    *,
    room_name: str,
    telephony_call_id: str | None = None,
) -> str | None:
    """Load remote party from telephony_calls by call id or room_name."""
    if db_conn is None or not (room_name or "").strip():
        return None
    try:
        if telephony_call_id:
            row = db_conn.execute(
                """
                select direction, from_number, to_number
                from telephony_calls
                where id = %s
                limit 1
                """,
                (telephony_call_id,),
            ).fetchone()
        else:
            row = db_conn.execute(
                """
                select direction, from_number, to_number
                from telephony_calls
                where room_name = %s
                order by created_at desc
                limit 1
                """,
                (room_name,),
            ).fetchone()
    except Exception as exc:
        logger.warning(
            "telephony_calls remote party lookup failed room=%s: %s",
            room_name,
            exc,
        )
        return None
    if not row:
        return None
    return remote_party_from_telephony_call(
        direction=row[0],
        from_number=row[1],
        to_number=row[2],
    )


def resolve_verified_caller_phone(
    *,
    dispatch_or_md: dict[str, Any] | None = None,
    participant: Any = None,
    room_name: str | None = None,
    db_conn: Any = None,
    telephony_call_id: str | None = None,
) -> str | None:
    """Resolve verified caller phone; never returns trunk e164."""
    md = dict(dispatch_or_md or {})

    # 1) Explicit host/mint field only — ignore e164_number / from_number on job meta.
    mint = normalize_phone(md.get("verified_caller_phone"))
    if mint:
        return mint

    # 2) SIP ANI
    participant_metadata = getattr(participant, "metadata", None) if participant else None
    participant_attributes = (
        getattr(participant, "attributes", None) if participant else None
    )
    if isinstance(participant_attributes, dict) or participant_metadata:
        extracted = extract_sip_participant_attributes(
            participant_metadata,
            participant_attributes if isinstance(participant_attributes, dict) else None,
        )
        ani = normalize_phone(extracted.get("caller_phone_number"))
        if ani:
            return ani

    # 3) telephony_calls remote party
    if db_conn is not None and room_name:
        call_id = telephony_call_id or str(md.get("telephony_call_id") or "") or None
        remote = load_remote_party_from_telephony_calls(
            db_conn,
            room_name=room_name,
            telephony_call_id=call_id,
        )
        if remote:
            return remote

    return None
