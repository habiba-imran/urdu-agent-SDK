"""Unit tests for telephony scaffold, status enums, errors, and models.

Phase 2 verification suite.
"""

from tenant_portal_api.telephony_errors import (
    TelephonyError,
    TelephonyErrorCode,
    redact_sensitive_string,
)
from tenant_portal_api.telephony_models import (
    ConnectTelnyxBody,
    CreateOutboundCallBody,
    SearchAvailableNumbersBody,
)
from tenant_portal_api.telephony_status import (
    CallDirection,
    CallPublicStatus,
    ConnectionPlatformStatus,
    NumberOrderPlatformStatus,
    NumberProvisioningStatus,
    NumberRoutingStatus,
    validate_call_status_transition,
)


def test_telephony_status_enums():
    assert ConnectionPlatformStatus.ACTIVE == "active"
    assert NumberProvisioningStatus.OWNED == "owned"
    assert NumberRoutingStatus.READY == "ready"
    assert NumberOrderPlatformStatus.PURCHASED == "purchased"


def test_call_status_transitions():
    # Outbound valid transitions
    assert validate_call_status_transition(
        CallPublicStatus.QUEUED, CallPublicStatus.DIALING, CallDirection.OUTBOUND
    )
    assert validate_call_status_transition(
        CallPublicStatus.DIALING, CallPublicStatus.RINGING, CallDirection.OUTBOUND
    )
    assert validate_call_status_transition(
        CallPublicStatus.RINGING, CallPublicStatus.IN_PROGRESS, CallDirection.OUTBOUND
    )
    assert validate_call_status_transition(
        CallPublicStatus.IN_PROGRESS, CallPublicStatus.COMPLETED, CallDirection.OUTBOUND
    )

    # Idempotent same status
    assert validate_call_status_transition(
        CallPublicStatus.IN_PROGRESS,
        CallPublicStatus.IN_PROGRESS,
        CallDirection.OUTBOUND,
    )

    # Terminal state transition rejection
    assert not validate_call_status_transition(
        CallPublicStatus.COMPLETED, CallPublicStatus.IN_PROGRESS, CallDirection.OUTBOUND
    )
    assert not validate_call_status_transition(
        CallPublicStatus.FAILED, CallPublicStatus.RINGING, CallDirection.INBOUND
    )


def test_telephony_error_redaction():
    raw_msg = (
        "Telnyx key KEY011234567890abcdef failed authentication with Bearer eyJhbGciOi"
    )
    redacted = redact_sensitive_string(raw_msg)
    assert "KEY011234567890abcdef" not in redacted
    assert "[REDACTED]" in redacted

    err = TelephonyError(
        status=401,
        code=TelephonyErrorCode.TELNYX_KEY_INVALID,
        message=raw_msg,
    )
    serialized = err.to_dict()
    assert serialized["error"]["status"] == 401
    assert serialized["error"]["code"] == "telnyx_key_invalid"
    assert "KEY011234567890abcdef" not in serialized["error"]["message"]


def test_telephony_models_validation():
    body = ConnectTelnyxBody(api_key="KEY01_test_key", label="Test Connection")
    assert body.api_key == "KEY01_test_key"

    search = SearchAvailableNumbersBody(
        country="US", area_code="555", features=["voice"]
    )
    assert search.country == "US"

    call_body = CreateOutboundCallBody(
        agent_id="agent_123",
        from_number_id="num_456",
        to_number="+15551234567",
        idempotency_key="idempotency_123",
    )
    assert call_body.to_number == "+15551234567"
    assert call_body.idempotency_key == "idempotency_123"
