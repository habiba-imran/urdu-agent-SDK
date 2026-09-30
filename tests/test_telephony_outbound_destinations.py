import os

import pytest

from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode
from tenant_portal_api.telephony_service import TelephonyService
from tenant_portal_api.telnyx_destinations import (
    TELNYX_DEFAULT_OUTBOUND_DESTINATION_COUNTRIES,
    assert_outbound_destination_allowed,
    e164_destination_countries,
)


def test_ensure_telephony_infrastructure_uses_env_destination_list(monkeypatch):
    monkeypatch.setenv("TELNYX_OUTBOUND_DESTINATIONS", "all")
    service = TelephonyService()
    captured: dict[str, list[str]] = {}

    def fake_upsert_sip_connection(
        tenant_id: str, outbound_voice_profile_provider_id: str | None = None
    ):
        return {
            "id": "sip_mock_123",
            "provider_outbound_voice_profile_id": outbound_voice_profile_provider_id,
        }

    def fake_upsert_outbound_voice_profile(tenant_id: str, allowed_destinations=None, **_kwargs):
        captured["allowed_destinations"] = list(allowed_destinations or [])
        return {
            "id": "ovp_mock_123",
            "provider_outbound_voice_profile_id": "provider_ovp_123",
        }

    monkeypatch.setattr(service, "upsert_telnyx_sip_connection", fake_upsert_sip_connection)
    monkeypatch.setattr(
        service,
        "upsert_telnyx_outbound_voice_profile",
        fake_upsert_outbound_voice_profile,
    )
    monkeypatch.setattr(
        service,
        "configure_outbound_trunk",
        lambda tenant_id: {"outbound_trunk_id": "trunk_mock_123"},
    )

    result = service.ensure_telephony_infrastructure("tenant_test_123")

    assert captured["allowed_destinations"] == list(
        TELNYX_DEFAULT_OUTBOUND_DESTINATION_COUNTRIES
    )
    assert "PK" in captured["allowed_destinations"]
    assert result["status"] == "ready"


def test_default_destinations_without_env_are_us_ca(monkeypatch):
    monkeypatch.delenv("TELNYX_OUTBOUND_DESTINATIONS", raising=False)
    from tenant_portal_api.telnyx_destinations import default_telnyx_outbound_destinations

    assert default_telnyx_outbound_destinations() == ["US", "CA"]


def test_e164_pakistan_and_nanp():
    assert "PK" in e164_destination_countries("+923001234567")
    assert "US" in e164_destination_countries("+14155550123")
    assert "CA" in e164_destination_countries("+14155550123")


def test_assert_outbound_destination_allows_pk_when_listed():
    assert assert_outbound_destination_allowed("+923001234567", ["US", "CA", "PK"]) == "PK"


def test_assert_outbound_destination_blocks_pk_when_us_ca_only():
    with pytest.raises(TelephonyError) as exc:
        assert_outbound_destination_allowed("+923001234567", ["US", "CA"])
    assert exc.value.code == TelephonyErrorCode.OUTBOUND_DESTINATION_DISABLED


def test_assert_outbound_destination_unknown_fails_closed():
    with pytest.raises(TelephonyError) as exc:
        assert_outbound_destination_allowed("+9991234567", ["US", "CA"])
    assert exc.value.code == TelephonyErrorCode.OUTBOUND_DESTINATION_DISABLED
