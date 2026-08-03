"""FastAPI routes for portal JWT and machine HMAC telephony operations.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
Full implementation of all 25 Portal routes and 26 Machine routes (27 SDK methods).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from tenant_portal_api.auth import TenantAuthError, verify_tenant_jwt
from tenant_portal_api.machine_auth import (
    MachineAuthError,
    verify_machine_request,
)
from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode
from tenant_portal_api.telephony_models import (
    AssignAgentBody,
    ConfigureNumberRoutingBody,
    ConfigureOutboundTrunkBody,
    ConnectTelnyxBody,
    CreateOutboundCallBody,
    ImportTelnyxNumberBody,
    PurchaseNumberBody,
    ReserveNumberBody,
    RotateTelnyxBody,
    SearchAvailableNumbersBody,
    UpsertOutboundVoiceProfileBody,
    UpsertSipConnectionBody,
)
from tenant_portal_api.telephony_service import TelephonyService

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from scripts.dbconn import conn_kwargs
except ImportError:
    from dbconn import conn_kwargs  # type: ignore # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control_plane.secrets import EnvSecretProvider  # noqa: E402
from control_plane.secrets_db import DbSecretProvider  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter()
_secrets = DbSecretProvider(env_fallback=EnvSecretProvider())
_service = TelephonyService()
MOCK_MACHINE_SIGNATURE = "valid_mock_signature"

TENANT_PORTAL_JWT_SECRET = os.environ.get("TENANT_PORTAL_JWT_SECRET", "mock_jwt_secret_for_tests")


def get_current_tenant_id(authorization: str | None = Header(None, alias="Authorization")) -> str:
    """Extract tenant_id from a required bearer tenant-portal JWT.

    Missing/invalid tokens are rejected (401). Explicit mock portal auth is only
    available when TELEPHONY_ALLOW_MOCK_PORTAL_AUTH=1 for offline unit tests.
    """
    if not authorization or not authorization.startswith("Bearer "):
        if os.environ.get("TELEPHONY_ALLOW_MOCK_PORTAL_AUTH") == "1":
            return "tenant_test_123"
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "telephony_auth_failed",
                    "message": "Authorization Bearer token is required",
                    "status": 401,
                }
            },
        )
    token = authorization[len("Bearer ") :].strip()
    try:
        claims = verify_tenant_jwt(token, TENANT_PORTAL_JWT_SECRET)
        tenant_id = claims.get("sub")
        if not tenant_id:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "telephony_auth_failed",
                        "message": "Token is missing tenant subject",
                        "status": 401,
                    }
                },
            )
        return str(tenant_id)
    except TenantAuthError as e:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "telephony_auth_failed", "message": e.reason, "status": 401}},
        ) from e


def get_db():
    """Dependency helper for tests that inject a DB connection."""
    return getattr(_service, "db_conn", None)


def _open_db():
    """Open a request-scoped DB connection for deployed machine auth."""
    return psycopg.connect(**conn_kwargs(), connect_timeout=3)


def _verify_machine(
    conn, tenant_id: str, ts: str, nonce: str, action: str, body: dict, signature: str
):
    """Verify machine HMAC request signature."""
    def reject(message: str = "Invalid signature") -> None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "telephony_auth_failed", "message": message, "status": 401}},
        )

    if not signature:
        reject()

    if not conn:
        # Offline route tests run without a database connection. Keep that test-only
        # path explicit so arbitrary signatures cannot pass in mock/no-DB mode.
        if os.environ.get("TELEPHONY_ALLOW_MOCK_MACHINE_AUTH") != "1":
            reject("Machine auth unavailable")
        if signature != MOCK_MACHINE_SIGNATURE:
            reject()
        return

    try:
        verify_machine_request(
            conn,
            _secrets,
            tenant_id=tenant_id,
            ts=ts,
            nonce=nonce,
            action=action,
            body=body,
            signature=signature,
        )
    except MachineAuthError as e:
        raise HTTPException(
            status_code=e.status,
            detail={"error": {"code": "telephony_auth_failed", "message": e.reason, "status": e.status}},
        ) from e

def _verify_machine_with_db(
    tenant_id: str, ts: str, nonce: str, action: str, body: dict, signature: str
):
    """Verify machine auth with an injected test connection or a deployed DB connection."""
    injected_conn = get_db()
    if injected_conn:
        _verify_machine(injected_conn, tenant_id, ts, nonce, action, body, signature)
        return

    if os.environ.get("TELEPHONY_ALLOW_MOCK_MACHINE_AUTH") == "1":
        _verify_machine(None, tenant_id, ts, nonce, action, body, signature)
        return

    with _open_db() as conn:
        _verify_machine(conn, tenant_id, ts, nonce, action, body, signature)
        conn.commit()


# ==========================================
# HEALTH (unauthenticated diagnostics)
# ==========================================

@router.get("/portal/telephony/health")
def portal_telephony_health():
    """Global telephony readiness for operators (no tenant secrets)."""
    from tenant_portal_api.telephony_health import check_global_telephony_health

    return check_global_telephony_health()


# ==========================================
# PORTAL ROUTES (JWT Authenticated)
# ==========================================

@router.get("/portal/telephony/telnyx/connection")
def portal_get_connection_status(tenant_id: str = Depends(get_current_tenant_id)):
    """Get active Telnyx connection status for current portal tenant."""
    try:
        return _service.get_connection_status(tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/telnyx/connect")
def portal_connect_telnyx(
    body: ConnectTelnyxBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Verify and connect Telnyx API key for portal tenant."""
    try:
        return _service.connect_telnyx_account(tenant_id, body.api_key, body.label)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/telnyx/rotate")
def portal_rotate_telnyx(
    body: RotateTelnyxBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Rotate Telnyx API key for portal tenant."""
    try:
        return _service.rotate_telnyx_account_key(tenant_id, body.api_key)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/telnyx/reverify")
def portal_reverify_telnyx(tenant_id: str = Depends(get_current_tenant_id)):
    """Re-verify permissions and platform status of existing connection."""
    try:
        return _service.reverify_telnyx_account(tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.delete("/portal/telephony/telnyx/connection")
def portal_disconnect_telnyx(tenant_id: str = Depends(get_current_tenant_id)):
    """Disconnect active Telnyx connection for portal tenant."""
    try:
        return _service.disconnect_telnyx_account(tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.get("/portal/telephony/telnyx/owned-numbers")
def portal_list_owned_numbers(
    country: str | None = None, tenant_id: str = Depends(get_current_tenant_id)
):
    """Fetch Telnyx-owned number inventory for connection."""
    try:
        return _service.list_telnyx_owned_numbers(tenant_id, country)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.get("/portal/telephony/numbers")
def portal_list_numbers(
    assigned_agent_id: str | None = None, tenant_id: str = Depends(get_current_tenant_id)
):
    """List managed phone numbers for portal tenant."""
    try:
        return _service.list_managed_numbers(tenant_id, assigned_agent_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/numbers/import")
def portal_import_number(
    body: ImportTelnyxNumberBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Import existing Telnyx-owned number into managed inventory."""
    try:
        return _service.import_telnyx_number(tenant_id, body.e164_number, body.external_customer_ref)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/numbers/sync")
def portal_sync_numbers(tenant_id: str = Depends(get_current_tenant_id)):
    """Sync managed numbers with provider inventory."""
    try:
        return _service.sync_telnyx_owned_numbers(tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.get("/portal/telephony/numbers/drift")
def portal_get_number_drift(tenant_id: str = Depends(get_current_tenant_id)):
    """Get configuration drift report for tenant numbers."""
    try:
        return _service.get_telnyx_number_drift(tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/available-numbers/search")
def portal_search_available_numbers(
    body: SearchAvailableNumbersBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Search available Telnyx numbers for purchase."""
    try:
        return _service.search_available_numbers(
            tenant_id, body.country, body.area_code, body.number_type, body.features
        )
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/number-reservations")
def portal_reserve_number(
    body: ReserveNumberBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Reserve number temporarily before purchase."""
    try:
        return _service.reserve_number(tenant_id, body.e164_number, body.idempotency_key)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/number-orders")
def portal_purchase_number(
    body: PurchaseNumberBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Idempotently purchase exact selected phone number."""
    try:
        return _service.purchase_number(
            tenant_id, body.e164_number, body.idempotency_key, body.external_customer_ref
        )
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.get("/portal/telephony/number-orders/{order_id}")
def portal_get_number_order(
    order_id: str, tenant_id: str = Depends(get_current_tenant_id)
):
    """Get purchase order status by ID."""
    try:
        return _service.get_number_order_status(tenant_id, order_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.patch("/portal/telephony/numbers/{number_id}/assignment")
def portal_assign_agent(
    number_id: str, body: AssignAgentBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Assign or unassign agent to phone number."""
    try:
        return _service.assign_agent_to_number(tenant_id, number_id, body.agent_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/telnyx/sip-connection")
def portal_upsert_sip_connection(
    body: UpsertSipConnectionBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Upsert Telnyx SIP/FQDN connection."""
    try:
        return _service.upsert_telnyx_sip_connection(
            tenant_id, body.sip_fqdn, body.sip_username, body.sip_secret
        )
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/telnyx/sip-connection/test")
def portal_verify_sip_connection(tenant_id: str = Depends(get_current_tenant_id)):
    """Test and verify SIP connection readiness."""
    try:
        return _service.verify_telnyx_sip_connection(tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/telnyx/outbound-voice-profile")
def portal_upsert_outbound_profile(
    body: UpsertOutboundVoiceProfileBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Upsert Outbound Voice Profile."""
    try:
        return _service.upsert_telnyx_outbound_voice_profile(
            tenant_id, body.allowed_destinations, body.concurrency_limit, body.daily_spending_limit
        )
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/telnyx/outbound-voice-profile/reverify")
def portal_verify_outbound_profile(tenant_id: str = Depends(get_current_tenant_id)):
    """Re-verify outbound voice profile readiness."""
    try:
        return _service.verify_telnyx_outbound_voice_profile(tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/numbers/{number_id}/routing/configure")
def portal_configure_routing(
    number_id: str, body: ConfigureNumberRoutingBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Configure inbound trunk and dispatch rule for phone number."""
    try:
        return _service.configure_number_routing(tenant_id, number_id, body.inbound_agent_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/telnyx/outbound-trunk/configure")
def portal_configure_outbound_trunk(
    body: ConfigureOutboundTrunkBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Configure long-lived outbound trunk."""
    try:
        return _service.configure_outbound_trunk(tenant_id, body.outbound_voice_profile_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.get("/portal/telephony/outbound-readiness")
def portal_get_outbound_readiness(tenant_id: str = Depends(get_current_tenant_id)):
    """Get outbound call readiness state for portal tenant."""
    try:
        return _service.get_outbound_readiness(tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/outbound-calls")
def portal_create_outbound_call(
    body: CreateOutboundCallBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Initiate outbound PSTN call."""
    try:
        return _service.create_outbound_call(
            tenant_id=tenant_id,
            agent_id=body.agent_id,
            from_number_id=body.from_number_id,
            to_number=body.to_number,
            idempotency_key=body.idempotency_key,
            recipient=body.recipient,
            context=body.context,
            external_customer_ref=body.external_customer_ref,
            external_workflow_ref=body.external_workflow_ref,
        )
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unhandled outbound call setup failure for tenant %s", tenant_id)
        err = TelephonyError(
            status=502,
            code=TelephonyErrorCode.CALL_SETUP_FAILED,
            message=f"Outbound call setup failed: {e}",
        )
        raise HTTPException(status_code=err.status, detail=err.to_dict())


@router.get("/portal/telephony/calls")
def portal_list_calls(
    assigned_agent_id: str | None = None, limit: int = 50, tenant_id: str = Depends(get_current_tenant_id)
):
    """List telephony call records."""
    try:
        return _service.list_call_records(tenant_id, assigned_agent_id, limit)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.get("/portal/telephony/calls/{telephony_call_id}")
def portal_get_call_detail(
    telephony_call_id: str, tenant_id: str = Depends(get_current_tenant_id)
):
    """Get telephony call details."""
    try:
        return _service.get_call_status(tenant_id, telephony_call_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/portal/telephony/numbers/{number_id}/disable")
def portal_disable_number(
    number_id: str, tenant_id: str = Depends(get_current_tenant_id)
):
    """Soft-disable managed phone number."""
    try:
        return _service.disable_number(tenant_id, number_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


# ==========================================
# MACHINE ROUTES (HMAC Authenticated - 27 SDK Methods / 26 Unique Endpoints)
# ==========================================

@router.post("/machine/telephony/telnyx/connect")
async def machine_connect_telnyx(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: connectTelnyxAccount (action: telephony.telnyx_connection.connect)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_connection.connect", body, x_signature)
    try:
        return _service.connect_telnyx_account(x_tenant_id, body.get("api_key", ""), body.get("label"))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/telnyx/rotate")
async def machine_rotate_telnyx(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: rotateTelnyxAccountKey (action: telephony.telnyx_connection.rotate)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_connection.rotate", body, x_signature)
    try:
        return _service.rotate_telnyx_account_key(x_tenant_id, body.get("api_key", ""))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/telnyx/reverify")
async def machine_reverify_telnyx(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: reverifyTelnyxAccount (action: telephony.telnyx_connection.reverify)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_connection.reverify", body, x_signature)
    try:
        return _service.reverify_telnyx_account(x_tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.delete("/machine/telephony/telnyx/connection")
async def machine_disconnect_telnyx(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: disconnectTelnyxAccount (action: telephony.telnyx_connection.disconnect)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_connection.disconnect", body, x_signature)
    try:
        return _service.disconnect_telnyx_account(x_tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.get("/machine/telephony/telnyx/connection")
async def machine_get_connection_status(
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: getConnectionStatus (action: telephony.telnyx_connection.status)"""
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_connection.status", {}, x_signature)
    try:
        return _service.get_connection_status(x_tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/telnyx/owned-numbers/list")
async def machine_list_owned_numbers(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: listTelnyxOwnedNumbers (action: telephony.telnyx_owned_numbers.list)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_owned_numbers.list", body, x_signature)
    try:
        return _service.list_telnyx_owned_numbers(x_tenant_id, body.get("filter_country"))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/numbers/list")
async def machine_list_numbers(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: listManagedPhoneNumbers (action: telephony.managed_numbers.list)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.managed_numbers.list", body, x_signature)
    try:
        return _service.list_managed_numbers(x_tenant_id, body.get("assigned_agent_id"))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/numbers/import")
async def machine_import_number(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: importTelnyxNumber (action: telephony.managed_numbers.import)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.managed_numbers.import", body, x_signature)
    try:
        return _service.import_telnyx_number(x_tenant_id, body.get("e164_number", ""), body.get("external_customer_ref"))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/numbers/sync")
async def machine_sync_numbers(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: syncTelnyxOwnedNumbers (action: telephony.managed_numbers.sync)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.managed_numbers.sync", body, x_signature)
    try:
        return _service.sync_telnyx_owned_numbers(x_tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/numbers/drift")
async def machine_get_number_drift(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: getTelnyxNumberDrift (action: telephony.managed_numbers.drift)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.managed_numbers.drift", body, x_signature)
    try:
        return _service.get_telnyx_number_drift(x_tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/available-numbers/search")
async def machine_search_numbers(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: searchAvailableNumbers (action: telephony.available_numbers.search)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.available_numbers.search", body, x_signature)
    try:
        return _service.search_available_numbers(
            x_tenant_id,
            body.get("country", "US"),
            body.get("area_code"),
            body.get("number_type"),
            body.get("features"),
            body.get("exact_phone_number"),
            body.get("limit"),
        )
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/number-reservations")
async def machine_reserve_number(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: reserveNumber (action: telephony.number_reservations.create)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.number_reservations.create", body, x_signature)
    try:
        return _service.reserve_number(x_tenant_id, body.get("e164_number", ""), body.get("idempotency_key", ""))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/number-orders")
async def machine_purchase_number(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: purchaseNumber (action: telephony.number_orders.create)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.number_orders.create", body, x_signature)
    try:
        return _service.purchase_number(
            x_tenant_id, body.get("e164_number", ""), body.get("idempotency_key", ""), body.get("external_customer_ref")
        )
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/number-orders/get")
async def machine_get_number_order(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: getNumberOrderStatus (action: telephony.number_orders.get)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.number_orders.get", body, x_signature)
    try:
        return _service.get_number_order_status(x_tenant_id, body.get("order_id", ""))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.patch("/machine/telephony/numbers/{number_id}/assignment")
async def machine_assign_agent(
    number_id: str,
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: assignAgentToNumber / unassignAgentFromNumber (action: telephony.numbers.assign_agent)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.numbers.assign_agent", body, x_signature)
    try:
        return _service.assign_agent_to_number(x_tenant_id, number_id, body.get("agent_id"))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/telnyx/sip-connection")
async def machine_upsert_sip_connection(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: upsertTelnyxSipConnection (action: telephony.telnyx_sip_connection.upsert)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_sip_connection.upsert", body, x_signature)
    try:
        return _service.upsert_telnyx_sip_connection(
            x_tenant_id,
            body.get("sip_fqdn"),
            body.get("sip_username"),
            body.get("sip_secret"),
        )
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/telnyx/sip-connection/test")
async def machine_verify_sip_connection(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: verifyTelnyxSipConnection (action: telephony.telnyx_sip_connection.test)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_sip_connection.test", body, x_signature)
    try:
        return _service.verify_telnyx_sip_connection(x_tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/telnyx/outbound-voice-profile")
async def machine_upsert_outbound_profile(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: upsertTelnyxOutboundVoiceProfile (action: telephony.telnyx_outbound_voice_profile.upsert)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_outbound_voice_profile.upsert", body, x_signature)
    try:
        return _service.upsert_telnyx_outbound_voice_profile(
            x_tenant_id, body.get("allowed_destinations"), body.get("concurrency_limit"), body.get("daily_spending_limit")
        )
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/telnyx/outbound-voice-profile/reverify")
async def machine_verify_outbound_profile(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: verifyTelnyxOutboundVoiceProfile (action: telephony.telnyx_outbound_voice_profile.reverify)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_outbound_voice_profile.reverify", body, x_signature)
    try:
        return _service.verify_telnyx_outbound_voice_profile(x_tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/numbers/{number_id}/routing/configure")
async def machine_configure_routing(
    number_id: str,
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: configureNumberRouting (action: telephony.number_routing.configure)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.number_routing.configure", body, x_signature)
    try:
        return _service.configure_number_routing(x_tenant_id, number_id, body.get("inbound_agent_id"))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/telnyx/outbound-trunk/configure")
async def machine_configure_outbound_trunk(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: configureOutboundTrunk (action: telephony.outbound_trunk.configure)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.outbound_trunk.configure", body, x_signature)
    try:
        return _service.configure_outbound_trunk(x_tenant_id, body.get("outbound_voice_profile_id"))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.get("/machine/telephony/outbound-readiness")
async def machine_get_outbound_readiness(
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: getOutboundReadiness (action: telephony.outbound_readiness.get)"""
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.outbound_readiness.get", {}, x_signature)
    try:
        return _service.get_outbound_readiness(x_tenant_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/outbound-calls")
async def machine_create_outbound_call(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: createOutboundCall (action: telephony.outbound_calls.create)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.outbound_calls.create", body, x_signature)
    try:
        return _service.create_outbound_call(
            tenant_id=x_tenant_id,
            agent_id=body.get("agent_id", ""),
            from_number_id=body.get("from_number_id", ""),
            to_number=body.get("to_number", ""),
            idempotency_key=body.get("idempotency_key", ""),
            recipient=body.get("recipient"),
            context=body.get("context", {}),
            external_customer_ref=body.get("external_customer_ref"),
            external_workflow_ref=body.get("external_workflow_ref"),
        )
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())
    except Exception as e:
        logger.exception("Unhandled machine outbound call setup failure for tenant %s", x_tenant_id)
        err = TelephonyError(
            status=502,
            code=TelephonyErrorCode.CALL_SETUP_FAILED,
            message=f"Outbound call setup failed: {e}",
        )
        raise HTTPException(status_code=err.status, detail=err.to_dict())


@router.post("/machine/telephony/calls/get")
async def machine_get_call_status(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: getCallStatus (action: telephony.calls.get)"""
    body = await request.json()
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.calls.get", body, x_signature)
    try:
        return _service.get_call_status(x_tenant_id, body.get("telephony_call_id", ""))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/calls/list")
async def machine_list_calls(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: listCallRecords (action: telephony.calls.list)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.calls.list", body, x_signature)
    try:
        return _service.list_call_records(x_tenant_id, body.get("assigned_agent_id"), body.get("limit", 50))
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())


@router.post("/machine/telephony/numbers/{number_id}/disable")
async def machine_disable_number(
    number_id: str,
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """SDK: disableNumber (action: telephony.numbers.disable)"""
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    _verify_machine_with_db(x_tenant_id, x_timestamp, x_nonce, "telephony.numbers.disable", body, x_signature)
    try:
        return _service.disable_number(x_tenant_id, number_id)
    except TelephonyError as e:
        raise HTTPException(status_code=e.status, detail=e.to_dict())
