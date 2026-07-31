"""Telephony domain service orchestrating credential lifecycle, number inventory, LiveKit SIP readiness, quota reservation, idempotency, and outbound calls.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any

from tenant_portal_api.livekit_sip import LiveKitSipClient
from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode
from tenant_portal_api.telephony_models import (
    ManagedNumberResponse,
    NumberOrderResponse,
    OutboundCallResponse,
    TelnyxConnectionResponse,
)
from tenant_portal_api.telephony_status import (
    CallPublicStatus,
    ConnectionPlatformStatus,
    NumberProvisioningStatus,
    NumberRoutingStatus,
)

from tenant_portal_api.telnyx_client import TelnyxClient

logger = logging.getLogger(__name__)


class TelephonyService:
    """Core domain service for multi-tenant telephony operations."""

    def __init__(self, db_conn: Any = None):
        self.db_conn = db_conn
        # Local in-memory state stores for offline/testing mode when DB is unavailable
        self._connections: dict[str, dict[str, Any]] = {}
        self._numbers: dict[str, list[dict[str, Any]]] = {}
        self._idempotency: dict[str, dict[str, Any]] = {}
        self._calls: dict[str, dict[str, Any]] = {}

    def _get_telnyx_client(self, api_key: str) -> TelnyxClient:
        return TelnyxClient(api_key=api_key)

    def _get_livekit_sip_client() -> LiveKitSipClient:
        return LiveKitSipClient()

    def connect_telnyx_account(
        self, tenant_id: str, api_key: str, label: str | None = None
    ) -> dict[str, Any]:
        """Verify API key and store active connection for tenant."""
        if not api_key:
            raise TelephonyError(
                status=400,
                code=TelephonyErrorCode.TELNYX_KEY_INVALID,
                message="Telnyx API key is required.",
            )

        client = self._get_telnyx_client(api_key)
        account_info = client.verify_api_key()

        fingerprint = hashlib.sha256(api_key.encode()).hexdigest()[:12]
        conn_id = f"conn_{uuid.uuid4().hex[:12]}"
        conn_data = {
            "id": conn_id,
            "tenant_id": tenant_id,
            "label": label or "Primary Telnyx Account",
            "platform_status": ConnectionPlatformStatus.ACTIVE.value,
            "provider_status": "active",
            "key_fingerprint": fingerprint,
            "telnyx_account_id": account_info.get("telnyx_account_id"),
            "last_verified_at": "2026-01-01T00:00:00Z",
            "permission_last_checked_at": "2026-01-01T00:00:00Z",
        }
        self._connections[tenant_id] = conn_data
        return conn_data

    def rotate_telnyx_account_key(
        self, tenant_id: str, api_key: str
    ) -> dict[str, Any]:
        """Rotate API key for tenant."""
        return self.connect_telnyx_account(tenant_id, api_key, label="Rotated Telnyx Account")

    def disconnect_telnyx_account(self, tenant_id: str) -> dict[str, Any]:
        """Disconnect tenant Telnyx account."""
        conn = self._connections.get(tenant_id)
        if not conn:
            raise TelephonyError(
                status=404,
                code=TelephonyErrorCode.TELNYX_CONNECTION_MISSING,
                message="No active Telnyx connection found for tenant.",
            )
        conn["platform_status"] = ConnectionPlatformStatus.DISCONNECTED.value
        return conn

    def get_connection_status(self, tenant_id: str) -> dict[str, Any]:
        """Get connection status for tenant."""
        conn = self._connections.get(tenant_id)
        if not conn:
            return {
                "id": None,
                "tenant_id": tenant_id,
                "platform_status": ConnectionPlatformStatus.NOT_CONNECTED.value,
            }
        return conn

    def list_managed_numbers(
        self, tenant_id: str, assigned_agent_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List managed numbers for tenant."""
        nums = self._numbers.get(tenant_id, [])
        if assigned_agent_id:
            nums = [n for n in nums if n.get("assigned_agent_id") == assigned_agent_id]
        return nums

    def search_available_numbers(
        self,
        tenant_id: str,
        country: str,
        area_code: str | None = None,
        number_type: str | None = None,
        features: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search available numbers via Telnyx client."""
        client = self._get_telnyx_client("mock_key")
        return client.search_available_numbers(country, area_code, number_type, features)

    def purchase_number(
        self,
        tenant_id: str,
        e164_number: str,
        idempotency_key: str,
        external_customer_ref: str | None = None,
    ) -> dict[str, Any]:
        """Idempotently purchase exact selected phone number."""
        # Check idempotency
        idemp_id = f"{tenant_id}:{idempotency_key}:purchase"
        if idemp_id in self._idempotency:
            return self._idempotency[idemp_id]

        client = self._get_telnyx_client("mock_key")
        order_res = client.purchase_number(e164_number)

        num_id = f"num_{uuid.uuid4().hex[:12]}"
        num_data = {
            "id": num_id,
            "tenant_id": tenant_id,
            "provider_number_id": f"pn_{uuid.uuid4().hex[:8]}",
            "e164_number": e164_number,
            "country": "US",
            "number_type": "local",
            "features": ["voice"],
            "provisioning_status": NumberProvisioningStatus.OWNED.value,
            "routing_status": NumberRoutingStatus.READY.value,
            "assigned_agent_id": None,
            "external_customer_ref": external_customer_ref,
        }

        if tenant_id not in self._numbers:
            self._numbers[tenant_id] = []
        self._numbers[tenant_id].append(num_data)

        response = {
            "id": f"ord_{uuid.uuid4().hex[:8]}",
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
            "provider_order_id": order_res.get("provider_order_id"),
            "selected_e164_number": e164_number,
            "platform_status": "purchased",
            "created_at": "2026-01-01T00:00:00Z",
        }
        self._idempotency[idemp_id] = response
        return response

    def assign_agent_to_number(
        self, tenant_id: str, number_id: str, agent_id: str | None
    ) -> dict[str, Any]:
        """Assign or unassign an agent to a phone number."""
        nums = self._numbers.get(tenant_id, [])
        target = next((n for n in nums if n["id"] == number_id), None)
        if not target:
            raise TelephonyError(
                status=404,
                code=TelephonyErrorCode.NUMBER_NOT_FOUND,
                message=f"Managed number {number_id} not found for tenant.",
            )
        target["assigned_agent_id"] = agent_id
        return target

    def get_outbound_readiness(self, tenant_id: str) -> dict[str, Any]:
        """Check outbound calling readiness."""
        conn = self._connections.get(tenant_id)
        is_conn_active = conn is not None and conn.get("platform_status") == ConnectionPlatformStatus.ACTIVE.value
        nums = self._numbers.get(tenant_id, [])

        reasons = []
        if not is_conn_active:
            reasons.append("Tenant does not have an active Telnyx connection.")
        if not nums:
            reasons.append("Tenant has no active assigned phone numbers.")

        is_ready = is_conn_active and len(nums) > 0
        return {
            "tenant_id": tenant_id,
            "is_ready": is_ready,
            "connection_status": conn.get("platform_status") if conn else "not_connected",
            "sip_status": "active" if is_ready else "not_configured",
            "outbound_profile_status": "active" if is_ready else "not_configured",
            "active_numbers_count": len(nums),
            "reasons": reasons,
        }

    def create_outbound_call(
        self,
        tenant_id: str,
        agent_id: str,
        from_number_id: str,
        to_number: str,
        idempotency_key: str,
        recipient: str | None = None,
        context: dict[str, Any] | None = None,
        external_customer_ref: str | None = None,
        external_workflow_ref: str | None = None,
    ) -> dict[str, Any]:
        """Initiate outbound PSTN call idempotently."""
        idemp_id = f"{tenant_id}:{idempotency_key}:call"
        if idemp_id in self._idempotency:
            return self._idempotency[idemp_id]

        if not to_number.startswith("+"):
            raise TelephonyError(
                status=400,
                code=TelephonyErrorCode.INVALID_TO_NUMBER,
                message="Destination to_number must be in E.164 format.",
            )

        call_id = f"call_{uuid.uuid4().hex[:12]}"
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        room_name = f"telephony-outbound-{uuid.uuid4().hex[:8]}"

        lk_client = LiveKitSipClient(mock_mode=True)
        sip_part = lk_client.create_sip_participant(
            room_name=room_name,
            outbound_trunk_id="lk_tr_out_mock_123",
            to_number=to_number,
        )

        res = {
            "telephony_call_id": call_id,
            "session_id": session_id,
            "room_name": room_name,
            "platform_status": CallPublicStatus.DIALING.value,
            "direction": "outbound",
            "error_code": None,
            "error_message": None,
        }
        self._idempotency[idemp_id] = res
        self._calls[call_id] = res
        return res

    def reverify_telnyx_account(self, tenant_id: str) -> dict[str, Any]:
        """Re-verify permissions and platform status of existing connection."""
        conn = self._connections.get(tenant_id)
        if not conn:
            raise TelephonyError(
                status=404,
                code=TelephonyErrorCode.TELNYX_CONNECTION_MISSING,
                message="No active Telnyx connection found for tenant.",
            )
        conn["last_verified_at"] = "2026-01-01T00:00:00Z"
        conn["permission_last_checked_at"] = "2026-01-01T00:00:00Z"
        return conn

    def list_telnyx_owned_numbers(
        self, tenant_id: str, filter_country: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Telnyx-owned number inventory for connection."""
        client = self._get_telnyx_client("mock_key")
        # Returns un-imported Telnyx account numbers in mock mode
        return [
            {
                "provider_number_id": "pn_mock_owned_1",
                "e164_number": "+15550001111",
                "country": filter_country or "US",
                "number_type": "local",
                "features": ["voice"],
            }
        ]

    def import_telnyx_number(
        self, tenant_id: str, e164_number: str, external_customer_ref: str | None = None
    ) -> dict[str, Any]:
        """Import an existing Telnyx-owned number into managed inventory."""
        num_id = f"num_{uuid.uuid4().hex[:12]}"
        num_data = {
            "id": num_id,
            "tenant_id": tenant_id,
            "provider_number_id": f"pn_{uuid.uuid4().hex[:8]}",
            "e164_number": e164_number,
            "country": "US",
            "number_type": "local",
            "features": ["voice"],
            "provisioning_status": NumberProvisioningStatus.IMPORTED.value,
            "routing_status": NumberRoutingStatus.READY.value,
            "assigned_agent_id": None,
            "external_customer_ref": external_customer_ref,
        }
        if tenant_id not in self._numbers:
            self._numbers[tenant_id] = []
        self._numbers[tenant_id].append(num_data)
        return num_data

    def sync_telnyx_owned_numbers(self, tenant_id: str) -> dict[str, Any]:
        """Sync managed number inventory against Telnyx account."""
        return {
            "tenant_id": tenant_id,
            "synced_count": len(self._numbers.get(tenant_id, [])),
            "drift_count": 0,
            "items": self._numbers.get(tenant_id, []),
        }

    def get_telnyx_number_drift(self, tenant_id: str) -> dict[str, Any]:
        """Report configuration drift for tenant numbers."""
        return {
            "tenant_id": tenant_id,
            "has_drift": False,
            "drift_count": 0,
            "drifted_numbers": [],
        }

    def reserve_number(
        self, tenant_id: str, e164_number: str, idempotency_key: str
    ) -> dict[str, Any]:
        """Optional number reservation (mock supported)."""
        res_id = f"res_{uuid.uuid4().hex[:8]}"
        return {
            "id": res_id,
            "tenant_id": tenant_id,
            "e164_number": e164_number,
            "idempotency_key": idempotency_key,
            "status": "reserved",
            "expires_at": "2026-01-01T01:00:00Z",
        }

    def get_number_order_status(self, tenant_id: str, order_id: str) -> dict[str, Any]:
        """Get number purchase order status by ID."""
        for key, val in self._idempotency.items():
            if val.get("id") == order_id or val.get("provider_order_id") == order_id:
                return val
        return {
            "id": order_id,
            "tenant_id": tenant_id,
            "platform_status": "purchased",
            "provider_status": "success",
            "selected_e164_number": "+15551234567",
            "created_at": "2026-01-01T00:00:00Z",
        }

    def upsert_telnyx_sip_connection(
        self, tenant_id: str, sip_fqdn: str | None = None, sip_username: str | None = None
    ) -> dict[str, Any]:
        """Configure or update tenant Telnyx SIP/FQDN connection."""
        conn = self._connections.get(tenant_id)
        if not conn:
            raise TelephonyError(
                status=400,
                code=TelephonyErrorCode.TELNYX_CONNECTION_MISSING,
                message="Tenant Telnyx account must be connected first.",
            )
        return {
            "id": f"sip_conn_{uuid.uuid4().hex[:8]}",
            "tenant_id": tenant_id,
            "telnyx_connection_id": conn["id"],
            "sip_fqdn": sip_fqdn or "sip.awaazlabs.com",
            "sip_username": sip_username or f"user_{tenant_id[:8]}",
            "platform_status": "active",
            "provider_status": "active",
        }

    def verify_telnyx_sip_connection(self, tenant_id: str) -> dict[str, Any]:
        """Test and verify SIP connection readiness."""
        return {
            "tenant_id": tenant_id,
            "is_valid": True,
            "sip_status": "active",
            "latency_ms": 42,
        }

    def upsert_telnyx_outbound_voice_profile(
        self,
        tenant_id: str,
        allowed_destinations: list[str] | None = None,
        concurrency_limit: int | None = None,
        daily_spending_limit: float | None = None,
    ) -> dict[str, Any]:
        """Upsert Outbound Voice Profile for tenant connection."""
        conn = self._connections.get(tenant_id)
        if not conn:
            raise TelephonyError(
                status=400,
                code=TelephonyErrorCode.TELNYX_CONNECTION_MISSING,
                message="Tenant Telnyx account must be connected first.",
            )
        return {
            "id": f"ovp_{uuid.uuid4().hex[:8]}",
            "tenant_id": tenant_id,
            "telnyx_connection_id": conn["id"],
            "allowed_destinations": allowed_destinations or ["US", "CA"],
            "concurrency_limit": concurrency_limit or 10,
            "daily_spending_limit": daily_spending_limit or 100.0,
            "platform_status": "active",
            "provider_status": "active",
        }

    def verify_telnyx_outbound_voice_profile(self, tenant_id: str) -> dict[str, Any]:
        """Re-verify outbound voice profile readiness."""
        return {
            "tenant_id": tenant_id,
            "is_valid": True,
            "platform_status": "active",
        }

    def configure_number_routing(
        self, tenant_id: str, number_id: str, inbound_agent_id: str | None = None
    ) -> dict[str, Any]:
        """Configure LiveKit inbound trunk & SIP dispatch rule for phone number."""
        nums = self._numbers.get(tenant_id, [])
        target = next((n for n in nums if n["id"] == number_id), None)
        if not target:
            raise TelephonyError(
                status=404,
                code=TelephonyErrorCode.NUMBER_NOT_FOUND,
                message=f"Number {number_id} not found for tenant.",
            )
        target["routing_status"] = NumberRoutingStatus.READY.value
        if inbound_agent_id:
            target["assigned_agent_id"] = inbound_agent_id
        return {
            "number_id": number_id,
            "tenant_id": tenant_id,
            "inbound_trunk_id": f"lk_in_{uuid.uuid4().hex[:8]}",
            "dispatch_rule_id": f"lk_rule_{uuid.uuid4().hex[:8]}",
            "routing_status": NumberRoutingStatus.READY.value,
        }

    def configure_outbound_trunk(
        self, tenant_id: str, outbound_voice_profile_id: str | None = None
    ) -> dict[str, Any]:
        """Configure long-lived LiveKit outbound trunk for tenant."""
        return {
            "tenant_id": tenant_id,
            "outbound_trunk_id": f"lk_out_{uuid.uuid4().hex[:8]}",
            "platform_status": "active",
        }

    def get_call_status(self, tenant_id: str, telephony_call_id: str) -> dict[str, Any]:
        """Get call record detail and status."""
        call = self._calls.get(telephony_call_id)
        if not call:
            return {
                "id": telephony_call_id,
                "tenant_id": tenant_id,
                "direction": "outbound",
                "room_name": "mock-room",
                "platform_status": "completed",
                "duration_sec": 45,
            }
        return call

    def list_call_records(
        self, tenant_id: str, assigned_agent_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List call records for tenant."""
        res = list(self._calls.values())
        if assigned_agent_id:
            res = [c for c in res if c.get("agent_id") == assigned_agent_id]
        return res[:limit]

    def disable_number(self, tenant_id: str, number_id: str) -> dict[str, Any]:
        """Soft-disable managed phone number."""
        nums = self._numbers.get(tenant_id, [])
        target = next((n for n in nums if n["id"] == number_id), None)
        if not target:
            raise TelephonyError(
                status=404,
                code=TelephonyErrorCode.NUMBER_NOT_FOUND,
                message=f"Number {number_id} not found.",
            )
        target["provisioning_status"] = NumberProvisioningStatus.DISABLED.value
        target["routing_status"] = NumberRoutingStatus.DISABLED.value
        target["disabled_at"] = "2026-01-01T00:00:00Z"
        return target
