"""Worker-side runtime resolver and event hooks for telephony SIP calls.

Extracts trusted LiveKit SIP participant attributes and resolves tenant, agent,
and phone number records before conversation startup.

Minimal non-intrusive hooks for worker/main.py.
Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tenant_portal_api.telephony_config import is_mock_provider_mode

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def extract_sip_participant_attributes(
    participant_metadata: dict[str, Any] | str | None = None,
    participant_attributes: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Extract LiveKit SIP attributes from participant attributes and/or metadata."""
    attrs = dict(participant_attributes or {})
    meta = _as_dict(participant_metadata)
    sip_meta = meta.get("sip") if isinstance(meta.get("sip"), dict) else meta

    def _get(*keys: str) -> str:
        for key in keys:
            if attrs.get(key):
                return str(attrs[key])
            if sip_meta.get(key):
                return str(sip_meta[key])
        return ""

    return {
        "sip_call_id": _get("sip.callID", "callID"),
        "sip_call_id_full": _get("sip.callIDFull", "callIDFull"),
        "trunk_phone_number": _get("sip.trunkPhoneNumber", "trunkPhoneNumber"),
        "trunk_id": _get("sip.trunkID", "trunkID"),
        "rule_id": _get("sip.ruleID", "ruleID"),
    }


def is_sip_participant(
    participant: Any = None,
    *,
    participant_metadata: dict[str, Any] | str | None = None,
    participant_attributes: dict[str, Any] | None = None,
) -> bool:
    """Return True when the joining participant looks like a LiveKit SIP caller."""
    attrs = dict(participant_attributes or {})
    if participant is not None:
        raw_attrs = getattr(participant, "attributes", None) or {}
        if isinstance(raw_attrs, dict):
            attrs.update(raw_attrs)
        kind = str(getattr(participant, "kind", "") or "").lower()
        identity = str(getattr(participant, "identity", "") or "").lower()
        if "sip" in kind or identity.startswith("sip_"):
            return True
    extracted = extract_sip_participant_attributes(participant_metadata, attrs)
    return bool(
        extracted["trunk_phone_number"]
        or extracted["sip_call_id"]
        or extracted["trunk_id"]
    )


def parse_job_telephony_metadata(job_metadata: Any) -> dict[str, Any]:
    """Parse CreateAgentDispatch / RoomAgentDispatch metadata for telephony jobs."""
    meta = _as_dict(job_metadata)
    tenant_id = meta.get("tenant_id")
    agent_id = meta.get("agent_id")
    if not tenant_id or not agent_id:
        return {}
    return {
        "tenant_id": str(tenant_id),
        "agent_id": str(agent_id),
        "telephony_call_id": str(meta.get("telephony_call_id") or ""),
        "direction": str(meta.get("direction") or "outbound"),
        "e164_number": str(meta.get("e164_number") or meta.get("from_number") or ""),
        "sip_call_id": str(meta.get("sip_call_id") or ""),
        "status": "resolved",
        "source": "job_metadata",
    }


def resolve_inbound_sip_call(
    participant_metadata: dict[str, Any] | str | None = None,
    db_conn: Any = None,
    participant_attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve tenant, agent, and number routing from LiveKit SIP participant attributes.

    Returns dict containing tenant_id, agent_id, e164_number, and call_id.
    Raises ValueError on unknown or unassigned numbers.
    """
    attributes = extract_sip_participant_attributes(
        participant_metadata, participant_attributes
    )
    trunk_num = attributes["trunk_phone_number"]

    # Explicit local/test mock mode. Real staging must provide a DB connection.
    if not db_conn:
        if not is_mock_provider_mode():
            raise ValueError(
                "Database connection is required for live inbound SIP resolution"
            )
        logger.info(
            "Resolving inbound SIP call for number: %s (mock mode)",
            trunk_num or "+15551234567",
        )
        return {
            "tenant_id": "tenant_test_123",
            "agent_id": "agent_test_456",
            "e164_number": trunk_num or "+15551234567",
            "sip_call_id": attributes["sip_call_id"] or "sip_call_mock_inbound",
            "direction": "inbound",
            "status": "resolved",
            "source": "sip_attributes",
        }

    if not trunk_num:
        raise ValueError("Inbound SIP participant is missing sip.trunkPhoneNumber")

    # DB Resolution using parameterized query
    row = db_conn.execute(
        """
        select n.tenant_id, n.assigned_agent_id, n.e164_number, n.routing_status, t.status, n.id
        from telephony_phone_numbers n
        join tenants t on t.id = n.tenant_id
        where n.e164_number = %s and n.disabled_at is null
        """,
        (trunk_num,),
    ).fetchone()

    if not row:
        logger.warning("Rejecting inbound call: unknown number %s", trunk_num)
        raise ValueError(f"Unknown inbound phone number: {trunk_num}")

    tenant_id, agent_id, e164_num, routing_status, tenant_status, phone_number_id = row

    if tenant_status != "active":
        raise ValueError(f"Tenant {tenant_id} is not active")

    if not agent_id:
        raise ValueError(f"Number {e164_num} is not assigned to an agent")

    if routing_status != "ready":
        raise ValueError(f"Number {e164_num} routing is not ready")

    return {
        "tenant_id": str(tenant_id),
        "agent_id": str(agent_id),
        "e164_number": e164_num,
        "phone_number_id": str(phone_number_id),
        "sip_call_id": attributes["sip_call_id"],
        "direction": "inbound",
        "status": "resolved",
        "source": "sip_attributes",
    }


def resolve_session_metadata(
    *,
    job_metadata: Any = None,
    participant: Any = None,
    db_conn: Any = None,
) -> dict[str, Any]:
    """Resolve tenant/agent session metadata for web or telephony jobs.

    Priority:
    1. Explicit agent-dispatch job metadata (outbound / pre-resolved inbound)
    2. SIP participant attributes → DB number lookup
    3. Participant JWT metadata (browser /v1/session mint path)
    """
    from_job = parse_job_telephony_metadata(job_metadata)
    if from_job:
        return {
            "tenant_id": from_job["tenant_id"],
            "agent_id": from_job["agent_id"],
            "telephony": from_job,
        }

    participant_metadata = (
        getattr(participant, "metadata", None) if participant is not None else None
    )
    participant_attributes = (
        getattr(participant, "attributes", None) if participant is not None else None
    )
    if isinstance(participant_attributes, dict) and is_sip_participant(
        participant,
        participant_metadata=participant_metadata,
        participant_attributes=participant_attributes,
    ):
        resolved = resolve_inbound_sip_call(
            participant_metadata=participant_metadata,
            participant_attributes=participant_attributes,
            db_conn=db_conn,
        )
        return {
            "tenant_id": resolved["tenant_id"],
            "agent_id": resolved["agent_id"],
            "telephony": resolved,
        }

    md = _as_dict(participant_metadata)
    return {
        "tenant_id": md.get("tenant_id", ""),
        "agent_id": md.get("agent_id", ""),
        "telephony": None,
    }
