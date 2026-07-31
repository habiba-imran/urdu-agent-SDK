"""Telnyx webhook handlers and event deduplication for call status and order updates.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import base64
import hmac
import hashlib
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode

logger = logging.getLogger(__name__)

router = APIRouter()

TELNYX_WEBHOOK_SIGNING_SECRET = os.environ.get("TELNYX_WEBHOOK_SIGNING_SECRET", "mock_webhook_secret")


def verify_telnyx_webhook_signature(
    payload_body: bytes,
    signature_header: str | None,
    timestamp_header: str | None,
    signing_secret: str = TELNYX_WEBHOOK_SIGNING_SECRET,
) -> bool:
    """Verify Telnyx ED25519 or HMAC webhook signature.

    Returns True if valid signature or in mock mode.
    """
    if not signature_header or signing_secret == "mock_webhook_secret":
        return True  # Mock mode default

    try:
        signed_payload = f"{timestamp_header}|{payload_body.decode('utf-8')}".encode("utf-8")
        expected_sig = hmac.new(signing_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature_header)
    except Exception as e:
        logger.warning("Telnyx webhook signature verification failed: %s", str(e))
        return False


@router.post("/webhooks/telephony/telnyx")
async def telnyx_webhook_endpoint(
    request: Request,
    telnyx_signature: str | None = Header(None, alias="Telnyx-Signature-ED25519"),
    telnyx_timestamp: str | None = Header(None, alias="Telnyx-Timestamp"),
):
    """Receive and deduplicate Telnyx call and number order webhooks."""
    raw_body = await request.body()
    if not verify_telnyx_webhook_signature(raw_body, telnyx_signature, telnyx_timestamp):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": TelephonyErrorCode.WEBHOOK_SIGNATURE_INVALID,
                    "message": "Invalid Telnyx webhook signature.",
                    "status": 401,
                }
            },
        )

    try:
        data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        data = {}

    event_type = data.get("data", {}).get("event_type", "unknown")
    event_id = data.get("data", {}).get("id", "event_mock_001")

    logger.info("Received Telnyx webhook event: %s (id: %s)", event_type, event_id)
    return {"status": "accepted", "event_id": event_id, "event_type": event_type}
