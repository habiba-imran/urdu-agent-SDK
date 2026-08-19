"""LiveKit SIP adapter for managing long-lived inbound/outbound trunks, SIP dispatch rules, and SIP participant creation.

Backend-only module. Mock mode is available only when explicitly requested.
Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Awaitable, TypeVar

from tenant_portal_api.telephony_config import is_mock_provider_mode, livekit_agent_name
from tenant_portal_api.telephony_errors import (
    TelephonyError,
    TelephonyErrorCode,
    redact_sensitive_string,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class LiveKitSipClient:
    """Adapter for LiveKit Server SIP APIs."""

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        mock_mode: bool | None = None,
    ):
        self.url = url or os.getenv("LIVEKIT_URL", "")
        self.api_key = api_key or os.getenv("LIVEKIT_API_KEY", "")
        self.api_secret = api_secret or os.getenv("LIVEKIT_API_SECRET", "")
        self.mock_mode = is_mock_provider_mode() if mock_mode is None else mock_mode

    def create_or_get_inbound_trunk(
        self, phone_number_id: str, e164_number: str
    ) -> dict[str, Any]:
        """Configure or retrieve a reusable long-lived LiveKit inbound trunk for a phone number."""
        if self.mock_mode:
            return {
                "livekit_inbound_trunk_id": f"lk_tr_in_mock_{phone_number_id[:8]}",
                "e164_number": e164_number,
                "status": "active",
            }
        self._require_credentials()

        async def op():
            import livekit.api as lk

            api = lk.LiveKitAPI(
                url=self.url, api_key=self.api_key, api_secret=self.api_secret
            )
            try:
                listed = await api.sip.list_sip_inbound_trunk(
                    lk.ListSIPInboundTrunkRequest(numbers=[e164_number])
                )
                for item in listed.items:
                    if e164_number in list(item.numbers):
                        return {
                            "livekit_inbound_trunk_id": item.sip_trunk_id,
                            "e164_number": e164_number,
                            "status": "active",
                        }
                trunk = lk.SIPInboundTrunkInfo(
                    name=f"uva-inbound-{phone_number_id}",
                    numbers=[e164_number],
                )
                created = await api.sip.create_sip_inbound_trunk(
                    lk.CreateSIPInboundTrunkRequest(trunk=trunk)
                )
                return {
                    "livekit_inbound_trunk_id": created.sip_trunk_id,
                    "e164_number": e164_number,
                    "status": "active",
                }
            finally:
                await api.aclose()

        return self._run(
            op(),
            TelephonyErrorCode.LIVEKIT_INBOUND_TRUNK_FAILED,
            "Failed to create or configure LiveKit inbound trunk.",
        )

    def create_or_get_outbound_trunk(
        self,
        telnyx_connection_id: str,
        sip_fqdn: str,
        trunk_numbers: list[str],
        sip_username: str | None = None,
        sip_secret: str | None = None,
    ) -> dict[str, Any]:
        """Configure or retrieve a reusable long-lived LiveKit outbound trunk for a Telnyx connection."""
        numbers = sorted(
            {
                number.strip()
                for number in trunk_numbers
                if number and number.strip().startswith("+")
            }
        )
        if not numbers:
            raise TelephonyError(
                status=409,
                code=TelephonyErrorCode.OUTBOUND_NOT_READY,
                message="Tenant has no eligible managed phone numbers for outbound trunk setup.",
            )
        if self.mock_mode:
            return {
                "livekit_outbound_trunk_id": f"lk_tr_out_mock_{telnyx_connection_id[:8]}",
                "sip_fqdn": sip_fqdn,
                "numbers": numbers,
                "status": "active",
            }
        self._require_credentials()

        async def op():
            import livekit.api as lk

            api = lk.LiveKitAPI(
                url=self.url, api_key=self.api_key, api_secret=self.api_secret
            )
            try:
                listed = await api.sip.list_sip_outbound_trunk(
                    lk.ListSIPOutboundTrunkRequest()
                )
                name = f"uva-outbound-{telnyx_connection_id}"
                for item in listed.items:
                    if item.name == name:
                        current_numbers = sorted(set(item.numbers))
                        current_username = getattr(item, "auth_username", "")
                        current_headers = dict(getattr(item, "headers", {}) or {})
                        expected_headers = (
                            {"X-Telnyx-Username": sip_username} if sip_username else {}
                        )
                        if (
                            current_numbers != numbers
                            or item.address != sip_fqdn
                            or current_username != (sip_username or "")
                            or current_headers != expected_headers
                        ):
                            item = await api.sip.update_outbound_trunk(
                                item.sip_trunk_id,
                                lk.SIPOutboundTrunkInfo(
                                    name=name,
                                    address=sip_fqdn,
                                    numbers=numbers,
                                    auth_username=sip_username or "",
                                    auth_password=sip_secret or "",
                                    headers=expected_headers,
                                    metadata=getattr(item, "metadata", ""),
                                    transport=getattr(item, "transport", None),
                                    destination_country=getattr(
                                        item, "destination_country", ""
                                    ),
                                    from_host=getattr(item, "from_host", ""),
                                    headers_to_attributes=dict(
                                        getattr(item, "headers_to_attributes", {}) or {}
                                    ),
                                    attributes_to_headers=dict(
                                        getattr(item, "attributes_to_headers", {}) or {}
                                    ),
                                    include_headers=getattr(
                                        item, "include_headers", None
                                    ),
                                    media=getattr(item, "media", None),
                                ),
                            )
                        return {
                            "livekit_outbound_trunk_id": item.sip_trunk_id,
                            "sip_fqdn": sip_fqdn,
                            "numbers": numbers,
                            "status": "active",
                        }
                trunk = lk.SIPOutboundTrunkInfo(
                    name=name,
                    address=sip_fqdn,
                    numbers=numbers,
                    auth_username=sip_username or "",
                    auth_password=sip_secret or "",
                    headers={"X-Telnyx-Username": sip_username} if sip_username else {},
                )
                created = await api.sip.create_outbound_trunk(
                    lk.CreateSIPOutboundTrunkRequest(trunk=trunk)
                )
                return {
                    "livekit_outbound_trunk_id": created.sip_trunk_id,
                    "sip_fqdn": sip_fqdn,
                    "numbers": numbers,
                    "status": "active",
                }
            finally:
                await api.aclose()

        return self._run(
            op(),
            TelephonyErrorCode.LIVEKIT_OUTBOUND_TRUNK_FAILED,
            "Failed to create or configure LiveKit outbound trunk.",
        )

    def create_or_get_dispatch_rule(
        self,
        inbound_trunk_id: str,
        phone_number_id: str,
        e164_number: str,
        *,
        tenant_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Configure or retrieve a reusable LiveKit SIP dispatch rule for a phone number.

        Uses an individual room prefix plus explicit RoomAgentDispatch so the named
        worker (LIVEKIT_AGENT_NAME) is dispatched into each inbound PSTN room.
        """
        agent_name = livekit_agent_name()
        if self.mock_mode:
            return {
                "livekit_sip_dispatch_rule_id": f"lk_rule_mock_{phone_number_id[:8]}",
                "inbound_trunk_id": inbound_trunk_id,
                "e164_number": e164_number,
                "agent_name": agent_name,
                "status": "active",
            }
        self._require_credentials()

        async def op():
            import json as _json

            import livekit.api as lk

            def _desired_dispatch_metadata() -> str:
                return _json.dumps(
                    {
                        "direction": "inbound",
                        "phone_number_id": phone_number_id,
                        "e164_number": e164_number,
                        "tenant_id": tenant_id or "",
                        "agent_id": agent_id or "",
                    }
                )

            def _desired_rule() -> Any:
                return lk.SIPDispatchRule(
                    dispatch_rule_individual=lk.SIPDispatchRuleIndividual(
                        room_prefix=f"telephony-inbound-{phone_number_id}-"
                    )
                )

            def _desired_room_config(dispatch_metadata: str) -> Any:
                return lk.RoomConfiguration(
                    agents=[
                        lk.RoomAgentDispatch(
                            agent_name=agent_name,
                            metadata=dispatch_metadata,
                        )
                    ]
                )

            api = lk.LiveKitAPI(
                url=self.url, api_key=self.api_key, api_secret=self.api_secret
            )
            try:
                name = f"uva-dispatch-{phone_number_id}"
                dispatch_metadata = _desired_dispatch_metadata()
                rule = _desired_rule()
                room_config = _desired_room_config(dispatch_metadata)
                listed = await api.sip.list_dispatch_rule(
                    lk.ListSIPDispatchRuleRequest()
                )
                matching_items = [
                    item for item in listed.items if getattr(item, "name", "") == name
                ]
                if matching_items:
                    item = next(
                        (
                            candidate
                            for candidate in matching_items
                            if inbound_trunk_id in list(getattr(candidate, "trunk_ids", []) or [])
                        ),
                        matching_items[0],
                    )
                    current_room_prefix = getattr(
                        getattr(getattr(item, "rule", None), "dispatch_rule_individual", None),
                        "room_prefix",
                        "",
                    )
                    current_trunk_ids = sorted(
                        str(value) for value in (getattr(item, "trunk_ids", []) or [])
                    )
                    current_inbound_numbers = [
                        str(value).strip()
                        for value in (getattr(item, "inbound_numbers", []) or [])
                        if str(value).strip()
                    ]
                    current_agents = list(
                        getattr(getattr(item, "room_config", None), "agents", []) or []
                    )
                    current_agent_name = (
                        getattr(current_agents[0], "agent_name", "") if current_agents else ""
                    )
                    current_agent_metadata = (
                        getattr(current_agents[0], "metadata", "") if current_agents else ""
                    )
                    expected_trunk_ids = [str(inbound_trunk_id)]
                    needs_update = (
                        current_trunk_ids != expected_trunk_ids
                        or current_room_prefix != f"telephony-inbound-{phone_number_id}-"
                        or current_agent_name != agent_name
                        or current_agent_metadata != dispatch_metadata
                        or bool(current_inbound_numbers)
                    )
                    if needs_update:
                        item = await api.sip.update_dispatch_rule(
                            item.sip_dispatch_rule_id,
                            lk.SIPDispatchRuleInfo(
                                sip_dispatch_rule_id=item.sip_dispatch_rule_id,
                                name=name,
                                rule=rule,
                                trunk_ids=[inbound_trunk_id],
                                inbound_numbers=[],
                                room_config=room_config,
                                metadata=getattr(item, "metadata", ""),
                                attributes=dict(getattr(item, "attributes", {}) or {}),
                                hide_phone_number=getattr(item, "hide_phone_number", False),
                                room_preset=getattr(item, "room_preset", ""),
                                media=getattr(item, "media", None),
                                krisp_enabled=getattr(item, "krisp_enabled", False),
                                media_encryption=getattr(item, "media_encryption", None),
                            ),
                        )
                    duplicate_items = [
                        candidate
                        for candidate in matching_items
                        if getattr(candidate, "sip_dispatch_rule_id", "") != getattr(item, "sip_dispatch_rule_id", "")
                    ]
                    for duplicate in duplicate_items:
                        await api.sip.delete_dispatch_rule(
                            lk.DeleteSIPDispatchRuleRequest(
                                sip_dispatch_rule_id=duplicate.sip_dispatch_rule_id
                            )
                        )
                    return {
                        "livekit_sip_dispatch_rule_id": item.sip_dispatch_rule_id,
                        "inbound_trunk_id": inbound_trunk_id,
                        "e164_number": e164_number,
                        "agent_name": agent_name,
                        "status": "active",
                    }
                created = await api.sip.create_sip_dispatch_rule(
                    lk.CreateSIPDispatchRuleRequest(
                        name=name,
                        rule=rule,
                        trunk_ids=[inbound_trunk_id],
                        room_config=room_config,
                    )
                )
                return {
                    "livekit_sip_dispatch_rule_id": created.sip_dispatch_rule_id,
                    "inbound_trunk_id": inbound_trunk_id,
                    "e164_number": e164_number,
                    "agent_name": agent_name,
                    "status": "active",
                }
            finally:
                await api.aclose()

        return self._run(
            op(),
            TelephonyErrorCode.LIVEKIT_SIP_DISPATCH_RULE_FAILED,
            "Failed to create or configure LiveKit SIP dispatch rule.",
        )

    def create_agent_dispatch(
        self,
        room_name: str,
        *,
        metadata: dict[str, Any] | str | None = None,
        agent_name: str | None = None,
    ) -> dict[str, Any]:
        """Explicitly dispatch the named voice agent into a telephony room."""
        resolved_agent = agent_name or livekit_agent_name()
        if isinstance(metadata, dict):
            import json as _json

            metadata_str = _json.dumps(metadata)
        else:
            metadata_str = metadata or ""

        if self.mock_mode:
            return {
                "room_name": room_name,
                "agent_name": resolved_agent,
                "dispatch_id": f"dispatch_mock_{room_name[:8]}",
                "status": "dispatched",
            }
        self._require_credentials()

        async def op():
            import livekit.api as lk

            api = lk.LiveKitAPI(
                url=self.url, api_key=self.api_key, api_secret=self.api_secret
            )
            try:
                created = await api.agent_dispatch.create_dispatch(
                    lk.CreateAgentDispatchRequest(
                        agent_name=resolved_agent,
                        room=room_name,
                        metadata=metadata_str,
                    )
                )
                return {
                    "room_name": room_name,
                    "agent_name": resolved_agent,
                    "dispatch_id": getattr(created, "id", None)
                    or getattr(created, "dispatch_id", ""),
                    "status": "dispatched",
                }
            finally:
                await api.aclose()

        return self._run(
            op(),
            TelephonyErrorCode.LIVEKIT_AGENT_DISPATCH_FAILED,
            "Failed to dispatch voice agent into telephony room.",
        )

    def create_sip_participant(
        self,
        room_name: str,
        outbound_trunk_id: str,
        to_number: str,
        participant_identity: str | None = None,
    ) -> dict[str, Any]:
        """Create an outbound SIP participant into a LiveKit room to dial out to a PSTN number."""
        if self.mock_mode:
            return {
                "livekit_sip_call_id": f"sip_call_mock_{room_name[:8]}",
                "livekit_sip_call_id_full": f"sip_call_mock_{room_name[:8]}_full",
                "room_name": room_name,
                "to_number": to_number,
                "status": "dialing",
            }
        self._require_credentials()

        async def op():
            import livekit.api as lk

            api = lk.LiveKitAPI(
                url=self.url, api_key=self.api_key, api_secret=self.api_secret
            )
            try:
                created = await api.sip.create_sip_participant(
                    lk.CreateSIPParticipantRequest(
                        sip_trunk_id=outbound_trunk_id,
                        sip_call_to=to_number,
                        room_name=room_name,
                        participant_identity=participant_identity or f"sip-{room_name}",
                    )
                )
                return {
                    "livekit_sip_call_id": created.sip_call_id,
                    "livekit_sip_call_id_full": getattr(
                        created, "sip_call_id_full", created.sip_call_id
                    ),
                    "room_name": room_name,
                    "to_number": to_number,
                    "status": "dialing",
                }
            finally:
                await api.aclose()

        return self._run(
            op(),
            TelephonyErrorCode.LIVEKIT_AGENT_DISPATCH_FAILED,
            "Failed to initiate outbound SIP participant.",
        )

    def delete_sip_dispatch_rule(self, dispatch_rule_id: str) -> dict[str, Any]:
        """Delete or disable a LiveKit SIP dispatch rule."""
        if self.mock_mode:
            return {"dispatch_rule_id": dispatch_rule_id, "status": "deleted"}
        self._require_credentials()

        async def op():
            import livekit.api as lk

            api = lk.LiveKitAPI(url=self.url, api_key=self.api_key, api_secret=self.api_secret)
            try:
                await api.sip.delete_sip_dispatch_rule(
                    lk.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=dispatch_rule_id)
                )
                return {"dispatch_rule_id": dispatch_rule_id, "status": "deleted"}
            finally:
                await api.aclose()

        return self._run(
            op(),
            TelephonyErrorCode.LIVEKIT_SIP_DISPATCH_RULE_FAILED,
            "Failed to delete LiveKit SIP dispatch rule.",
        )


    def _require_credentials(self) -> None:
        if not self.url or not self.api_key or not self.api_secret:
            raise TelephonyError(
                status=503,
                code=TelephonyErrorCode.PROVIDER_CREDENTIALS_MISSING,
                message="LiveKit SIP credentials are not configured.",
            )

    def _run(self, awaitable: Awaitable[T], code: str, message: str) -> T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                return asyncio.run(awaitable)
            except TelephonyError:
                raise
            except Exception as exc:
                self._raise_provider_error(exc, code, message)

        result: dict[str, T] = {}
        error: dict[str, BaseException] = {}

        def runner() -> None:
            try:
                result["value"] = asyncio.run(awaitable)
            except BaseException as exc:  # noqa: BLE001 - re-raised in caller thread
                error["error"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if error:
            exc = error["error"]
            if isinstance(exc, TelephonyError):
                raise exc
            self._raise_provider_error(exc, code, message)
        return result["value"]

    def _raise_provider_error(
        self, exc: BaseException, code: str, message: str
    ) -> None:
        provider_message = str(exc)
        sanitized_provider_message = redact_sensitive_string(provider_message)
        logger.error(
            "LiveKit SIP provider operation failed: %s",
            sanitized_provider_message,
        )
        if (
            code == TelephonyErrorCode.LIVEKIT_OUTBOUND_TRUNK_FAILED
            and "no trunk numbers specified" in provider_message.lower()
        ):
            raise TelephonyError(
                status=409,
                code=TelephonyErrorCode.OUTBOUND_NOT_READY,
                message="Tenant has no eligible managed phone numbers for outbound trunk setup.",
            ) from exc
        raise TelephonyError(
            status=502,
            code=code,
            message=message,
            detail={"provider_message": sanitized_provider_message},
        ) from exc
