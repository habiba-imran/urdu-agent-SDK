"""Unit tests for LiveKit SIP adapter.

Phase 4 & 5 verification suite.
"""

import sys
import types

import pytest
from tenant_portal_api.livekit_sip import LiveKitSipClient
from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode


def test_livekit_sip_client_mock():
    client = LiveKitSipClient(mock_mode=True)

    inbound = client.create_or_get_inbound_trunk("phone_12345678", "+15551234567")
    assert inbound["status"] == "active"
    assert "lk_tr_in_mock_" in inbound["livekit_inbound_trunk_id"]
    assert inbound["e164_number"] == "+15551234567"

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


class _FakeDispatchRuleIndividual:
    def __init__(self, room_prefix: str = ""):
        self.room_prefix = room_prefix


class _FakeDispatchRule:
    def __init__(self, dispatch_rule_individual=None):
        self.dispatch_rule_individual = dispatch_rule_individual


class _FakeRoomAgentDispatch:
    def __init__(self, agent_name: str = "", metadata: str = ""):
        self.agent_name = agent_name
        self.metadata = metadata


class _FakeRoomConfiguration:
    def __init__(self, agents=None):
        self.agents = list(agents or [])


class _FakeCreateSIPDispatchRuleRequest:
    def __init__(
        self,
        *,
        name: str = "",
        rule=None,
        trunk_ids=None,
        inbound_numbers=None,
        room_config=None,
    ):
        self.name = name
        self.rule = rule
        self.trunk_ids = list(trunk_ids or [])
        self.inbound_numbers = list(inbound_numbers or [])
        self.room_config = room_config


class _FakeSIPDispatchRuleInfo:
    def __init__(
        self,
        *,
        sip_dispatch_rule_id: str = "",
        name: str = "",
        rule=None,
        trunk_ids=None,
        inbound_numbers=None,
        room_config=None,
        metadata: str = "",
        attributes=None,
        hide_phone_number: bool = False,
        room_preset: str = "",
        media=None,
        krisp_enabled: bool = False,
        media_encryption=None,
    ):
        self.sip_dispatch_rule_id = sip_dispatch_rule_id
        self.name = name
        self.rule = rule
        self.trunk_ids = list(trunk_ids or [])
        self.inbound_numbers = list(inbound_numbers or [])
        self.room_config = room_config
        self.metadata = metadata
        self.attributes = dict(attributes or {})
        self.hide_phone_number = hide_phone_number
        self.room_preset = room_preset
        self.media = media
        self.krisp_enabled = krisp_enabled
        self.media_encryption = media_encryption


class _FakeListSIPDispatchRuleRequest:
    def __init__(self, trunk_ids=None):
        self.trunk_ids = list(trunk_ids or [])


class _FakeListSIPDispatchRuleResponse:
    def __init__(self, items):
        self.items = items


class _FakeDeleteSIPDispatchRuleRequest:
    def __init__(self, *, sip_dispatch_rule_id: str = ""):
        self.sip_dispatch_rule_id = sip_dispatch_rule_id


class _FakeDispatchService:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.created_requests = []
        self.updated_rules = []
        self.deleted_rule_ids = []

    async def list_dispatch_rule(self, request):
        self.last_list_request = request
        return _FakeListSIPDispatchRuleResponse(self.items)

    async def create_sip_dispatch_rule(self, request):
        self.created_requests.append(request)
        created = _FakeSIPDispatchRuleInfo(
            sip_dispatch_rule_id="lk_rule_created_123",
            name=request.name,
            rule=request.rule,
            trunk_ids=request.trunk_ids,
            inbound_numbers=request.inbound_numbers,
            room_config=request.room_config,
        )
        self.items = [created]
        return created

    async def update_dispatch_rule(self, rule_id, rule):
        self.updated_rules.append((rule_id, rule))
        updated = _FakeSIPDispatchRuleInfo(
            sip_dispatch_rule_id=rule_id,
            name=rule.name,
            rule=rule.rule,
            trunk_ids=rule.trunk_ids,
            inbound_numbers=rule.inbound_numbers,
            room_config=rule.room_config,
            metadata=rule.metadata,
            attributes=rule.attributes,
            hide_phone_number=rule.hide_phone_number,
            room_preset=rule.room_preset,
            media=rule.media,
            krisp_enabled=rule.krisp_enabled,
            media_encryption=rule.media_encryption,
        )
        self.items = [updated]
        return updated

    async def delete_dispatch_rule(self, request):
        self.deleted_rule_ids.append(request.sip_dispatch_rule_id)
        self.items = [
            item
            for item in self.items
            if item.sip_dispatch_rule_id != request.sip_dispatch_rule_id
        ]
        return _FakeSIPDispatchRuleInfo(sip_dispatch_rule_id=request.sip_dispatch_rule_id)


class _FakeLiveKitAPI:
    dispatch_service = None

    def __init__(self, url, api_key, api_secret):  # noqa: ARG002
        self.sip = self.__class__.dispatch_service

    async def aclose(self):
        return None


def _install_fake_livekit_api(monkeypatch, dispatch_service):
    fake_api_module = types.ModuleType("livekit.api")
    fake_api_module.LiveKitAPI = _FakeLiveKitAPI
    fake_api_module.ListSIPDispatchRuleRequest = _FakeListSIPDispatchRuleRequest
    fake_api_module.CreateSIPDispatchRuleRequest = _FakeCreateSIPDispatchRuleRequest
    fake_api_module.DeleteSIPDispatchRuleRequest = _FakeDeleteSIPDispatchRuleRequest
    fake_api_module.SIPDispatchRuleInfo = _FakeSIPDispatchRuleInfo
    fake_api_module.SIPDispatchRule = _FakeDispatchRule
    fake_api_module.SIPDispatchRuleIndividual = _FakeDispatchRuleIndividual
    fake_api_module.RoomConfiguration = _FakeRoomConfiguration
    fake_api_module.RoomAgentDispatch = _FakeRoomAgentDispatch

    fake_livekit_pkg = types.ModuleType("livekit")
    fake_livekit_pkg.api = fake_api_module
    _FakeLiveKitAPI.dispatch_service = dispatch_service
    monkeypatch.setitem(sys.modules, "livekit", fake_livekit_pkg)
    monkeypatch.setitem(sys.modules, "livekit.api", fake_api_module)


def test_livekit_dispatch_rule_created_without_inbound_numbers_and_bound_to_trunk(monkeypatch):
    dispatch_service = _FakeDispatchService()
    _install_fake_livekit_api(monkeypatch, dispatch_service)

    client = LiveKitSipClient(
        url="wss://livekit.example", api_key="key", api_secret="secret", mock_mode=False
    )

    result = client.create_or_get_dispatch_rule(
        "ST_5NPaEZ43u4BS",
        "phone_12345678",
        "+14755587853",
        tenant_id="tenant_123",
        agent_id="agent_123",
    )

    assert result["status"] == "active"
    assert dispatch_service.created_requests
    created_request = dispatch_service.created_requests[0]
    assert created_request.trunk_ids == ["ST_5NPaEZ43u4BS"]
    assert created_request.inbound_numbers == []
    assert created_request.rule.dispatch_rule_individual.room_prefix == "telephony-inbound-phone_12345678-"
    assert created_request.room_config.agents[0].agent_name == "uva-dev-agent"
    assert '"phone_number_id": "phone_12345678"' in created_request.room_config.agents[0].metadata
    assert '"+14755587853"' in created_request.room_config.agents[0].metadata


def test_livekit_dispatch_rule_repairs_stale_inbound_numbers_rule(monkeypatch):
    stale_rule = _FakeSIPDispatchRuleInfo(
        sip_dispatch_rule_id="lk_rule_stale_123",
        name="uva-dispatch-phone_12345678",
        rule=_FakeDispatchRule(
            dispatch_rule_individual=_FakeDispatchRuleIndividual(room_prefix="telephony-inbound-phone_12345678-")
        ),
        trunk_ids=["ST_5NPaEZ43u4BS"],
        inbound_numbers=["+14755587853"],
        room_config=_FakeRoomConfiguration(
            agents=[_FakeRoomAgentDispatch(agent_name="uva-dev-agent", metadata='{"direction":"inbound"}')]
        ),
    )
    dispatch_service = _FakeDispatchService(items=[stale_rule])
    _install_fake_livekit_api(monkeypatch, dispatch_service)

    client = LiveKitSipClient(
        url="wss://livekit.example", api_key="key", api_secret="secret", mock_mode=False
    )

    result = client.create_or_get_dispatch_rule(
        "ST_5NPaEZ43u4BS",
        "phone_12345678",
        "+14755587853",
        tenant_id="tenant_123",
        agent_id="agent_123",
    )

    assert result["status"] == "active"
    assert len(dispatch_service.updated_rules) == 1
    rule_id, updated_rule = dispatch_service.updated_rules[0]
    assert rule_id == "lk_rule_stale_123"
    assert updated_rule.trunk_ids == ["ST_5NPaEZ43u4BS"]
    assert updated_rule.inbound_numbers == []
    assert updated_rule.rule.dispatch_rule_individual.room_prefix == "telephony-inbound-phone_12345678-"
    assert updated_rule.room_config.agents[0].agent_name == "uva-dev-agent"
    assert '"agent_id": "agent_123"' in updated_rule.room_config.agents[0].metadata
    assert '"+14755587853"' in updated_rule.room_config.agents[0].metadata
    assert dispatch_service.created_requests == []


def test_livekit_dispatch_rule_removes_duplicate_same_name_rules(monkeypatch):
    primary_rule = _FakeSIPDispatchRuleInfo(
        sip_dispatch_rule_id="lk_rule_primary_123",
        name="uva-dispatch-phone_12345678",
        rule=_FakeDispatchRule(
            dispatch_rule_individual=_FakeDispatchRuleIndividual(room_prefix="telephony-inbound-phone_12345678-")
        ),
        trunk_ids=["ST_5NPaEZ43u4BS"],
        inbound_numbers=[],
        room_config=_FakeRoomConfiguration(
            agents=[
                _FakeRoomAgentDispatch(
                    agent_name="uva-dev-agent",
                    metadata='{"direction":"inbound","phone_number_id":"phone_12345678","e164_number":"+14755587853","tenant_id":"tenant_123","agent_id":"agent_123"}',
                )
            ]
        ),
    )
    duplicate_rule = _FakeSIPDispatchRuleInfo(
        sip_dispatch_rule_id="lk_rule_duplicate_123",
        name="uva-dispatch-phone_12345678",
        rule=_FakeDispatchRule(
            dispatch_rule_individual=_FakeDispatchRuleIndividual(room_prefix="telephony-inbound-phone_12345678-")
        ),
        trunk_ids=["ST_OLD"],
        inbound_numbers=["+14755587853"],
        room_config=_FakeRoomConfiguration(
            agents=[_FakeRoomAgentDispatch(agent_name="uva-dev-agent", metadata='{"direction":"inbound"}')]
        ),
    )
    dispatch_service = _FakeDispatchService(items=[primary_rule, duplicate_rule])
    _install_fake_livekit_api(monkeypatch, dispatch_service)

    client = LiveKitSipClient(
        url="wss://livekit.example", api_key="key", api_secret="secret", mock_mode=False
    )

    result = client.create_or_get_dispatch_rule(
        "ST_5NPaEZ43u4BS",
        "phone_12345678",
        "+14755587853",
        tenant_id="tenant_123",
        agent_id="agent_123",
    )

    assert result["status"] == "active"
    assert dispatch_service.updated_rules == []
    assert dispatch_service.deleted_rule_ids == ["lk_rule_duplicate_123"]
