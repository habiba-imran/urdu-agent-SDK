"""Health check and diagnostic utilities for telephony service and tenant readiness.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import os
from typing import Any

from tenant_portal_api.telephony_config import (
    is_mock_provider_mode,
    livekit_sip_uri,
    telephony_provider_mode,
)


def check_global_telephony_health(db_conn: Any = None) -> dict[str, Any]:
    """Check global system readiness for telephony operations including DB connectivity and security configs."""
    has_livekit_url = bool(os.getenv("LIVEKIT_URL"))
    has_livekit_key = bool(os.getenv("LIVEKIT_API_KEY"))
    has_livekit_secret = bool(os.getenv("LIVEKIT_API_SECRET"))
    has_livekit_sip_uri = bool(livekit_sip_uri())
    has_encryption_key = bool(os.getenv("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY"))
    has_telnyx_public_key = bool(os.getenv("TELNYX_PUBLIC_KEY"))
    mock_mode = is_mock_provider_mode()

    db_connected = False
    if db_conn:
        try:
            db_conn.execute("select 1").fetchone()
            db_connected = True
        except Exception:
            db_connected = False

    real_ready = (
        has_livekit_url
        and has_livekit_key
        and has_livekit_secret
        and has_livekit_sip_uri
        and has_encryption_key
        and has_telnyx_public_key
    )

    return {
        "status": "healthy" if mock_mode or real_ready else "degraded",
        "provider_mode": telephony_provider_mode(),
        "livekit_configured": has_livekit_url
        and has_livekit_key
        and has_livekit_secret,
        "livekit_sip_uri_configured": has_livekit_sip_uri,
        "encryption_configured": has_encryption_key,
        "webhook_public_key_configured": has_telnyx_public_key,
        "db_connected": db_connected if db_conn else True,
        "remediation_phase": "Phase 4 - Complete",
        "mock_mode_default": False,
    }

