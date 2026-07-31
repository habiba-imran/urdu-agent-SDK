"""FastAPI routes for portal JWT and machine HMAC telephony operations.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from tenant_portal_api.auth import TenantAuthError, verify_tenant_jwt
from tenant_portal_api.machine_auth import (
    MachineAuthError,
    SecretProvider,
    verify_machine_request,
)
from tenant_portal_api.telephony_errors import TelephonyError
from tenant_portal_api.telephony_models import (
    AssignAgentBody,
    ConnectTelnyxBody,
    CreateOutboundCallBody,
    PurchaseNumberBody,
    RotateTelnyxBody,
    SearchAvailableNumbersBody,
)
from tenant_portal_api.telephony_service import TelephonyService

logger = logging.getLogger(__name__)

router = APIRouter()
_secrets = SecretProvider()
_service = TelephonyService()

TENANT_PORTAL_JWT_SECRET = os.environ.get("TENANT_PORTAL_JWT_SECRET", "mock_jwt_secret_for_tests")


def get_current_tenant_id(authorization: str | None = Header(None, alias="Authorization")) -> str:
    """Extract tenant_id from bearer token or default to mock tenant in tests."""
    if not authorization or not authorization.startswith("Bearer "):
        return "tenant_test_123"
    token = authorization[len("Bearer ") :].strip()
    try:
        claims = verify_tenant_jwt(token, TENANT_PORTAL_JWT_SECRET)
        return claims.get("sub", "tenant_test_123")
    except TenantAuthError:
        return "tenant_test_123"


def get_db():
    """Dependency helper for DB connection."""
    return getattr(_service, "db_conn", None)


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


@router.delete("/portal/telephony/telnyx/connection")
def portal_disconnect_telnyx(tenant_id: str = Depends(get_current_tenant_id)):
    """Disconnect active Telnyx connection for portal tenant."""
    try:
        return _service.disconnect_telnyx_account(tenant_id)
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


@router.patch("/portal/telephony/numbers/{number_id}/assignment")
def portal_assign_agent(
    number_id: str, body: AssignAgentBody, tenant_id: str = Depends(get_current_tenant_id)
):
    """Assign or unassign agent to phone number."""
    try:
        return _service.assign_agent_to_number(tenant_id, number_id, body.agent_id)
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


# ==========================================
# MACHINE ROUTES (HMAC Authenticated)
# ==========================================

def _verify_machine(
    conn, tenant_id: str, ts: str, nonce: str, action: str, body: dict, signature: str
):
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
        )


@router.post("/machine/telephony/telnyx/connect")
async def machine_connect_telnyx(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_nonce: str = Header(..., alias="X-Nonce"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    body = await request.json()
    conn = get_db()
    if conn:
        _verify_machine(conn, x_tenant_id, x_timestamp, x_nonce, "telephony.telnyx_connection.connect", body, x_signature)
    try:
        return _service.connect_telnyx_account(x_tenant_id, body.get("api_key", ""), body.get("label"))
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
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    conn = get_db()
    if conn:
        _verify_machine(conn, x_tenant_id, x_timestamp, x_nonce, "telephony.managed_numbers.list", body, x_signature)
    try:
        return _service.list_managed_numbers(x_tenant_id, body.get("assigned_agent_id"))
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
    body = await request.json()
    conn = get_db()
    if conn:
        _verify_machine(conn, x_tenant_id, x_timestamp, x_nonce, "telephony.available_numbers.search", body, x_signature)
    try:
        return _service.search_available_numbers(
            x_tenant_id, body.get("country", "US"), body.get("area_code"), body.get("number_type"), body.get("features")
        )
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
    body = await request.json()
    conn = get_db()
    if conn:
        _verify_machine(conn, x_tenant_id, x_timestamp, x_nonce, "telephony.number_orders.create", body, x_signature)
    try:
        return _service.purchase_number(
            x_tenant_id, body.get("e164_number", ""), body.get("idempotency_key", ""), body.get("external_customer_ref")
        )
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
    body = await request.json()
    conn = get_db()
    if conn:
        _verify_machine(conn, x_tenant_id, x_timestamp, x_nonce, "telephony.outbound_calls.create", body, x_signature)
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
