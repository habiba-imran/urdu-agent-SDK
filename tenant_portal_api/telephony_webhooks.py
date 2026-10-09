"""Telnyx webhook handlers and event deduplication for call status and order updates.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from collections import OrderedDict
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from tenant_portal_api.telephony_config import is_mock_provider_mode, telnyx_public_key
from tenant_portal_api.telephony_errors import TelephonyErrorCode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from scripts.dbconn import conn_kwargs
except ImportError:
    from dbconn import conn_kwargs  # type: ignore # noqa: E402

logger = logging.getLogger(__name__)

# F-M4: Telnyx webhooks are a few KB; 256 KiB is generous and bounded.
MAX_WEBHOOK_BODY_BYTES = 256 * 1024

router = APIRouter()

_WEBHOOK_REPLAY_WINDOW_SEC = 300
# F-H5: these grew without bound and reset on every deploy. Bounded LRUs now — still
# per-process (durable dedup is the database's job, below), but no longer a slow leak.
_MAX_SEEN_ENTRIES = 20_000
_seen_webhook_signatures: OrderedDict[tuple[str, str], None] = OrderedDict()
_seen_webhook_event_ids: OrderedDict[str, None] = OrderedDict()


# Audit §5a: "None at all on /portal/login, /admin/login, /portal/telephony/outbound-calls,
# or the Telnyx webhook". Logins are F-H14 and outbound calls are inside F-H17; this is the
# webhook itself. Unauthenticated endpoint, so the bucket is the caller's IP and it is
# checked before signature verification does any cryptographic work.
WEBHOOK_RATE_LIMIT_PER_MIN = 600  # Telnyx bursts on call state; generous but finite
_webhook_hits: OrderedDict[str, list[float]] = OrderedDict()
_webhook_hits_lock = threading.Lock()


def _webhook_rate_limited(client_ip: str) -> bool:
    now = time.time()
    with _webhook_hits_lock:
        window = _webhook_hits.setdefault(client_ip, [])
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= WEBHOOK_RATE_LIMIT_PER_MIN:
            return True
        window.append(now)
        _webhook_hits.move_to_end(client_ip)
        while len(_webhook_hits) > _MAX_SEEN_ENTRIES:
            _webhook_hits.popitem(last=False)
    return False


def _remember(seen: OrderedDict, key) -> None:
    seen[key] = None
    seen.move_to_end(key)
    while len(seen) > _MAX_SEEN_ENTRIES:
        seen.popitem(last=False)


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _extract_call_error_details(event_type: str, payload: dict[str, Any]) -> tuple[str | None, str | None]:
    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
    # Accept either the outer ``data`` object or the inner ``data.payload`` — callers pass
    # the inner one, which previously meant hangup_cause / sip codes were never read.
    payload_detail = (
        payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    )
    code = _first_non_empty(
        payload_detail.get("sip_response_code"),
        payload_detail.get("hangup_cause"),
        payload_detail.get("hangup_cause_code"),
        payload_detail.get("failure_code"),
        payload_detail.get("error_code"),
        detail.get("code"),
    )
    message = _first_non_empty(
        payload_detail.get("sip_reason"),
        payload_detail.get("failure_reason"),
        payload_detail.get("hangup_cause"),
        payload_detail.get("hangup_source"),
        payload_detail.get("error_message"),
        payload_detail.get("detail"),
        detail.get("message"),
        detail.get("reason"),
    )
    if not code and not message and (
        ".fail" in event_type or ".failed" in event_type or ".error" in event_type
    ):
        message = event_type
    benign_markers = {"normal_clearing", "normal clearing", "completed", "success", "ok"}
    if code and code.strip().lower() in benign_markers:
        code = None
    if message and message.strip().lower() in benign_markers:
        message = None
    return code, message


_TERMINAL_STATUSES = ("completed", "busy", "no_answer", "failed", "cancelled")


def _map_call_platform_status(event_type: str, provider_status: str, error_code: str | None) -> str | None:
    normalized_event = event_type.lower()
    normalized_status = provider_status.lower()
    if normalized_event == "call.initiated":
        return "dialing"
    if normalized_event == "call.ringing":
        return "ringing"
    if normalized_event in {"call.answered", "call.bridged"}:
        return "in_progress"
    if "busy" in normalized_event or "busy" in normalized_status:
        return "busy"
    if "no_answer" in normalized_event or "no-answer" in normalized_event or "no answer" in normalized_status:
        return "no_answer"
    if "cancel" in normalized_event or "cancel" in normalized_status:
        return "cancelled"
    if ".fail" in normalized_event or ".error" in normalized_event or error_code:
        return "failed"
    if normalized_event == "call.hangup":
        return "failed" if error_code else "completed"
    return None


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
    # M4-F01: never soft-accept on hosted — defense in depth beyond startup assert.
    from control_plane.runtime_env import is_hosted

    if is_mock_provider_mode() and not configured_public_key:
        if is_hosted():
            return False
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

    _remember(_seen_webhook_signatures, replay_key)
    return True


def _apply_webhook_side_effects(
    conn: Any,
    event_type: str,
    payload: dict,
    matched_call: tuple[str, str] | None = None,
) -> None:
    """Durable updates for number-order and call webhook events.

    ``matched_call`` is ``(call_id, tenant_id)`` already resolved by the caller. When
    omitted (direct callers / tests) the call is resolved here via
    :mod:`telephony_call_correlation` — never by comparing Telnyx ids to LiveKit ids.
    """
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
        _apply_call_event(
            conn,
            event_type,
            payload if isinstance(payload, dict) else {},
            event_payload,
            provider_status,
            matched_call,
        )


def _resolve_call_event(conn: Any, payload: dict[str, Any]) -> tuple[str, str] | None:
    """A-01.1: correlate a Telnyx call event to a telephony_calls row (never by LiveKit id)."""
    from tenant_portal_api.telephony_call_correlation import (
        extract_call_identity,
        resolve_call_for_event,
    )

    return resolve_call_for_event(conn, extract_call_identity(payload))


def _apply_call_event(
    conn: Any,
    event_type: str,
    payload: dict[str, Any],
    event_payload: dict[str, Any],
    provider_status: str,
    matched_call: tuple[str, str] | None,
) -> None:
    if matched_call is None:
        matched_call = _resolve_call_event(conn, payload)
    if matched_call is None:
        logger.warning(
            "unmatched Telnyx call event type=%s call_control_id=%s — no telephony_calls row "
            "correlates (claimed, not applied)",
            event_type,
            event_payload.get("call_control_id") or "-",
        )
        return

    call_id, tenant_id = matched_call
    error_code, error_message = _extract_call_error_details(event_type, event_payload)
    # Telnyx call events carry ``state`` (and ``hangup_cause`` on hangup), not ``status``.
    provider_status = provider_status or _first_non_empty(
        event_payload.get("state"), event_payload.get("hangup_cause")
    ) or ""
    status_text = " ".join(
        s for s in (
            provider_status,
            str(event_payload.get("hangup_cause") or ""),
            str(event_payload.get("sip_hangup_cause") or ""),
        ) if s
    ).lower()
    mapped = _map_call_platform_status(event_type, status_text or event_type, error_code)
    if not mapped:
        return

    terminal = mapped in _TERMINAL_STATUSES
    answered = mapped == "in_progress"
    # Param order is load-bearing for the test fakes: params[0] == mapped, params[-1] == call id.
    conn.execute(
        """
        update telephony_calls
        set platform_status = case
                when telephony_calls.platform_status in ('completed', 'busy', 'no_answer', 'failed', 'cancelled')
                  and %s not in ('completed', 'busy', 'no_answer', 'failed', 'cancelled')
                then telephony_calls.platform_status
                else %s
            end,
            provider_status = %s,
            error_code = coalesce(%s, error_code),
            error_message = coalesce(%s, error_message),
            started_at = coalesce(started_at, now()),
            answered_at = case
                when %s and answered_at is null then now()
                else answered_at
            end,
            ended_at = case
                when %s and ended_at is null then now()
                else ended_at
            end,
            duration_sec = case
                when %s and duration_sec is null and answered_at is not null
                then greatest(0, extract(epoch from (now() - answered_at)))::int
                else duration_sec
            end,
            updated_at = now()
        where id = %s
        """,
        (
            mapped,
            mapped,
            provider_status or event_type,
            error_code,
            error_message,
            answered,
            terminal,
            terminal,
            call_id,
        ),
    )

    if terminal:
        # A-01.2: the reservation taken in create_outbound_call / resolve_inbound_sip_call
        # was never released anywhere. Idempotent via quota_released_at, so a worker-side
        # release landing later is safe too.
        from tenant_portal_api import telephony_queries as queries

        released = queries.release_call_quota_once(conn, call_id, tenant_id)
        logger.info(
            "telephony call terminal call_id=%s tenant=%s status=%s quota_released=%s",
            call_id,
            tenant_id,
            mapped,
            released,
        )



def _persist_telnyx_webhook_event(
    event_id: str,
    event_type: str,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    with psycopg.connect(**conn_kwargs(), connect_timeout=3) as conn:
        # M4-F02: claim the provider event id in a durable inbox BEFORE side effects,
        # including when no telephony_calls row matches yet.
        try:
            claimed = conn.execute(
                """
                insert into telephony_webhook_claims (provider_event_id, event_type, payload)
                values (%s, %s, %s::jsonb)
                on conflict (provider_event_id) do nothing
                returning provider_event_id
                """,
                (str(event_id), event_type, json.dumps(data)),
            ).fetchone()
            if not claimed:
                conn.commit()
                return {
                    "status": "duplicate",
                    "event_id": event_id,
                    "event_type": event_type,
                }
        except psycopg.errors.UndefinedTable:
            # Migration 0038 not applied yet — fall through to call_events-only path.
            conn.rollback()
            logger.warning(
                "telephony_webhook_claims missing — apply migration 0038; "
                "using legacy call_events dedupe only"
            )

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

        # A-01.1: Telnyx ids are not LiveKit ids. Correlate (and bind on first contact)
        # through telephony_call_correlation; only call.* events have a call to match.
        matched: tuple[str, str] | None = None
        if event_type.startswith("call."):
            matched = _resolve_call_event(conn, data)
        if matched:
            tenant_id = matched[1]
            try:
                inserted = conn.execute(
                    """
                    insert into telephony_call_events (
                        tenant_id, telephony_call_id, source, event_type, provider_event_id, payload
                    ) values (%s, %s, 'telnyx', %s, %s, %s::jsonb)
                    on conflict do nothing
                    returning id
                    """,
                    (
                        tenant_id,
                        matched[0],
                        event_type,
                        str(event_id),
                        json.dumps(data),
                    ),
                ).fetchone()
                if not inserted:
                    logger.info(
                        "Skipping duplicate webhook event %s for tenant %s",
                        event_id,
                        tenant_id,
                    )
                    conn.commit()
                    return {
                        "status": "duplicate",
                        "event_id": event_id,
                        "event_type": event_type,
                    }
            except Exception:
                # P3-H2 / F-H6: abort side effects and let the outer endpoint return 500
                # so Telnyx retries. Never mutate call status/quota without a durable row.
                logger.error(
                    "webhook event insert failed tenant=%s event_id=%s type=%s — "
                    "aborting side effects",
                    tenant_id,
                    event_id,
                    event_type,
                    exc_info=True,
                )
                raise
        _apply_webhook_side_effects(conn, event_type, data, matched_call=matched)
        conn.commit()
    return None



@router.post("/webhooks/telephony/telnyx")
async def telnyx_webhook_endpoint(
    request: Request,
    telnyx_signature: str | None = Header(None, alias="Telnyx-Signature-Ed25519"),
    telnyx_timestamp: str | None = Header(None, alias="Telnyx-Timestamp"),
):
    """Receive and deduplicate Telnyx call and number order webhooks."""
    client_ip = request.client.host if request.client else "unknown"
    if _webhook_rate_limited(client_ip):
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": TelephonyErrorCode.WEBHOOK_SIGNATURE_INVALID,
                    "message": "Too many webhook requests.",
                    "status": 429,
                }
            },
        )
    # F-M4: this endpoint is unauthenticated (the signature is verified below, after the
    # body is read), so an arbitrarily large body used to be pulled into memory first.
    # Telnyx webhook payloads are a few KB; anything near the cap is not one.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="webhook payload too large")
    raw_body = await request.body()
    if len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        # Chunked requests have no content-length to check up front.
        raise HTTPException(status_code=413, detail="webhook payload too large")
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
    _remember(_seen_webhook_event_ids, event_id)

    if not is_mock_provider_mode():
        try:
            duplicate = await run_in_threadpool(
                _persist_telnyx_webhook_event,
                str(event_id),
                event_type,
                data,
            )
            if duplicate:
                return duplicate
        except Exception as exc:
            # F-H6: this used to log and fall through to HTTP 200, so the provider never
            # retried and the event was lost for good — taking call terminal status and
            # quota release with it. Forget the id first, or the retry we are now asking
            # for would be rejected as a duplicate by the in-memory guard above.
            _seen_webhook_event_ids.pop(event_id, None)
            logger.error(
                "Telnyx webhook durable write failed for event %s (%s) - asking the "
                "provider to retry",
                event_id,
                exc.__class__.__name__,
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": TelephonyErrorCode.WEBHOOK_PERSIST_FAILED,
                        "message": "Webhook could not be recorded; retry expected.",
                        "status": 500,
                    }
                },
            ) from exc

    logger.info("Received Telnyx webhook event: %s (id: %s)", event_type, event_id)
    return {"status": "accepted", "event_id": event_id, "event_type": event_type}
