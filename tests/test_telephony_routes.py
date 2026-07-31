"""Unit tests for telephony FastAPI routes and service layer.

Phase 7 & 8 verification suite.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

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

    target = numbers[0]["e164_number"]
    purchase_resp = client.post(
        "/portal/telephony/number-orders",
        json={"e164_number": target, "idempotency_key": "idemp_test_001"},
    )
    assert purchase_resp.status_code == 200
    assert purchase_resp.json()["platform_status"] == "purchased"


def test_portal_outbound_readiness_and_call():
    readiness = client.get("/portal/telephony/outbound-readiness")
    assert readiness.status_code == 200
    assert readiness.json()["is_ready"] is True

    # Get list of numbers to fetch num_id
    num_list = client.get("/portal/telephony/numbers")
    assert num_list.status_code == 200
    num_id = num_list.json()[0]["id"]

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


def test_portal_disconnect():
    resp = client.delete("/portal/telephony/telnyx/connection")
    assert resp.status_code == 200
    assert resp.json()["platform_status"] == "disconnected"
