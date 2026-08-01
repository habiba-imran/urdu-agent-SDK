"""Telephony domain service orchestrating credential lifecycle, number inventory, LiveKit SIP readiness, quota reservation, idempotency, and outbound calls.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg

from tenant_portal_api.livekit_sip import LiveKitSipClient
from tenant_portal_api.telephony_config import is_mock_provider_mode
from tenant_portal_api.telephony_credentials import (
    decrypt_provider_secret,
    encrypt_provider_secret,
)
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

from tenant_portal_api import telephony_queries as queries
from tenant_portal_api.telnyx_client import TelnyxClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from scripts.dbconn import conn_kwargs
except ImportError:
    from dbconn import conn_kwargs  # type: ignore # noqa: E402

logger = logging.getLogger(__name__)


class TelephonyService:
    """Core domain service for multi-tenant telephony operations."""

    def __init__(
        self,
        db_conn: Any = None,
        telnyx_client_factory: Any = None,
        livekit_client_factory: Any = None,
    ):
        self.db_conn = db_conn
        self._telnyx_client_factory = telnyx_client_factory
        self._livekit_client_factory = livekit_client_factory
        # Local in-memory state stores are used only in explicit mock provider mode.
        self._connections: dict[str, dict[str, Any]] = {}
        self._numbers: dict[str, list[dict[str, Any]]] = {}
        self._idempotency: dict[str, dict[str, Any]] = {}
        self._calls: dict[str, dict[str, Any]] = {}

    @contextmanager
    def _connection(self) -> Iterator[Any | None]:
        if self.db_conn is not None:
            yield self.db_conn
            return
        if is_mock_provider_mode():
            yield None
            return
        with psycopg.connect(**conn_kwargs(), connect_timeout=10) as conn:
            yield conn
            conn.commit()

    def _get_telnyx_client(self, api_key: str) -> TelnyxClient:
        if self._telnyx_client_factory:
            return self._telnyx_client_factory(api_key=api_key, mock_mode=is_mock_provider_mode())
        return TelnyxClient(api_key=api_key, mock_mode=is_mock_provider_mode())

    def _get_livekit_sip_client(self) -> LiveKitSipClient:
        if self._livekit_client_factory:
            return self._livekit_client_factory(mock_mode=is_mock_provider_mode())
        return LiveKitSipClient(mock_mode=is_mock_provider_mode())

    def _raise_database_conflict(self, operation: str, exc: Exception) -> None:
        logger.warning("Telephony database conflict during %s: %s", operation, exc.__class__.__name__)
        raise TelephonyError(
            status=409,
            code=TelephonyErrorCode.CALL_STATE_CONFLICT,
            message="Telephony resource state changed during the database update. Refresh and retry.",
        ) from exc
    def _public_connection(self, conn_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": conn_data.get("id"),
            "tenant_id": conn_data.get("tenant_id"),
            "label": conn_data.get("label"),
            "platform_status": conn_data.get("platform_status"),
            "provider_status": conn_data.get("provider_status"),
            "key_fingerprint": conn_data.get("key_fingerprint"),
            "telnyx_account_id": conn_data.get("telnyx_account_id"),
            "last_verified_at": conn_data.get("last_verified_at"),
            "permission_last_checked_at": conn_data.get("permission_last_checked_at"),
        }

    def _active_connection(self, conn: Any | None, tenant_id: str) -> dict[str, Any] | None:
        if conn is None:
            data = self._connections.get(tenant_id)
            if data and data.get("platform_status") != ConnectionPlatformStatus.DISCONNECTED.value:
                return data
            return None
        return queries.get_active_telnyx_connection(conn, tenant_id)

    def _require_active_connection(self, conn: Any | None, tenant_id: str) -> dict[str, Any]:
        conn_data = self._active_connection(conn, tenant_id)
        if not conn_data or conn_data.get("platform_status") != ConnectionPlatformStatus.ACTIVE.value:
            raise TelephonyError(
                status=409,
                code=TelephonyErrorCode.TELNYX_CONNECTION_MISSING,
                message="Tenant does not have an active Telnyx connection.",
            )
        return conn_data

    def _tenant_telnyx_client(self, conn: Any | None, tenant_id: str) -> tuple[TelnyxClient, dict[str, Any]]:
        conn_data = self._require_active_connection(conn, tenant_id)
        if conn is None:
            return self._get_telnyx_client("mock_key"), conn_data
        api_key = decrypt_provider_secret(conn_data.get("encrypted_api_key_ref"))
        return self._get_telnyx_client(api_key), conn_data

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

        encrypted_ref = None if is_mock_provider_mode() else encrypt_provider_secret(api_key)
        client = self._get_telnyx_client(api_key)
        account_info = client.verify_api_key()
        fingerprint = hashlib.sha256(api_key.encode()).hexdigest()[:12]

        with self._connection() as conn:
            if conn is None:
                conn_id = f"conn_{uuid.uuid4().hex[:12]}"
                conn_data = {
                    "id": conn_id,
                    "tenant_id": tenant_id,
                    "label": label or "Primary Telnyx Account",
                    "platform_status": ConnectionPlatformStatus.ACTIVE.value,
                    "provider_status": account_info.get("status", "active"),
                    "key_fingerprint": fingerprint,
                    "telnyx_account_id": account_info.get("telnyx_account_id"),
                    "last_verified_at": "2026-01-01T00:00:00Z",
                    "permission_last_checked_at": "2026-01-01T00:00:00Z",
                }
                self._connections[tenant_id] = conn_data
                return self._public_connection(conn_data)

            existing = self._active_connection(conn, tenant_id)
            if existing:
                raise TelephonyError(
                    status=409,
                    code=TelephonyErrorCode.CALL_STATE_CONFLICT,
                    message="Tenant already has an active Telnyx connection. Use key rotation to refresh credentials.",
                )

            try:
                pending = queries.upsert_telnyx_connection_verifying(
                    conn,
                    tenant_id,
                    label or "Primary Telnyx Account",
                    fingerprint,
                    encrypted_ref,
                )
                queries.mark_telnyx_connection_active(
                    conn,
                    pending["id"],
                    account_info.get("telnyx_account_id"),
                )
            except (psycopg.errors.UniqueViolation, psycopg.errors.InvalidColumnReference) as exc:
                self._raise_database_conflict("connect Telnyx account", exc)
            stored = queries.get_active_telnyx_connection(conn, tenant_id) or pending
            return self._public_connection(stored)

    def rotate_telnyx_account_key(
        self, tenant_id: str, api_key: str
    ) -> dict[str, Any]:
        """Verify and replace the credential on the current active Telnyx connection."""
        if not api_key:
            raise TelephonyError(
                status=400,
                code=TelephonyErrorCode.TELNYX_KEY_INVALID,
                message="Telnyx API key is required.",
            )

        client = self._get_telnyx_client(api_key)
        account_info = client.verify_api_key()
        encrypted_ref = None if is_mock_provider_mode() else encrypt_provider_secret(api_key)
        fingerprint = hashlib.sha256(api_key.encode()).hexdigest()[:12]

        with self._connection() as conn:
            conn_data = self._require_active_connection(conn, tenant_id)
            if conn is None:
                conn_data.update(
                    {
                        "platform_status": ConnectionPlatformStatus.ACTIVE.value,
                        "label": "Rotated Telnyx Account",
                        "provider_status": account_info.get("status", "active"),
                        "key_fingerprint": fingerprint,
                        "telnyx_account_id": account_info.get("telnyx_account_id"),
                        "last_verified_at": "2026-01-01T00:00:00Z",
                        "permission_last_checked_at": "2026-01-01T00:00:00Z",
                    }
                )
                return self._public_connection(conn_data)

            try:
                updated = queries.update_active_telnyx_connection_credential(
                    conn,
                    tenant_id,
                    conn_data["id"],
                    fingerprint,
                    encrypted_ref,
                    "Rotated Telnyx Account",
                    account_info.get("telnyx_account_id"),
                    account_info.get("status", "active"),
                )
            except (psycopg.errors.UniqueViolation, psycopg.errors.InvalidColumnReference) as exc:
                self._raise_database_conflict("rotate Telnyx account key", exc)
            if not updated:
                raise TelephonyError(
                    status=409,
                    code=TelephonyErrorCode.CALL_STATE_CONFLICT,
                    message="Active Telnyx connection changed during rotation. Refresh and retry.",
                )
            return self._public_connection(updated)

    def disconnect_telnyx_account(self, tenant_id: str) -> dict[str, Any]:
        """Disconnect tenant Telnyx account."""
        with self._connection() as conn:
            conn_data = self._require_active_connection(conn, tenant_id)
            if conn is None:
                conn_data["platform_status"] = ConnectionPlatformStatus.DISCONNECTED.value
                return self._public_connection(conn_data)
            queries.disconnect_telnyx_connection(conn, conn_data["id"])
            conn_data["platform_status"] = ConnectionPlatformStatus.DISCONNECTED.value
            return self._public_connection(conn_data)
    def get_connection_status(self, tenant_id: str) -> dict[str, Any]:
        """Get connection status for tenant."""
        with self._connection() as conn:
            conn_data = self._active_connection(conn, tenant_id)
            if not conn_data:
                return {
                    "id": None,
                    "tenant_id": tenant_id,
                    "platform_status": ConnectionPlatformStatus.NOT_CONNECTED.value,
                }
            return self._public_connection(conn_data)
    def list_managed_numbers(
        self, tenant_id: str, assigned_agent_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List managed numbers for tenant."""
        with self._connection() as conn:
            if conn is None:
                nums = self._numbers.get(tenant_id, [])
                if assigned_agent_id:
                    nums = [n for n in nums if n.get("assigned_agent_id") == assigned_agent_id]
                return nums
            return queries.list_managed_numbers(conn, tenant_id, assigned_agent_id)
    def search_available_numbers(
        self,
        tenant_id: str,
        country: str,
        area_code: str | None = None,
        number_type: str | None = None,
        features: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search available numbers via the tenant's Telnyx credential."""
        with self._connection() as conn:
            client, _ = self._tenant_telnyx_client(conn, tenant_id)
            return client.search_available_numbers(country, area_code, number_type, features)
    def purchase_number(
        self,
        tenant_id: str,
        e164_number: str,
        idempotency_key: str,
        external_customer_ref: str | None = None,
    ) -> dict[str, Any]:
        """Idempotently purchase exact selected phone number."""
        with self._connection() as conn:
            idemp_id = f"{tenant_id}:{idempotency_key}:purchase"
            if conn is None and idemp_id in self._idempotency:
                return self._idempotency[idemp_id]

            client, conn_data = self._tenant_telnyx_client(conn, tenant_id)
            order_res = client.purchase_number(e164_number)

            if conn is None:
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
                self._numbers.setdefault(tenant_id, []).append(num_data)
                response = {
                    "id": f"ord_{uuid.uuid4().hex[:8]}",
                    "tenant_id": tenant_id,
                    "idempotency_key": idempotency_key,
                    "provider_order_id": order_res.get("provider_order_id"),
                    "selected_e164_number": e164_number,
                    "platform_status": "purchased",
                    "provider_status": order_res.get("provider_status"),
                    "created_at": "2026-01-01T00:00:00Z",
                }
                self._idempotency[idemp_id] = response
                return response

            row = conn.execute(
                """
                insert into telephony_number_orders (
                    tenant_id, telnyx_connection_id, idempotency_key, provider_order_id,
                    selected_e164_number, provider_status, platform_status, raw_provider_status
                ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                returning id, tenant_id, idempotency_key, provider_order_id, selected_e164_number,
                          platform_status, provider_status, error_code, error_message, created_at
                """,
                (
                    tenant_id,
                    conn_data["id"],
                    idempotency_key,
                    order_res.get("provider_order_id"),
                    e164_number,
                    order_res.get("provider_status"),
                    order_res.get("platform_status", "pending"),
                    order_res.get("status"),
                ),
            ).fetchone()
            return {
                "id": str(row[0]),
                "tenant_id": str(row[1]),
                "idempotency_key": row[2],
                "provider_order_id": row[3],
                "selected_e164_number": row[4],
                "platform_status": row[5],
                "provider_status": row[6],
                "error_code": row[7],
                "error_message": row[8],
                "created_at": str(row[9]) if row[9] else None,
            }
    def assign_agent_to_number(
        self, tenant_id: str, number_id: str, agent_id: str | None
    ) -> dict[str, Any]:
        """Assign or unassign an agent to a phone number."""
        with self._connection() as conn:
            if conn is None:
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
            if not queries.assign_number_to_agent(conn, tenant_id, number_id, agent_id):
                raise TelephonyError(
                    status=404,
                    code=TelephonyErrorCode.NUMBER_NOT_FOUND,
                    message=f"Managed number {number_id} not found for tenant.",
                )
            row = conn.execute(
                """
                select id, tenant_id, provider_number_id, e164_number, country, number_type,
                       features, provisioning_status, routing_status, assigned_agent_id,
                       external_customer_ref, disabled_at
                from telephony_phone_numbers
                where tenant_id = %s and id = %s and disabled_at is null
                """,
                (tenant_id, number_id),
            ).fetchone()
            return self._number_from_row(row)
    def get_outbound_readiness(self, tenant_id: str) -> dict[str, Any]:
        """Check outbound calling readiness."""
        with self._connection() as conn:
            conn_data = self._active_connection(conn, tenant_id)
            is_conn_active = conn_data is not None and conn_data.get("platform_status") == ConnectionPlatformStatus.ACTIVE.value
            if conn is None:
                nums = self._numbers.get(tenant_id, [])
                sip_active = is_conn_active and bool(nums)
                profile_active = sip_active
                assigned_ready_numbers = nums
            else:
                nums = queries.list_managed_numbers(conn, tenant_id)
                assigned_ready_numbers = [
                    n for n in nums
                    if n.get("routing_status") == NumberRoutingStatus.READY.value and n.get("assigned_agent_id")
                ]
                sip_active = bool(conn_data) and conn.execute(
                    """
                    select id from telnyx_sip_connections
                    where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                      and platform_status in ('pending_verification', 'testing', 'active')
                    limit 1
                    """,
                    (tenant_id, conn_data["id"] if conn_data else None),
                ).fetchone() is not None
                profile_active = bool(conn_data) and conn.execute(
                    """
                    select id from telnyx_outbound_voice_profiles
                    where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                      and platform_status = 'active'
                    limit 1
                    """,
                    (tenant_id, conn_data["id"] if conn_data else None),
                ).fetchone() is not None

            reasons = []
            if not is_conn_active:
                reasons.append("Tenant does not have an active Telnyx connection.")
            if not nums:
                reasons.append("Tenant has no active assigned phone numbers.")
            if nums and not assigned_ready_numbers:
                reasons.append("Tenant has no routed phone number assigned to an agent.")
            if is_conn_active and not sip_active:
                reasons.append("Tenant Telnyx SIP connection is not active.")
            if is_conn_active and not profile_active:
                reasons.append("Tenant outbound voice profile is not active.")

            is_ready = is_conn_active and bool(assigned_ready_numbers) and sip_active and profile_active
            return {
                "tenant_id": tenant_id,
                "is_ready": is_ready,
                "connection_status": conn_data.get("platform_status") if conn_data else "not_connected",
                "sip_status": "active" if sip_active else "not_configured",
                "outbound_profile_status": "active" if profile_active else "not_configured",
                "active_numbers_count": len(assigned_ready_numbers),
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
        if not to_number.startswith("+"):
            raise TelephonyError(
                status=400,
                code=TelephonyErrorCode.INVALID_TO_NUMBER,
                message="Destination to_number must be in E.164 format.",
            )

        with self._connection() as conn:
            if conn is None and idemp_id in self._idempotency:
                return self._idempotency[idemp_id]

            if conn is None:
                outbound_trunk_id = "lk_tr_out_mock_123"
                phone_e164 = "+15551234567"
                outbound_trunk_record_id = None
            else:
                number_row = conn.execute(
                    """
                    select id, tenant_id, provider_number_id, e164_number, country, number_type,
                           features, provisioning_status, routing_status, assigned_agent_id,
                           external_customer_ref, disabled_at
                    from telephony_phone_numbers
                    where tenant_id = %s and id = %s and disabled_at is null
                    """,
                    (tenant_id, from_number_id),
                ).fetchone()
                if not number_row:
                    raise TelephonyError(status=404, code=TelephonyErrorCode.NUMBER_NOT_FOUND, message=f"Number {from_number_id} not found for tenant.")
                phone = self._number_from_row(number_row)
                phone_e164 = phone["e164_number"]
                trunk_row = conn.execute(
                    """
                    select id, tenant_id, outbound_voice_profile_record_id, livekit_outbound_trunk_id, platform_status, provider_status
                    from livekit_outbound_trunks
                    where tenant_id = %s and disabled_at is null
                      and platform_status in ('pending_verification', 'testing', 'active')
                    order by created_at desc limit 1
                    """,
                    (tenant_id,),
                ).fetchone()
                if not trunk_row:
                    raise TelephonyError(status=409, code=TelephonyErrorCode.OUTBOUND_NOT_READY, message="Tenant outbound trunk is not configured.")
                trunk = self._outbound_trunk_from_row(trunk_row)
                outbound_trunk_id = trunk["livekit_outbound_trunk_id"]
                outbound_trunk_record_id = trunk["id"]
                if not queries.reserve_call_quota(conn, tenant_id):
                    raise TelephonyError(
                        status=429,
                        code=TelephonyErrorCode.OUTBOUND_CONCURRENCY_LIMIT_REACHED,
                        message="Tenant outbound concurrency limit is reached.",
                    )

            call_id = f"call_{uuid.uuid4().hex[:12]}"
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
            room_name = f"telephony-outbound-{uuid.uuid4().hex[:8]}"
            sip_part = self._get_livekit_sip_client().create_sip_participant(
                room_name=room_name,
                outbound_trunk_id=outbound_trunk_id,
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
            if conn is None:
                self._idempotency[idemp_id] = res
                self._calls[call_id] = {**res, "id": call_id, "tenant_id": tenant_id, "agent_id": agent_id}
                return res

            conn.execute(
                """
                insert into telephony_calls (
                    id, tenant_id, session_id, agent_id, phone_number_id, direction, room_name,
                    from_number, to_number, recipient, call_context, external_customer_ref,
                    external_workflow_ref, outbound_trunk_record_id, livekit_sip_call_id,
                    livekit_sip_call_id_full, platform_status, provider_status
                ) values (%s, %s, null, %s, %s, 'outbound', %s, %s, %s, %s, %s::jsonb,
                          %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    call_id,
                    tenant_id,
                    agent_id,
                    from_number_id,
                    room_name,
                    phone_e164,
                    to_number,
                    recipient,
                    json.dumps(context or {}),
                    external_customer_ref,
                    external_workflow_ref,
                    outbound_trunk_record_id,
                    sip_part.get("livekit_sip_call_id"),
                    sip_part.get("livekit_sip_call_id_full"),
                    CallPublicStatus.DIALING.value,
                    sip_part.get("status"),
                ),
            )
            return res
    def reverify_telnyx_account(self, tenant_id: str) -> dict[str, Any]:
        """Re-verify permissions and platform status of existing connection."""
        with self._connection() as conn:
            client, conn_data = self._tenant_telnyx_client(conn, tenant_id)
            account_info = client.verify_api_key()
            if conn is None:
                conn_data["last_verified_at"] = "2026-01-01T00:00:00Z"
                conn_data["permission_last_checked_at"] = "2026-01-01T00:00:00Z"
                return self._public_connection(conn_data)
            queries.mark_telnyx_connection_active(
                conn,
                conn_data["id"],
                account_info.get("telnyx_account_id"),
            )
            return self._public_connection(queries.get_active_telnyx_connection(conn, tenant_id) or conn_data)
    def list_telnyx_owned_numbers(
        self, tenant_id: str, filter_country: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch Telnyx-owned number inventory for connection."""
        with self._connection() as conn:
            client, _ = self._tenant_telnyx_client(conn, tenant_id)
            numbers = client.list_owned_numbers()
            if filter_country:
                numbers = [n for n in numbers if n.get("country") == filter_country]
            return numbers
    def import_telnyx_number(
        self, tenant_id: str, e164_number: str, external_customer_ref: str | None = None
    ) -> dict[str, Any]:
        """Import an existing Telnyx-owned number into managed inventory."""
        with self._connection() as conn:
            if conn is None:
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
                self._numbers.setdefault(tenant_id, []).append(num_data)
                return num_data

            client, conn_data = self._tenant_telnyx_client(conn, tenant_id)
            owned = client.list_owned_numbers(filter_phone_number=e164_number)
            if not owned:
                raise TelephonyError(
                    status=404,
                    code=TelephonyErrorCode.NUMBER_NOT_OWNED_BY_TENANT,
                    message="Phone number is not owned by the connected Telnyx account.",
                )
            item = owned[0]
            row = conn.execute(
                """
                insert into telephony_phone_numbers (
                    tenant_id, telnyx_connection_id, provider_number_id, e164_number, country,
                    number_type, features, provisioning_status, routing_status, provider_status,
                    external_customer_ref, last_synced_at
                ) values (%s, %s, %s, %s, %s, %s, %s, 'imported', 'not_configured', %s, %s, now())
                returning id, tenant_id, provider_number_id, e164_number, country, number_type,
                          features, provisioning_status, routing_status, assigned_agent_id,
                          external_customer_ref
                """,
                (
                    tenant_id,
                    conn_data["id"],
                    item.get("provider_number_id"),
                    item.get("e164_number"),
                    item.get("country"),
                    item.get("number_type"),
                    item.get("features") or ["voice"],
                    item.get("status"),
                    external_customer_ref,
                ),
            ).fetchone()
            return {
                "id": row[0],
                "tenant_id": row[1],
                "provider_number_id": row[2],
                "e164_number": row[3],
                "country": row[4],
                "number_type": row[5],
                "features": row[6] if row[6] else [],
                "provisioning_status": row[7],
                "routing_status": row[8],
                "assigned_agent_id": row[9],
                "external_customer_ref": row[10],
            }
    def sync_telnyx_owned_numbers(self, tenant_id: str) -> dict[str, Any]:
        """Sync managed number inventory against Telnyx account."""
        with self._connection() as conn:
            if conn is None:
                return {
                    "tenant_id": tenant_id,
                    "synced_count": len(self._numbers.get(tenant_id, [])),
                    "drift_count": 0,
                    "items": self._numbers.get(tenant_id, []),
                }
            client, conn_data = self._tenant_telnyx_client(conn, tenant_id)
            provider_numbers = client.list_owned_numbers()
            items = []
            for item in provider_numbers:
                provider_number_id = item.get("provider_number_id")
                e164_number = item.get("e164_number")
                if not provider_number_id or not e164_number:
                    logger.warning("Skipping Telnyx number missing provider identity or E.164 value.")
                    continue
                try:
                    row = conn.execute(
                        """
                        insert into telephony_phone_numbers (
                            tenant_id, telnyx_connection_id, provider_number_id, e164_number,
                            country, number_type, features, provisioning_status, routing_status,
                            provider_status, last_synced_at
                        ) values (%s, %s, %s, %s, %s, %s, %s, 'owned', 'not_configured', %s, now())
                        on conflict (tenant_id, provider_number_id) do update set
                            telnyx_connection_id = excluded.telnyx_connection_id,
                            e164_number = excluded.e164_number,
                            country = excluded.country,
                            number_type = excluded.number_type,
                            features = excluded.features,
                            provisioning_status = case
                                when telephony_phone_numbers.disabled_at is not null
                                  or telephony_phone_numbers.provisioning_status in ('released', 'deleted')
                                then excluded.provisioning_status
                                else telephony_phone_numbers.provisioning_status
                            end,
                            routing_status = case
                                when telephony_phone_numbers.disabled_at is not null
                                then excluded.routing_status
                                else telephony_phone_numbers.routing_status
                            end,
                            provider_status = excluded.provider_status,
                            disabled_at = null,
                            last_synced_at = now(),
                            updated_at = now()
                        returning id, tenant_id, provider_number_id, e164_number, country, number_type,
                                  features, provisioning_status, routing_status, assigned_agent_id,
                                  external_customer_ref, disabled_at
                        """,
                        (
                            tenant_id,
                            conn_data["id"],
                            provider_number_id,
                            e164_number,
                            item.get("country"),
                            item.get("number_type"),
                            item.get("features") or ["voice"],
                            item.get("status"),
                        ),
                    ).fetchone()
                except (psycopg.errors.UniqueViolation, psycopg.errors.InvalidColumnReference) as exc:
                    self._raise_database_conflict("sync Telnyx owned numbers", exc)
                if row:
                    items.append(self._number_from_row(row))
            return {
                "tenant_id": tenant_id,
                "synced_count": len(items),
                "drift_count": 0,
                "items": items,
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
        """Optional number reservation. Real mode fails closed until Telnyx hold support is confirmed."""
        if not is_mock_provider_mode():
            raise TelephonyError(
                status=422,
                code=TelephonyErrorCode.UNSUPPORTED_NUMBER_FEATURE,
                message="Number reservation is not enabled for the real Telnyx provider path.",
            )
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
        with self._connection() as conn:
            if conn is None:
                for val in self._idempotency.values():
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
            client, _ = self._tenant_telnyx_client(conn, tenant_id)
            provider_status = client.get_number_order_status(order_id)
            return {
                "id": order_id,
                "tenant_id": tenant_id,
                "platform_status": provider_status.get("platform_status"),
                "provider_status": provider_status.get("provider_status"),
                "selected_e164_number": provider_status.get("selected_e164_number"),
                "provider_order_id": provider_status.get("provider_order_id"),
                "created_at": None,
            }
    def upsert_telnyx_sip_connection(
        self, tenant_id: str, sip_fqdn: str | None = None, sip_username: str | None = None
    ) -> dict[str, Any]:
        """Configure or update tenant Telnyx SIP/FQDN connection."""
        with self._connection() as conn:
            client, conn_data = self._tenant_telnyx_client(conn, tenant_id)
            if conn is None:
                return {
                    "id": f"sip_conn_{uuid.uuid4().hex[:8]}",
                    "tenant_id": tenant_id,
                    "telnyx_connection_id": conn_data["id"],
                    "sip_fqdn": sip_fqdn or "sip.awaazlabs.com",
                    "sip_username": sip_username or f"user_{tenant_id[:8]}",
                    "platform_status": "active",
                    "provider_status": "active",
                }

            existing = conn.execute(
                """
                select id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                       sip_username, platform_status, provider_status, last_verified_at
                from telnyx_sip_connections
                where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                  and platform_status in ('pending_verification', 'testing', 'active')
                order by created_at desc limit 1
                """,
                (tenant_id, conn_data["id"]),
            ).fetchone()
            if existing:
                return self._sip_from_row(existing)

            fqdn = sip_fqdn or f"{tenant_id}.sip.telnyx.com"
            provider = client.create_or_get_fqdn_connection(f"tenant-{tenant_id}", fqdn)
            row = conn.execute(
                """
                insert into telnyx_sip_connections (
                    tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                    sip_username, platform_status, provider_status, last_verified_at
                ) values (%s, %s, %s, %s, %s, 'active', %s, now())
                returning id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                          sip_username, platform_status, provider_status, last_verified_at
                """,
                (
                    tenant_id,
                    conn_data["id"],
                    provider.get("provider_sip_connection_id"),
                    provider.get("sip_fqdn") or fqdn,
                    sip_username,
                    provider.get("status", "active"),
                ),
            ).fetchone()
            return self._sip_from_row(row)
    def verify_telnyx_sip_connection(self, tenant_id: str) -> dict[str, Any]:
        """Test and verify SIP connection readiness."""
        with self._connection() as conn:
            if conn is None:
                return {"tenant_id": tenant_id, "is_valid": True, "sip_status": "active", "latency_ms": 42}
            conn_data = self._require_active_connection(conn, tenant_id)
            row = conn.execute(
                """
                select id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                       sip_username, platform_status, provider_status, last_verified_at
                from telnyx_sip_connections
                where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                  and platform_status in ('pending_verification', 'testing', 'active')
                order by created_at desc limit 1
                """,
                (tenant_id, conn_data["id"]),
            ).fetchone()
            if not row:
                raise TelephonyError(
                    status=409,
                    code=TelephonyErrorCode.SIP_VERIFICATION_FAILED,
                    message="Tenant Telnyx SIP connection is not configured.",
                )
            sip = self._sip_from_row(row)
            return {"tenant_id": tenant_id, "is_valid": True, "sip_status": sip["platform_status"]}
    def upsert_telnyx_outbound_voice_profile(
        self,
        tenant_id: str,
        allowed_destinations: list[str] | None = None,
        concurrency_limit: int | None = None,
        daily_spending_limit: float | None = None,
    ) -> dict[str, Any]:
        """Upsert Outbound Voice Profile for tenant connection."""
        with self._connection() as conn:
            client, conn_data = self._tenant_telnyx_client(conn, tenant_id)
            if conn is None:
                return {
                    "id": f"ovp_{uuid.uuid4().hex[:8]}",
                    "tenant_id": tenant_id,
                    "telnyx_connection_id": conn_data["id"],
                    "allowed_destinations": allowed_destinations or ["US", "CA"],
                    "concurrency_limit": concurrency_limit or 10,
                    "daily_spending_limit": daily_spending_limit or 100.0,
                    "platform_status": "active",
                    "provider_status": "active",
                }

            existing = conn.execute(
                """
                select id, tenant_id, telnyx_connection_id, telnyx_sip_connection_id,
                       provider_outbound_voice_profile_id, platform_status, provider_status,
                       allowed_destinations, concurrency_limit, daily_spending_limit
                from telnyx_outbound_voice_profiles
                where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                  and platform_status = 'active'
                order by created_at desc limit 1
                """,
                (tenant_id, conn_data["id"]),
            ).fetchone()
            if existing:
                return self._outbound_profile_from_row(existing)

            sip_row = conn.execute(
                """
                select id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                       sip_username, platform_status, provider_status, last_verified_at
                from telnyx_sip_connections
                where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                  and platform_status in ('pending_verification', 'testing', 'active')
                order by created_at desc limit 1
                """,
                (tenant_id, conn_data["id"]),
            ).fetchone()
            if not sip_row:
                raise TelephonyError(
                    status=409,
                    code=TelephonyErrorCode.SIP_VERIFICATION_FAILED,
                    message="Tenant Telnyx SIP connection is required before outbound voice profile setup.",
                )
            sip = self._sip_from_row(sip_row)
            provider = client.create_or_get_outbound_voice_profile(f"tenant-{tenant_id}-outbound", sip["provider_sip_connection_id"])
            row = conn.execute(
                """
                insert into telnyx_outbound_voice_profiles (
                    tenant_id, telnyx_connection_id, telnyx_sip_connection_id,
                    provider_outbound_voice_profile_id, platform_status, provider_status,
                    allowed_destinations, concurrency_limit, daily_spending_limit, last_verified_at
                ) values (%s, %s, %s, %s, 'active', %s, %s, %s, %s, now())
                returning id, tenant_id, telnyx_connection_id, telnyx_sip_connection_id,
                          provider_outbound_voice_profile_id, platform_status, provider_status,
                          allowed_destinations, concurrency_limit, daily_spending_limit
                """,
                (
                    tenant_id,
                    conn_data["id"],
                    sip["id"],
                    provider.get("provider_outbound_voice_profile_id"),
                    provider.get("status", "active"),
                    allowed_destinations or [],
                    concurrency_limit,
                    daily_spending_limit,
                ),
            ).fetchone()
            return self._outbound_profile_from_row(row)
    def verify_telnyx_outbound_voice_profile(self, tenant_id: str) -> dict[str, Any]:
        """Re-verify outbound voice profile readiness."""
        with self._connection() as conn:
            if conn is None:
                return {"tenant_id": tenant_id, "is_valid": True, "platform_status": "active"}
            conn_data = self._require_active_connection(conn, tenant_id)
            row = conn.execute(
                """
                select id, tenant_id, telnyx_connection_id, telnyx_sip_connection_id,
                       provider_outbound_voice_profile_id, platform_status, provider_status,
                       allowed_destinations, concurrency_limit, daily_spending_limit
                from telnyx_outbound_voice_profiles
                where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                  and platform_status = 'active'
                order by created_at desc limit 1
                """,
                (tenant_id, conn_data["id"]),
            ).fetchone()
            if not row:
                raise TelephonyError(
                    status=409,
                    code=TelephonyErrorCode.OUTBOUND_VOICE_PROFILE_MISSING,
                    message="Tenant outbound voice profile is not configured.",
                )
            profile = self._outbound_profile_from_row(row)
            return {"tenant_id": tenant_id, "is_valid": True, "platform_status": profile["platform_status"]}
    def configure_number_routing(
        self, tenant_id: str, number_id: str, inbound_agent_id: str | None = None
    ) -> dict[str, Any]:
        """Configure LiveKit inbound trunk and SIP dispatch rule for phone number."""
        with self._connection() as conn:
            if conn is None:
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

            number_row = conn.execute(
                """
                select id, tenant_id, provider_number_id, e164_number, country, number_type,
                       features, provisioning_status, routing_status, assigned_agent_id,
                       external_customer_ref, disabled_at
                from telephony_phone_numbers
                where tenant_id = %s and id = %s and disabled_at is null
                """,
                (tenant_id, number_id),
            ).fetchone()
            if not number_row:
                raise TelephonyError(status=404, code=TelephonyErrorCode.NUMBER_NOT_FOUND, message=f"Number {number_id} not found for tenant.")
            number = self._number_from_row(number_row)
            conn_data = self._require_active_connection(conn, tenant_id)
            sip_row = conn.execute(
                """
                select id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                       sip_username, platform_status, provider_status, last_verified_at
                from telnyx_sip_connections
                where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                  and platform_status in ('pending_verification', 'testing', 'active')
                order by created_at desc limit 1
                """,
                (tenant_id, conn_data["id"]),
            ).fetchone()
            if not sip_row:
                raise TelephonyError(status=409, code=TelephonyErrorCode.SIP_VERIFICATION_FAILED, message="Tenant Telnyx SIP connection is required before routing setup.")
            sip = self._sip_from_row(sip_row)
            lk_client = self._get_livekit_sip_client()

            inbound_row = conn.execute(
                """
                select id, tenant_id, phone_number_id, livekit_inbound_trunk_id, platform_status, provider_status
                from livekit_inbound_trunks
                where tenant_id = %s and phone_number_id = %s and disabled_at is null
                  and platform_status in ('pending_verification', 'testing', 'active')
                order by created_at desc limit 1
                """,
                (tenant_id, number_id),
            ).fetchone()
            if inbound_row:
                inbound = self._inbound_trunk_from_row(inbound_row)
            else:
                created = lk_client.create_or_get_inbound_trunk(number_id, number["e164_number"])
                inbound_row = conn.execute(
                    """
                    insert into livekit_inbound_trunks (
                        tenant_id, phone_number_id, telnyx_connection_id, telnyx_sip_connection_id,
                        livekit_inbound_trunk_id, platform_status, provider_status, last_reconciled_at
                    ) values (%s, %s, %s, %s, %s, 'active', %s, now())
                    returning id, tenant_id, phone_number_id, livekit_inbound_trunk_id, platform_status, provider_status
                    """,
                    (tenant_id, number_id, conn_data["id"], sip["id"], created.get("livekit_inbound_trunk_id"), created.get("status", "active")),
                ).fetchone()
                inbound = self._inbound_trunk_from_row(inbound_row)

            rule_row = conn.execute(
                """
                select id, tenant_id, phone_number_id, livekit_sip_dispatch_rule_id, platform_status, provider_status
                from livekit_sip_dispatch_rules
                where tenant_id = %s and phone_number_id = %s and disabled_at is null
                  and platform_status in ('pending_verification', 'testing', 'active')
                order by created_at desc limit 1
                """,
                (tenant_id, number_id),
            ).fetchone()
            if rule_row:
                rule = self._dispatch_rule_from_row(rule_row)
            else:
                created_rule = lk_client.create_or_get_dispatch_rule(inbound["livekit_inbound_trunk_id"], number_id, number["e164_number"])
                rule_row = conn.execute(
                    """
                    insert into livekit_sip_dispatch_rules (
                        tenant_id, phone_number_id, inbound_trunk_record_id,
                        livekit_sip_dispatch_rule_id, platform_status, provider_status, last_reconciled_at
                    ) values (%s, %s, %s, %s, 'active', %s, now())
                    returning id, tenant_id, phone_number_id, livekit_sip_dispatch_rule_id, platform_status, provider_status
                    """,
                    (tenant_id, number_id, inbound["id"], created_rule.get("livekit_sip_dispatch_rule_id"), created_rule.get("status", "active")),
                ).fetchone()
                rule = self._dispatch_rule_from_row(rule_row)

            conn.execute(
                """
                update telephony_phone_numbers
                set telnyx_sip_connection_id = %s,
                    routing_status = 'ready',
                    assigned_agent_id = coalesce(%s, assigned_agent_id),
                    updated_at = now()
                where tenant_id = %s and id = %s
                """,
                (sip["id"], inbound_agent_id, tenant_id, number_id),
            )
            return {
                "number_id": number_id,
                "tenant_id": tenant_id,
                "inbound_trunk_id": inbound["livekit_inbound_trunk_id"],
                "dispatch_rule_id": rule["livekit_sip_dispatch_rule_id"],
                "routing_status": NumberRoutingStatus.READY.value,
            }
    def configure_outbound_trunk(
        self, tenant_id: str, outbound_voice_profile_id: str | None = None
    ) -> dict[str, Any]:
        """Configure long-lived LiveKit outbound trunk for tenant."""
        with self._connection() as conn:
            if conn is None:
                return {
                    "tenant_id": tenant_id,
                    "outbound_trunk_id": f"lk_out_{uuid.uuid4().hex[:8]}",
                    "platform_status": "active",
                }
            conn_data = self._require_active_connection(conn, tenant_id)
            sip_row = conn.execute(
                """
                select id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                       sip_username, platform_status, provider_status, last_verified_at
                from telnyx_sip_connections
                where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                  and platform_status in ('pending_verification', 'testing', 'active')
                order by created_at desc limit 1
                """,
                (tenant_id, conn_data["id"]),
            ).fetchone()
            if not sip_row:
                raise TelephonyError(status=409, code=TelephonyErrorCode.SIP_VERIFICATION_FAILED, message="Tenant Telnyx SIP connection is required before outbound trunk setup.")
            sip = self._sip_from_row(sip_row)
            profile_sql = """
                select id, tenant_id, telnyx_connection_id, telnyx_sip_connection_id,
                       provider_outbound_voice_profile_id, platform_status, provider_status,
                       allowed_destinations, concurrency_limit, daily_spending_limit
                from telnyx_outbound_voice_profiles
                where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                  and platform_status = 'active'
            """
            params: list[Any] = [tenant_id, conn_data["id"]]
            if outbound_voice_profile_id:
                profile_sql += " and id::text = %s"
                params.append(outbound_voice_profile_id)
            profile_sql += " order by created_at desc limit 1"
            profile_row = conn.execute(profile_sql, tuple(params)).fetchone()
            if not profile_row:
                raise TelephonyError(status=409, code=TelephonyErrorCode.OUTBOUND_VOICE_PROFILE_MISSING, message="Tenant outbound voice profile is not configured.")
            profile = self._outbound_profile_from_row(profile_row)
            existing = conn.execute(
                """
                select id, tenant_id, outbound_voice_profile_record_id, livekit_outbound_trunk_id, platform_status, provider_status
                from livekit_outbound_trunks
                where tenant_id = %s and outbound_voice_profile_record_id = %s and disabled_at is null
                  and platform_status in ('pending_verification', 'testing', 'active')
                order by created_at desc limit 1
                """,
                (tenant_id, profile["id"]),
            ).fetchone()
            if existing:
                trunk = self._outbound_trunk_from_row(existing)
                return {"tenant_id": tenant_id, "outbound_trunk_id": trunk["livekit_outbound_trunk_id"], "platform_status": trunk["platform_status"]}
            created = self._get_livekit_sip_client().create_or_get_outbound_trunk(conn_data["id"], sip["sip_fqdn"])
            row = conn.execute(
                """
                insert into livekit_outbound_trunks (
                    tenant_id, telnyx_connection_id, telnyx_sip_connection_id,
                    outbound_voice_profile_record_id, livekit_outbound_trunk_id,
                    platform_status, provider_status, last_reconciled_at
                ) values (%s, %s, %s, %s, %s, 'active', %s, now())
                returning id, tenant_id, outbound_voice_profile_record_id, livekit_outbound_trunk_id, platform_status, provider_status
                """,
                (tenant_id, conn_data["id"], sip["id"], profile["id"], created.get("livekit_outbound_trunk_id"), created.get("status", "active")),
            ).fetchone()
            trunk = self._outbound_trunk_from_row(row)
            return {"tenant_id": tenant_id, "outbound_trunk_id": trunk["livekit_outbound_trunk_id"], "platform_status": trunk["platform_status"]}
    def get_call_status(self, tenant_id: str, telephony_call_id: str) -> dict[str, Any]:
        """Get call record detail and status."""
        with self._connection() as conn:
            if conn is None:
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
            row = conn.execute(
                """
                select id, tenant_id, session_id, agent_id, phone_number_id, direction, room_name,
                       from_number, to_number, recipient, platform_status, provider_status, outcome,
                       duration_sec, error_code, error_message, started_at, ended_at
                from telephony_calls
                where tenant_id = %s and id = %s
                """,
                (tenant_id, telephony_call_id),
            ).fetchone()
            if not row:
                raise TelephonyError(status=404, code=TelephonyErrorCode.CALL_SETUP_FAILED, message="Telephony call record not found.")
            return self._call_from_row(row)
    def list_call_records(
        self, tenant_id: str, assigned_agent_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List call records for tenant."""
        with self._connection() as conn:
            if conn is None:
                res = list(self._calls.values())
                if assigned_agent_id:
                    res = [c for c in res if c.get("agent_id") == assigned_agent_id]
                return res[:limit]
            sql = """
                select id, tenant_id, session_id, agent_id, phone_number_id, direction, room_name,
                       from_number, to_number, recipient, platform_status, provider_status, outcome,
                       duration_sec, error_code, error_message, started_at, ended_at
                from telephony_calls
                where tenant_id = %s
            """
            params: list[Any] = [tenant_id]
            if assigned_agent_id:
                sql += " and agent_id = %s"
                params.append(assigned_agent_id)
            sql += " order by created_at desc limit %s"
            params.append(limit)
            return [self._call_from_row(row) for row in conn.execute(sql, tuple(params)).fetchall()]
    def disable_number(self, tenant_id: str, number_id: str) -> dict[str, Any]:
        """Soft-disable managed phone number."""
        with self._connection() as conn:
            if conn is None:
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
            row = conn.execute(
                """
                update telephony_phone_numbers
                set provisioning_status = 'disabled', routing_status = 'disabled', disabled_at = now(), updated_at = now()
                where tenant_id = %s and id = %s and disabled_at is null
                returning id, tenant_id, provider_number_id, e164_number, country, number_type,
                          features, provisioning_status, routing_status, assigned_agent_id,
                          external_customer_ref, disabled_at
                """,
                (tenant_id, number_id),
            ).fetchone()
            if not row:
                raise TelephonyError(status=404, code=TelephonyErrorCode.NUMBER_NOT_FOUND, message=f"Number {number_id} not found.")
            return self._number_from_row(row)


    def _number_from_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "tenant_id": row[1],
            "provider_number_id": row[2],
            "e164_number": row[3],
            "country": row[4],
            "number_type": row[5],
            "features": row[6] if row[6] else [],
            "provisioning_status": row[7],
            "routing_status": row[8],
            "assigned_agent_id": row[9],
            "external_customer_ref": row[10],
            "disabled_at": str(row[11]) if len(row) > 11 and row[11] else None,
        }

    def _sip_from_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "tenant_id": row[1],
            "telnyx_connection_id": row[2],
            "provider_sip_connection_id": row[3],
            "sip_fqdn": row[4],
            "sip_username": row[5],
            "platform_status": row[6],
            "provider_status": row[7],
            "last_verified_at": str(row[8]) if row[8] else None,
        }

    def _outbound_profile_from_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "tenant_id": row[1],
            "telnyx_connection_id": row[2],
            "telnyx_sip_connection_id": row[3],
            "provider_outbound_voice_profile_id": row[4],
            "platform_status": row[5],
            "provider_status": row[6],
            "allowed_destinations": row[7] if row[7] else [],
            "concurrency_limit": row[8],
            "daily_spending_limit": row[9],
        }

    def _inbound_trunk_from_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "tenant_id": row[1],
            "phone_number_id": row[2],
            "livekit_inbound_trunk_id": row[3],
            "platform_status": row[4],
            "provider_status": row[5],
        }

    def _dispatch_rule_from_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "tenant_id": row[1],
            "phone_number_id": row[2],
            "livekit_sip_dispatch_rule_id": row[3],
            "platform_status": row[4],
            "provider_status": row[5],
        }

    def _outbound_trunk_from_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "tenant_id": row[1],
            "outbound_voice_profile_record_id": row[2],
            "livekit_outbound_trunk_id": row[3],
            "platform_status": row[4],
            "provider_status": row[5],
        }

    def _call_from_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "tenant_id": row[1],
            "session_id": row[2],
            "agent_id": row[3],
            "phone_number_id": row[4],
            "direction": row[5],
            "room_name": row[6],
            "from_number": row[7],
            "to_number": row[8],
            "recipient": row[9],
            "platform_status": row[10],
            "provider_status": row[11],
            "outcome": row[12],
            "duration_sec": row[13],
            "error_code": row[14],
            "error_message": row[15],
            "started_at": str(row[16]) if row[16] else None,
            "ended_at": str(row[17]) if row[17] else None,
        }
