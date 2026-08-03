"""Unit tests for telephony FastAPI routes and service layer.

Phase 7 & 8 verification suite.
"""

import os

os.environ["TELEPHONY_PROVIDER_MODE"] = "mock"
os.environ["TELEPHONY_ALLOW_MOCK_PORTAL_AUTH"] = "1"
os.environ["TELEPHONY_ALLOW_MOCK_MACHINE_AUTH"] = "1"

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tenant_portal_api.telephony_routes import router as telephony_router

test_app = FastAPI(title="Telephony Test App")
test_app.include_router(telephony_router)

client = TestClient(test_app)


def test_portal_connect_and_status():
    resp = client.post(
        "/portal/telephony/telnyx/connect",
        json={"api_key": "test_mock_key", "label": "Test Portal Account"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform_status"] == "active"
    assert data["tenant_id"] == "tenant_test_123"

    # Fetch status
    status_resp = client.get("/portal/telephony/telnyx/connection")
    assert status_resp.status_code == 200
    assert status_resp.json()["platform_status"] == "active"


def test_portal_search_and_purchase():
    search_resp = client.post(
        "/portal/telephony/available-numbers/search",
        json={"country": "US", "area_code": "555"},
    )
    assert search_resp.status_code == 200
    numbers = search_resp.json()
    assert len(numbers) > 0
    assert numbers[0]["upfront_cost"] == "1.00"
    assert numbers[0]["monthly_cost"] == "1.00"
    assert numbers[0]["currency"] == "USD"

    target = numbers[0]["e164_number"]
    purchase_resp = client.post(
        "/portal/telephony/number-orders",
        json={"e164_number": target, "idempotency_key": "idemp_test_001"},
    )
    assert purchase_resp.status_code == 200
    assert purchase_resp.json()["platform_status"] == "purchased"
    assert purchase_resp.json()["managed_number_id"] is not None


def test_portal_outbound_readiness_and_call():
    num = client.post(
        "/portal/telephony/numbers/import",
        json={"e164_number": "+15557650001"},
    ).json()
    num_id = num["id"]

    assign_resp = client.patch(
        f"/portal/telephony/numbers/{num_id}/assignment",
        json={"number_id": num_id, "agent_id": "agent_123"},
    )
    assert assign_resp.status_code == 200

    route_resp = client.post(
        f"/portal/telephony/numbers/{num_id}/routing/configure",
        json={"inbound_agent_id": "agent_123"},
    )
    assert route_resp.status_code == 200

    readiness = client.get("/portal/telephony/outbound-readiness")
    assert readiness.status_code == 200
    assert readiness.json()["is_ready"] is True

    call_resp = client.post(
        "/portal/telephony/outbound-calls",
        json={
            "agent_id": "agent_123",
            "from_number_id": num_id,
            "to_number": "+15557654321",
            "idempotency_key": "call_idemp_001",
        },
    )
    assert call_resp.status_code == 200
    call_data = call_resp.json()
    assert call_data["platform_status"] == "dialing"
    assert call_data["direction"] == "outbound"


def test_portal_outbound_call_rejects_number_bound_to_another_agent():
    num = client.post(
        "/portal/telephony/numbers/import",
        json={"e164_number": "+15557650002"},
    ).json()
    num_id = num["id"]

    client.patch(
        f"/portal/telephony/numbers/{num_id}/assignment",
        json={"number_id": num_id, "agent_id": "agent_bound"},
    )
    client.post(
        f"/portal/telephony/numbers/{num_id}/routing/configure",
        json={"inbound_agent_id": "agent_bound"},
    )

    call_resp = client.post(
        "/portal/telephony/outbound-calls",
        json={
            "agent_id": "agent_other",
            "from_number_id": num_id,
            "to_number": "+15557654321",
            "idempotency_key": "call_idemp_wrong_agent",
        },
    )
    assert call_resp.status_code == 409
    assert call_resp.json()["detail"]["error"]["code"] == "number_not_assigned"


def test_portal_disconnect():
    resp = client.delete("/portal/telephony/telnyx/connection")
    assert resp.status_code == 200
    assert resp.json()["platform_status"] == "disconnected"
