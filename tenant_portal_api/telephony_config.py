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
