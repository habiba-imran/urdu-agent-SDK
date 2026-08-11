"""Platform status enums and transition rules for telephony resources.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

from enum import Enum


class ConnectionPlatformStatus(str, Enum):
    NOT_CONNECTED = "not_connected"
    VERIFYING = "verifying"
    ACTIVE = "active"
    VERIFICATION_FAILED = "verification_failed"
    ROTATION_REQUIRED = "rotation_required"
    PERMISSION_FAILED = "permission_failed"
    COMPROMISED = "compromised"
    DISABLED = "disabled"
    DISCONNECTED = "disconnected"


class NumberProvisioningStatus(str, Enum):
    DISCOVERED = "discovered"
    IMPORT_PENDING = "import_pending"
    IMPORTED = "imported"
    PURCHASE_PENDING = "purchase_pending"
    PURCHASE_FAILED = "purchase_failed"
    OWNED = "owned"
    PROVIDER_REMOVED = "provider_removed"
    SUSPENDED = "suspended"
    DISABLED = "disabled"
    RELEASED = "released"
    DELETED = "deleted"


class NumberRoutingStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    CONFIGURING = "configuring"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    DISABLED = "disabled"


class NumberOrderPlatformStatus(str, Enum):
    PENDING = "pending"
    PURCHASED = "purchased"
    CONFIGURING_ROUTING = "configuring_routing"
    READY = "ready"
    ACTION_REQUIRED = "action_required"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELETED = "deleted"


class SipConnectionPlatformStatus(str, Enum):
    DRAFT = "draft"
    PENDING_VERIFICATION = "pending_verification"
    TESTING = "testing"
    ACTIVE = "active"
    FAILED = "failed"
    DISABLED = "disabled"


class OutboundVoiceProfilePlatformStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    CONFIGURING = "configuring"
    ACTIVE = "active"
    DESTINATION_RESTRICTED = "destination_restricted"
    LIMIT_REACHED = "limit_reached"
    VERIFICATION_REQUIRED = "verification_required"
    FAILED = "failed"
    DISABLED = "disabled"


class CallDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallPublicStatus(str, Enum):
    QUEUED = "queued"
    DIALING = "dialing"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InternalStage(str, Enum):
    VALIDATING = "validating"
    QUOTA_RESERVED = "quota_reserved"
    SESSION_CREATED = "session_created"
    ROOM_CREATED = "room_created"
    LIVEKIT_AGENT_DISPATCH_CREATED = "livekit_agent_dispatch_created"
    SIP_PARTICIPANT_CREATED = "sip_participant_created"
    CLEANUP_STARTED = "cleanup_started"
    QUOTA_RELEASED = "quota_released"
    USAGE_RECORDED = "usage_recorded"


TERMINAL_CALL_STATUSES = {
    CallPublicStatus.COMPLETED,
    CallPublicStatus.BUSY,
    CallPublicStatus.NO_ANSWER,
    CallPublicStatus.FAILED,
    CallPublicStatus.CANCELLED,
}

VALID_OUTBOUND_TRANSITIONS = {
    CallPublicStatus.QUEUED: {
        CallPublicStatus.QUEUED,
        CallPublicStatus.DIALING,
        CallPublicStatus.FAILED,
        CallPublicStatus.CANCELLED,
    },
    CallPublicStatus.DIALING: {
        CallPublicStatus.DIALING,
        CallPublicStatus.RINGING,
        CallPublicStatus.IN_PROGRESS,
        CallPublicStatus.BUSY,
        CallPublicStatus.NO_ANSWER,
        CallPublicStatus.FAILED,
        CallPublicStatus.CANCELLED,
    },
    CallPublicStatus.RINGING: {
        CallPublicStatus.RINGING,
        CallPublicStatus.IN_PROGRESS,
        CallPublicStatus.BUSY,
        CallPublicStatus.NO_ANSWER,
        CallPublicStatus.FAILED,
        CallPublicStatus.CANCELLED,
    },
    CallPublicStatus.IN_PROGRESS: {
        CallPublicStatus.IN_PROGRESS,
        CallPublicStatus.COMPLETED,
        CallPublicStatus.FAILED,
        CallPublicStatus.CANCELLED,
    },
}

VALID_INBOUND_TRANSITIONS = {
    CallPublicStatus.RINGING: {
        CallPublicStatus.RINGING,
        CallPublicStatus.IN_PROGRESS,
        CallPublicStatus.FAILED,
        CallPublicStatus.CANCELLED,
    },
    CallPublicStatus.IN_PROGRESS: {
        CallPublicStatus.IN_PROGRESS,
        CallPublicStatus.COMPLETED,
        CallPublicStatus.FAILED,
        CallPublicStatus.CANCELLED,
    },
}


def validate_call_status_transition(
    current: CallPublicStatus, new_status: CallPublicStatus, direction: CallDirection
) -> bool:
    """Returns True if transition from `current` to `new_status` is valid for `direction`.

    Idempotent transition to the same status is always allowed.
    Terminal states cannot transition to any other status.
    """
    if current == new_status:
        return True

    if current in TERMINAL_CALL_STATUSES:
        return False

    if direction == CallDirection.OUTBOUND:
        allowed = VALID_OUTBOUND_TRANSITIONS.get(current, set())
        return new_status in allowed

    if direction == CallDirection.INBOUND:
        allowed = VALID_INBOUND_TRANSITIONS.get(current, set())
        return new_status in allowed

    return False
