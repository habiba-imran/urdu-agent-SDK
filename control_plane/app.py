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
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from fastapi import Body, FastAPI, Header, HTTPException, Request
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
_CORS_ORIGINS = [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()] or ["*"]

_SENTRY_DSN = os.environ.get("SENTRY_DSN") or _ENV.get("SENTRY_DSN", "")
if _SENTRY_DSN and sentry_sdk is not None:
    try:
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.1,
            environment=os.environ.get("ENVIRONMENT", "production"),
        )
    except Exception:
        pass


app = FastAPI(
    title="UVA Control Plane",
    description="Voice-Agent-as-a-Service token minting, quota enforcement, and LiveKit session management API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
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
        pass

    # Fallback default catalog if DB query fails or unpopulated
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
_hits: dict[str, list[float]] = defaultdict(list)


class SessionBody(BaseModel):
    agent_id: str


class DevSessionBody(BaseModel):
    agentId: str
    publishableKey: str | None = None


class RefreshBody(BaseModel):
    token: str


class RefreshResponse(BaseModel):
    token: str
    wsUrl: str
    roomName: str
    refreshUrl: str
    expiresIn: int


def _rate_limited(tenant_id: str) -> bool:
    now = time.time()
    window = _hits[tenant_id]
    window[:] = [t for t in window if now - t < 60]
    if len(window) >= RATE_LIMIT_PER_MIN:
        return True
    window.append(now)
    return False


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

    refreshed = (
        api.AccessToken(_LK_KEY, _LK_SECRET)
        .with_identity(claims.identity)
        .with_ttl(datetime.timedelta(seconds=TTL_SEC))
        .with_metadata(json.dumps({"tenant_id": tenant_id, "agent_id": agent_id}))
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


async def _dispatch_agent(
    room_name: str, *, tenant_id: str, agent_id: str
) -> None:
    async with api.LiveKitAPI(
        url=_LK_URL,
        api_key=_LK_KEY,
        api_secret=_LK_SECRET,
    ) as lkapi:
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=_LK_AGENT_NAME,
                room=room_name,
                metadata=json.dumps(
                    {"tenant_id": tenant_id, "agent_id": agent_id}
                ),
            )
        )


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


def _with_dispatch(res: dict, tenant_id: str, agent_id: str) -> dict:
    try:
        asyncio.run(
            _dispatch_agent(
                res["roomName"],
                tenant_id=tenant_id,
                agent_id=agent_id,
            )
        )
    except Exception as e:
        _rollback_dispatched_session(tenant_id=tenant_id, room_name=res["roomName"])
        raise HTTPException(
            status_code=502,
            detail=f"agent dispatch failed: {e}",
        ) from e
    return {**res, "refreshUrl": "/v1/session/refresh", "expiresIn": TTL_SEC}


def _dev_mint_session(
    *, tenant_id: str, agent_id: str, request: Request, auto_reset_quota: bool
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

    with psycopg.connect(**conn_kwargs(), connect_timeout=10) as conn:
        try:
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
            )
        except MintError as e:
            if (
                auto_reset_quota
                and e.status == 429
                and e.reason == "concurrent cap reached"
            ):
                _dev_reset_concurrency(conn, tenant_id)
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
                )
            else:
                record_mint_rejection(tenant_id, e.status, e.reason)
                raise HTTPException(status_code=e.status, detail=e.reason) from e
    return _with_dispatch(res, tenant_id, agent_id)


@app.post("/v1/session")
def create_session(
    body: SessionBody,
    request: Request,
    x_tenant_id: str = Header(...),
    x_timestamp: str = Header(...),
    x_nonce: str = Header(...),
    x_signature: str = Header(...),
):
    if _rate_limited(x_tenant_id):
        record_mint_rejection(x_tenant_id, 429, "rate limited")
        return JSONResponse({"error": "rate limited"}, status_code=429)
    try:
        with psycopg.connect(**conn_kwargs(), connect_timeout=10) as conn:
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
            )
            return _session_response(
                _with_dispatch(res, x_tenant_id, body.agent_id)
            )
    except MintError as e:
        record_mint_rejection(x_tenant_id, e.status, e.reason)
        return JSONResponse({"error": e.reason}, status_code=e.status)


@app.post("/v1/session/dev-mint")
def create_dev_session(body: DevSessionBody, request: Request):
    tenant_id = _lookup_tenant_for_agent(body.agentId)
    return _session_response(
        _dev_mint_session(
            tenant_id=tenant_id,
            agent_id=body.agentId,
            request=request,
            auto_reset_quota=True,
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
