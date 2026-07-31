"""Unit tests for LiveKit SIP adapter.

Phase 4 & 5 verification suite.
"""

import pytest
from tenant_portal_api.livekit_sip import LiveKitSipClient


def test_livekit_sip_client_mock():
    client = LiveKitSipClient(mock_mode=True)

    inbound = client.create_or_get_inbound_trunk("phone_12345678", "+15551234567")
    assert inbound["status"] == "active"
    assert "lk_tr_in_mock_" in inbound["livekit_inbound_trunk_id"]

    outbound = client.create_or_get_outbound_trunk("telnyx_12345678", "sip.telnyx.com")
    assert outbound["status"] == "active"
    assert "lk_tr_out_mock_" in outbound["livekit_outbound_trunk_id"]

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
