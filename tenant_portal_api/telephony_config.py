"""Runtime configuration helpers for telephony provider wiring."""

from __future__ import annotations

import os


def telephony_provider_mode() -> str:
    """Return the explicit telephony provider mode.

    Staging and production must run real providers unless the operator
    deliberately opts into local/test mock mode.
    """
    return os.getenv("TELEPHONY_PROVIDER_MODE", "real").strip().lower()


def is_mock_provider_mode() -> bool:
    return telephony_provider_mode() in {"mock", "test", "local"}


def require_real_provider_mode() -> bool:
    return not is_mock_provider_mode()


def telnyx_public_key() -> str:
    """Return the Telnyx API v2 webhook Ed25519 public key."""
    return os.getenv("TELNYX_PUBLIC_KEY", "").strip()


def livekit_sip_uri() -> str:
    """Platform LiveKit SIP URI that Telnyx FQDN connections must target for inbound PSTN."""
    return os.getenv("LIVEKIT_SIP_URI", "").strip()


def livekit_agent_name() -> str:
    """Named agent worker that telephony rooms must explicitly dispatch."""
    return os.getenv("LIVEKIT_AGENT_NAME", "uva-dev-agent").strip() or "uva-dev-agent"


def telnyx_sip_outbound_address() -> str:
    """SIP address LiveKit outbound trunks dial (Telnyx edge, not LiveKit)."""
    return os.getenv("TELNYX_SIP_OUTBOUND_ADDRESS", "sip.telnyx.com").strip() or "sip.telnyx.com"


def require_livekit_sip_uri() -> str:
    """Return LIVEKIT_SIP_URI or raise when real mode needs inbound Telnyx routing."""
    uri = livekit_sip_uri()
    if uri:
        return uri
    if is_mock_provider_mode():
        return "sip.livekit.cloud"
    from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode

    raise TelephonyError(
        status=503,
        code=TelephonyErrorCode.PROVIDER_CREDENTIALS_MISSING,
        message="LIVEKIT_SIP_URI is not configured for Telnyx inbound SIP routing.",
    )
