from tenant_portal_api.telephony_service import TelephonyService
from tenant_portal_api.telnyx_destinations import (
    TELNYX_DEFAULT_OUTBOUND_DESTINATION_COUNTRIES,
)


def test_ensure_telephony_infrastructure_uses_full_telnyx_destination_list(monkeypatch):
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
