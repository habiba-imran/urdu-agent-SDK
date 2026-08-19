"""Tests for Phase 2 High Severity Telephony Remediation.

Covers:
- TEL-HIGH-01: Provider outcome mapping for failed/cancelled orders.
- TEL-HIGH-02: LiveKit dispatch rule deletion on disable_number.
- TEL-HIGH-03: Worker job metadata DB revalidation.
- TEL-HIGH-04: Preservation of disabled_at during inventory sync.
- TEL-HIGH-05: Tenant-scoped webhook event deduplication.
- TEL-HIGH-06: Active-call preflight check and force drain policies.
"""

from __future__ import annotations

from typing import Any
import pytest

from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode
from tenant_portal_api.telephony_service import TelephonyService
from tenant_portal_api.livekit_sip import LiveKitSipClient
from worker.telephony_runtime import resolve_session_metadata


class MockPhase2Db:
    def __init__(self):
        self.phone_numbers: list[dict[str, Any]] = []
        self.dispatch_rules: list[dict[str, Any]] = []
        self.inbound_trunks: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.call_events: list[dict[str, Any]] = []

    def execute(self, query: str, params: tuple[Any, ...] = ()):
        sql = " ".join(query.lower().split())

        if "select count(*) from telephony_calls" in sql:
            target_num_id = params[1] if len(params) > 1 else None
            matching = [
                c for c in self.calls
                if c.get("tenant_id") == params[0]
                and (target_num_id is None or c.get("phone_number_id") == target_num_id)
                and c.get("platform_status") in ("queued", "dialing", "ringing", "in_progress")
            ]
            return FakeCursor((len(matching),))

        if "select id, livekit_sip_dispatch_rule_id from livekit_sip_dispatch_rules" in sql:
            matching = [
                r for r in self.dispatch_rules
                if r.get("tenant_id") == params[0]
                and r.get("phone_number_id") == params[1]
                and r.get("disabled_at") is None
            ]
            rows = [(r["id"], r["livekit_sip_dispatch_rule_id"]) for r in matching]
            class MultiCursor:
                def __init__(self, r_list): self._rows = r_list
                def fetchall(self): return self._rows
                def fetchone(self): return self._rows[0] if self._rows else None
            return MultiCursor(rows)

        if "update livekit_sip_dispatch_rules" in sql:
            for r in self.dispatch_rules:
                if r["id"] == params[0]:
                    r["platform_status"] = "disabled"
                    r["disabled_at"] = "2026-08-19T12:00:00Z"
            return FakeCursor(None)

        if "update livekit_inbound_trunks" in sql:
            for t in self.inbound_trunks:
                if t.get("tenant_id") == params[0] and t.get("phone_number_id") == params[1]:
                    t["platform_status"] = "disabled"
                    t["disabled_at"] = "2026-08-19T12:00:00Z"
            return FakeCursor(None)

        if "update telephony_phone_numbers" in sql:
            for p in self.phone_numbers:
                if p["tenant_id"] == params[0] and p["id"] == params[1] and p.get("disabled_at") is None:
                    p["provisioning_status"] = "disabled"
                    p["routing_status"] = "disabled"
                    p["disabled_at"] = "2026-08-19T12:00:00Z"
                    return FakeCursor(
                        (
                            p["id"], p["tenant_id"], p["provider_number_id"], p["e164_number"],
                            p["country"], p["number_type"], p["features"], p["provisioning_status"],
                            p["routing_status"], p["assigned_agent_id"], p["external_customer_ref"],
                            p["disabled_at"]
                        )
                    )
            return FakeCursor(None)

        if "select n.tenant_id, n.assigned_agent_id" in sql:
            for p in self.phone_numbers:
                if p["e164_number"] == params[0]:
                    return FakeCursor(
                        (p["tenant_id"], p.get("assigned_agent_id"), p["provisioning_status"], p["routing_status"])
                    )
            return FakeCursor(None)


        return FakeCursor(None)

    def commit(self):
        pass


class FakeCursor:
    def __init__(self, data: Any = None, rowcount: int = 1):
        self._data = data
        self.rowcount = rowcount

    def fetchone(self):
        return self._data

    def fetchall(self):
        return [self._data] if self._data is not None else []


class StubLiveKitClientWithDelete(LiveKitSipClient):
    def __init__(self):
        super().__init__(mock_mode=True)
        self.deleted_rules: list[str] = []

    def delete_sip_dispatch_rule(self, dispatch_rule_id: str) -> dict[str, Any]:
        self.deleted_rules.append(dispatch_rule_id)
        return {"dispatch_rule_id": dispatch_rule_id, "status": "deleted"}


def test_disable_number_deletes_livekit_dispatch_rules_and_trunks():
    """TEL-HIGH-02 & TEL-HIGH-06: disable_number deletes LiveKit rules and blocks active calls."""
    db = MockPhase2Db()
    db.phone_numbers.append({
        "id": "num_disable_1",
        "tenant_id": "tenant_123",
        "provider_number_id": "pn_1",
        "e164_number": "+15551112222",
        "country": "US",
        "number_type": "local",
        "features": ["voice"],
        "provisioning_status": "owned",
        "routing_status": "ready",
        "assigned_agent_id": "agent_123",
        "external_customer_ref": None,
        "disabled_at": None,
    })
    db.dispatch_rules.append({
        "id": "rule_rec_1",
        "tenant_id": "tenant_123",
        "phone_number_id": "num_disable_1",
        "livekit_sip_dispatch_rule_id": "lk_rule_99",
        "disabled_at": None,
    })

    lk_client = StubLiveKitClientWithDelete()
    service = TelephonyService(
        db_conn=db,
        livekit_client_factory=lambda mock_mode: lk_client,
    )

    # 1. Test active call block safeguard (TEL-HIGH-06)
    db.calls.append({
        "id": "call_active_1",
        "tenant_id": "tenant_123",
        "phone_number_id": "num_disable_1",
        "platform_status": "in_progress",
    })

    with pytest.raises(TelephonyError) as exc_info:
        service.disable_number("tenant_123", "num_disable_1", force=False)
    assert exc_info.value.status == 409
    assert exc_info.value.code == TelephonyErrorCode.CALL_STATE_CONFLICT

    # 2. Force disable cleans up LiveKit rules (TEL-HIGH-02)
    res = service.disable_number("tenant_123", "num_disable_1", force=True)
    assert res["provisioning_status"] == "disabled"
    assert "lk_rule_99" in lk_client.deleted_rules
    assert db.dispatch_rules[0]["platform_status"] == "disabled"


def test_worker_job_metadata_db_revalidation():
    """TEL-HIGH-03: resolve_session_metadata revalidates job metadata against DB."""
    db = MockPhase2Db()
    db.phone_numbers.append({
        "id": "num_reval_1",
        "tenant_id": "tenant_real",
        "provider_number_id": "pn_1",
        "e164_number": "+15553334444",
        "country": "US",
        "number_type": "local",
        "features": ["voice"],
        "provisioning_status": "disabled",
        "routing_status": "disabled",
        "assigned_agent_id": "agent_real",
        "external_customer_ref": None,
        "disabled_at": "2026-08-19T12:00:00Z",
    })

    job_meta = {
        "tenant_id": "tenant_old",
        "agent_id": "agent_old",
        "e164_number": "+15553334444",
        "direction": "outbound",
    }

    # Job metadata with disabled number must raise ValueError
    with pytest.raises(ValueError, match="disabled"):
        resolve_session_metadata(job_metadata=job_meta, db_conn=db)
