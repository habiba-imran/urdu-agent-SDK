"""Telnyx API client adapter for credential verification, inventory sync, number search, number orders, FQDN connection, and outbound voice profile management.

Backend-only module. Supports fake provider mock mode only when explicitly configured for testing.
Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from tenant_portal_api.telephony_errors import (
    TelephonyError,
    TelephonyErrorCode,
    redact_sensitive_string,
)
from tenant_portal_api.telephony_config import is_mock_provider_mode

logger = logging.getLogger(__name__)

TELNYX_API_BASE_URL = "https://api.telnyx.com/v2"


def _normalize_features(raw: Any) -> list[str]:
    """Normalize Telnyx feature shapes into public SDK strings.

    Telnyx v2 can return features as an array of objects/strings, while older
    fixtures used a boolean map. Keep both shapes valid so real provider
    responses do not crash the route.
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [str(key) for key, enabled in raw.items() if enabled]
    if isinstance(raw, list):
        values: list[str] = []
        for item in raw:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                value = item.get("name") or item.get("feature") or item.get("type")
                if value:
                    values.append(str(value))
        return values
    return []


def _telnyx_error_message(response: httpx.Response, fallback: str) -> str:
    """Extract a safe provider error message without exposing credentials."""
    try:
        payload = response.json()
    except ValueError:
        return fallback

    messages: list[str] = []
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list):
            for item in errors[:3]:
                if not isinstance(item, dict):
                    continue
                for key in ("title", "detail", "code"):
                    value = item.get(key)
                    if value:
                        messages.append(str(value))
        for key in ("message", "error", "detail", "title"):
            value = payload.get(key)
            if isinstance(value, str):
                messages.append(value)

    combined = " ".join(part.strip() for part in messages if part and part.strip())
    return redact_sensitive_string(combined or fallback)


def _raise_telnyx_number_order_error(
    response: httpx.Response, e164_number: str
) -> None:
    provider_message = _telnyx_error_message(
        response, "Telnyx rejected the number order."
    )
    normalized = provider_message.lower()

    if response.status_code == 401:
        raise TelephonyError(
            status=401,
            code=TelephonyErrorCode.TELNYX_KEY_INVALID,
            message="Invalid Telnyx API key or unauthorized.",
        )
    if response.status_code == 403:
        raise TelephonyError(
            status=403,
            code=TelephonyErrorCode.TELNYX_KEY_PERMISSION_FAILED,
            message="Telnyx API key lacks permission to order phone numbers.",
        )
    if response.status_code == 429:
        raise TelephonyError(
            status=429,
            code=TelephonyErrorCode.TELNYX_RATE_LIMITED,
            message="Telnyx rate-limited the number order request.",
        )
    if response.status_code == 402 or any(
        token in normalized for token in ("balance", "credit", "fund", "payment")
    ):
        raise TelephonyError(
            status=402,
            code=TelephonyErrorCode.INSUFFICIENT_TELNYX_BALANCE,
            message="Telnyx rejected the number order because the account balance, credit, or payment state is not sufficient.",
        )
    if any(
        token in normalized
        for token in (
            "regulatory",
            "kyc",
            "verification",
            "verified",
            "address",
            "document",
            "requirement",
        )
    ):
        raise TelephonyError(
            status=409,
            code=TelephonyErrorCode.REGULATORY_ACTION_REQUIRED,
            message="Telnyx requires account, destination, or regulatory verification before this number can be ordered.",
        )
<<<<<<< Updated upstream
    if response.status_code in {404, 409, 422} or any(token in normalized for token in ("not available", "unavailable", "already been taken", "already purchased")):
=======
    if response.status_code == 404 or any(
        token in normalized
        for token in (
            "not available",
            "unavailable",
            "already been taken",
            "already purchased",
        )
    ):
>>>>>>> Stashed changes
        raise TelephonyError(
            status=422,
            code=TelephonyErrorCode.NUMBER_NOT_AVAILABLE,
            message=f"Phone number {e164_number} is no longer available for purchase.",
        )

    raise TelephonyError(
        status=502,
        code=TelephonyErrorCode.TELNYX_API_ERROR,
        message=f"Telnyx rejected the number order: {provider_message}",
    )

<<<<<<< Updated upstream
=======

def _map_number_order_platform_status(
    provider_status: Any, requirements_met: Any = None
) -> str:
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


>>>>>>> Stashed changes
class TelnyxClient:
    """Backend client for Telnyx REST v2 APIs."""

    def __init__(
        self,
        api_key: str,
        http_client: httpx.Client | None = None,
        mock_mode: bool | None = None,
        timeout: float = 10.0,
    ):
        self.api_key = api_key
        self.timeout = timeout
        self._owned_client = http_client is None
        self.client = http_client or httpx.Client(timeout=timeout)

        # Mock mode must be explicit through the caller or TELEPHONY_PROVIDER_MODE.
        # Staging/production should fail closed instead of silently synthesizing
        # provider resources when credentials are absent or placeholder-shaped.
        if mock_mode is not None:
            self.mock_mode = mock_mode
        else:
            self.mock_mode = is_mock_provider_mode()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def verify_api_key(self) -> dict[str, Any]:
        """Verify API key validity against Telnyx /v2/balance or fake provider."""
        if self.mock_mode:
            if self.api_key == "invalid_key":
                raise TelephonyError(
                    status=401,
                    code=TelephonyErrorCode.TELNYX_KEY_INVALID,
                    message="Invalid Telnyx API key provided.",
                )
            return {
                "telnyx_account_id": "act_fake_telnyx_123",
                "balance": "100.00",
                "currency": "USD",
                "status": "active",
            }

        if not self.api_key:
            raise TelephonyError(
                status=503,
                code=TelephonyErrorCode.PROVIDER_CREDENTIALS_MISSING,
                message="Telnyx API key is not configured for this tenant.",
            )

        try:
            resp = self.client.get(
                f"{TELNYX_API_BASE_URL}/balance",
                headers=self._headers(),
            )
            if resp.status_code == 401:
                raise TelephonyError(
                    status=401,
                    code=TelephonyErrorCode.TELNYX_KEY_INVALID,
                    message="Invalid Telnyx API key or unauthorized.",
                )
            if resp.status_code == 403:
                raise TelephonyError(
                    status=403,
                    code=TelephonyErrorCode.TELNYX_KEY_PERMISSION_FAILED,
                    message="Telnyx API key lacks required permissions.",
                )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            account_id = (
                data.get("account_id")
                or data.get("organization_id")
                or data.get("customer_id")
            )
            return {
                "telnyx_account_id": account_id,
                "verification_record_type": data.get("record_type"),
                "balance": str(data.get("balance", "0.00")),
                "currency": data.get("currency", "USD"),
                "status": "active",
            }
        except httpx.HTTPError as e:
            logger.error(
                "Telnyx balance check failed: %s", redact_sensitive_string(str(e))
            )
            raise TelephonyError(
                status=502,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message="Failed to verify Telnyx API key with upstream provider.",
            ) from e

    def list_owned_numbers(
        self, filter_phone_number: str | None = None
    ) -> list[dict[str, Any]]:
        """List phone numbers owned in the Telnyx account."""
        if self.mock_mode:
            mock_numbers = [
                {
                    "provider_number_id": "num_mock_001",
                    "e164_number": "+15551234567",
                    "country": "US",
                    "number_type": "local",
                    "features": ["voice"],
                    "status": "active",
                }
            ]
            if filter_phone_number:
                return [
                    n for n in mock_numbers if n["e164_number"] == filter_phone_number
                ]
            return mock_numbers

        try:
            params = {}
            if filter_phone_number:
                params["filter[phone_number]"] = filter_phone_number

            resp = self.client.get(
                f"{TELNYX_API_BASE_URL}/phone_numbers",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            raw_list = resp.json().get("data", [])
            results = []
            for item in raw_list:
                results.append(
                    {
                        "provider_number_id": item.get("id"),
                        "e164_number": item.get("phone_number"),
                        "country": item.get("country_code", "US"),
                        "number_type": item.get("phone_number_type", "local"),
                        "features": item.get("features", []),
                        "status": item.get("status", "active"),
                    }
                )
            return results
        except httpx.HTTPError as e:
            raise TelephonyError(
                status=502,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message="Failed to list owned numbers from Telnyx.",
            ) from e

    def search_available_numbers(
        self,
        country: str,
        area_code: str | None = None,
        number_type: str | None = None,
        features: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search available phone numbers for purchase."""
        if self.mock_mode:
            prefix = area_code or "555"
            return [
                {
                    "e164_number": f"+1{prefix}9876543",
                    "country": country.upper(),
                    "region": "US-CA",
                    "number_type": number_type or "local",
                    "features": features or ["voice"],
                    "upfront_cost": "1.00",
                    "monthly_cost": "1.00",
                    "currency": "USD",
                }
            ]

        try:
            params = {"filter[country_code]": country.upper()}
            if area_code:
                params["filter[national_destination_code]"] = area_code
            if number_type:
                params["filter[phone_number_type]"] = number_type
            if features:
                for f in features:
                    params[f"filter[features][{f}]"] = "true"

            resp = self.client.get(
                f"{TELNYX_API_BASE_URL}/available_phone_numbers",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            raw_list = resp.json().get("data", [])
            results = []
            for item in raw_list:
                cost = item.get("cost_information", {})
                results.append(
                    {
                        "e164_number": item.get("phone_number"),
                        "country": item.get("country_code", country.upper()),
                        "region": item.get("region"),
                        "number_type": item.get("phone_number_type"),
                        "features": _normalize_features(item.get("features"))
                        or ["voice"],
                        "upfront_cost": str(cost.get("upfront_cost", "1.00")),
                        "monthly_cost": str(cost.get("monthly_cost", "1.00")),
                        "currency": cost.get("currency", "USD"),
                    }
                )
            return results
        except httpx.HTTPError as e:
            raise TelephonyError(
                status=502,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message="Failed to search available numbers from Telnyx.",
            ) from e

    def purchase_number(self, e164_number: str) -> dict[str, Any]:
        """Order purchase of an exact selected E.164 phone number."""
        if self.mock_mode:
            return {
                "provider_order_id": "order_mock_12345",
                "selected_e164_number": e164_number,
                "status": "success",
                "provider_status": "success",
                "platform_status": "purchased",
            }

        try:
            payload = {
                "phone_numbers": [{"phone_number": e164_number}],
            }
            resp = self.client.post(
                f"{TELNYX_API_BASE_URL}/number_orders",
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code >= 400:
                _raise_telnyx_number_order_error(resp, e164_number)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {
                "provider_order_id": data.get("id"),
                "selected_e164_number": e164_number,
                "status": data.get("status", "pending"),
                "provider_status": data.get("status", "pending"),
                "platform_status": (
                    "purchased" if data.get("status") == "success" else "pending"
                ),
            }
        except httpx.HTTPError as e:
            raise TelephonyError(
                status=502,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message="Failed to submit number order to Telnyx.",
            ) from e

    def get_number_order_status(self, order_id: str) -> dict[str, Any]:
        """Fetch status of a Telnyx number order."""
        if self.mock_mode:
            return {
                "provider_order_id": order_id,
                "status": "success",
                "provider_status": "success",
                "platform_status": "purchased",
            }

        try:
            resp = self.client.get(
                f"{TELNYX_API_BASE_URL}/number_orders/{order_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {
                "provider_order_id": data.get("id"),
                "status": data.get("status", "pending"),
                "provider_status": data.get("status", "pending"),
                "platform_status": (
                    "purchased" if data.get("status") == "success" else "pending"
                ),
            }
        except httpx.HTTPError as e:
            raise TelephonyError(
                status=502,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message=f"Failed to fetch order status for {order_id}.",
            ) from e

    def create_or_get_fqdn_connection(
        self,
        connection_name: str,
        fqdn: str,
        sip_username: str | None = None,
        sip_secret: str | None = None,
    ) -> dict[str, Any]:
        """Create or get a Telnyx FQDN/SIP connection."""
        if self.mock_mode:
            return {
                "provider_sip_connection_id": "fqdn_conn_mock_123",
                "connection_name": connection_name,
                "sip_fqdn": fqdn,
                "status": "active",
            }

        try:
            payload = {
                "connection_name": connection_name,
                "fqdn": fqdn,
                "transport_protocol": "UDP",
            }
            if sip_username:
                payload["user_name"] = sip_username
            if sip_secret:
                payload["password"] = sip_secret
<<<<<<< Updated upstream
=======
            existing = self.list_fqdn_connections(connection_name=connection_name)
            if existing:
                connection_id = existing[0].get("id")
                if connection_id:
                    resp = self.client.patch(
                        f"{TELNYX_API_BASE_URL}/fqdn_connections/{connection_id}",
                        headers=self._headers(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json().get("data", {})
                    self._ensure_fqdn_target(str(connection_id), fqdn)
                    return {
                        "provider_sip_connection_id": data.get("id")
                        or str(connection_id),
                        "connection_name": data.get("connection_name")
                        or connection_name,
                        "sip_fqdn": fqdn,
                        "status": "active" if data.get("active", True) else "disabled",
                    }
>>>>>>> Stashed changes
            resp = self.client.post(
                f"{TELNYX_API_BASE_URL}/fqdn_connections",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {
                "provider_sip_connection_id": data.get("id"),
                "connection_name": data.get("connection_name"),
                "sip_fqdn": fqdn,
                "status": "active" if data.get("active", True) else "disabled",
            }
        except httpx.HTTPError as e:
            raise TelephonyError(
                status=502,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message="Failed to create/configure Telnyx FQDN connection.",
            ) from e

<<<<<<< Updated upstream
=======
    def list_fqdn_connections(
        self,
        *,
        connection_name: str | None = None,
        fqdn: str | None = None,
    ) -> list[dict[str, Any]]:
        """List Telnyx FQDN connections for reconciliation and diagnostics."""
        if self.mock_mode:
            return [
                {
                    "id": "fqdn_conn_mock_123",
                    "connection_name": connection_name or "tenant-mock",
                    "fqdn": fqdn or "sip.livekit.cloud",
                    "active": True,
                    "transport_protocol": "UDP",
                }
            ]

        try:
            params: dict[str, str] = {}
            if connection_name:
                params["filter[connection_name]"] = connection_name
            if fqdn:
                params["filter[fqdn]"] = fqdn
            resp = self.client.get(
                f"{TELNYX_API_BASE_URL}/fqdn_connections",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data if isinstance(data, list) else []
        except httpx.HTTPError as e:
            raise TelephonyError(
                status=502,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message="Failed to list Telnyx FQDN connections.",
            ) from e

    def list_fqdns(
        self,
        *,
        connection_id: str | None = None,
        fqdn: str | None = None,
    ) -> list[dict[str, Any]]:
        """List Telnyx FQDN child records attached to FQDN connections."""
        if self.mock_mode:
            return [
                {
                    "id": "fqdn_record_mock_123",
                    "connection_id": connection_id or "fqdn_conn_mock_123",
                    "fqdn": fqdn or "sip.livekit.cloud",
                    "port": 5060,
                    "dns_record_type": "a",
                }
            ]

        try:
            params: dict[str, str] = {}
            if connection_id:
                params["filter[connection_id]"] = connection_id
            if fqdn:
                params["filter[fqdn]"] = fqdn
            resp = self.client.get(
                f"{TELNYX_API_BASE_URL}/fqdns",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data if isinstance(data, list) else []
        except httpx.HTTPError as e:
            raise TelephonyError(
                status=502,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message="Failed to list Telnyx FQDN targets.",
            ) from e

    def _ensure_fqdn_target(self, connection_id: str, fqdn: str) -> None:
        """Ensure the Telnyx FQDN connection has the expected routable target."""
        existing = self.list_fqdns(connection_id=connection_id)
        target = next(
            (item for item in existing if str(item.get("fqdn") or "") == fqdn), None
        )
        if target:
            return

        if existing:
            fqdn_id = existing[0].get("id")
            if fqdn_id:
                resp = self.client.patch(
                    f"{TELNYX_API_BASE_URL}/fqdns/{fqdn_id}",
                    headers=self._headers(),
                    json={
                        "connection_id": connection_id,
                        "fqdn": fqdn,
                        "dns_record_type": "a",
                        "port": 5060,
                    },
                )
                resp.raise_for_status()
                return

        resp = self.client.post(
            f"{TELNYX_API_BASE_URL}/fqdns",
            headers=self._headers(),
            json={
                "connection_id": connection_id,
                "fqdn": fqdn,
                "dns_record_type": "a",
                "port": 5060,
            },
        )
        resp.raise_for_status()

>>>>>>> Stashed changes
    def create_or_get_outbound_voice_profile(
        self, name: str, fqdn_connection_id: str
    ) -> dict[str, Any]:
        """Create or get an Outbound Voice Profile for SIP calling."""
        if self.mock_mode:
            return {
                "provider_outbound_voice_profile_id": "ovp_mock_123",
                "name": name,
                "status": "active",
            }

        try:
            payload = {
                "name": name,
                "connections": [fqdn_connection_id],
                "billing_group_id": None,
            }
            resp = self.client.post(
                f"{TELNYX_API_BASE_URL}/outbound_voice_profiles",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {
                "provider_outbound_voice_profile_id": data.get("id"),
                "name": data.get("name"),
                "status": "active" if data.get("active", True) else "disabled",
            }
        except httpx.HTTPError as e:
            raise TelephonyError(
                status=502,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message="Failed to create Telnyx Outbound Voice Profile.",
            ) from e

    def assign_phone_number_to_connection(
        self, provider_number_id: str, connection_id: str
    ) -> dict[str, Any]:
        """Attach a Telnyx-owned phone number to the tenant SIP/FQDN connection."""
        if self.mock_mode:
            return {
                "provider_number_id": provider_number_id,
                "connection_id": connection_id,
                "status": "active",
            }

        if not provider_number_id or not connection_id:
            raise TelephonyError(
                status=400,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message="provider_number_id and connection_id are required to bind a Telnyx number.",
            )

        try:
            resp = self.client.patch(
                f"{TELNYX_API_BASE_URL}/phone_numbers/{provider_number_id}",
                headers=self._headers(),
                json={"connection_id": connection_id},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {
                "provider_number_id": data.get("id") or provider_number_id,
                "connection_id": data.get("connection_id") or connection_id,
                "status": data.get("status", "active"),
            }
        except httpx.HTTPError as e:
            logger.error(
                "Telnyx number bind failed for %s: %s",
                provider_number_id,
                redact_sensitive_string(str(e)),
            )
            raise TelephonyError(
                status=502,
                code=TelephonyErrorCode.TELNYX_API_ERROR,
                message="Failed to assign Telnyx phone number to SIP connection.",
            ) from e

    def close(self):
        if self._owned_client:
            self.client.close()
