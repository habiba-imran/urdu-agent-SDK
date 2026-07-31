"""Stable platform error codes and standardized exception mapping for telephony.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import re
from typing import Any


class TelephonyErrorCode:
    # Auth & Tenant
    TELEPHONY_AUTH_FAILED = "telephony_auth_failed"
    TENANT_NOT_ACTIVE = "tenant_not_active"
    TENANT_NOT_FOUND = "tenant_not_found"

    # Credentials
    TELNYX_CONNECTION_MISSING = "telnyx_connection_missing"
    TELNYX_KEY_INVALID = "telnyx_key_invalid"
    TELNYX_KEY_UNAUTHORIZED = "telnyx_key_unauthorized"
    TELNYX_KEY_PERMISSION_FAILED = "telnyx_key_permission_failed"
    TELNYX_KEY_COMPROMISED = "telnyx_key_compromised"
    PROVIDER_CREDENTIALS_MISSING = "provider_credentials_missing"

    # Validation & Readiness
    AGENT_NOT_FOUND = "agent_not_found"
    NUMBER_NOT_FOUND = "number_not_found"
    NUMBER_NOT_OWNED_BY_TENANT = "number_not_owned_by_tenant"
    NUMBER_NOT_ASSIGNED = "number_not_assigned"
    NUMBER_NOT_ROUTING_READY = "number_not_routing_ready"
    OUTBOUND_VOICE_PROFILE_MISSING = "outbound_voice_profile_missing"
    OUTBOUND_DESTINATION_DISABLED = "outbound_destination_disabled"
    OUTBOUND_SPENDING_LIMIT_REACHED = "outbound_spending_limit_reached"
    OUTBOUND_CONCURRENCY_LIMIT_REACHED = "outbound_concurrency_limit_reached"
    OUTBOUND_VERIFICATION_REQUIRED = "outbound_verification_required"
    INVALID_TO_NUMBER = "invalid_to_number"
    UNSUPPORTED_NUMBER_FEATURE = "unsupported_number_feature"
    OUTBOUND_NOT_READY = "outbound_not_ready"

    # Idempotency
    DUPLICATE_IDEMPOTENCY_KEY = "duplicate_idempotency_key"
    IDEMPOTENCY_PAYLOAD_MISMATCH = "idempotency_payload_mismatch"

    # Provider / API
    TELNYX_API_ERROR = "telnyx_api_error"
    TELNYX_RATE_LIMITED = "telnyx_rate_limited"
    NUMBER_NOT_AVAILABLE = "number_not_available"
    INSUFFICIENT_TELNYX_BALANCE = "insufficient_telnyx_balance"
    NUMBER_ORDER_ACTION_REQUIRED = "number_order_action_required"
    REGULATORY_ACTION_REQUIRED = "regulatory_action_required"
    PROVIDER_TIMEOUT = "provider_timeout"

    # LiveKit / SIP
    LIVEKIT_INBOUND_TRUNK_FAILED = "livekit_inbound_trunk_failed"
    LIVEKIT_OUTBOUND_TRUNK_FAILED = "livekit_outbound_trunk_failed"
    LIVEKIT_SIP_DISPATCH_RULE_FAILED = "livekit_sip_dispatch_rule_failed"
    LIVEKIT_AGENT_DISPATCH_FAILED = "livekit_agent_dispatch_failed"
    SIP_VERIFICATION_FAILED = "sip_verification_failed"
    SIP_MEDIA_FAILED = "sip_media_failed"

    # Runtime & Quota
    CALL_SETUP_FAILED = "call_setup_failed"
    CALL_STATE_CONFLICT = "call_state_conflict"
    QUOTA_RESERVATION_FAILED = "quota_reservation_failed"
    QUOTA_RELEASE_FAILED = "quota_release_failed"
    UNKNOWN_INBOUND_NUMBER = "unknown_inbound_number"
    ROUTING_IDENTIFIER_MISMATCH = "routing_identifier_mismatch"
    ASSIGNED_AGENT_LOAD_FAILED = "assigned_agent_load_failed"
    PROVIDER_PIPELINE_START_FAILED = "provider_pipeline_start_failed"
    WORKER_METADATA_MISSING = "worker_metadata_missing"
    WORKER_SESSION_FAILED = "worker_session_failed"

    # Webhooks
    WEBHOOK_SIGNATURE_INVALID = "webhook_signature_invalid"
    WEBHOOK_DUPLICATE = "webhook_duplicate"
    WEBHOOK_UNMAPPED_PROVIDER_ID = "webhook_unmapped_provider_id"

    # Data Governance
    RETENTION_POLICY_VIOLATION = "retention_policy_violation"
    EXPORT_NOT_AUTHORIZED = "export_not_authorized"
    RESTRICTED_PAYLOAD_ACCESS_DENIED = "restricted_payload_access_denied"


class TelephonyError(Exception):
    """Base exception for platform telephony errors with HTTP status and stable code."""

    def __init__(self, status: int, code: str, message: str, detail: Any = None):
        super().__init__(f"{status} [{code}]: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": redact_sensitive_string(self.message),
                "status": self.status,
            }
        }


_SENSITIVE_PATTERNS = [
    re.compile(r"KEY[A-Za-z0-9_\-]{16,}", re.IGNORECASE),
    re.compile(r"KEY01[A-Za-z0-9_\-]{10,}", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"secret[A-Za-z0-9_\-]{10,}", re.IGNORECASE),
]


def redact_sensitive_string(text: str) -> str:
    """Mask raw Telnyx API keys, tokens, or secrets from error messages."""
    if not text:
        return ""
    result = text
    for pat in _SENSITIVE_PATTERNS:
        result = pat.sub("[REDACTED]", result)
    return result
