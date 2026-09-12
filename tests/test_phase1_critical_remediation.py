"""Focused test suite for Phase 1 Critical Remediation (TEL-CRIT-01, TEL-CRIT-02, TEL-CRIT-03)."""

from __future__ import annotations

import json
from typing import Any
import pytest

from tenant_portal_api.telephony_credentials import encrypt_provider_secret
from tenant_portal_api.telephony_errors import TelephonyError
from tenant_portal_api.telephony_reconcile import reconcile_telephony_state
from tenant_portal_api.telephony_service import TelephonyService
from tenant_portal_api.telephony_status import CallPublicStatus, NumberProvisioningStatus, NumberRoutingStatus

RAW_KEY = "KEY01_TEST_KEY_1234567890"
ENCRYPTED_KEY = encrypt_provider_secret(RAW_KEY)


class FakeCursor:
    def __init__(self, row: Any = None, rowcount: int = 1):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row else []


class MockPhase1Db:
    def __init__(self):
        self.connection = {
            "id": "conn_123",
            "tenant_id": "tenant_123",
            "label": "primary",
            "platform_status": "active",
            "provider_status": "active",
            "key_fingerprint": "fingerprint",
            "telnyx_account_id": "acct_123",
            "last_verified_at": "2026-08-03T12:00:00Z",
            "permission_last_checked_at": "2026-08-03T12:00:00Z",
            "encrypted_api_key_ref": ENCRYPTED_KEY,
        }
        self.idempotency: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.number_orders: list[dict[str, Any]] = []
        self.phone_numbers: list[dict[str, Any]] = [
            {
                "id": "num_123",
                "tenant_id": "tenant_123",
                "provider_number_id": "pn_123",
                "e164_number": "+15550001111",
                "country": "US",
                "number_type": "local",
                "features": ["voice"],
                "provisioning_status": "owned",
                "routing_status": "ready",
                "assigned_agent_id": "agent_123",
                "external_customer_ref": None,
                "disabled_at": None,
            }
        ]
        self.outbound_trunks: list[dict[str, Any]] = [
            {
                "id": "trk_123",
                "tenant_id": "tenant_123",
                "outbound_voice_profile_record_id": "ovp_123",
                "livekit_outbound_trunk_id": "lk_tr_out_123",
                "platform_status": "active",
                "provider_status": "active",
                "disabled_at": None,
            }
        ]
        self.calls: list[dict[str, Any]] = []
        self.quota_reserved = False
        self.provider_purchase_calls = 0

    def execute(self, query: str, params: tuple[Any, ...] = ()):  # noqa: C901
        sql = " ".join(query.lower().split())

        if "from tenant_telnyx_connections" in sql:
            row = self.connection
            return FakeCursor(
                (
                    row["id"],
                    row["tenant_id"],
                    row["label"],
                    row["platform_status"],
                    row["provider_status"],
                    row["key_fingerprint"],
                    row["telnyx_account_id"],
                    row["last_verified_at"],
                    row["permission_last_checked_at"],
                    row["encrypted_api_key_ref"],
                )
            )

        if "from telephony_idempotency_keys" in sql:
            key = (params[0], params[1], params[2])
            row = self.idempotency.get(key)
            if not row:
                return FakeCursor(None, rowcount=0)
            return FakeCursor(
                (
                    row["tenant_id"],
                    row["idempotency_key"],
                    row["action"],
                    row["request_hash"],
                    row["response_body"],
                    row["platform_status"],
                    row["created_at"],
                    row["completed_at"],
                ),
                rowcount=1,
            )

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

        if "update telephony_idempotency_keys" in sql:
            key = (params[1], params[2], params[3]) if len(params) > 3 else (params[0], params[1], params[2])
            if key in self.idempotency:
                self.idempotency[key]["platform_status"] = "completed"
                if isinstance(params[0], str) and params[0].startswith("{"):
                    self.idempotency[key]["response_body"] = json.loads(params[0])
            return FakeCursor(None, rowcount=1)

        if "delete from telephony_idempotency_keys" in sql:
            key = (params[0], params[1], params[2])
            self.idempotency.pop(key, None)
            return FakeCursor(None, rowcount=1)

        if "insert into telephony_number_orders" in sql:
            order = {
                "id": f"ord_db_{len(self.number_orders) + 1}",
                "tenant_id": params[0],
                "telnyx_connection_id": params[1],
                "idempotency_key": params[2],
                "provider_order_id": params[3],
                "selected_e164_number": params[4],
                "provider_status": params[5],
                "platform_status": params[6],
                "raw_provider_status": params[7],
                "error_code": None,
                "error_message": None,
                "created_at": "2026-08-03T12:10:00Z",
            }
            self.number_orders.append(order)
            return FakeCursor(
                (
                    order["id"],
                    order["tenant_id"],
                    order["idempotency_key"],
                    order["provider_order_id"],
                    order["selected_e164_number"],
                    order["platform_status"],
                    order["provider_status"],
                    order["error_code"],
                    order["error_message"],
                    order["created_at"],
                )
            )

        if "from telephony_phone_numbers" in sql and "select" in sql:
            if "provisioning_status = 'purchase_pending'" in sql:
                matches = [p for p in self.phone_numbers if p.get("provisioning_status") == "purchase_pending"]
                rows = [(m["id"], m["tenant_id"], m["e164_number"]) for m in matches]
                class MultiCursor:
                    def __init__(self, r_list): self._rows = r_list
                    def fetchall(self): return self._rows
                    def fetchone(self): return self._rows[0] if self._rows else None
                return MultiCursor(rows)

            for p in self.phone_numbers:
                if len(params) >= 2 and p["tenant_id"] == params[0] and (p["id"] == params[1] or p["e164_number"] == params[1]):
                    return FakeCursor(
                        (
                            p["id"],
                            p["tenant_id"],
                            p["provider_number_id"],
                            p["e164_number"],
                            p["country"],
                            p["number_type"],
                            p["features"],
                            p["provisioning_status"],
                            p["routing_status"],
                            p["assigned_agent_id"],
                            p["external_customer_ref"],
                            p["disabled_at"],
                        )
                    )
                if len(params) == 1 and p["tenant_id"] == params[0]:
                    return FakeCursor(
                        (
                            p["id"],
                            p["tenant_id"],
                            p["provider_number_id"],
                            p["e164_number"],
                            p["country"],
                            p["number_type"],
                            p["features"],
                            p["provisioning_status"],
                            p["routing_status"],
                            p["assigned_agent_id"],
                            p["external_customer_ref"],
                            p["disabled_at"],
                        )
                    )
            return FakeCursor(None)

        if "update telephony_phone_numbers" in sql:
            for p in self.phone_numbers:
                if "provisioning_status = 'owned'" in sql or "then %s" in sql or "then excluded.provisioning_status" in sql:
                    p["provisioning_status"] = "owned"
            return FakeCursor(("num_123",))

        if "insert into telephony_phone_numbers" in sql:
            return FakeCursor(("num_123",))

        if "from livekit_outbound_trunks" in sql:
            row = self.outbound_trunks[0]
            return FakeCursor(
                (
                    row["id"],
                    row["tenant_id"],
                    row["outbound_voice_profile_record_id"],
                    row["livekit_outbound_trunk_id"],
                    row["platform_status"],
                    row["provider_status"],
                )
            )

        if "quota_state" in sql and "update" in sql:
            self.quota_reserved = True
            return FakeCursor(None)

        if "insert into telephony_calls" in sql:
            call = {
                "id": params[0],
                "tenant_id": params[1],
                "agent_id": params[2],
                "from_number_id": params[3],
                "room_name": params[4],
                "from_number": params[5],
                "to_number": params[6],
                "platform_status": params[14] if len(params) > 14 else "dialing",
            }
            self.calls.append(call)
            return FakeCursor(None)


        return FakeCursor(None)

    def commit(self):
        pass


class FakeTelnyxClient:
    def __init__(self, db: MockPhase1Db):
        self._db = db

    def purchase_number(self, e164_number: str) -> dict[str, Any]:
        self._db.provider_purchase_calls += 1
        return {
            "provider_order_id": "ord_t1",
            "provider_status": "success",
            "platform_status": "purchased",
            "status": "success",
        }

    def get_number_order_status(self, provider_order_id: str) -> dict[str, Any]:
        return {
            "provider_order_id": provider_order_id,
            "provider_status": "success",
            "platform_status": "purchased",
            "status": "success",
        }

    def list_owned_numbers(self, filter_phone_number: str | None = None) -> list[dict[str, Any]]:
        return [
            {
                "provider_number_id": "pn_new_123",
                "e164_number": filter_phone_number or "+15550009999",
                "country": "US",
                "number_type": "local",
                "features": ["voice"],
            }
        ]


class FakeLiveKitClient:
    def create_agent_dispatch(self, room_name: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"dispatch_id": "disp_123"}

    def create_sip_participant(self, room_name: str, outbound_trunk_id: str, to_number: str) -> dict[str, Any]:
        return {
            "sip_participant_id": "sp_123",
            "livekit_sip_call_id": "call_sip_123",
            "livekit_sip_call_id_full": "call_sip_full_123",
            "status": "active",
        }


def test_outbound_call_idempotency_real_db_mode():
    """TEL-CRIT-01: Outbound call idempotency returns cached response for duplicate requests."""
    db = MockPhase1Db()
    service = TelephonyService(
        db_conn=db,
        livekit_client_factory=lambda mock_mode=False: FakeLiveKitClient(),
    )

    res1 = service.create_outbound_call(
        tenant_id="tenant_123",
        agent_id="agent_123",
        from_number_id="num_123",
        to_number="+15559998888",
        idempotency_key="call-idemp-001",
    )
    assert res1["platform_status"] == CallPublicStatus.DIALING.value
    call_id_1 = res1["telephony_call_id"]

    # Second call with same idempotency key and same parameters
    res2 = service.create_outbound_call(
        tenant_id="tenant_123",
        agent_id="agent_123",
        from_number_id="num_123",
        to_number="+15559998888",
        idempotency_key="call-idemp-001",
    )
    assert res2["telephony_call_id"] == call_id_1

    # Third call with same idempotency key but DIFFERENT payload should raise 409 Conflict
    with pytest.raises(TelephonyError) as exc_info:
        service.create_outbound_call(
            tenant_id="tenant_123",
            agent_id="agent_123",
            from_number_id="num_123",
            to_number="+15550000000",  # Different to_number
            idempotency_key="call-idemp-001",
        )
    assert exc_info.value.status == 409


def test_purchase_number_race_closure():
    """TEL-CRIT-02: Purchase pre-locks idempotency key so Telnyx API is invoked only once."""
    db = MockPhase1Db()
    service = TelephonyService(
        db_conn=db,
        telnyx_client_factory=lambda api_key, mock_mode=False: FakeTelnyxClient(db),
    )

    res1 = service.purchase_number(
        tenant_id="tenant_123",
        e164_number="+15550009999",
        idempotency_key="purch-idemp-001",
    )
    assert res1["platform_status"] == "purchased"
    assert db.provider_purchase_calls == 1

    # Re-issued purchase call with same idempotency key returns cached result without invoking Telnyx again
    res2 = service.purchase_number(
        tenant_id="tenant_123",
        e164_number="+15550009999",
        idempotency_key="purch-idemp-001",
    )
    assert res2["id"] == res1["id"]
    assert db.provider_purchase_calls == 1  # Provider call count remains 1!


def test_purchase_pending_progression_repair():
    """TEL-CRIT-03: Stuck purchase_pending numbers promote to owned during materialization and reconciler scan."""
    db = MockPhase1Db()
    db.phone_numbers.append(
        {
            "id": "num_pending_123",
            "tenant_id": "tenant_123",
            "provider_number_id": "pn_pending_123",
            "e164_number": "+15559990000",
            "country": "US",
            "number_type": "local",
            "features": ["voice"],
            "provisioning_status": "purchase_pending",
            "routing_status": "not_configured",
            "assigned_agent_id": None,
            "external_customer_ref": None,
            "disabled_at": None,
        }
    )

    service = TelephonyService(
        db_conn=db,
        telnyx_client_factory=lambda api_key, mock_mode=False: FakeTelnyxClient(db),
    )

    # Materialize number as owned
    mat_id = service._materialize_managed_number(
        db,
        tenant_id="tenant_123",
        telnyx_connection_id="conn_123",
        provider_number_id="pn_pending_123",
        e164_number="+15559990000",
        country="US",
        number_type="local",
        features=["voice"],
        provisioning_status=NumberProvisioningStatus.OWNED.value,
        routing_status=NumberRoutingStatus.NOT_CONFIGURED.value,
        provider_status="active",
    )
    assert mat_id is not None
    assert db.phone_numbers[-1]["provisioning_status"] == "owned"

    # Test reconciler sweep
    db.phone_numbers[-1]["provisioning_status"] = "purchase_pending"
    repairs = reconcile_telephony_state(db_conn=db, dry_run=False)
    assert repairs["pending_purchases_promoted"] == 1
    assert db.phone_numbers[-1]["provisioning_status"] == "owned"
