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

from tenant_portal_api.telephony_config import is_mock_provider_mode
from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode, redact_sensitive_string

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

            api = lk.LiveKitAPI(url=self.url, api_key=self.api_key, api_secret=self.api_secret)
            try:
                listed = await api.sip.list_sip_inbound_trunk(lk.ListSIPInboundTrunkRequest(numbers=[e164_number]))
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
                created = await api.sip.create_sip_inbound_trunk(lk.CreateSIPInboundTrunkRequest(trunk=trunk))
                return {
                    "livekit_inbound_trunk_id": created.sip_trunk_id,
                    "e164_number": e164_number,
                    "status": "active",
                }
            finally:
                await api.aclose()

        return self._run(op(), TelephonyErrorCode.LIVEKIT_INBOUND_TRUNK_FAILED, "Failed to create or configure LiveKit inbound trunk.")

    def create_or_get_outbound_trunk(
        self, telnyx_connection_id: str, sip_fqdn: str, trunk_numbers: list[str]
    ) -> dict[str, Any]:
        """Configure or retrieve a reusable long-lived LiveKit outbound trunk for a Telnyx connection."""
        numbers = sorted({number.strip() for number in trunk_numbers if number and number.strip().startswith("+")})
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

            api = lk.LiveKitAPI(url=self.url, api_key=self.api_key, api_secret=self.api_secret)
            try:
                listed = await api.sip.list_sip_outbound_trunk(lk.ListSIPOutboundTrunkRequest())
                name = f"uva-outbound-{telnyx_connection_id}"
                for item in listed.items:
                    if item.name == name:
                        current_numbers = sorted(set(item.numbers))
                        if current_numbers != numbers or item.address != sip_fqdn:
                            item = await api.sip.update_outbound_trunk_fields(
                                item.sip_trunk_id,
                                address=sip_fqdn,
                                numbers=numbers,
                            )
                        return {
                            "livekit_outbound_trunk_id": item.sip_trunk_id,
                            "sip_fqdn": sip_fqdn,
                            "numbers": numbers,
                            "status": "active",
                        }
                trunk = lk.SIPOutboundTrunkInfo(name=name, address=sip_fqdn, numbers=numbers)
                created = await api.sip.create_outbound_trunk(lk.CreateSIPOutboundTrunkRequest(trunk=trunk))
                return {
                    "livekit_outbound_trunk_id": created.sip_trunk_id,
                    "sip_fqdn": sip_fqdn,
                    "numbers": numbers,
                    "status": "active",
                }
            finally:
                await api.aclose()

        return self._run(op(), TelephonyErrorCode.LIVEKIT_OUTBOUND_TRUNK_FAILED, "Failed to create or configure LiveKit outbound trunk.")

    def create_or_get_dispatch_rule(
        self, inbound_trunk_id: str, phone_number_id: str, e164_number: str
    ) -> dict[str, Any]:
        """Configure or retrieve a reusable LiveKit SIP dispatch rule for a phone number."""
        if self.mock_mode:
            return {
                "livekit_sip_dispatch_rule_id": f"lk_rule_mock_{phone_number_id[:8]}",
                "inbound_trunk_id": inbound_trunk_id,
                "e164_number": e164_number,
                "status": "active",
            }
        self._require_credentials()

        async def op():
            import livekit.api as lk

            api = lk.LiveKitAPI(url=self.url, api_key=self.api_key, api_secret=self.api_secret)
            try:
                listed = await api.sip.list_sip_dispatch_rule(lk.ListSIPDispatchRuleRequest(trunk_ids=[inbound_trunk_id]))
                name = f"uva-dispatch-{phone_number_id}"
                for item in listed.items:
                    if item.name == name:
                        return {
                            "livekit_sip_dispatch_rule_id": item.sip_dispatch_rule_id,
                            "inbound_trunk_id": inbound_trunk_id,
                            "e164_number": e164_number,
                            "status": "active",
                        }
                rule = lk.SIPDispatchRule(dispatch_rule_direct=lk.SIPDispatchRuleDirect(room_name=f"telephony-inbound-{phone_number_id}"))
                created = await api.sip.create_sip_dispatch_rule(
                    lk.CreateSIPDispatchRuleRequest(
                        name=name,
                        rule=rule,
                        trunk_ids=[inbound_trunk_id],
                        inbound_numbers=[e164_number],
                    )
                )
                return {
                    "livekit_sip_dispatch_rule_id": created.sip_dispatch_rule_id,
                    "inbound_trunk_id": inbound_trunk_id,
                    "e164_number": e164_number,
                    "status": "active",
                }
            finally:
                await api.aclose()

        return self._run(op(), TelephonyErrorCode.LIVEKIT_SIP_DISPATCH_RULE_FAILED, "Failed to create or configure LiveKit SIP dispatch rule.")

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

            api = lk.LiveKitAPI(url=self.url, api_key=self.api_key, api_secret=self.api_secret)
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
                    "livekit_sip_call_id_full": getattr(created, "sip_call_id_full", created.sip_call_id),
                    "room_name": room_name,
                    "to_number": to_number,
                    "status": "dialing",
                }
            finally:
                await api.aclose()

        return self._run(op(), TelephonyErrorCode.LIVEKIT_AGENT_DISPATCH_FAILED, "Failed to initiate outbound SIP participant.")

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

    def _raise_provider_error(self, exc: BaseException, code: str, message: str) -> None:
        provider_message = str(exc)
        logger.error("LiveKit SIP provider operation failed: %s", redact_sensitive_string(provider_message))
        if code == TelephonyErrorCode.LIVEKIT_OUTBOUND_TRUNK_FAILED and "no trunk numbers specified" in provider_message.lower():
            raise TelephonyError(
                status=409,
                code=TelephonyErrorCode.OUTBOUND_NOT_READY,
                message="Tenant has no eligible managed phone numbers for outbound trunk setup.",
            ) from exc
        raise TelephonyError(status=502, code=code, message=message) from exc
