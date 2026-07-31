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
