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

class FakeTelnyxResponse:
    status_code = 200

    def json(self):
        return {
            "data": [
                {
                    "phone_number": "+12125550123",
                    "country_code": "US",
                    "region": "US-NY",
                    "phone_number_type": "local",
                    "features": [{"name": "voice"}, {"name": "sms"}],
                    "cost_information": {
                        "upfront_cost": "1.00",
                        "monthly_cost": "1.00",
                        "currency": "USD",
                    },
                }
            ]
        }

    def raise_for_status(self):
        return None


class FakeTelnyxHttpClient:
    def __init__(self):
        self.requests = []

    def get(self, url, headers=None, params=None):
        self.requests.append({"url": url, "headers": headers, "params": params})
        return FakeTelnyxResponse()


def test_telnyx_client_real_search_normalizes_feature_arrays():
    http_client = FakeTelnyxHttpClient()
    client = TelnyxClient(api_key="real-shaped-test-key", http_client=http_client, mock_mode=False)

    results = client.search_available_numbers(country="US", area_code="212", features=["voice"])

    assert results == [
        {
            "e164_number": "+12125550123",
            "country": "US",
            "region": "US-NY",
            "number_type": "local",
            "features": ["voice", "sms"],
            "upfront_cost": "1.00",
            "monthly_cost": "1.00",
            "currency": "USD",
        }
    ]
    assert http_client.requests[0]["params"]["filter[national_destination_code]"] == "212"
    assert http_client.requests[0]["params"]["filter[features][voice]"] == "true"


class FakeTelnyxOrderErrorResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        raise AssertionError("purchase_number should map order errors before raise_for_status")


class FakeTelnyxOrderHttpClient:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def post(self, url, headers=None, json=None):
        self.requests.append({"url": url, "headers": headers, "json": json})
        return self.response


def test_purchase_number_maps_insufficient_balance_response():
    response = FakeTelnyxOrderErrorResponse(
        402,
        {"errors": [{"title": "Payment required", "detail": "Insufficient balance for number order."}]},
    )
    http_client = FakeTelnyxOrderHttpClient(response)
    client = TelnyxClient(api_key="real-shaped-test-key", http_client=http_client, mock_mode=False)

    with pytest.raises(TelephonyError) as exc_info:
        client.purchase_number("+14155550123")

    assert exc_info.value.status == 402
    assert exc_info.value.code == "insufficient_telnyx_balance"
    assert "real-shaped-test-key" not in exc_info.value.message
    assert http_client.requests[0]["json"] == {"phone_numbers": [{"phone_number": "+14155550123"}]}


def test_purchase_number_maps_regulatory_or_verification_response():
    response = FakeTelnyxOrderErrorResponse(
        422,
        {"errors": [{"title": "Regulatory requirements missing", "detail": "Verified address is required."}]},
    )
    client = TelnyxClient(api_key="real-shaped-test-key", http_client=FakeTelnyxOrderHttpClient(response), mock_mode=False)

    with pytest.raises(TelephonyError) as exc_info:
        client.purchase_number("+14155550123")

    assert exc_info.value.status == 409
    assert exc_info.value.code == "regulatory_action_required"
    assert exc_info.value.detail["provider_message"] == "Regulatory requirements missing Verified address is required."


def test_purchase_number_maps_generic_422_to_action_required_instead_of_not_available():
    response = FakeTelnyxOrderErrorResponse(
        422,
        {"errors": [{"title": "Order rejected", "detail": "Customer reference is invalid for this order type."}]},
    )
    client = TelnyxClient(
        api_key="real-shaped-test-key",
        http_client=FakeTelnyxOrderHttpClient(response),
        mock_mode=False,
    )

    with pytest.raises(TelephonyError) as exc_info:
        client.purchase_number("+14155550123")

    assert exc_info.value.status == 409
    assert exc_info.value.code == "number_order_action_required"
    assert "Customer reference is invalid" in exc_info.value.detail["provider_message"]


class FakeTelnyxOrderSuccessResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeTelnyxOrderStatusHttpClient:
    def __init__(self, response):
        self.response = response

    def post(self, url, headers=None, json=None):
        return self.response

    def get(self, url, headers=None):
        return self.response


def test_purchase_number_maps_action_required_when_requirements_not_met():
    response = FakeTelnyxOrderSuccessResponse(
        {"data": {"id": "ord_123", "status": "pending", "requirements_met": False}}
    )
    client = TelnyxClient(
        api_key="real-shaped-test-key",
        http_client=FakeTelnyxOrderStatusHttpClient(response),
        mock_mode=False,
    )

    result = client.purchase_number("+14155550123")

    assert result["provider_order_id"] == "ord_123"
    assert result["provider_status"] == "pending"
    assert result["platform_status"] == "action_required"


def test_get_number_order_status_maps_failure_and_cancelled_states():
    failed_client = TelnyxClient(
        api_key="real-shaped-test-key",
        http_client=FakeTelnyxOrderStatusHttpClient(
            FakeTelnyxOrderSuccessResponse({"data": {"id": "ord_failed", "status": "failure"}})
        ),
        mock_mode=False,
    )
    cancelled_client = TelnyxClient(
        api_key="real-shaped-test-key",
        http_client=FakeTelnyxOrderStatusHttpClient(
            FakeTelnyxOrderSuccessResponse({"data": {"id": "ord_cancelled", "status": "cancelled"}})
        ),
        mock_mode=False,
    )

    assert failed_client.get_number_order_status("ord_failed")["platform_status"] == "failed"
    assert cancelled_client.get_number_order_status("ord_cancelled")["platform_status"] == "cancelled"
