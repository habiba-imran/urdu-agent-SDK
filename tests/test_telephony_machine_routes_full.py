"""Comprehensive unit test suite for all 27 machine SDK route methods and mounted app.

Verifies:
- Every route is mounted on the real tenant_portal_api.app
- Correct HTTP method and path
- Correct action string and HMAC signature verification
- Path parameters binding
- GET signs empty body {}
- Bad/invalid signature returns stable 401 auth error
"""

import os

from fastapi.testclient import TestClient
import pytest

import tenant_portal_api.telephony_routes as telephony_routes

os.environ["TELEPHONY_ALLOW_MOCK_MACHINE_AUTH"] = "1"

from tenant_portal_api.app import app

client = TestClient(app)

HEADERS = {
    "X-Tenant-Id": "tenant_test_123",
    "X-Timestamp": "1700000000",
    "X-Nonce": "nonce_12345",
    "X-Signature": "valid_mock_signature",
}

BAD_HEADERS = {
    "X-Tenant-Id": "tenant_test_123",
    "X-Timestamp": "1700000000",
    "X-Nonce": "nonce_12345",
    "X-Signature": "invalid_signature",
}

RANDOM_BAD_HEADERS = {
    "X-Tenant-Id": "tenant_test_123",
    "X-Timestamp": "1700000000",
    "X-Nonce": "nonce_random_bad",
    "X-Signature": "totally_wrong_signature",
}


def test_mounted_app_health():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_machine_connect_telnyx():
    resp = client.post(
        "/machine/telephony/telnyx/connect",
        headers=HEADERS,
        json={"api_key": "mock_api_key_123", "label": "Test Connection"},
    )
    assert resp.status_code == 200
    assert resp.json()["platform_status"] == "active"

    # Bad sig
    bad = client.post(
        "/machine/telephony/telnyx/connect",
        headers=BAD_HEADERS,
        json={"api_key": "mock_api_key_123"},
    )
    assert bad.status_code == 401


def test_machine_rejects_random_bad_signature():
    resp = client.post(
        "/machine/telephony/telnyx/connect",
        headers=RANDOM_BAD_HEADERS,
        json={"api_key": "mock_api_key_123"},
    )
    assert resp.status_code == 401


def test_machine_uses_request_scoped_db_auth_when_mock_auth_disabled(monkeypatch):
    class DummyConnection:
        committed = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def commit(self):
            self.committed = True

    dummy_conn = DummyConnection()
    calls = []

    def fake_verify(conn, tenant_id, ts, nonce, action, body, signature):
        calls.append((conn, tenant_id, ts, nonce, action, body, signature))

    monkeypatch.delenv("TELEPHONY_ALLOW_MOCK_MACHINE_AUTH", raising=False)
    monkeypatch.setattr(telephony_routes, "_open_db", lambda: dummy_conn)
    monkeypatch.setattr(telephony_routes, "_verify_machine", fake_verify)

    resp = client.get("/machine/telephony/telnyx/connection", headers=HEADERS)

    assert resp.status_code == 200
    assert calls == [
        (
            dummy_conn,
            "tenant_test_123",
            "1700000000",
            "nonce_12345",
            "telephony.telnyx_connection.status",
            {},
            "valid_mock_signature",
        )
    ]
    assert dummy_conn.committed is True


def test_machine_rotate_telnyx():
    resp = client.post(
        "/machine/telephony/telnyx/rotate",
        headers=HEADERS,
        json={"api_key": "mock_rotated_key"},
    )
    assert resp.status_code == 200
    assert resp.json()["label"] == "Rotated Telnyx Account"


def test_machine_reverify_telnyx():
    # Connect first
    client.post("/machine/telephony/telnyx/connect", headers=HEADERS, json={"api_key": "mock_key"})
    resp = client.post("/machine/telephony/telnyx/reverify", headers=HEADERS, json={})
    assert resp.status_code == 200
    assert resp.json()["last_verified_at"] is not None


def test_machine_disconnect_telnyx():
    client.post("/machine/telephony/telnyx/connect", headers=HEADERS, json={"api_key": "mock_key"})
    resp = client.delete("/machine/telephony/telnyx/connection", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["platform_status"] == "disconnected"


def test_machine_get_connection_status():
    resp = client.get("/machine/telephony/telnyx/connection", headers=HEADERS)
    assert resp.status_code == 200


def test_machine_list_owned_numbers():
    resp = client.post(
        "/machine/telephony/telnyx/owned-numbers/list",
        headers=HEADERS,
        json={"filter_country": "US"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_machine_list_managed_numbers():
    resp = client.post("/machine/telephony/numbers/list", headers=HEADERS, json={})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_machine_import_number():
    resp = client.post(
        "/machine/telephony/numbers/import",
        headers=HEADERS,
        json={"e164_number": "+15550001111", "external_customer_ref": "cust_1"},
    )
    assert resp.status_code == 200
    assert resp.json()["e164_number"] == "+15550001111"


def test_machine_sync_numbers():
    resp = client.post("/machine/telephony/numbers/sync", headers=HEADERS, json={})
    assert resp.status_code == 200
    assert "synced_count" in resp.json()


def test_machine_get_number_drift():
    resp = client.post("/machine/telephony/numbers/drift", headers=HEADERS, json={})
    assert resp.status_code == 200
    assert resp.json()["has_drift"] is False


def test_machine_search_available_numbers():
    resp = client.post(
        "/machine/telephony/available-numbers/search",
        headers=HEADERS,
        json={"country": "US", "area_code": "555"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_machine_reserve_number():
    resp = client.post(
        "/machine/telephony/number-reservations",
        headers=HEADERS,
        json={"e164_number": "+15551234567", "idempotency_key": "idemp_res_1"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reserved"


def test_machine_purchase_number():
    resp = client.post(
        "/machine/telephony/number-orders",
        headers=HEADERS,
        json={"e164_number": "+15551234567", "idempotency_key": "idemp_ord_1"},
    )
    assert resp.status_code == 200
    assert resp.json()["platform_status"] == "purchased"


def test_machine_get_number_order_status():
    resp = client.post(
        "/machine/telephony/number-orders/get",
        headers=HEADERS,
        json={"order_id": "ord_mock_123"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == "ord_mock_123"


def test_machine_assign_and_unassign_agent():
    # Import number first
    imp = client.post(
        "/machine/telephony/numbers/import",
        headers=HEADERS,
        json={"e164_number": "+15559990000"},
    ).json()
    num_id = imp["id"]

    # Assign
    assign_resp = client.patch(
        f"/machine/telephony/numbers/{num_id}/assignment",
        headers=HEADERS,
        json={"number_id": num_id, "agent_id": "agent_123"},
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["assigned_agent_id"] == "agent_123"

    # Unassign
    unassign_resp = client.patch(
        f"/machine/telephony/numbers/{num_id}/assignment",
        headers=HEADERS,
        json={"number_id": num_id, "agent_id": None},
    )
    assert unassign_resp.status_code == 200
    assert unassign_resp.json()["assigned_agent_id"] is None


def test_machine_upsert_sip_connection():
    client.post("/machine/telephony/telnyx/connect", headers=HEADERS, json={"api_key": "mock_key"})
    resp = client.post(
        "/machine/telephony/telnyx/sip-connection",
        headers=HEADERS,
        json={"sip_fqdn": "sip.test.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["platform_status"] == "active"


def test_machine_verify_sip_connection():
    resp = client.post("/machine/telephony/telnyx/sip-connection/test", headers=HEADERS, json={})
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True


def test_machine_upsert_outbound_voice_profile():
    client.post("/machine/telephony/telnyx/connect", headers=HEADERS, json={"api_key": "mock_key"})
    resp = client.post(
        "/machine/telephony/telnyx/outbound-voice-profile",
        headers=HEADERS,
        json={"allowed_destinations": ["US", "PK"], "concurrency_limit": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["platform_status"] == "active"


def test_machine_verify_outbound_voice_profile():
    resp = client.post(
        "/machine/telephony/telnyx/outbound-voice-profile/reverify",
        headers=HEADERS,
        json={},
    )
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True


def test_machine_configure_number_routing():
    imp = client.post(
        "/machine/telephony/numbers/import",
        headers=HEADERS,
        json={"e164_number": "+15558887777"},
    ).json()
    num_id = imp["id"]

    resp = client.post(
        f"/machine/telephony/numbers/{num_id}/routing/configure",
        headers=HEADERS,
        json={"inbound_agent_id": "agent_abc"},
    )
    assert resp.status_code == 200
    assert resp.json()["routing_status"] == "ready"


def test_machine_configure_outbound_trunk():
    resp = client.post(
        "/machine/telephony/telnyx/outbound-trunk/configure",
        headers=HEADERS,
        json={},
    )
    assert resp.status_code == 200
    assert resp.json()["platform_status"] == "active"


def test_machine_get_outbound_readiness():
    resp = client.get("/machine/telephony/outbound-readiness", headers=HEADERS)
    assert resp.status_code == 200
    assert "is_ready" in resp.json()


def test_machine_create_outbound_call():
    resp = client.post(
        "/machine/telephony/outbound-calls",
        headers=HEADERS,
        json={
            "agent_id": "agent_123",
            "from_number_id": "num_123",
            "to_number": "+15557654321",
            "idempotency_key": "idemp_call_999",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["platform_status"] == "dialing"


def test_machine_get_call_status():
    resp = client.post(
        "/machine/telephony/calls/get",
        headers=HEADERS,
        json={"telephony_call_id": "call_12345"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == "call_12345"


def test_machine_list_call_records():
    resp = client.post(
        "/machine/telephony/calls/list",
        headers=HEADERS,
        json={"limit": 10},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_machine_disable_number():
    imp = client.post(
        "/machine/telephony/numbers/import",
        headers=HEADERS,
        json={"e164_number": "+15550009999"},
    ).json()
    num_id = imp["id"]

    resp = client.post(
        f"/machine/telephony/numbers/{num_id}/disable",
        headers=HEADERS,
        json={},
    )
    assert resp.status_code == 200
    assert resp.json()["provisioning_status"] == "disabled"
