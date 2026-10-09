"""Comprehensive Client Calling Simulation & Telephony Edge-Case Test Suite.

Simulates how a client interacts with the telephony platform:
1. Client calling the agent (Inbound SIP call resolution, number assignment, routing readiness, quota checks).
2. Agent calling the client (Outbound SIP call creation, idempotency locking, LiveKit dispatching, quota limits).
3. Webhook status callbacks & out-of-order event delivery handling.
4. Number lifecycle & active-call drain safeguards.
"""

from __future__ import annotations

import json
from typing import Any
import pytest

from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode
from tenant_portal_api.telephony_service import TelephonyService
from tenant_portal_api.livekit_sip import LiveKitSipClient
from tenant_portal_api.telephony_webhooks import _apply_webhook_side_effects
from worker.telephony_runtime import resolve_inbound_sip_call, resolve_session_metadata


class ClientCallingSimulationDb:
    def __init__(self):
        self.tenants = [{"id": "tenant_client_1", "status": "active", "max_concurrent": 2}]
        self.minutes: dict[str, int] = {}
        self.phone_numbers = [{
            "id": "num_client_1",
            "tenant_id": "tenant_client_1",
            "provider_number_id": "pn_client_1",
            "e164_number": "+18005550199",
            "country": "US",
            "number_type": "toll_free",
            "features": ["voice"],
            "provisioning_status": "owned",
            "routing_status": "ready",
            "assigned_agent_id": "agent_voice_1",
            "external_customer_ref": "cust_ref_001",
            "disabled_at": None,
        }]
        self.dispatch_rules = [{
            "id": "rule_1",
            "tenant_id": "tenant_client_1",
            "phone_number_id": "num_client_1",
            "livekit_sip_dispatch_rule_id": "lk_rule_client_1",
            "disabled_at": None,
        }]
        self.calls: list[dict[str, Any]] = []
        self.sessions: list[dict[str, Any]] = []
        self.idempotency: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.quota: dict[str, int] = {"tenant_client_1": 0}

    def execute(self, query: str, params: tuple[Any, ...] = ()):
        sql = " ".join(query.lower().split())

        # A-01.3: outbound calls get a sessions row in the same transaction.
        if "insert into sessions" in sql:
            self.sessions.append({
                "id": params[0],
                "tenant_id": params[1],
                "agent_id": params[2],
                "room_name": params[3],
                "ended_at": None,
            })
            return FakeCursor(None)

        # F-H17: reserve_call_quota now reads the monthly cap and tenant status too, so
        # PSTN spend is gated the same way browser sessions always were.
        if "select max_concurrent" in sql and "from tenants" in sql:
            t = next((x for x in self.tenants if x["id"] == params[0]), None)
            if not t:
                return FakeCursor(None)
            return FakeCursor(
                (
                    t["max_concurrent"],
                    t.get("max_minutes_month", 100000),
                    t.get("status", "active"),
                )
            )

        if "insert into quota_state" in sql:
            if params[0] not in self.quota:
                self.quota[params[0]] = 0
            return FakeCursor()

        if "select concurrent_now" in sql and "from quota_state" in sql:
            return FakeCursor(
                (self.quota.get(params[0], 0), self.minutes.get(params[0], 0))
            )

        if "update quota_state set concurrent_now = concurrent_now + 1" in sql:
            self.quota[params[0]] = self.quota.get(params[0], 0) + 1
            return FakeCursor()

        if "update quota_state set concurrent_now = greatest(0, concurrent_now - 1)" in sql:
            self.quota[params[0]] = max(0, self.quota.get(params[0], 0) - 1)
            return FakeCursor()

        if "select n.tenant_id, n.assigned_agent_id, n.e164_number, n.routing_status, t.status, n.id" in sql:
            for p in self.phone_numbers:
                if p["e164_number"] == params[0] and p.get("disabled_at") is None:
                    t = next((x for x in self.tenants if x["id"] == p["tenant_id"]), None)
                    t_status = t["status"] if t else "active"
                    return FakeCursor((p["tenant_id"], p["assigned_agent_id"], p["e164_number"], p["routing_status"], t_status, p["id"]))
            return FakeCursor(None)

        if "from telephony_phone_numbers" in sql and "select" in sql:
            for p in self.phone_numbers:
                if p["tenant_id"] == params[0] and (p["id"] == params[1] or p["e164_number"] == params[1]) and p.get("disabled_at") is None:
                    return FakeCursor((
                        p["id"], p["tenant_id"], p["provider_number_id"], p["e164_number"],
                        p["country"], p["number_type"], p["features"], p["provisioning_status"],
                        p["routing_status"], p["assigned_agent_id"], p["external_customer_ref"], p["disabled_at"]
                    ))
            return FakeCursor(None)

        if "select id, livekit_sip_dispatch_rule_id from livekit_sip_dispatch_rules" in sql:
            matching = [r for r in self.dispatch_rules if r["tenant_id"] == params[0] and r["phone_number_id"] == params[1] and r.get("disabled_at") is None]
            class MultiCursor:
                def __init__(self, r_list): self._rows = r_list
                def fetchall(self): return [(r["id"], r["livekit_sip_dispatch_rule_id"]) for r in self._rows]
                def fetchone(self): return (self._rows[0]["id"], self._rows[0]["livekit_sip_dispatch_rule_id"]) if self._rows else None
            return MultiCursor(matching)

        # --- A-01.1 Telnyx ↔ telephony_calls correlation (telephony_call_correlation.py) ---
        if "from information_schema.columns" in sql:
            return FakeCursor((1,))

        if "from telnyx_sip_connections" in sql and "provider_sip_connection_id = %s" in sql:
            return FakeCursor(None)

        if "select id, tenant_id from telephony_calls" in sql and "provider_call_control_id = %s" in sql:
            c = next((x for x in self.calls if x.get("provider_call_control_id") == params[0]), None)
            return FakeCursor((c["id"], c["tenant_id"]) if c else None)

        if "select id, tenant_id from telephony_calls" in sql and "provider_call_session_id = %s" in sql:
            c = next((x for x in self.calls if x.get("provider_call_session_id") == params[0]), None)
            return FakeCursor((c["id"], c["tenant_id"]) if c else None)

        if "select id, tenant_id from telephony_calls" in sql and "livekit_sip_call_id = %s" in sql:
            c = next(
                (x for x in self.calls if x.get("livekit_sip_call_id") == params[0] or x.get("livekit_sip_call_id_full") == params[1]),
                None,
            )
            return FakeCursor((c["id"], c["tenant_id"]) if c else None)

        if "select id, tenant_id, created_at" in sql and "provider_call_control_id is null" in sql:
            digits = lambda s: "".join(ch for ch in str(s or "") if ch.isdigit())  # noqa: E731
            matching = [
                c for c in self.calls
                if c.get("provider_call_control_id") is None
                and c.get("platform_status") in ("queued", "dialing", "ringing", "in_progress")
                and digits(c.get("from_number")) == params[1]
                and digits(c.get("to_number")) == params[2]
            ]
            if "and direction = %s" in sql:
                matching = [c for c in matching if c.get("direction") == params[3]]
            class MultiCursor:
                def __init__(self, r_list): self._rows = r_list
                def fetchall(self): return [(c["id"], c["tenant_id"], None) for c in self._rows]
                def fetchone(self): return (self._rows[0]["id"], self._rows[0]["tenant_id"], None) if self._rows else None
            return MultiCursor(matching)

        if "update telephony_calls" in sql and "set provider_call_control_id = %s" in sql:
            for c in self.calls:
                if c["id"] == params[-1] and c.get("provider_call_control_id") is None:
                    c["provider_call_control_id"] = params[0]
                    c["provider_call_session_id"] = params[1]
                    c["provider_call_leg_id"] = params[2]
                    return FakeCursor((c["id"],))
            return FakeCursor(None)

        if "select count(*) from telephony_calls" in sql:
            matching = [
                c for c in self.calls
                if c.get("tenant_id") == params[0]
                and (len(params) <= 1 or params[1] is None or c.get("phone_number_id") == params[1])
                and c.get("platform_status") in ("queued", "dialing", "ringing", "in_progress")
            ]
            return FakeCursor((len(matching),))

        if "select from_number_id, tenant_id, agent_id" in sql:
            c = next((x for x in self.calls if x["id"] == params[0]), None)
            return FakeCursor((c["phone_number_id"], c["tenant_id"], c["agent_id"]) if c else None)

        if "update telephony_calls set quota_released_at" in sql:
            for c in self.calls:
                if c["id"] == params[0] and c.get("quota_released_at") is None:
                    c["quota_released_at"] = "2026-08-19T12:00:00Z"
                    return FakeCursor((c["id"],))
            return FakeCursor(None)

        if "insert into telephony_calls" in sql and "'inbound'" in sql:
            # A-01.4: worker-side inbound persistence (worker/telephony_runtime.py)
            self.calls.append({
                "id": params[0],
                "tenant_id": params[1],
                "session_id": params[2],
                "agent_id": params[3],
                "phone_number_id": params[4],
                "room_name": params[5],
                "from_number": params[6],
                "to_number": params[7],
                "inbound_trunk_record_id": params[8],
                "sip_dispatch_rule_record_id": params[9],
                "livekit_sip_call_id": params[10],
                "livekit_sip_call_id_full": params[11],
                "sip_trunk_phone_number": params[12],
                "quota_reserved_at": "2026-08-19T12:00:00Z" if params[13] else None,
                "quota_released_at": None,
                "platform_status": "in_progress",
                "direction": "inbound",
                "provider_call_control_id": None,
            })
            return FakeCursor(None)

        if "insert into telephony_calls" in sql:
            self.calls.append({
                "id": params[0],
                "tenant_id": params[1],
                "agent_id": params[2],
                "phone_number_id": params[3],
                "room_name": params[4],
                "from_number": params[5],
                "to_number": params[6],
                "platform_status": params[14],
                "quota_released_at": None,
                "livekit_sip_call_id": params[12],
                "livekit_sip_call_id_full": params[13],
                "direction": "outbound",
                "provider_call_control_id": None,
                "session_id": params[-1],
            })
            return FakeCursor(None)

        if "update telephony_calls" in sql:
            # A-01.1: status updates target the resolved row by id, never by provider id.
            target_call_id = params[-1]
            mapped = params[0]
            for c in self.calls:
                if c["id"] == target_call_id:
                    existing_status = c.get("platform_status")
                    terminal_states = {"completed", "busy", "no_answer", "failed", "cancelled"}
                    if existing_status in terminal_states and mapped not in terminal_states:
                        pass
                    else:
                        c["platform_status"] = mapped
            return FakeCursor(None)

        if "from livekit_outbound_trunks" in sql:
            return FakeCursor((
                "trunk_rec_1", "tenant_client_1", "ovp_1", "lk_tr_out_mock_123", "active", "active"
            ))

        if "from telephony_idempotency_keys" in sql:
            key = (params[0], params[1], params[2])
            row = self.idempotency.get(key)
            if not row:
                return FakeCursor(None)
            return FakeCursor((
                row["tenant_id"], row["idempotency_key"], row["action"], row["request_hash"],
                row["response_body"], row["platform_status"], row["created_at"], row["completed_at"]
            ))

        if "insert into telephony_idempotency_keys" in sql:
            key = (params[0], params[1], params[2])
            if "on conflict" in sql and "do update" in sql and key in self.idempotency:
                resp = json.loads(params[4]) if len(params) > 4 and isinstance(params[4], str) and params[4].startswith("{") else (params[4] if len(params) > 4 and isinstance(params[4], dict) else None)
                self.idempotency[key]["platform_status"] = "completed"
                if resp:
                    self.idempotency[key]["response_body"] = resp
                return FakeCursor(None, rowcount=1)
            if key in self.idempotency:
                return FakeCursor(None, rowcount=0)
            resp = json.loads(params[4]) if len(params) > 4 and isinstance(params[4], str) and params[4].startswith("{") else (params[4] if len(params) > 4 and isinstance(params[4], dict) else None)
            self.idempotency[key] = {
                "tenant_id": params[0],
                "idempotency_key": params[1],
                "action": params[2],
                "request_hash": params[3],
                "response_body": resp,
                "platform_status": params[4] if len(params) > 4 and isinstance(params[4], str) and params[4] in ("in_progress", "pending", "completed") else ("completed" if resp else "in_progress"),
                "created_at": "2026-08-03T12:00:00Z",
                "completed_at": "2026-08-03T12:00:00Z" if resp else None,
            }
            return FakeCursor(None, rowcount=1)

        if "update livekit_sip_dispatch_rules" in sql:
            for r in self.dispatch_rules:
                if r["id"] == params[0]:
                    r["disabled_at"] = "2026-08-19T12:00:00Z"
            return FakeCursor(None)

        if "update telephony_phone_numbers" in sql:
            for p in self.phone_numbers:
                if p["id"] == params[1]:
                    p["provisioning_status"] = "disabled"
                    p["disabled_at"] = "2026-08-19T12:00:00Z"
                    return FakeCursor((
                        p["id"], p["tenant_id"], p["provider_number_id"], p["e164_number"],
                        p["country"], p["number_type"], p["features"], p["provisioning_status"],
                        p["routing_status"], p["assigned_agent_id"], p["external_customer_ref"], p["disabled_at"]
                    ))
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


def test_client_calling_agent_inbound_resolution_flow():
    """Simulates a client placing an inbound call to the tenant agent number."""
    db = ClientCallingSimulationDb()

    # 1. Client calls +18005550199 -> Inbound SIP attributes passed from LiveKit
    attrs = {
        "sip.trunkPhoneNumber": "+18005550199",
        "sip.callID": "sip_call_inbound_001",
    }

    resolved = resolve_inbound_sip_call(
        participant_attributes=attrs,
        db_conn=db,
    )
    assert resolved["tenant_id"] == "tenant_client_1"
    assert resolved["agent_id"] == "agent_voice_1"
    assert resolved["status"] == "resolved"
    # Verify quota was reserved on inbound call resolution
    assert db.quota["tenant_client_1"] == 1


def test_client_calling_agent_inbound_quota_exhaustion():
    """Simulates client calling agent when max concurrent calls limit is reached."""
    db = ClientCallingSimulationDb()
    db.quota["tenant_client_1"] = 2  # Max quota is 2

    attrs = {
        "sip.trunkPhoneNumber": "+18005550199",
        "sip.callID": "sip_call_inbound_overflow",
    }

    with pytest.raises(ValueError, match="concurrency limit reached"):
        resolve_inbound_sip_call(
            participant_attributes=attrs,
            db_conn=db,
        )


def test_agent_calling_client_outbound_and_idempotency_flow():
    """Simulates agent placing an outbound call to a client number."""
    db = ClientCallingSimulationDb()
    service = TelephonyService(
        db_conn=db,
        livekit_client_factory=lambda mock_mode: LiveKitSipClient(mock_mode=True),
    )

    res1 = service.create_outbound_call(
        tenant_id="tenant_client_1",
        agent_id="agent_voice_1",
        from_number_id="num_client_1",
        to_number="+14155550999",
        idempotency_key="outbound-call-key-1",
    )

    assert res1["platform_status"] == "dialing"
    assert res1["room_name"].startswith("telephony-outbound-")
    assert db.quota["tenant_client_1"] == 1
    # A-01.3: a real sessions row is written and linked so the worker can bill/transcribe.
    assert res1["session_id"] is not None
    assert db.sessions == [{
        "id": res1["session_id"],
        "tenant_id": "tenant_client_1",
        "agent_id": "agent_voice_1",
        "room_name": res1["room_name"],
        "ended_at": None,
    }]
    assert db.calls[-1]["session_id"] == res1["session_id"]

    # Re-sent outbound call request with matching idempotency key returns cached response
    res2 = service.create_outbound_call(
        tenant_id="tenant_client_1",
        agent_id="agent_voice_1",
        from_number_id="num_client_1",
        to_number="+14155550999",
        idempotency_key="outbound-call-key-1",
    )
    assert res2["telephony_call_id"] == res1["telephony_call_id"]


def test_outbound_call_quota_limit_enforcement():
    """Simulates agent outbound call creation failure when concurrency quota is full."""
    db = ClientCallingSimulationDb()
    db.quota["tenant_client_1"] = 2  # Max limit is 2
    service = TelephonyService(
        db_conn=db,
        livekit_client_factory=lambda mock_mode: LiveKitSipClient(mock_mode=True),
    )

    with pytest.raises(TelephonyError) as exc_info:
        service.create_outbound_call(
            tenant_id="tenant_client_1",
            agent_id="agent_voice_1",
            from_number_id="num_client_1",
            to_number="+14155550888",
            idempotency_key="outbound-call-key-overflow",
        )
    assert exc_info.value.status == 429
    assert exc_info.value.code == TelephonyErrorCode.OUTBOUND_CONCURRENCY_LIMIT_REACHED


def test_webhook_lifecycle_and_out_of_order_protection():
    """Simulates full webhook call lifecycle and out-of-order delivery protection."""
    db = ClientCallingSimulationDb()
    service = TelephonyService(
        db_conn=db,
        livekit_client_factory=lambda mock_mode: LiveKitSipClient(mock_mode=True),
    )

    # 1. Outbound call created
    call_res = service.create_outbound_call(
        tenant_id="tenant_client_1",
        agent_id="agent_voice_1",
        from_number_id="num_client_1",
        to_number="+14155550777",
        idempotency_key="call-life-001",
    )

    call_id = call_res["telephony_call_id"]
    call_row = db.calls[-1]
    assert call_row["provider_call_control_id"] is None
    assert db.quota["tenant_client_1"] == 1  # reservation taken at dial

    # A-01.1: Telnyx sends ITS OWN ids — never LiveKit's sip_call_id. The first event
    # must bind by direction + from/to, later events match the bound provider id exactly.
    telnyx_cc = "v3:telnyx-call-control-abc"
    assert telnyx_cc != call_row["livekit_sip_call_id"]

    # 2. Webhook call.answered arrives (first contact, carries from/to) -> in_progress + bind
    _apply_webhook_side_effects(db, "call.answered", {"data": {"payload": {
        "call_control_id": telnyx_cc,
        "call_session_id": "sess-1",
        "call_leg_id": "leg-1",
        "direction": "outgoing",
        "from": "+18005550199",
        "to": "+14155550777",
        "status": "answered",
    }}})
    assert db.calls[-1]["platform_status"] == "in_progress"
    assert db.calls[-1]["provider_call_control_id"] == telnyx_cc
    assert db.calls[-1]["provider_call_session_id"] == "sess-1"

    # 3. Webhook call.hangup arrives (ids only) -> exact match -> completed + quota released once
    _apply_webhook_side_effects(db, "call.hangup", {"data": {"payload": {"call_control_id": telnyx_cc, "status": "completed"}}})
    assert db.calls[-1]["platform_status"] == "completed"
    assert db.calls[-1]["quota_released_at"] is not None
    assert db.quota["tenant_client_1"] == 0

    # 4. Out-of-order delayed call.initiated webhook arrives late -> remains completed, no double release
    _apply_webhook_side_effects(db, "call.initiated", {"data": {"payload": {"call_control_id": telnyx_cc, "status": "initiated"}}})
    assert db.calls[-1]["platform_status"] == "completed"
    _apply_webhook_side_effects(db, "call.hangup", {"data": {"payload": {"call_control_id": telnyx_cc, "status": "completed"}}})
    assert db.quota["tenant_client_1"] == 0


def test_disable_number_active_calls_drain_guardrail():
    """Simulates attempting to disable a number while a client call is active."""
    db = ClientCallingSimulationDb()
    service = TelephonyService(
        db_conn=db,
        livekit_client_factory=lambda mock_mode: LiveKitSipClient(mock_mode=True),
    )

    # 1. Active call in progress on number num_client_1
    service.create_outbound_call(
        tenant_id="tenant_client_1",
        agent_id="agent_voice_1",
        from_number_id="num_client_1",
        to_number="+14155550666",
        idempotency_key="active-call-drain-1",
    )

    # 2. Disabling number without force raises 409 Conflict
    with pytest.raises(TelephonyError) as exc_info:
        service.disable_number("tenant_client_1", "num_client_1", force=False)
    assert exc_info.value.status == 409
    assert exc_info.value.code == TelephonyErrorCode.CALL_STATE_CONFLICT

    # 3. Disabling number with force=True succeeds and cleans up LiveKit routing
    res = service.disable_number("tenant_client_1", "num_client_1", force=True)
    assert res["provisioning_status"] == "disabled"
    assert db.dispatch_rules[0]["disabled_at"] is not None
