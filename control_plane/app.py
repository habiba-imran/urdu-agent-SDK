"""FastAPI control-plane endpoint: POST /v1/session — the only endpoint that matters.

Reads the host-platform's HMAC-signed headers, runs the mint (all gates in mint.py), and returns
{token, wsUrl, roomName} or the appropriate 4xx. Adds a per-tenant-per-minute rate limit (P2-T06);
the origin allowlist is enforced inside the mint from the tenant's `allowed_origins`.

The endpoint is a sync `def` so FastAPI runs it in a threadpool — the mint uses sync psycopg, so
this keeps blocking DB work off the event loop without an async driver.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path

import aiohttp
import psycopg
from dotenv import dotenv_values
from fastapi import Body, FastAPI, Header, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from livekit import api
from pydantic import BaseModel

try:
    import sentry_sdk  # type: ignore
except ImportError:
    sentry_sdk = None


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from scripts.dbconn import conn_kwargs
except ImportError:
    from dbconn import conn_kwargs  # type: ignore # noqa: E402


from .mint import MintError, TTL_SEC, mint_session  # noqa: E402
from .runtime_env import is_hosted, resolve_allowed_origins  # noqa: E402
from .security_headers import SecurityHeadersMiddleware  # noqa: E402
from .mint_db import mint_db_connection  # noqa: E402
from .secrets import EnvSecretProvider  # noqa: E402
from .secrets_db import DbSecretProvider  # noqa: E402
from .warm import run_warm_probe  # noqa: E402


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from admin.audit import record_mint_rejection  # noqa: E402

# P9 FIX (2026-07-18): previously read LIVEKIT_* ONLY from a physical .env.local file --
# correct for local dev, silently empty in any deployed environment with no such file
# (dotenv_values() on a missing file returns {}, no error). Checks os.environ first now,
# matching control_plane/secrets.py::EnvSecretProvider's already-established pattern.
_ENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env.local")
_LK_URL = os.environ.get("LIVEKIT_URL") or _ENV.get("LIVEKIT_URL", "")
_LK_KEY = os.environ.get("LIVEKIT_API_KEY") or _ENV.get("LIVEKIT_API_KEY", "")
_LK_SECRET = os.environ.get("LIVEKIT_API_SECRET") or _ENV.get("LIVEKIT_API_SECRET", "")
_LK_AGENT_NAME = os.environ.get("LIVEKIT_AGENT_NAME") or _ENV.get(
    "LIVEKIT_AGENT_NAME", "uva-dev-agent"
)
RATE_LIMIT_PER_MIN = 120
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_mint_log = logging.getLogger("control_plane.mint")
_voices_log = logging.getLogger("control_plane.voices")


def _require_env() -> None:
    missing = [
        key
        for key, value in {
            "LIVEKIT_URL": _LK_URL,
            "LIVEKIT_API_KEY": _LK_KEY,
            "LIVEKIT_API_SECRET": _LK_SECRET,
            "SUPABASE_DB_URL": os.environ.get("SUPABASE_DB_URL")
            or _ENV.get("SUPABASE_DB_URL", ""),
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "control_plane startup blocked: missing required env var(s): "
            + ", ".join(missing)
        )


_require_env()

from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

_CORS_ORIGINS_RAW = os.environ.get("CP_ALLOWED_ORIGINS") or _ENV.get(
    "CP_ALLOWED_ORIGINS", ""
)
# F-C3: an unset CP_ALLOWED_ORIGINS used to mean allow_origins=["*"] WITH
# allow_credentials=True, in production as well as dev, so any website could drive this API
# from a visitor's browser. A hosted deployment must now name its origins; local development
# falls back to the usual localhost ports instead of the whole web.
_DEV_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_CORS_ORIGINS, _CORS_ALLOW_CREDENTIALS = resolve_allowed_origins(
    _CORS_ORIGINS_RAW,
    hosted=is_hosted(),
    dev_defaults=_DEV_DEFAULT_ORIGINS,
    var_name="CP_ALLOWED_ORIGINS",
    why=(
        "It is the browser origin allowlist for session minting; an empty value "
        "previously meant 'allow every origin, with credentials'."
    ),
)
if _CORS_ORIGINS == _DEV_DEFAULT_ORIGINS and not _CORS_ORIGINS_RAW.strip():
    logging.getLogger("control_plane").warning(
        "CP_ALLOWED_ORIGINS is not set - defaulting to local development origins (%s)",
        ", ".join(_CORS_ORIGINS),
    )


_SENTRY_DSN = os.environ.get("SENTRY_DSN") or _ENV.get("SENTRY_DSN", "")
if _SENTRY_DSN and sentry_sdk is not None:
    try:
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.1,
            environment=os.environ.get("ENVIRONMENT", "production"),
        )
    except Exception:
        # F-M1: a swallowed failure here means error reporting is off for the whole
        # service with nothing to show for it. Startup still proceeds — Sentry is not
        # required to mint sessions — but it must be visible in the logs.
        logging.getLogger("control_plane").warning(
            "sentry_sdk.init failed — error reporting is disabled", exc_info=True
        )


# F-M6: the interactive schema (including the dev-mint route) was public in production.
# Off by default on a hosted deployment; CP_ENABLE_DOCS=1 re-enables it deliberately.
_DOCS_ENABLED = (os.environ.get("CP_ENABLE_DOCS") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
} or not is_hosted()

app = FastAPI(
    title="UVA Control Plane",
    description="Voice-Agent-as-a-Service token minting, quota enforcement, and LiveKit session management API",
    version="1.0.0",
    docs_url="/docs" if _DOCS_ENABLED else None,
    redoc_url="/redoc" if _DOCS_ENABLED else None,
    openapi_url="/openapi.json" if _DOCS_ENABLED else None,
)


# F-M10: no service set CSP, HSTS, X-Frame-Options or X-Content-Type-Options.
app.add_middleware(
    SecurityHeadersMiddleware,
    hsts=is_hosted(),
    docs_enabled=_DOCS_ENABLED,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=_CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def health_check():
    """Minimal liveness probe — does not verify DB/LK connectivity, just confirms the process is up."""
    return {"status": "ok", "service": "uva-control-plane"}


@app.get("/healthz/deep")
def deep_health_check():
    """Deep readiness probe — verifies live PostgreSQL DB connectivity and LiveKit credentials configuration."""
    health = {
        "status": "healthy",
        "service": "uva-control-plane",
        "database": "unknown",
        "livekit": "configured",
    }

    # 1. Verify DB
    try:
        with psycopg.connect(**conn_kwargs(), connect_timeout=3) as conn:
            conn.execute("SELECT 1").fetchone()
            health["database"] = "connected"
    except Exception as e:
        health["database"] = f"failed: {e}"
        health["status"] = "unhealthy"

    # 2. Verify LiveKit env configuration
    if not _LK_URL or not _LK_KEY or not _LK_SECRET:
        health["livekit"] = "missing_credentials"
        health["status"] = "unhealthy"

    status_code = 200 if health["status"] == "healthy" else 503
    return JSONResponse(status_code=status_code, content=health)


@app.get("/healthz/warm")
async def warm_health_check():
    """Warm probe — pings DB + LiveKit API to keep staging instances hot (UVA-9)."""
    health = await run_warm_probe(
        lk_url=_LK_URL,
        lk_key=_LK_KEY,
        lk_secret=_LK_SECRET,
        agent_name=_LK_AGENT_NAME,
    )
    status_code = 200 if health["status"] == "warm" else 503
    return JSONResponse(status_code=status_code, content=health)


@app.get("/v1/voices")
def list_voices():
    """Returns published Urdu voices from the voices catalogue for client/dashboard picker."""
    try:
        with psycopg.connect(**conn_kwargs(), connect_timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT id, display_name, gender, preview_url, artwork_url, enabled,
                       provider, language
                FROM voices
                WHERE enabled = true
                ORDER BY display_name ASC
                """
            ).fetchall()
            if rows:
                return [
                    {
                        "id": str(r[0]),
                        "displayName": r[1],
                        "gender": r[2] or "unspecified",
                        "previewUrl": r[3],
                        "artworkUrl": r[4],
                        "enabled": bool(r[5]),
                        # Additive (ADR-036 voice-catalogue expansion): lets multi-provider
                        # consumers group/filter voices by provider+language client-side. Existing
                        # consumers (e.g. awaaz-labs-voice-catalogue) ignore unknown fields.
                        "provider": r[6],
                        "language": r[7],
                    }
                    for r in rows
                ]
    except Exception:
        # F-M1: this used to fall through to the static catalogue below, so a DB outage
        # was indistinguishable from a small voice list — clients rendered five voices
        # that do not exist for this tenant. Fail loudly instead.
        _voices_log.exception("/v1/voices database query failed")
        raise HTTPException(
            status_code=503, detail="voice catalogue temporarily unavailable"
        )

    # DB reachable but the catalogue is empty (fresh/dev database) — keep the built-in
    # demo list so local setups are not blocked. This is NOT the DB-failure path.
    _voices_log.warning("/v1/voices returned no enabled rows — serving demo catalogue")
    return [
        {
            "id": "v_meklc281",
            "displayName": "Demo Voice (Default)",
            "gender": "female",
            "previewUrl": None,
            "artworkUrl": None,
            "enabled": True,
        },
        {
            "id": "helpdesk-agent",
            "displayName": "Helpdesk Agent",
            "gender": "female",
            "previewUrl": None,
            "artworkUrl": None,
            "enabled": True,
        },
        {
            "id": "street-vendor",
            "displayName": "Street Vendor",
            "gender": "male",
            "previewUrl": None,
            "artworkUrl": None,
            "enabled": True,
        },
        {
            "id": "prime-time-anchor",
            "displayName": "Prime Time Anchor",
            "gender": "male",
            "previewUrl": None,
            "artworkUrl": None,
            "enabled": True,
        },
        {
            "id": "nosey-aunty",
            "displayName": "Nosey Aunty",
            "gender": "female",
            "previewUrl": None,
            "artworkUrl": None,
            "enabled": True,
        },
    ]


_secrets = DbSecretProvider(env_fallback=EnvSecretProvider())
_hits: OrderedDict[str, list[float]] = OrderedDict()


class SessionBody(BaseModel):
    agent_id: str
    greeting: str | None = None
    custom_greeting: str | None = None
    greeting_mode: str | None = None
    # F-C7 / A.4: phone number the HOST has already verified belongs to this caller.
    # Optional; the worker fail-closes on browser cancel/reschedule without it.
    verified_caller_phone: str | None = None


class DevSessionBody(BaseModel):
    agentId: str
    publishableKey: str | None = None
    greeting: str | None = None
    customGreeting: str | None = None
    greetingMode: str | None = None
    verifiedCallerPhone: str | None = None
    verified_caller_phone: str | None = None


# F-C7 / A.4. Mirrors worker/write_tool_gate.py::normalize_phone so the value the worker
# compares against is the value it was sent: keep a leading "+", keep digits, drop the rest.
# Normalizing here also keeps newlines and other junk out of the dispatch metadata JSON.
_MAX_PHONE_DIGITS = 15  # E.164 maximum


def _normalize_caller_phone(raw: str | None) -> str | None:
    """Return the normalized phone, or None when absent. Raises 400 on a non-empty but
    unusable value — silently dropping it would surface much later as the worker refusing
    a cancel/reschedule, with nothing pointing back at the host's malformed field."""
    text = (raw or "").strip()
    if not text:
        return None
    digits = "".join(c for c in text if c.isdigit())
    if not digits or len(digits) > _MAX_PHONE_DIGITS:
        raise HTTPException(
            status_code=400,
            detail="verified_caller_phone must be a phone number (E.164 preferred)",
        )
    return ("+" + digits) if text.startswith("+") else digits


def _opening_greeting(*candidates: str | None) -> str | None:
    for value in candidates:
        text = (value or "").strip()
        if text:
            return text
    return None


class RefreshBody(BaseModel):
    token: str


class RefreshResponse(BaseModel):
    token: str
    wsUrl: str
    roomName: str
    refreshUrl: str
    expiresIn: int


# F-H4: the limiter used to be checked AND filled from the raw X-Tenant-Id header before any
# signature was verified. Since that header is the tenant UUID the dashboard displays as the
# "publishable key", anyone who knew it could send 120 junk requests a minute and lock the
# real tenant out of minting, with no credential at all.
#
# Split into check and record: the tenant bucket is still checked up front, but only a
# request that actually passed HMAC verification records a hit, so unauthenticated junk can
# no longer fill someone else's bucket. Floods are absorbed by a separate per-IP bucket,
# which spends the caller's own resource rather than the victim's.
#
# F-H5: this state is per process and in memory. With N workers the effective limit is N
# times the stated one, and it resets on every deploy — documented here rather than implied.
# It is now bounded: at most _MAX_TRACKED_KEYS buckets, oldest evicted first, so a flood of
# distinct keys cannot grow it without limit.
RATE_LIMIT_IP_PER_MIN = 240
_MAX_TRACKED_KEYS = 10_000
_hits_lock = threading.Lock()


_PRUNE_INTERVAL_SEC = 60
_last_prune = 0.0


def _prune_locked(now: float) -> None:
    """Keep _hits bounded without making every request pay for a full scan.

    Eviction of the oldest bucket is O(1) and happens only when the cap is exceeded; the
    full sweep for expired windows runs at most once a minute. An earlier version scanned
    every bucket on every request, which turned the limiter itself into the bottleneck
    under exactly the flood it exists to absorb.
    """
    global _last_prune
    while len(_hits) > _MAX_TRACKED_KEYS:
        _hits.popitem(last=False)
    if now - _last_prune < _PRUNE_INTERVAL_SEC:
        return
    _last_prune = now
    for key in [k for k, window in _hits.items() if not window or now - window[-1] >= 60]:
        del _hits[key]


def _rate_limit_exceeded(key: str, limit: int) -> bool:
    """True when `key` is already at its limit. Does not count this request."""
    now = time.time()
    with _hits_lock:
        window = _hits.get(key)
        if window is None:
            return False
        window[:] = [t for t in window if now - t < 60]
        return len(window) >= limit


def _rate_limit_record(key: str) -> None:
    now = time.time()
    with _hits_lock:
        window = _hits.setdefault(key, [])
        window[:] = [t for t in window if now - t < 60]
        window.append(now)
        _hits.move_to_end(key)
        _prune_locked(now)


def _client_ip(request: Request) -> str:
    """Best-effort client identity for the pre-auth bucket. X-Forwarded-For is attacker
    controlled, so it is only a courtesy for correct proxies — the bucket is a flood damper,
    not an authorization decision."""
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return f"ip:{forwarded}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def _rate_limited(tenant_id: str) -> bool:
    """Back-compat wrapper: check-and-record against the tenant bucket.

    Still used by dev-mint, where the caller is already inside the dev gate.
    """
    if _rate_limit_exceeded(tenant_id, RATE_LIMIT_PER_MIN):
        return True
    _rate_limit_record(tenant_id)
    return False


# F-H7. A session's token is refreshed every TTL_SEC (120s) for as long as the call runs,
# so this is the only place the platform can revoke an in-flight call.
MAX_REFRESHES = 720  # ~24h at a 120s TTL; a real call never reaches this


def _next_refresh_count(metadata: dict) -> int:
    try:
        count = int(metadata.get("refresh_count", 0))
    except (TypeError, ValueError):
        count = 0
    count += 1
    if count > MAX_REFRESHES:
        raise HTTPException(status_code=403, detail="refresh limit reached")
    return count


def _enforce_refresh_gates(*, tenant_id: str, room: str) -> None:
    """Re-run the mint's tenant/quota/session gates on every refresh.

    Deliberately fails OPEN on an infrastructure error: a database blip must not drop every
    live call at once. It fails CLOSED on an actual answer — suspended tenant, closed
    session, monthly cap reached — which is the case F-H7 is about.
    """
    try:
        with mint_db_connection(connect_timeout=5) as conn:
            row = conn.execute(
                "select status, max_minutes_month from tenants where id = %s",
                (tenant_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=401, detail="unknown tenant")
            status, max_minutes = row
            if status != "active":
                raise HTTPException(status_code=403, detail="tenant not active")

            session_row = conn.execute(
                "select ended_at from sessions where tenant_id = %s and room_name = %s "
                "order by started_at desc limit 1",
                (tenant_id, room),
            ).fetchone()
            if session_row is not None and session_row[0] is not None:
                raise HTTPException(status_code=409, detail="session already closed")

            quota = conn.execute(
                "select minutes_this_month from quota_state where tenant_id = %s",
                (tenant_id,),
            ).fetchone()
            if quota is not None and max_minutes is not None and quota[0] is not None:
                if quota[0] >= max_minutes:
                    raise HTTPException(
                        status_code=429, detail="monthly minutes cap reached"
                    )
    except HTTPException:
        raise
    except Exception:
        _mint_log.warning(
            "refresh gate checks unavailable tenant=%s room=%s - allowing refresh",
            tenant_id,
            room,
            exc_info=True,
        )


def _mint_refresh_token(token: str) -> RefreshResponse:
    try:
        claims = api.TokenVerifier(_LK_KEY, _LK_SECRET).verify(token)
    except Exception as e:  # library raises PyJWT errors and ValueErrors
        raise HTTPException(status_code=401, detail="invalid or expired token") from e

    room = claims.video.room if claims.video else ""
    if not room or not claims.identity:
        raise HTTPException(status_code=401, detail="token missing room or identity")
    try:
        metadata = json.loads(claims.metadata or "{}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=401, detail="token metadata is invalid") from e
    tenant_id = metadata.get("tenant_id")
    agent_id = metadata.get("agent_id")
    if not tenant_id or not agent_id:
        raise HTTPException(
            status_code=401, detail="token metadata missing tenant or agent"
        )

    # F-H7: refresh used to verify only the JWT signature and re-issue the same grants —
    # it never re-read tenant status, never re-checked quota, never noticed a closed
    # session, and had no cap. A tenant suspended for non-payment or abuse kept every
    # in-flight call alive indefinitely, so "suspend" was not a stop control.
    _enforce_refresh_gates(tenant_id=tenant_id, room=room)

    refresh_count = _next_refresh_count(metadata)

    # A.4: refresh must not strip metadata the mint put there (e.g. verified_caller_phone),
    # otherwise a mid-call refresh would silently revoke the caller's write-tool ownership.
    refreshed_metadata = {
        k: v for k, v in metadata.items() if isinstance(k, str) and v is not None
    }
    refreshed_metadata["tenant_id"] = tenant_id
    refreshed_metadata["agent_id"] = agent_id
    refreshed_metadata["refresh_count"] = refresh_count

    refreshed = (
        api.AccessToken(_LK_KEY, _LK_SECRET)
        .with_identity(claims.identity)
        .with_ttl(datetime.timedelta(seconds=TTL_SEC))
        .with_metadata(json.dumps(refreshed_metadata))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=claims.video.can_publish if claims.video else True,
                can_subscribe=claims.video.can_subscribe if claims.video else True,
                can_publish_data=claims.video.can_publish_data
                if claims.video
                else True,
            )
        )
        .to_jwt()
    )
    return RefreshResponse(
        token=refreshed,
        wsUrl=_LK_URL,
        roomName=room,
        refreshUrl="/v1/session/refresh",
        expiresIn=TTL_SEC,
    )


def _lookup_tenant_for_agent(agent_id: str) -> str:
    with psycopg.connect(**conn_kwargs(), connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("select tenant_id from agents where id = %s", (agent_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="agent not found")
    return str(row[0])


def _dev_reset_concurrency(conn: psycopg.Connection, tenant_id: str) -> None:
    conn.execute(
        "insert into quota_state (tenant_id, concurrent_now) values (%s, 0) "
        "on conflict (tenant_id) do update set concurrent_now = 0",
        (tenant_id,),
    )


# Agent dispatch runs on the critical path to first audio (audit §3.1). It used to pay for a new
# event loop (asyncio.run), a new aiohttp session and a new TCP+TLS handshake to LiveKit on every
# session. Instead, one long-lived event loop on a daemon thread owns one LiveKitAPI client whose
# keep-alive connections are reused across dispatches. Both are created lazily, per process.
# livekit-api's own per-attempt timeout is 10 s; allow one region failover.
_DISPATCH_TIMEOUT_SEC = 20
# Kept short so an idle pooled connection is rarely stale when reused.
_DISPATCH_KEEPALIVE_SEC = 30
_dispatch_lock = threading.Lock()
_dispatch_loop: asyncio.AbstractEventLoop | None = None
_dispatch_client: api.LiveKitAPI | None = None
_dispatch_session: aiohttp.ClientSession | None = None


def _get_dispatch_loop() -> asyncio.AbstractEventLoop:
    global _dispatch_loop
    with _dispatch_lock:
        if _dispatch_loop is None or _dispatch_loop.is_closed():
            loop = asyncio.new_event_loop()
            threading.Thread(
                target=loop.run_forever, name="livekit-dispatch", daemon=True
            ).start()
            _dispatch_loop = loop
        return _dispatch_loop


def _get_dispatch_client() -> api.LiveKitAPI:
    """Only called on the dispatch loop's thread, so no lock is needed."""
    global _dispatch_client, _dispatch_session
    if _dispatch_client is None:
        _dispatch_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            connector=aiohttp.TCPConnector(keepalive_timeout=_DISPATCH_KEEPALIVE_SEC),
        )
        _dispatch_client = api.LiveKitAPI(
            url=_LK_URL,
            api_key=_LK_KEY,
            api_secret=_LK_SECRET,
            session=_dispatch_session,
        )
    return _dispatch_client


async def _reset_dispatch_client() -> None:
    """Drop the shared client after a failure so the next dispatch starts from a fresh
    connection pool instead of reusing a possibly broken one."""
    global _dispatch_client, _dispatch_session
    session = _dispatch_session
    _dispatch_client = None
    _dispatch_session = None
    if session is not None and not session.closed:
        await session.close()


async def _dispatch_agent(
    room_name: str,
    *,
    tenant_id: str,
    agent_id: str,
    greeting: str | None = None,
    verified_caller_phone: str | None = None,
) -> None:
    metadata: dict[str, str] = {"tenant_id": tenant_id, "agent_id": agent_id}
    if greeting:
        metadata["greeting"] = greeting
    if verified_caller_phone:
        # Read by worker/caller_identity.py::resolve_verified_caller_phone (A.4 source 1).
        metadata["verified_caller_phone"] = verified_caller_phone
    try:
        await _get_dispatch_client().agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=_LK_AGENT_NAME,
                room=room_name,
                metadata=json.dumps(metadata),
            )
        )
    except BaseException:
        await _reset_dispatch_client()
        raise


def _rollback_dispatched_session(
    *, tenant_id: str, room_name: str, end_reason: str = "dispatch_failed"
) -> None:
    with psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        conn.execute(
            "update sessions "
            "set ended_at = now(), duration_sec = 0, end_reason = %s "
            "where tenant_id = %s and room_name = %s and ended_at is null",
            (end_reason, tenant_id, room_name),
        )
        conn.execute(
            "update quota_state "
            "set concurrent_now = greatest(concurrent_now - 1, 0) "
            "where tenant_id = %s",
            (tenant_id,),
        )


def _session_response(payload: dict) -> JSONResponse:
    """Session mint/refresh payloads must never be cached — token and room are single-use."""
    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


def _run_dispatch_background(
    room_name: str,
    tenant_id: str,
    agent_id: str,
    greeting: str | None = None,
    verified_caller_phone: str | None = None,
) -> None:
    log = logging.getLogger("control_plane.dispatch")
    started = time.monotonic()
    future = asyncio.run_coroutine_threadsafe(
        _dispatch_agent(
            room_name,
            tenant_id=tenant_id,
            agent_id=agent_id,
            greeting=greeting,
            verified_caller_phone=verified_caller_phone,
        ),
        _get_dispatch_loop(),
    )
    try:
        future.result(timeout=_DISPATCH_TIMEOUT_SEC)
        log.info(
            "agent dispatch ok room=%s tenant=%s agent=%s elapsed_ms=%d",
            room_name,
            tenant_id,
            agent_id,
            int((time.monotonic() - started) * 1000),
        )
    except Exception:
        future.cancel()
        log.exception(
            "agent dispatch failed room=%s tenant=%s agent=%s — rolling back session",
            room_name,
            tenant_id,
            agent_id,
        )
        _rollback_dispatched_session(tenant_id=tenant_id, room_name=room_name)


def _with_dispatch(
    res: dict,
    tenant_id: str,
    agent_id: str,
    background_tasks: BackgroundTasks,
    *,
    greeting: str | None = None,
    verified_caller_phone: str | None = None,
) -> dict:
    background_tasks.add_task(
        _run_dispatch_background,
        res["roomName"],
        tenant_id,
        agent_id,
        greeting,
        verified_caller_phone,
    )
    return {**res, "refreshUrl": "/v1/session/refresh", "expiresIn": TTL_SEC}


def _dev_mint_session(
    *,
    tenant_id: str,
    agent_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    auto_reset_quota: bool,
    greeting: str | None = None,
    verified_caller_phone: str | None = None,
) -> dict:
    secret = _secrets.get(tenant_id)
    if not secret:
        raise HTTPException(
            status_code=400,
            detail="tenant secret missing from CP_TENANT_SECRETS for this agent",
        )

    ts = str(int(time.time()))
    nonce = os.urandom(8).hex()
    from .mint import expected_signature  # local import to keep top-level surface small

    signature = expected_signature(secret, tenant_id, ts, nonce, agent_id)
    if _rate_limited(tenant_id):
        record_mint_rejection(tenant_id, 429, "rate limited")
        raise HTTPException(status_code=429, detail="rate limited")

    with mint_db_connection(connect_timeout=10) as conn:
        try:
            mint_t0 = time.monotonic()
            res = mint_session(
                conn=conn,
                secrets=_secrets,
                livekit_key=_LK_KEY,
                livekit_secret=_LK_SECRET,
                livekit_url=_LK_URL,
                tenant_id=tenant_id,
                ts=ts,
                nonce=nonce,
                agent_id=agent_id,
                signature=signature,
                origin=request.headers.get("origin"),
                verified_caller_phone=verified_caller_phone,
            )
            _mint_log.info(
                "mint_elapsed_ms=%d tenant=%s agent=%s room=%s source=dev_mint",
                int((time.monotonic() - mint_t0) * 1000),
                tenant_id,
                agent_id,
                res.get("roomName"),
            )
        except MintError as e:
            if (
                auto_reset_quota
                and e.status == 429
                and e.reason == "concurrent cap reached"
            ):
                _dev_reset_concurrency(conn, tenant_id)
                mint_t0 = time.monotonic()
                res = mint_session(
                    conn=conn,
                    secrets=_secrets,
                    livekit_key=_LK_KEY,
                    livekit_secret=_LK_SECRET,
                    livekit_url=_LK_URL,
                    tenant_id=tenant_id,
                    ts=ts,
                    nonce=nonce,
                    agent_id=agent_id,
                    signature=signature,
                    origin=request.headers.get("origin"),
                    verified_caller_phone=verified_caller_phone,
                )
                _mint_log.info(
                    "mint_elapsed_ms=%d tenant=%s agent=%s room=%s source=dev_mint_retry",
                    int((time.monotonic() - mint_t0) * 1000),
                    tenant_id,
                    agent_id,
                    res.get("roomName"),
                )
            else:
                record_mint_rejection(tenant_id, e.status, e.reason)
                raise HTTPException(status_code=e.status, detail=e.reason) from e
    return _with_dispatch(
        res,
        tenant_id,
        agent_id,
        background_tasks,
        greeting=greeting,
        verified_caller_phone=verified_caller_phone,
    )


@app.post("/v1/session")
def create_session(
    body: SessionBody,
    request: Request,
    background_tasks: BackgroundTasks,
    x_tenant_id: str = Header(...),
    x_timestamp: str = Header(...),
    x_nonce: str = Header(...),
    x_signature: str = Header(...),
):
    # F-H4: the caller's own bucket first — this one is filled by unauthenticated requests
    # because it costs the sender, not the tenant.
    ip_key = _client_ip(request)
    if _rate_limit_exceeded(ip_key, RATE_LIMIT_IP_PER_MIN):
        return JSONResponse({"error": "rate limited"}, status_code=429)
    _rate_limit_record(ip_key)

    if _rate_limit_exceeded(x_tenant_id, RATE_LIMIT_PER_MIN):
        record_mint_rejection(x_tenant_id, 429, "rate limited")
        return JSONResponse({"error": "rate limited"}, status_code=429)
    greeting = _opening_greeting(body.greeting, body.custom_greeting)
    verified_caller_phone = _normalize_caller_phone(body.verified_caller_phone)
    try:
        with mint_db_connection(connect_timeout=10) as conn:
            mint_t0 = time.monotonic()
            res = mint_session(
                conn=conn,
                secrets=_secrets,
                livekit_key=_LK_KEY,
                livekit_secret=_LK_SECRET,
                livekit_url=_LK_URL,
                tenant_id=x_tenant_id,
                ts=x_timestamp,
                nonce=x_nonce,
                agent_id=body.agent_id,
                signature=x_signature,
                origin=request.headers.get("origin"),
                verified_caller_phone=verified_caller_phone,
            )
            # Only an authenticated mint counts against the tenant's bucket (F-H4).
            _rate_limit_record(x_tenant_id)
            _mint_log.info(
                "mint_elapsed_ms=%d tenant=%s agent=%s room=%s source=session",
                int((time.monotonic() - mint_t0) * 1000),
                x_tenant_id,
                body.agent_id,
                res.get("roomName"),
            )
            return _session_response(
                _with_dispatch(
                    res,
                    x_tenant_id,
                    body.agent_id,
                    background_tasks,
                    greeting=greeting,
                    verified_caller_phone=verified_caller_phone,
                )
            )
    except MintError as e:
        record_mint_rejection(x_tenant_id, e.status, e.reason)
        return JSONResponse({"error": e.reason}, status_code=e.status)


def _dev_mint_enabled() -> bool:
    """F-C2: dev-mint issues a real LiveKit token to anyone who knows an agent UUID.

    It exists so the dashboard Test Studio (and the local sandbox page) can start a call
    without a host backend. That is a development convenience, so it is off by default on a
    hosted deployment and must be turned on deliberately with CP_ENABLE_DEV_MINT=1.
    """
    flag = (os.environ.get("CP_ENABLE_DEV_MINT") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    return not is_hosted()


def _dev_mint_reset_quota_allowed() -> bool:
    """F-C2: dev-mint used to call _dev_reset_concurrency on every concurrency-cap hit,
    zeroing the tenant's live concurrent_now — which defeated the concurrency cap outright
    and let one caller consume a tenant's provider spend without limit. Opt-in only."""
    return (os.environ.get("CP_DEV_MINT_RESET_QUOTA") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@app.post("/v1/session/dev-mint")
def create_dev_session(
    body: DevSessionBody, request: Request, background_tasks: BackgroundTasks
):
    if not _dev_mint_enabled():
        # 404, not 403: a disabled development endpoint should not advertise that it exists.
        raise HTTPException(status_code=404, detail="not found")

    tenant_id = _lookup_tenant_for_agent(body.agentId)

    # F-C2: publishableKey was accepted and discarded, so agentId alone was the only thing
    # standing between a stranger and a live session. It is the tenant id (F-L4), not a
    # secret, but requiring it to match the agent's owner stops a lone leaked agent UUID
    # from minting sessions.
    supplied_key = (body.publishableKey or "").strip()
    if not supplied_key:
        raise HTTPException(status_code=401, detail="publishableKey is required")
    if supplied_key != str(tenant_id):
        record_mint_rejection(tenant_id, 403, "dev-mint publishable key mismatch")
        raise HTTPException(
            status_code=403, detail="publishableKey does not match this agent"
        )

    greeting = _opening_greeting(body.greeting, body.customGreeting)
    verified_caller_phone = _normalize_caller_phone(
        body.verifiedCallerPhone or body.verified_caller_phone
    )
    return _session_response(
        _dev_mint_session(
            tenant_id=tenant_id,
            agent_id=body.agentId,
            request=request,
            background_tasks=background_tasks,
            auto_reset_quota=_dev_mint_reset_quota_allowed(),
            greeting=greeting,
            verified_caller_phone=verified_caller_phone,
        )
    )


@app.post("/v1/session/refresh")
def refresh_session_token(
    authorization: str | None = Header(default=None),
    body: RefreshBody | None = Body(default=None),
):
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
    elif body and body.token:
        token = body.token.strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return _session_response(_mint_refresh_token(token).model_dump())


if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
