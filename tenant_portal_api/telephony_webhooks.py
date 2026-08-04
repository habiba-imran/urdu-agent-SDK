"""Telnyx webhook handlers and event deduplication for call status and order updates.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Header, HTTPException, Request

from tenant_portal_api.telephony_config import is_mock_provider_mode, telnyx_public_key
from tenant_portal_api.telephony_errors import TelephonyErrorCode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from scripts.dbconn import conn_kwargs
except ImportError:
    from dbconn import conn_kwargs  # type: ignore # noqa: E402

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
    configured_public_key = (
        public_key if public_key is not None else telnyx_public_key()
    )
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
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature, signed_payload
        )
    except (ValueError, InvalidSignature, TypeError) as exc:
        logger.warning(
            "Telnyx webhook signature verification failed: %s", exc.__class__.__name__
        )
        return False

    _seen_webhook_signatures.add(replay_key)
    return True


def _apply_webhook_side_effects(conn: Any, event_type: str, payload: dict) -> None:
    """Best-effort durable updates for number-order and call webhook events."""
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    event_payload = (
        data.get("payload") if isinstance(data.get("payload"), dict) else data
    )
    provider_order_id = (
        event_payload.get("order_id") or event_payload.get("id") or data.get("id")
    )
    provider_status = str(event_payload.get("status") or "").lower()

    if event_type.startswith("number_order.") and provider_order_id:
        platform_status = (
            "purchased" if provider_status in {"success", "completed"} else "pending"
        )
        if provider_status in {"failure", "failed"}:
            platform_status = "failed"
        conn.execute(
            """
            update telephony_number_orders
            set provider_status = %s,
                platform_status = %s,
                raw_provider_status = %s,
                updated_at = now()
            where provider_order_id = %s
            """,
            (
                provider_status or None,
                platform_status,
                provider_status or None,
                str(provider_order_id),
            ),
        )

    if event_type.startswith("call."):
        call_control_id = str(
            event_payload.get("call_control_id")
            or event_payload.get("call_session_id")
            or ""
        )
        if call_control_id:
            mapped = {
                "call.initiated": "dialing",
                "call.answered": "in_progress",
                "call.hangup": "completed",
                "call.bridged": "in_progress",
            }.get(event_type)
            if mapped:
                conn.execute(
                    """
                    update telephony_calls
                    set platform_status = %s,
                        provider_status = %s,
                        updated_at = now()
                    where livekit_sip_call_id = %s or livekit_sip_call_id_full = %s
                    """,
                    (mapped, event_type, call_control_id, call_control_id),
                )


@router.post("/webhooks/telephony/telnyx")
async def telnyx_webhook_endpoint(
    request: Request,
    telnyx_signature: str | None = Header(None, alias="Telnyx-Signature-Ed25519"),
    telnyx_timestamp: str | None = Header(None, alias="Telnyx-Timestamp"),
):
    """Receive and deduplicate Telnyx call and number order webhooks."""
    raw_body = await request.body()
    if not verify_telnyx_webhook_signature(
        raw_body, telnyx_signature, telnyx_timestamp
    ):
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

    if not is_mock_provider_mode():
        try:
            with psycopg.connect(**conn_kwargs(), connect_timeout=3) as conn:
                existing = conn.execute(
                    """
                    select 1 from telephony_call_events
                    where source = 'telnyx' and provider_event_id = %s
                    limit 1
                    """,
                    (str(event_id),),
                ).fetchone()
                if existing:
                    conn.commit()
                    return {
                        "status": "duplicate",
                        "event_id": event_id,
                        "event_type": event_type,
                    }

                # Attach to a matching call when possible; otherwise skip event insert
                # (provider_event_id uniqueness still guarded by process-local set).
                matched = conn.execute(
                    """
                    select id, tenant_id from telephony_calls
                    where livekit_sip_call_id = %s or livekit_sip_call_id_full = %s
                    order by created_at desc limit 1
                    """,
                    (
                        str(
                            data.get("data", {})
                            .get("payload", {})
                            .get("call_control_id")
                            or ""
                        ),
                        str(
                            data.get("data", {})
                            .get("payload", {})
                            .get("call_control_id")
                            or ""
                        ),
                    ),
                ).fetchone()
                if matched:
                    conn.execute(
                        """
                        insert into telephony_call_events (
                            tenant_id, telephony_call_id, source, event_type, provider_event_id, payload
                        ) values (%s, %s, 'telnyx', %s, %s, %s::jsonb)
                        on conflict do nothing
                        """,
                        (
                            matched[1],
                            matched[0],
                            event_type,
                            str(event_id),
                            json.dumps(data),
                        ),
                    )
                _apply_webhook_side_effects(conn, event_type, data)
                conn.commit()
        except Exception as exc:
            logger.warning(
                "Telnyx webhook durable processing failed: %s", exc.__class__.__name__
            )

    logger.info("Received Telnyx webhook event: %s (id: %s)", event_type, event_id)
    return {"status": "accepted", "event_id": event_id, "event_type": event_type}
