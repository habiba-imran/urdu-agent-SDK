"""Unit tests for worker telephony runtime, webhooks, reconciler, and health diagnostics.

Phase 9, 11 & 12 verification suite.
"""

import os

os.environ["TELEPHONY_PROVIDER_MODE"] = "mock"
os.environ.pop("TELNYX_PUBLIC_KEY", None)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def mock_telephony_env(monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER_MODE", "mock")
    monkeypatch.delenv("TELNYX_PUBLIC_KEY", raising=False)


from tenant_portal_api.telephony_health import check_global_telephony_health
from tenant_portal_api.telephony_reconcile import reconcile_telephony_state
from tenant_portal_api.telephony_webhooks import (
    router as webhook_router,
    verify_telnyx_webhook_signature,
)
from worker.telephony_runtime import (
    extract_sip_participant_attributes,
    resolve_inbound_sip_call,
    session_audio_channel,
)

webhook_app = FastAPI(title="Webhook Test App")
webhook_app.include_router(webhook_router)
webhook_client = TestClient(webhook_app)


def test_extract_sip_participant_attributes():
    meta = {
        "sip": {
            "sip.callID": "call_123",
            "sip.trunkPhoneNumber": "+15551234567",
        }
    }
    attrs = extract_sip_participant_attributes(meta)
    assert attrs["sip_call_id"] == "call_123"
    assert attrs["trunk_phone_number"] == "+15551234567"


def test_resolve_inbound_sip_call_mock():
    meta = {"sip": {"sip.trunkPhoneNumber": "+15559998888"}}
    res = resolve_inbound_sip_call(meta, db_conn=None)
    assert res["tenant_id"] == "tenant_test_123"
    assert res["e164_number"] == "+15559998888"


def test_session_audio_channel_telephony_when_metadata_present():
    resolved = {
        "tenant_id": "tenant-1",
        "agent_id": "agent-1",
        "telephony": {"direction": "outbound"},
    }
    assert session_audio_channel(resolved) == "telephony"


def test_session_audio_channel_webrtc_by_default():
    resolved = {"tenant_id": "tenant-1", "agent_id": "agent-1", "telephony": None}
    assert session_audio_channel(resolved) == "webrtc"


def test_telnyx_webhook_signature_verification():
    assert verify_telnyx_webhook_signature(b"{}", None, None) is True


def test_telnyx_webhook_endpoint():
    resp = webhook_client.post(
        "/webhooks/telephony/telnyx",
        json={"data": {"event_type": "call.initiated", "id": "evt_123"}},
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "call.initiated"


def test_reconcile_telephony_state():
    res = reconcile_telephony_state(db_conn=None, dry_run=True)
    assert res["status"] == "completed"
    assert res["dry_run"] is True


def test_check_global_telephony_health():
    health = check_global_telephony_health()
    assert health["status"] == "healthy"
