"""Telnyx webhook handlers and event deduplication for call status and order updates.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import base64
import json
import logging
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Header, HTTPException, Request

from tenant_portal_api.telephony_config import is_mock_provider_mode, telnyx_public_key
from tenant_portal_api.telephony_errors import TelephonyErrorCode

logger = logging.getLogger(__name__)

router = APIRouter()

_WEBHOOK_REPLAY_WINDOW_SEC = 300
_seen_webhook_signatures: set[tuple[str, str]] = set()
_seen_webhook_event_ids: set[str] = set()


def verify_telnyx_webhook_signature(
    payload_body: bytes,
    signature_header: str | None,
    timestamp_header: str | None,
    public_key: str | None = None,
) -> bool:
    """Verify a Telnyx API v2 Ed25519 webhook signature.

    Telnyx signs the exact string ``{timestamp}|{raw_body}`` and sends the
    base64-encoded Ed25519 signature in ``telnyx-signature-ed25519``. The
    public verification key comes from Mission Control and is configured as
    ``TELNYX_PUBLIC_KEY``.
    """
    configured_public_key = public_key if public_key is not None else telnyx_public_key()
    if is_mock_provider_mode() and not configured_public_key:
        return True
    if not configured_public_key or not signature_header or not timestamp_header:
        return False

    try:
        timestamp_int = int(timestamp_header)
    except (TypeError, ValueError):
        return False
    now = int(time.time())
    if abs(now - timestamp_int) > _WEBHOOK_REPLAY_WINDOW_SEC:
        return False

    replay_key = (timestamp_header, signature_header)
    if replay_key in _seen_webhook_signatures:
        return False

    try:
        public_key_bytes = base64.b64decode(configured_public_key, validate=True)
        signature = base64.b64decode(signature_header, validate=True)
        signed_payload = timestamp_header.encode("utf-8") + b"|" + payload_body
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, signed_payload)
    except (ValueError, InvalidSignature, TypeError) as exc:
        logger.warning("Telnyx webhook signature verification failed: %s", exc.__class__.__name__)
        return False

    _seen_webhook_signatures.add(replay_key)
    return True


@router.post("/webhooks/telephony/telnyx")
async def telnyx_webhook_endpoint(
    request: Request,
    telnyx_signature: str | None = Header(None, alias="Telnyx-Signature-Ed25519"),
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
    event_id = data.get("data", {}).get("id")
    if not event_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": TelephonyErrorCode.WEBHOOK_UNMAPPED_PROVIDER_ID,
                    "message": "Webhook event id is missing.",
                    "status": 400,
                }
            },
        )

    if event_id in _seen_webhook_event_ids:
        return {"status": "duplicate", "event_id": event_id, "event_type": event_type}
    _seen_webhook_event_ids.add(event_id)

    logger.info("Received Telnyx webhook event: %s (id: %s)", event_type, event_id)
    return {"status": "accepted", "event_id": event_id, "event_type": event_type}
