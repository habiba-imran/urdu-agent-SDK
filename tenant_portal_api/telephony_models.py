"""Pydantic request and response schemas for telephony backend API routes.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# Connection Models
class ConnectTelnyxBody(BaseModel):
    api_key: str = Field(..., description="Telnyx API key")
    label: str | None = Field(None, description="Optional connection label")


class RotateTelnyxBody(BaseModel):
    api_key: str = Field(..., description="New Telnyx API key to rotate in")


class TelnyxConnectionResponse(BaseModel):
    id: str
    tenant_id: str
    label: str | None = None
    platform_status: str
    provider_status: str | None = None
    key_fingerprint: str | None = None
    telnyx_account_id: str | None = None
    last_verified_at: str | None = None
    permission_last_checked_at: str | None = None


# Number Models
class SearchAvailableNumbersBody(BaseModel):
    country: str = Field(..., description="ISO 2-letter country code (e.g. US, PK)")
    area_code: str | None = Field(None, description="Optional area code prefix")
    number_type: str | None = Field(None, description="local, toll_free, national, mobile")
    features: list[str] | None = Field(None, description="voice, sms, mms")


class AvailableNumberItem(BaseModel):
    e164_number: str
    country: str
    region: str | None = None
    number_type: str | None = None
    features: list[str] = Field(default_factory=list)
    upfront_cost: str | None = None
    monthly_cost: str | None = None
    currency: str = "USD"


class ReserveNumberBody(BaseModel):
    e164_number: str
    idempotency_key: str


class PurchaseNumberBody(BaseModel):
    e164_number: str
    external_customer_ref: str | None = None
    idempotency_key: str


class NumberOrderResponse(BaseModel):
    id: str
    tenant_id: str
    idempotency_key: str
    provider_order_id: str | None = None
    selected_e164_number: str
    platform_status: str
    provider_status: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str


class ImportTelnyxNumberBody(BaseModel):
    e164_number: str
    external_customer_ref: str | None = None


class AssignAgentBody(BaseModel):
    number_id: str
    agent_id: str | None = Field(None, description="Set agent_id to null to unassign")


class ManagedNumberResponse(BaseModel):
    id: str
    tenant_id: str
    provider_number_id: str | None = None
    e164_number: str
    country: str | None = None
    number_type: str | None = None
    features: list[str] = Field(default_factory=list)
    provisioning_status: str
    routing_status: str
    assigned_agent_id: str | None = None
    external_customer_ref: str | None = None
    disabled_at: str | None = None


# SIP & Voice Profile Models
class UpsertSipConnectionBody(BaseModel):
    sip_fqdn: str | None = None
    sip_username: str | None = None
    sip_secret: str | None = None


class UpsertOutboundVoiceProfileBody(BaseModel):
    allowed_destinations: list[str] = Field(default_factory=list)
    concurrency_limit: int | None = None
    daily_spending_limit: float | None = None


class TelephonyReadinessResponse(BaseModel):
    tenant_id: str
    is_ready: bool
    connection_status: str
    sip_status: str
    outbound_profile_status: str
    active_numbers_count: int
    reasons: list[str] = Field(default_factory=list)


# Call Orchestration Models
class CreateOutboundCallBody(BaseModel):
    agent_id: str
    from_number_id: str
    to_number: str
    recipient: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    external_customer_ref: str | None = None
    external_workflow_ref: str | None = None
    idempotency_key: str


class OutboundCallResponse(BaseModel):
    telephony_call_id: str
    session_id: str | None = None
    room_name: str
    platform_status: str
    direction: str = "outbound"
    error_code: str | None = None
    error_message: str | None = None


class TelephonyCallDetailResponse(BaseModel):
    id: str
    tenant_id: str
    session_id: str | None = None
    agent_id: str | None = None
    phone_number_id: str | None = None
    direction: str
    room_name: str
    from_number: str | None = None
    to_number: str | None = None
    recipient: str | None = None
    platform_status: str
    provider_status: str | None = None
    outcome: str | None = None
    duration_sec: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


# Machine Route Action Body Models
class GetNumberOrderStatusBody(BaseModel):
    order_id: str = Field(..., description="Target order ID")


class GetCallStatusBody(BaseModel):
    telephony_call_id: str = Field(..., description="Target call ID")


class ListCallRecordsBody(BaseModel):
    assigned_agent_id: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class ListManagedNumbersBody(BaseModel):
    assigned_agent_id: str | None = None


class ListTelnyxOwnedNumbersBody(BaseModel):
    filter_country: str | None = None


class ConfigureNumberRoutingBody(BaseModel):
    inbound_agent_id: str | None = None


class ConfigureOutboundTrunkBody(BaseModel):
    outbound_voice_profile_id: str | None = None
