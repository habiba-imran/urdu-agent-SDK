"""Unit tests for Telnyx API client adapter.

Phase 3 verification suite.
"""

import pytest
from tenant_portal_api.telephony_errors import TelephonyError
from tenant_portal_api.telnyx_client import TelnyxClient


def test_telnyx_client_mock_verification():
    client = TelnyxClient(api_key="mock_valid_key", mock_mode=True)
    res = client.verify_api_key()
    assert res["status"] == "active"
    assert res["telnyx_account_id"] == "act_fake_telnyx_123"


def test_telnyx_client_mock_invalid_key():
    client = TelnyxClient(api_key="invalid_key", mock_mode=True)
    with pytest.raises(TelephonyError) as exc_info:
        client.verify_api_key()
    assert exc_info.value.code == "telnyx_key_invalid"
    assert exc_info.value.status == 401


def test_telnyx_client_search_and_purchase():
    client = TelnyxClient(api_key="test_key_123", mock_mode=True)
    results = client.search_available_numbers(country="US", area_code="555")
    assert len(results) > 0
    assert results[0]["country"] == "US"
    target_num = results[0]["e164_number"]

    order = client.purchase_number(target_num)
    assert order["selected_e164_number"] == target_num
    assert order["platform_status"] == "purchased"


def test_telnyx_client_fqdn_and_profile():
    client = TelnyxClient(api_key="test_key_123", mock_mode=True)
    fqdn = client.create_or_get_fqdn_connection("test_conn", "sip.test.com")
    assert fqdn["status"] == "active"

    profile = client.create_or_get_outbound_voice_profile(
        "test_profile", fqdn["provider_sip_connection_id"]
    )
    assert profile["status"] == "active"


def test_telnyx_client_real_mode_requires_api_key(monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER_MODE", "real")
    client = TelnyxClient(api_key="")

    with pytest.raises(TelephonyError) as exc_info:
        client.verify_api_key()

    assert exc_info.value.code == "provider_credentials_missing"
    assert exc_info.value.status == 503
