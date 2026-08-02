"""Worker-side runtime resolver and event hooks for telephony SIP calls.

Extracts trusted LiveKit SIP participant attributes and resolves tenant, agent,
and phone number records before conversation startup.

Minimal non-intrusive hooks for worker/main.py.
Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import logging
from typing import Any

from tenant_portal_api.telephony_config import is_mock_provider_mode

logger = logging.getLogger(__name__)


def extract_sip_participant_attributes(participant_metadata: dict[str, Any] | str) -> dict[str, str]:
    """Extract LiveKit SIP attributes from participant metadata dictionary or JSON string."""
    meta = participant_metadata
    if isinstance(participant_metadata, str):
        import json
        try:
            meta = json.loads(participant_metadata)
        except Exception:
            meta = {}

    if not isinstance(meta, dict):
        meta = {}

    sip_data = meta.get("sip", {}) if isinstance(meta.get("sip"), dict) else meta
    return {
        "sip_call_id": sip_data.get("sip.callID") or sip_data.get("callID") or "",
        "sip_call_id_full": sip_data.get("sip.callIDFull") or sip_data.get("callIDFull") or "",
        "trunk_phone_number": sip_data.get("sip.trunkPhoneNumber") or sip_data.get("trunkPhoneNumber") or "",
        "trunk_id": sip_data.get("sip.trunkID") or sip_data.get("trunkID") or "",
        "rule_id": sip_data.get("sip.ruleID") or sip_data.get("ruleID") or "",
    }


def resolve_inbound_sip_call(
    participant_metadata: dict[str, Any] | str,
    db_conn: Any = None,
) -> dict[str, Any]:
    """Resolve tenant, agent, and number routing from LiveKit SIP participant attributes.

    Returns dict containing tenant_id, agent_id, e164_number, and call_id.
    Raises ValueError on unknown or unassigned numbers.
    """
    attributes = extract_sip_participant_attributes(participant_metadata)
    trunk_num = attributes["trunk_phone_number"]

    # Explicit local/test mock mode. Real staging must provide a DB connection.
    if not db_conn:
        if not is_mock_provider_mode():
            raise ValueError("Database connection is required for live inbound SIP resolution")
        logger.info("Resolving inbound SIP call for number: %s (mock mode)", trunk_num or "+15551234567")
        return {
            "tenant_id": "tenant_test_123",
            "agent_id": "agent_test_456",
            "e164_number": trunk_num or "+15551234567",
            "sip_call_id": attributes["sip_call_id"] or "sip_call_mock_inbound",
            "status": "resolved",
        }

    # DB Resolution using parameterized query
    row = db_conn.execute(
        """
        select n.tenant_id, n.assigned_agent_id, n.e164_number, n.routing_status, t.status
        from telephony_phone_numbers n
        join tenants t on t.id = n.tenant_id
        where n.e164_number = %s and n.disabled_at is null
        """,
        (trunk_num,),
    ).fetchone()

    if not row:
        logger.warning("Rejecting inbound call: unknown number %s", trunk_num)
        raise ValueError(f"Unknown inbound phone number: {trunk_num}")

    tenant_id, agent_id, e164_num, routing_status, tenant_status = row

    if tenant_status != "active":
        raise ValueError(f"Tenant {tenant_id} is not active")

    if not agent_id:
        raise ValueError(f"Number {e164_num} is not assigned to an agent")

    if routing_status != "ready":
        raise ValueError(f"Number {e164_num} routing is not ready")

    return {
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "e164_number": e164_num,
        "sip_call_id": attributes["sip_call_id"],
        "status": "resolved",
    }
