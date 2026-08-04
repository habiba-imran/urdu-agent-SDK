"""Unit tests for LiveKit SIP adapter.

Phase 4 & 5 verification suite.
"""

import pytest
from tenant_portal_api.livekit_sip import LiveKitSipClient
from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode


def test_livekit_sip_client_mock():
    client = LiveKitSipClient(mock_mode=True)

    inbound = client.create_or_get_inbound_trunk("phone_12345678", "+15551234567")
    assert inbound["status"] == "active"
    assert "lk_tr_in_mock_" in inbound["livekit_inbound_trunk_id"]

    outbound = client.create_or_get_outbound_trunk(
        "telnyx_12345678",
        "sip.telnyx.com",
        ["+15551234567"],
        sip_username="telnyx-user",
        sip_secret="telnyx-secret",
    )
    assert outbound["status"] == "active"
    assert "lk_tr_out_mock_" in outbound["livekit_outbound_trunk_id"]
    assert outbound["numbers"] == ["+15551234567"]

    rule = client.create_or_get_dispatch_rule(
        inbound["livekit_inbound_trunk_id"], "phone_12345678", "+15551234567"
    )
    assert rule["status"] == "active"
    assert "lk_rule_mock_" in rule["livekit_sip_dispatch_rule_id"]

    sip_part = client.create_sip_participant(
        room_name="room_12345678",
        outbound_trunk_id=outbound["livekit_outbound_trunk_id"],
        to_number="+15557654321",
    )
    assert sip_part["status"] == "dialing"
    assert "sip_call_mock_" in sip_part["livekit_sip_call_id"]


def test_livekit_sip_real_mode_requires_credentials(monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER_MODE", "real")
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    client = LiveKitSipClient(mock_mode=False)

    with pytest.raises(TelephonyError) as exc_info:
        client.create_or_get_inbound_trunk("phone_12345678", "+15551234567")

    assert exc_info.value.code == "provider_credentials_missing"
    assert exc_info.value.status == 503


def test_livekit_outbound_trunk_requires_numbers_before_provider_call():
    client = LiveKitSipClient(mock_mode=True)

    with pytest.raises(TelephonyError) as exc_info:
        client.create_or_get_outbound_trunk("telnyx_12345678", "sip.telnyx.com", [])

    assert exc_info.value.code == "outbound_not_ready"
    assert exc_info.value.status == 409


def test_livekit_outbound_trunk_validation_maps_to_readiness_error():
    client = LiveKitSipClient(
        url="wss://livekit.example", api_key="key", api_secret="secret", mock_mode=False
    )

    with pytest.raises(TelephonyError) as exc_info:
        client._raise_provider_error(
            RuntimeError(
                "ServerError(code=invalid_argument, message=no trunk numbers specified, status=400)"
            ),
            TelephonyErrorCode.LIVEKIT_OUTBOUND_TRUNK_FAILED,
            "Failed to create or configure LiveKit outbound trunk.",
        )

    assert exc_info.value.code == "outbound_not_ready"
    assert exc_info.value.status == 409
