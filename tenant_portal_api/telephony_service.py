"""Telephony domain service orchestrating credential lifecycle, number inventory, LiveKit SIP readiness, quota reservation, idempotency, and outbound calls.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import string
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg

from tenant_portal_api.livekit_sip import LiveKitSipClient
from tenant_portal_api.telephony_config import (
    is_mock_provider_mode,
    require_livekit_sip_uri,
    telnyx_sip_outbound_address,
)
from tenant_portal_api.telephony_credentials import (
    decrypt_provider_secret,
    encrypt_provider_secret,
)
from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode
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
        purchase_reconcile_attempts: int = 3,
        purchase_reconcile_delay_sec: float = 0.35,
    ):
        self.db_conn = db_conn
        self._telnyx_client_factory = telnyx_client_factory
        self._livekit_client_factory = livekit_client_factory
        self._purchase_reconcile_attempts = max(1, purchase_reconcile_attempts)
        self._purchase_reconcile_delay_sec = max(0.0, purchase_reconcile_delay_sec)
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
        with psycopg.connect(**conn_kwargs(), connect_timeout=3) as conn:
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

    def _default_sip_username(self, tenant_id: str) -> str:
        normalized_tenant = "".join(ch for ch in str(tenant_id) if ch.isalnum()).lower()
        suffix = (normalized_tenant or uuid.uuid4().hex)[:16]
        return f"tenant{suffix}"

    def _normalize_sip_username(self, tenant_id: str, value: str | None) -> str:
        normalized = "".join(ch for ch in str(value or "") if ch.isalnum()).lower()
        if normalized:
            return normalized[:24]
        return self._default_sip_username(tenant_id)

    def _generate_sip_secret(self) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(24))

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

    def _eligible_outbound_trunk_numbers(self, conn: Any, tenant_id: str, telnyx_connection_id: str) -> list[str]:
        rows = conn.execute(
            """
            select distinct e164_number
            from telephony_phone_numbers
            where tenant_id = %s
              and telnyx_connection_id = %s
              and provider_number_id is not null
              and disabled_at is null
              and deleted_at is null
              and provisioning_status in ('owned', 'active')
              and e164_number ~ '^\\+[1-9][0-9]{7,14}$'
            order by e164_number
            """,
            (tenant_id, telnyx_connection_id),
        ).fetchall()
        return [row[0] for row in rows if row and row[0]]

    def _assert_number_bound_to_agent(
        self,
        phone: dict[str, Any],
        agent_id: str,
        require_ready_routing: bool = True,
    ) -> None:
        assigned_agent_id = str(phone.get("assigned_agent_id")) if phone.get("assigned_agent_id") else None
        if not assigned_agent_id:
            raise TelephonyError(
                status=409,
                code=TelephonyErrorCode.NUMBER_NOT_ASSIGNED,
                message="Phone number is not assigned to an agent.",
            )
        if str(assigned_agent_id) != str(agent_id):
            raise TelephonyError(
                status=409,
                code=TelephonyErrorCode.NUMBER_NOT_ASSIGNED,
                message="Phone number is assigned to a different agent.",
            )
        if require_ready_routing and phone.get("routing_status") != NumberRoutingStatus.READY.value:
            raise TelephonyError(
                status=409,
                code=TelephonyErrorCode.NUMBER_NOT_ROUTING_READY,
                message="Phone number routing is not ready for this agent.",
            )

    def _order_platform_status(self, provider_status: str | None, requirements_met: bool | None = None) -> str:
        normalized = str(provider_status or "").strip().lower()
        if requirements_met is False:
            return "action_required"
        if normalized == "success":
            return "purchased"
        if normalized in {"failure", "failed"}:
            return "failed"
        if normalized in {"cancelled", "canceled"}:
            return "cancelled"
        if normalized == "deleted":
            return "deleted"
        return "pending"

    def _reconcile_number_purchase(
        self,
        client: TelnyxClient,
        e164_number: str,
        order_res: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Give newly submitted Telnyx orders a short chance to materialize cleanly.

        Telnyx can accept a number order but lag briefly before either:
        1. flipping the order status from pending to success, or
        2. returning the purchased number from owned-number inventory.

        A short bounded reconciliation loop makes the common "click buy" path
        return a usable managed number immediately instead of forcing clients to
        do an extra manual refresh when the provider already finished.
        """
        latest = dict(order_res)
        owned: list[dict[str, Any]] = []

        for attempt in range(self._purchase_reconcile_attempts):
            provider_order_id = latest.get("provider_order_id")
            if provider_order_id and latest.get("platform_status") not in {
                "purchased",
                "failed",
                "cancelled",
                "deleted",
                "action_required",
            }:
                refreshed = client.get_number_order_status(str(provider_order_id))
                latest.update({k: v for k, v in refreshed.items() if v is not None})

            owned = client.list_owned_numbers(filter_phone_number=e164_number)
            if owned:
                if latest.get("platform_status") not in {"failed", "cancelled", "deleted", "action_required"}:
                    latest["platform_status"] = "purchased"
                break

            if latest.get("platform_status") in {"failed", "cancelled", "deleted", "action_required"}:
                break
            if attempt < self._purchase_reconcile_attempts - 1 and self._purchase_reconcile_delay_sec > 0:
                time.sleep(self._purchase_reconcile_delay_sec)

        return latest, owned

    def _materialize_managed_number(
        self,
        conn: Any,
        *,
        tenant_id: str,
        telnyx_connection_id: str,
        e164_number: str,
        country: str,
        number_type: str,
        features: list[str],
        provisioning_status: str,
        routing_status: str,
        provider_status: str | None,
        external_customer_ref: str | None = None,
        provider_number_id: str | None = None,
        touch_last_synced_at: bool = False,
    ) -> str | None:
        """Upsert a managed number while reconciling later provider identity arrival.

        Real Telnyx orders can succeed before the purchased number appears in the
        owned-number inventory response. In that case we store a temporary row
        without provider identity and later let inventory sync attach the real
        `provider_number_id` by matching on E.164.
        """
        features_array = features if isinstance(features, list) else ["voice"]
        last_synced_sql = ", last_synced_at = now()" if touch_last_synced_at else ""

        if provider_number_id:
            row = conn.execute(
                f"""
                update telephony_phone_numbers
                set telnyx_connection_id = %s,
                    provider_number_id = %s,
                    country = %s,
                    number_type = %s,
                    features = %s::text[],
                    provisioning_status = case
                        when disabled_at is not null
                          or provisioning_status in ('released', 'deleted')
                        then %s
                        else telephony_phone_numbers.provisioning_status
                    end,
                    routing_status = case
                        when disabled_at is not null
                        then %s
                        else telephony_phone_numbers.routing_status
                    end,
                    provider_status = %s,
                    external_customer_ref = coalesce(%s, external_customer_ref),
                    disabled_at = null,
                    updated_at = now()
                    {last_synced_sql}
                where tenant_id = %s and e164_number = %s
                  and disabled_at is null
                  and (provider_number_id is null or provider_number_id = %s)
                returning id
                """,
                (
                    telnyx_connection_id,
                    provider_number_id,
                    country,
                    number_type,
                    features_array,
                    provisioning_status,
                    routing_status,
                    provider_status,
                    external_customer_ref,
                    tenant_id,
                    e164_number,
                    provider_number_id,
                ),
            ).fetchone()
            if row:
                return str(row[0])

            row = conn.execute(
                f"""
                insert into telephony_phone_numbers (
                    tenant_id, telnyx_connection_id, provider_number_id, e164_number,
                    country, number_type, features, provisioning_status, routing_status,
                    provider_status, external_customer_ref{", last_synced_at" if touch_last_synced_at else ""}
                ) values (%s, %s, %s, %s, %s, %s, %s::text[], %s, %s, %s, %s{", now()" if touch_last_synced_at else ""})
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
                    external_customer_ref = coalesce(excluded.external_customer_ref, telephony_phone_numbers.external_customer_ref),
                    disabled_at = null,
                    updated_at = now()
                    {last_synced_sql}
                returning id
                """,
                (
                    tenant_id,
                    telnyx_connection_id,
                    provider_number_id,
                    e164_number,
                    country,
                    number_type,
                    features_array,
                    provisioning_status,
                    routing_status,
                    provider_status,
                    external_customer_ref,
                ),
            ).fetchone()
            return str(row[0]) if row else None

        row = conn.execute(
            """
            update telephony_phone_numbers
                set telnyx_connection_id = %s,
                country = %s,
                number_type = %s,
                features = %s::text[],
                provisioning_status = case
                    when disabled_at is not null
                      or provisioning_status in ('released', 'deleted')
                    then %s
                    else telephony_phone_numbers.provisioning_status
                end,
                routing_status = case
                    when disabled_at is not null
                    then %s
                    else telephony_phone_numbers.routing_status
                end,
                provider_status = %s,
                external_customer_ref = coalesce(%s, external_customer_ref),
                disabled_at = null,
                updated_at = now()
            where tenant_id = %s and e164_number = %s and disabled_at is null
            returning id
            """,
            (
                telnyx_connection_id,
                country,
                number_type,
                features_array,
                provisioning_status,
                routing_status,
                provider_status,
                external_customer_ref,
                tenant_id,
                e164_number,
            ),
        ).fetchone()
        if row:
            return str(row[0])

        row = conn.execute(
            """
            insert into telephony_phone_numbers (
                tenant_id, telnyx_connection_id, provider_number_id, e164_number,
                country, number_type, features, provisioning_status, routing_status,
                provider_status, external_customer_ref
            ) values (%s, %s, null, %s, %s, %s, %s::text[], %s, %s, %s, %s)
            returning id
            """,
            (
                tenant_id,
                telnyx_connection_id,
                e164_number,
                country,
                number_type,
                features_array,
                provisioning_status,
                routing_status,
                provider_status,
                external_customer_ref,
            ),
        ).fetchone()
        return str(row[0]) if row else None


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
                public = self._public_connection(conn_data)
            else:
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
                public = self._public_connection(stored)
        # Auto-provision SIP + OVP after credentials are active so clients only bring an API key.
        try:
            self.ensure_telephony_infrastructure(tenant_id)
        except TelephonyError as exc:
            logger.warning(
                "Telnyx connected but infrastructure auto-provision incomplete for tenant %s: %s",
                tenant_id,
                exc.code,
            )
            public = {**public, "infrastructure_status": "pending", "infrastructure_error": exc.code}
        else:
            public = {**public, "infrastructure_status": "ready"}
        return public

    def ensure_telephony_infrastructure(self, tenant_id: str) -> dict[str, Any]:
        """Create/reuse Telnyx SIP FQDN (→ LiveKit), outbound voice profile, and LiveKit outbound trunk."""
        sip = self.upsert_telnyx_sip_connection(tenant_id)
        profile = self.upsert_telnyx_outbound_voice_profile(tenant_id, allowed_destinations=["US", "CA"])
        if profile.get("provider_outbound_voice_profile_id"):
            sip = self.upsert_telnyx_sip_connection(
                tenant_id,
                outbound_voice_profile_provider_id=str(
                    profile.get("provider_outbound_voice_profile_id")
                ),
            )
        trunk: dict[str, Any] | None = None
        try:
            trunk = self.configure_outbound_trunk(tenant_id)
        except TelephonyError as exc:
            # Outbound trunk needs at least one managed number; connect may precede inventory sync.
            if exc.code not in {
                TelephonyErrorCode.OUTBOUND_NOT_READY,
                TelephonyErrorCode.NUMBER_NOT_FOUND,
            }:
                raise
            logger.info(
                "Outbound trunk deferred for tenant %s until managed numbers exist (%s)",
                tenant_id,
                exc.code,
            )
        return {
            "tenant_id": tenant_id,
            "sip_connection_id": sip.get("id"),
            "outbound_voice_profile_id": profile.get("id"),
            "outbound_trunk_id": (trunk or {}).get("outbound_trunk_id"),
            "status": "ready" if trunk else "sip_ready",
        }

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
        exact_phone_number: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search available numbers via the tenant's Telnyx credential."""
        with self._connection() as conn:
            client, _ = self._tenant_telnyx_client(conn, tenant_id)
            return client.search_available_numbers(
                country,
                area_code,
                number_type,
                features,
                exact_phone_number=exact_phone_number,
                limit=limit,
            )
    def purchase_number(
        self,
        tenant_id: str,
        e164_number: str,
        idempotency_key: str,
        external_customer_ref: str | None = None,
    ) -> dict[str, Any]:
        """Idempotently purchase exact selected phone number.

        Bills the tenant's own Telnyx account via their stored API key. On success,
        also upserts a managed `telephony_phone_numbers` row so clients do not need
        a separate sync before assign/routing.
        """
        action = "telephony.number_orders.create"
        request_hash = hashlib.sha256(
            f"{tenant_id}:{e164_number}:{external_customer_ref or ''}".encode()
        ).hexdigest()

        with self._connection() as conn:
            idemp_id = f"{tenant_id}:{idempotency_key}:purchase"
            if conn is None and idemp_id in self._idempotency:
                return self._idempotency[idemp_id]

            if conn is not None:
                existing = queries.get_idempotency_key(conn, tenant_id, idempotency_key, action)
                if existing:
                    if existing.get("request_hash") != request_hash:
                        raise TelephonyError(
                            status=409,
                            code=TelephonyErrorCode.CALL_STATE_CONFLICT,
                            message="Idempotency key was reused with a different purchase payload.",
                        )
                    return existing["response_body"]

            client, conn_data = self._tenant_telnyx_client(conn, tenant_id)
            order_res = client.purchase_number(e164_number)
            order_res, owned = self._reconcile_number_purchase(client, e164_number, order_res)

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
                    "routing_status": NumberRoutingStatus.NOT_CONFIGURED.value,
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
                    "managed_number_id": num_id,
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

            managed_number_id = None
            try:
                provider_number_id = owned[0].get("provider_number_id") if owned else None
                country = (owned[0].get("country") if owned else "US") or "US"
                number_type = (owned[0].get("number_type") if owned else "local") or "local"
                features = (owned[0].get("features") if owned else ["voice"]) or ["voice"]
                managed_number_id = self._materialize_managed_number(
                    conn,
                    tenant_id=tenant_id,
                    telnyx_connection_id=conn_data["id"],
                    provider_number_id=provider_number_id,
                    e164_number=e164_number,
                    country=country,
                    number_type=number_type,
                    features=features if isinstance(features, list) else ["voice"],
                    provisioning_status=(
                        NumberProvisioningStatus.OWNED.value
                        if order_res.get("platform_status") == "purchased"
                        else NumberProvisioningStatus.PURCHASE_PENDING.value
                    ),
                    routing_status=NumberRoutingStatus.NOT_CONFIGURED.value,
                    provider_status=order_res.get("provider_status"),
                    external_customer_ref=external_customer_ref,
                )
            except Exception as exc:
                logger.warning(
                    "Purchase succeeded but managed number materialization failed for %s: %s",
                    e164_number,
                    exc,
                )

            response = {
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
                "managed_number_id": managed_number_id,
            }
            queries.save_idempotency_key(
                conn, tenant_id, idempotency_key, action, request_hash, response
            )
            return response

    def assign_agent_to_number(
        self, tenant_id: str, number_id: str, agent_id: str | None
    ) -> dict[str, Any]:
        """Assign or unassign an agent to a phone number.

        On assign: bind the Telnyx number to the tenant SIP connection and configure
        LiveKit inbound routing so the number becomes call-ready without extra client steps.
        """
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
                if agent_id:
                    target["routing_status"] = NumberRoutingStatus.READY.value
                else:
                    target["routing_status"] = NumberRoutingStatus.NOT_CONFIGURED.value
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
            number = self._number_from_row(row)

        if agent_id:
            # Auto-provision tenant SIP/OVP/trunk prerequisites so client integrations
            # only need to connect Telnyx, sync/buy a number, and assign it to an agent.
            try:
                self.ensure_telephony_infrastructure(tenant_id)
            except TelephonyError as exc:
                if exc.code not in {
                    TelephonyErrorCode.OUTBOUND_NOT_READY,
                    TelephonyErrorCode.NUMBER_NOT_FOUND,
                }:
                    raise
                logger.info(
                    "Telephony infrastructure partially ready for tenant %s during assign: %s",
                    tenant_id,
                    exc.code,
                )

            # Fail closed here. If the Telnyx number is not actually attached to the
            # tenant SIP connection, the UI should not show a misleading routed-ready
            # state while real PSTN inbound calls never reach LiveKit.
            self._bind_telnyx_number_to_sip(tenant_id, number)
            routing = self.configure_number_routing(
                tenant_id, number_id, inbound_agent_id=agent_id
            )
            number["routing_status"] = routing.get(
                "routing_status", NumberRoutingStatus.READY.value
            )
            number["assigned_agent_id"] = agent_id
            try:
                self.ensure_telephony_infrastructure(tenant_id)
            except TelephonyError as exc:
                if exc.code not in {
                    TelephonyErrorCode.OUTBOUND_NOT_READY,
                    TelephonyErrorCode.SIP_VERIFICATION_FAILED,
                    TelephonyErrorCode.OUTBOUND_VOICE_PROFILE_MISSING,
                }:
                    raise
                logger.info(
                    "Outbound trunk refresh deferred after assign for tenant %s: %s",
                    tenant_id,
                    exc.code,
                )
        else:
            with self._connection() as conn:
                if conn is not None:
                    conn.execute(
                        """
                        update telephony_phone_numbers
                        set routing_status = 'not_configured',
                            updated_at = now()
                        where tenant_id = %s and id = %s
                        """,
                        (tenant_id, number_id),
                    )
            number["routing_status"] = NumberRoutingStatus.NOT_CONFIGURED.value
            number["assigned_agent_id"] = None
        return number

    def _bind_telnyx_number_to_sip(self, tenant_id: str, number: dict[str, Any]) -> None:
        """Attach managed number to the tenant Telnyx FQDN/SIP connection."""
        provider_number_id = number.get("provider_number_id")
        if not provider_number_id:
            raise TelephonyError(
                status=409,
                code=TelephonyErrorCode.NUMBER_NOT_FOUND,
                message="Managed number is missing provider_number_id for Telnyx bind.",
            )
        with self._connection() as conn:
            client, conn_data = self._tenant_telnyx_client(conn, tenant_id)
            if conn is None:
                sip = self.upsert_telnyx_sip_connection(tenant_id)
                connection_id = sip.get("provider_sip_connection_id") or "fqdn_conn_mock_123"
            else:
                sip_row = conn.execute(
                    """
                    select provider_sip_connection_id
                    from telnyx_sip_connections
                    where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                      and platform_status in ('pending_verification', 'testing', 'active')
                    order by created_at desc limit 1
                    """,
                    (tenant_id, conn_data["id"]),
                ).fetchone()
                if not sip_row or not sip_row[0]:
                    sip = self.upsert_telnyx_sip_connection(tenant_id)
                    connection_id = sip.get("provider_sip_connection_id")
                else:
                    connection_id = sip_row[0]
            if not connection_id:
                raise TelephonyError(
                    status=409,
                    code=TelephonyErrorCode.SIP_VERIFICATION_FAILED,
                    message="Tenant Telnyx SIP connection id is missing.",
                )
            client.assign_phone_number_to_connection(str(provider_number_id), str(connection_id))

    def get_outbound_readiness(self, tenant_id: str) -> dict[str, Any]:
        """Check outbound calling readiness."""
        with self._connection() as conn:
            conn_data = self._active_connection(conn, tenant_id)
            is_conn_active = conn_data is not None and conn_data.get("platform_status") == ConnectionPlatformStatus.ACTIVE.value
            if conn is None:
                nums = self._numbers.get(tenant_id, [])
                sip_active = is_conn_active and bool(nums)
                profile_active = sip_active
                assigned_ready_numbers = [
                    n for n in nums
                    if n.get("routing_status") == NumberRoutingStatus.READY.value and n.get("assigned_agent_id")
                ]
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
                phone = next(
                    (n for n in self._numbers.get(tenant_id, []) if n["id"] == from_number_id),
                    None,
                )
                if not phone:
                    raise TelephonyError(
                        status=404,
                        code=TelephonyErrorCode.NUMBER_NOT_FOUND,
                        message=f"Number {from_number_id} not found for tenant.",
                    )
                self._assert_number_bound_to_agent(phone, agent_id)
                outbound_trunk_id = "lk_tr_out_mock_123"
                phone_e164 = phone["e164_number"]
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
                self._assert_number_bound_to_agent(phone, agent_id)
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
                    try:
                        self.configure_outbound_trunk(tenant_id)
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
                    except Exception as err:
                        logger.warning("Auto-configuring outbound trunk deferred: %s", err)
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

            call_id = str(uuid.uuid4())
            room_name = f"telephony-outbound-{uuid.uuid4().hex[:8]}"
            lk_client = self._get_livekit_sip_client()
            # Dispatch the named worker into the room BEFORE dialing so the agent is
            # present when the PSTN party answers (job metadata carries tenant/agent).
            lk_client.create_agent_dispatch(
                room_name,
                metadata={
                    "direction": "outbound",
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "telephony_call_id": call_id,
                    "from_number_id": from_number_id,
                    "from_number": phone_e164,
                    "to_number": to_number,
                },
            )
            try:
                sip_part = lk_client.create_sip_participant(
                    room_name=room_name,
                    outbound_trunk_id=outbound_trunk_id,
                    to_number=to_number,
                )
            except TelephonyError as exc:
                if conn is not None:
                    queries.release_call_quota(conn, tenant_id, call_id)
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                provider_message = detail.get("provider_message") if isinstance(detail, dict) else None
                raise TelephonyError(
                    status=exc.status,
                    code=exc.code,
                    message=exc.message,
                    detail={
                        **detail,
                        "from_number": phone_e164,
                        "to_number": to_number,
                        "room_name": room_name,
                        "outbound_trunk_id": outbound_trunk_id,
                        **({"provider_message": provider_message} if provider_message else {}),
                    },
                ) from exc

            res = {
                "telephony_call_id": call_id,
                "session_id": None,
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
                    materialized_id = self._materialize_managed_number(
                        conn,
                        tenant_id=tenant_id,
                        telnyx_connection_id=conn_data["id"],
                        provider_number_id=provider_number_id,
                        e164_number=e164_number,
                        country=item.get("country"),
                        number_type=item.get("number_type"),
                        features=item.get("features") or ["voice"],
                        provisioning_status=NumberProvisioningStatus.OWNED.value,
                        routing_status=NumberRoutingStatus.NOT_CONFIGURED.value,
                        provider_status=item.get("status"),
                        touch_last_synced_at=True,
                    )
                except (psycopg.errors.UniqueViolation, psycopg.errors.InvalidColumnReference) as exc:
                    self._raise_database_conflict("sync Telnyx owned numbers", exc)
                if materialized_id:
                    row = conn.execute(
                        """
                        select id, tenant_id, provider_number_id, e164_number, country, number_type,
                               features, provisioning_status, routing_status, assigned_agent_id,
                               external_customer_ref, disabled_at
                        from telephony_phone_numbers
                        where tenant_id = %s and id = %s
                        """,
                        (tenant_id, materialized_id),
                    ).fetchone()
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
        self,
        tenant_id: str,
        sip_fqdn: str | None = None,
        sip_username: str | None = None,
        sip_secret: str | None = None,
        outbound_voice_profile_provider_id: str | None = None,
    ) -> dict[str, Any]:
        """Configure or update tenant Telnyx SIP/FQDN connection."""
        with self._connection() as conn:
            client, conn_data = self._tenant_telnyx_client(conn, tenant_id)
            if conn is None:
                return {
                    "id": f"sip_conn_{uuid.uuid4().hex[:8]}",
                    "tenant_id": tenant_id,
                    "telnyx_connection_id": conn_data["id"],
                    "sip_fqdn": sip_fqdn or require_livekit_sip_uri(),
                    "sip_username": self._normalize_sip_username(tenant_id, sip_username),
                    "provider_sip_connection_id": "fqdn_conn_mock_123",
                    "platform_status": "active",
                    "provider_status": "active",
                }

            existing = conn.execute(
                """
                select id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                       sip_username, encrypted_sip_secret_ref, platform_status, provider_status, last_verified_at
                from telnyx_sip_connections
                where tenant_id = %s and telnyx_connection_id = %s and disabled_at is null
                  and platform_status in ('pending_verification', 'testing', 'active')
                order by created_at desc limit 1
                """,
                (tenant_id, conn_data["id"]),
            ).fetchone()
            fqdn = sip_fqdn or (self._sip_from_row(existing).get("sip_fqdn") if existing else None) or require_livekit_sip_uri()
            if existing:
                current = self._sip_from_row(existing)
                effective_sip_username = self._normalize_sip_username(
                    tenant_id,
                    sip_username or current.get("sip_username"),
                )
                effective_sip_secret = sip_secret
                if not effective_sip_secret and current.get("encrypted_sip_secret_ref"):
                    effective_sip_secret = decrypt_provider_secret(current.get("encrypted_sip_secret_ref"))
                if not effective_sip_secret:
                    effective_sip_secret = self._generate_sip_secret()
                encrypted_sip_secret_ref = (
                    None
                    if not effective_sip_secret or is_mock_provider_mode()
                    else encrypt_provider_secret(effective_sip_secret)
                )
                provider = client.create_or_get_fqdn_connection(
                    f"tenant-{tenant_id}",
                    fqdn,
                    sip_username=effective_sip_username,
                    sip_secret=effective_sip_secret,
                    outbound_voice_profile_id=outbound_voice_profile_provider_id,
                )
                updated = conn.execute(
                    """
                    update telnyx_sip_connections
                    set provider_sip_connection_id = %s,
                        sip_fqdn = %s,
                        sip_username = coalesce(%s, sip_username),
                        encrypted_sip_secret_ref = coalesce(%s, encrypted_sip_secret_ref),
                        platform_status = 'active',
                        provider_status = %s,
                        last_verified_at = now(),
                        updated_at = now()
                    where tenant_id = %s and id = %s
                    returning id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                              sip_username, encrypted_sip_secret_ref, platform_status, provider_status, last_verified_at
                    """,
                    (
                        provider.get("provider_sip_connection_id"),
                        provider.get("sip_fqdn") or fqdn,
                        effective_sip_username,
                        encrypted_sip_secret_ref,
                        provider.get("status", "active"),
                        tenant_id,
                        existing[0],
                    ),
                ).fetchone()
                return self._sip_from_row(updated or existing)

            effective_sip_username = self._normalize_sip_username(tenant_id, sip_username)
            effective_sip_secret = sip_secret or self._generate_sip_secret()
            encrypted_sip_secret_ref = (
                None
                if not effective_sip_secret or is_mock_provider_mode()
                else encrypt_provider_secret(effective_sip_secret)
            )
            provider = client.create_or_get_fqdn_connection(
                f"tenant-{tenant_id}",
                fqdn,
                sip_username=effective_sip_username,
                sip_secret=effective_sip_secret,
                outbound_voice_profile_id=outbound_voice_profile_provider_id,
            )
            row = conn.execute(
                """
                insert into telnyx_sip_connections (
                    tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                    sip_username, encrypted_sip_secret_ref, platform_status, provider_status, last_verified_at
                ) values (%s, %s, %s, %s, %s, %s, 'active', %s, now())
                returning id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                          sip_username, encrypted_sip_secret_ref, platform_status, provider_status, last_verified_at
                """,
                (
                    tenant_id,
                    conn_data["id"],
                    provider.get("provider_sip_connection_id"),
                    provider.get("sip_fqdn") or fqdn,
                    effective_sip_username,
                    encrypted_sip_secret_ref,
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
            client, _ = self._tenant_telnyx_client(conn, tenant_id)
            row = conn.execute(
                """
                select id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                       sip_username, encrypted_sip_secret_ref, platform_status, provider_status, last_verified_at
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
            provider_connection = next(
                (
                    item
                    for item in client.list_fqdn_connections(connection_name=f"tenant-{tenant_id}")
                    if str(item.get("id") or "") == str(sip.get("provider_sip_connection_id") or "")
                ),
                None,
            )
            provider_fqdns = client.list_fqdns(connection_id=str(sip.get("provider_sip_connection_id") or ""))
            matched_fqdn = next(
                (item for item in provider_fqdns if str(item.get("fqdn") or "") == str(sip.get("sip_fqdn") or "")),
                None,
            )
            return {
                "tenant_id": tenant_id,
                "is_valid": bool(provider_connection and matched_fqdn),
                "sip_status": sip["platform_status"] if provider_connection and matched_fqdn else "mismatch",
                "provider_connection_id": provider_connection.get("id") if provider_connection else None,
                "provider_fqdn": matched_fqdn.get("fqdn") if matched_fqdn else None,
                "expected_provider_connection_id": sip.get("provider_sip_connection_id"),
                "expected_fqdn": sip.get("sip_fqdn"),
            }
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
            effective_allowed_destinations = [
                str(item).strip().upper()
                for item in (allowed_destinations or [])
                if str(item).strip()
            ]
            effective_concurrency_limit = concurrency_limit
            effective_daily_spending_limit = daily_spending_limit

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
            sip_row = conn.execute(
                """
                select id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
                       sip_username, encrypted_sip_secret_ref, platform_status, provider_status, last_verified_at
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
            if existing:
                current = self._outbound_profile_from_row(existing)
                if not effective_allowed_destinations:
                    effective_allowed_destinations = [
                        str(item).strip().upper()
                        for item in (current.get("allowed_destinations") or [])
                        if str(item).strip()
                    ]
                if effective_concurrency_limit is None:
                    effective_concurrency_limit = current.get("concurrency_limit")
                if effective_daily_spending_limit is None:
                    effective_daily_spending_limit = current.get("daily_spending_limit")
                provider = client.update_outbound_voice_profile(
                    str(current.get("provider_outbound_voice_profile_id") or ""),
                    name=f"tenant-{tenant_id}-outbound",
                    fqdn_connection_id=str(sip["provider_sip_connection_id"]),
                    allowed_destinations=effective_allowed_destinations,
                    concurrency_limit=effective_concurrency_limit,
                    daily_spending_limit=effective_daily_spending_limit,
                )
                updated = conn.execute(
                    """
                    update telnyx_outbound_voice_profiles
                    set provider_outbound_voice_profile_id = %s,
                        provider_status = %s,
                        allowed_destinations = %s,
                        concurrency_limit = %s,
                        daily_spending_limit = %s,
                        last_verified_at = now(),
                        updated_at = now()
                    where tenant_id = %s and id = %s
                    returning id, tenant_id, telnyx_connection_id, telnyx_sip_connection_id,
                              provider_outbound_voice_profile_id, platform_status, provider_status,
                              allowed_destinations, concurrency_limit, daily_spending_limit
                    """,
                    (
                        provider.get("provider_outbound_voice_profile_id")
                        or current.get("provider_outbound_voice_profile_id"),
                        provider.get("status", current.get("provider_status", "active")),
                        effective_allowed_destinations,
                        effective_concurrency_limit,
                        effective_daily_spending_limit,
                        tenant_id,
                        existing[0],
                    ),
                ).fetchone()
                synced_profile = self._outbound_profile_from_row(updated or existing)
                self.upsert_telnyx_sip_connection(
                    tenant_id,
                    outbound_voice_profile_provider_id=str(
                        provider.get("provider_outbound_voice_profile_id")
                        or current.get("provider_outbound_voice_profile_id")
                        or ""
                    ),
                )
                return synced_profile

            provider = client.create_or_get_outbound_voice_profile(
                f"tenant-{tenant_id}-outbound",
                str(sip["provider_sip_connection_id"]),
                allowed_destinations=effective_allowed_destinations,
                concurrency_limit=effective_concurrency_limit,
                daily_spending_limit=effective_daily_spending_limit,
            )
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
                    effective_allowed_destinations,
                    effective_concurrency_limit,
                    effective_daily_spending_limit,
                ),
            ).fetchone()
            created_profile = self._outbound_profile_from_row(row)
            self.upsert_telnyx_sip_connection(
                tenant_id,
                outbound_voice_profile_provider_id=str(
                    provider.get("provider_outbound_voice_profile_id") or ""
                ),
            )
            return created_profile
    def verify_telnyx_outbound_voice_profile(self, tenant_id: str) -> dict[str, Any]:
        """Re-verify outbound voice profile readiness."""
        with self._connection() as conn:
            if conn is None:
                return {"tenant_id": tenant_id, "is_valid": True, "platform_status": "active"}
            client, conn_data = self._tenant_telnyx_client(conn, tenant_id)
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
            provider_profile = client.get_outbound_voice_profile(
                str(profile.get("provider_outbound_voice_profile_id") or "")
            )
            expected_destinations = sorted(
                {
                    str(item).strip().upper()
                    for item in (profile.get("allowed_destinations") or [])
                    if str(item).strip()
                }
            )
            actual_destinations = sorted(
                {
                    str(item).strip().upper()
                    for item in (provider_profile.get("allowed_destinations") or [])
                    if str(item).strip()
                }
            )
            expected_concurrency = profile.get("concurrency_limit")
            actual_concurrency = provider_profile.get("concurrency_limit")
            expected_daily_spending = (
                None
                if profile.get("daily_spending_limit") is None
                else str(profile.get("daily_spending_limit"))
            )
            actual_daily_spending = (
                None
                if provider_profile.get("daily_spending_limit") is None
                else str(provider_profile.get("daily_spending_limit"))
            )
            expected_connection_id = conn_data["id"]
            provider_connections = provider_profile.get("connections") or []
            actual_connection_ids = {
                str(item.get("id") or item.get("connection_id") or "")
                for item in provider_connections
                if isinstance(item, dict)
            }
            mismatches = []
            if provider_profile.get("status") != "active":
                mismatches.append("Provider outbound voice profile is not active.")
            if expected_destinations and expected_destinations != actual_destinations:
                mismatches.append("Provider whitelisted destinations do not match the expected tenant destinations.")
            if expected_concurrency is not None and expected_concurrency != actual_concurrency:
                mismatches.append("Provider concurrent call limit does not match the expected tenant limit.")
            if expected_daily_spending is not None and expected_daily_spending != actual_daily_spending:
                mismatches.append("Provider daily spend limit does not match the expected tenant limit.")
            if expected_connection_id and actual_connection_ids and expected_connection_id not in actual_connection_ids:
                mismatches.append("Provider outbound voice profile is not linked to the expected Telnyx SIP connection.")
            return {
                "tenant_id": tenant_id,
                "is_valid": not mismatches,
                "platform_status": profile["platform_status"],
                "provider_status": provider_profile.get("status"),
                "expected": {
                    "allowed_destinations": expected_destinations,
                    "concurrency_limit": expected_concurrency,
                    "daily_spending_limit": expected_daily_spending,
                    "connection_id": expected_connection_id,
                },
                "provider": {
                    "allowed_destinations": actual_destinations,
                    "concurrency_limit": actual_concurrency,
                    "daily_spending_limit": actual_daily_spending,
                    "connection_ids": sorted(item for item in actual_connection_ids if item),
                    "provider_outbound_voice_profile_id": provider_profile.get(
                        "provider_outbound_voice_profile_id"
                    ),
                },
                "mismatches": mismatches,
            }
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
                       sip_username, encrypted_sip_secret_ref, platform_status, provider_status, last_verified_at
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
                created_rule = lk_client.create_or_get_dispatch_rule(
                    inbound["livekit_inbound_trunk_id"],
                    number_id,
                    number["e164_number"],
                    tenant_id=tenant_id,
                    agent_id=inbound_agent_id or number.get("assigned_agent_id"),
                )
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
                       sip_username, encrypted_sip_secret_ref, platform_status, provider_status, last_verified_at
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
            trunk_numbers = self._eligible_outbound_trunk_numbers(conn, tenant_id, conn_data["id"])
            if not trunk_numbers:
                raise TelephonyError(
                    status=409,
                    code=TelephonyErrorCode.OUTBOUND_NOT_READY,
                    message="Tenant has no eligible managed phone numbers for outbound trunk setup.",
                )
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
            created = self._get_livekit_sip_client().create_or_get_outbound_trunk(
                conn_data["id"],
                telnyx_sip_outbound_address(),
                trunk_numbers,
                sip_username=sip.get("sip_username"),
                sip_secret=(
                    decrypt_provider_secret(sip.get("encrypted_sip_secret_ref"))
                    if sip.get("encrypted_sip_secret_ref")
                    else None
                ),
            )
            if existing:
                row = conn.execute(
                    """
                    update livekit_outbound_trunks
                    set livekit_outbound_trunk_id = %s,
                        platform_status = 'active',
                        provider_status = %s,
                        last_reconciled_at = now(),
                        updated_at = now()
                    where tenant_id = %s and id = %s
                    returning id, tenant_id, outbound_voice_profile_record_id, livekit_outbound_trunk_id, platform_status, provider_status
                    """,
                    (created.get("livekit_outbound_trunk_id"), created.get("status", "active"), tenant_id, existing[0]),
                ).fetchone()
                trunk = self._outbound_trunk_from_row(row or existing)
                return {"tenant_id": tenant_id, "outbound_trunk_id": trunk["livekit_outbound_trunk_id"], "platform_status": trunk["platform_status"]}
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
                       duration_sec, error_code, error_message, started_at, ended_at,
                       raw_livekit_sip_participant_status
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
                       duration_sec, error_code, error_message, started_at, ended_at,
                       raw_livekit_sip_participant_status
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
            "assigned_agent_id": str(row[9]) if row[9] else None,
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
            "encrypted_sip_secret_ref": row[6] if len(row) > 9 else None,
            "platform_status": row[7] if len(row) > 9 else row[6],
            "provider_status": row[8] if len(row) > 9 else row[7],
            "last_verified_at": str(row[9]) if len(row) > 9 and row[9] else (str(row[8]) if len(row) > 8 and row[8] else None),
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
            "raw_livekit_sip_participant_status": row[18] if len(row) > 18 else None,
        }
