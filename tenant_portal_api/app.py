"""Tenant-facing dashboard backend/API layer.

Separate FastAPI app for tenant-scoped management APIs. This intentionally does NOT reuse
admin/ or control_plane/ routes:
- admin is a super-admin domain with separate auth and full-system visibility
- control_plane is the session mint/refresh path
- tenant_portal_api is the tenant self-service management surface
"""

from __future__ import annotations

import os
import time
import sys
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Iterator

import psycopg
from dotenv import dotenv_values, load_dotenv
from fastapi import FastAPI, Header, HTTPException, Body, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .auth import TenantAuthError, login as tenant_login, verify_tenant_jwt
from .membership import (
    claim_existing_tenant_for_auth_user,
    exchange_supabase_user_for_portal_session,
    invite_member_to_tenant,
    list_members,
)
from .supabase_auth import verify_supabase_access_token
from .db_pool import portal_db_connection, warm_portal_db_pool
from .jwt_secret import portal_jwt_secret
from .machine_auth import MachineAuthError, verify_machine_request
from .provider_capabilities import get_public_capabilities
from .provider_validation import ProviderValidationError, resolve_agent_provider_fields
from .greeting_fields import GreetingConfigError, normalize_first_speaker, normalize_greeting
from .tools_webhook import (
    ToolsWebhookError,
    assert_tools_webhook_pair,
    normalize_tools_auth_secret,
    normalize_tools_base_url,
)
from . import queries
from .recording_urls import enrich_session_recording
from .telephony_routes import router as telephony_router
from .telephony_webhooks import router as telephony_webhook_router

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control_plane.login_guard import (  # noqa: E402
    LoginThrottled,
    assert_not_throttled,
    record_attempt,
)
from control_plane.runtime_env import is_hosted  # noqa: E402
from control_plane.security_headers import SecurityHeadersMiddleware  # noqa: E402
from control_plane.secrets import EnvSecretProvider  # noqa: E402
from control_plane.secrets_db import DbSecretProvider  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _ROOT / ".env.local"
load_dotenv(_ENV_PATH, override=False)


# F-C1/F-H13: resolution lives in tenant_portal_api/jwt_secret.py so this module and
# telephony_routes.py cannot disagree about the signing key, and so a hosted service with
# no secret configured fails to start instead of generating a fresh one into .env.local
# on every deploy (which silently invalidated every issued session).
TENANT_PORTAL_JWT_SECRET = portal_jwt_secret()
DEFAULT_PORTAL_ORIGINS = "http://localhost:3000,http://localhost:5173"
TENANT_PORTAL_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "TENANT_PORTAL_ORIGINS",
        dotenv_values(_ENV_PATH).get("TENANT_PORTAL_ORIGINS", DEFAULT_PORTAL_ORIGINS),
    ).split(",")
    if o.strip()
]

_machine_secrets = DbSecretProvider(env_fallback=EnvSecretProvider())


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Best-effort: open the first pooled socket at boot so the first dashboard
    # request is not paying full Supabase TLS cost on a cold worker.
    warm_portal_db_pool()
    yield


app = FastAPI(title="UVA tenant portal API", lifespan=_lifespan)
# F-M10: baseline security headers (CSP is the main mitigation for the F-C6 XSS chain).
app.add_middleware(
    SecurityHeadersMiddleware,
    hsts=is_hosted(),
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=TENANT_PORTAL_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Tenant-Id",
        "X-Timestamp",
        "X-Nonce",
        "X-Signature",
    ],
)


class TenantLoginBody(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    tenant_secret: str = Field(..., min_length=1)


class SupabaseExchangeBody(BaseModel):
    """Dashboard Phase 1: exchange a Supabase access_token for a tenant portal JWT."""

    access_token: str = Field(..., min_length=1)


class ClaimTenantBody(BaseModel):
    """Link email login to a pre-existing tenant (HMAC-era) without creating a new one."""

    access_token: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    tenant_secret: str = Field(..., min_length=1)


class InviteMemberBody(BaseModel):
    """Phase 2: invite email only — tenant_id is taken from the portal JWT, never the body."""

    email: str = Field(..., min_length=3, max_length=320)


# F-M2 (portal half): agents.prompt had no length limit at write time, so a tenant could
# store an arbitrarily large persona that every LLM turn then paid for — the mechanism behind
# the observed Groq ITPM exhaustion. worker/prompt_compact.py only compacts at session build,
# for Groq, after the row already exists. This is the cap at the point of storage.
#
# Deliberately far above worker/prompt_compact.py's ~3000-char Groq soft cap: personas for
# other providers are legitimately longer, and this is a sanity ceiling, not a token budget.
MAX_PROMPT_CHARS = 24_000
MAX_GREETING_CHARS = 2_000
# F-M26: unbounded resource creation on an authenticated but unmetered endpoint.
MAX_AGENTS_PER_TENANT = int(os.environ.get("PORTAL_MAX_AGENTS_PER_TENANT", "100"))
# F-M3: ?limit=1000000 returned every session with full transcripts - memory pressure and a
# data-exfiltration amplifier.
MAX_PAGE_LIMIT = 200


class CreateAgentBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    prompt: str = Field(..., min_length=1, max_length=MAX_PROMPT_CHARS)
    voice_id: str = Field(..., min_length=1)
    llm_model: str = Field(default="gemini-2.5-flash", min_length=1)
    # Additive, Phase 3 of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036). All
    # optional — omitting them keeps the exact pre-Phase-3 behavior (ur+gladia+gemini+uplift).
    # tts_voice_id takes priority over voice_id when both are given (guide's explicit rule),
    # resolved in resolve_agent_provider_fields, never here.
    agent_language: str | None = Field(default=None, min_length=1)
    stt_provider: str | None = Field(default=None, min_length=1)
    stt_model: str | None = Field(default=None, min_length=1)
    stt_options: dict | None = Field(default=None)
    llm_provider: str | None = Field(default=None, min_length=1)
    llm_options: dict | None = Field(default=None)
    tts_provider: str | None = Field(default=None, min_length=1)
    tts_voice_id: str | None = Field(default=None, min_length=1)
    tts_options: dict | None = Field(default=None)
    greeting: str | None = Field(default=None, max_length=MAX_GREETING_CHARS)
    first_speaker: str | None = Field(default=None)
    # F-C4: opt-in call recording (default false — column default matches).
    recording_enabled: bool | None = Field(default=None)
    # Client backend tool gateway (RAG/FAQ/scheduling). Per-agent so multi-client SDK
    # workers call the right host — not a single global worker env URL.
    tools_base_url: str | None = Field(default=None)
    tools_auth_secret: str | None = Field(default=None)


class UpdateAgentBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    prompt: str | None = Field(default=None, min_length=1, max_length=MAX_PROMPT_CHARS)
    voice_id: str | None = Field(default=None, min_length=1)
    llm_model: str | None = Field(default=None, min_length=1)
    agent_language: str | None = Field(default=None, min_length=1)
    stt_provider: str | None = Field(default=None, min_length=1)
    stt_model: str | None = Field(default=None, min_length=1)
    stt_options: dict | None = Field(default=None)
    llm_provider: str | None = Field(default=None, min_length=1)
    llm_options: dict | None = Field(default=None)
    tts_provider: str | None = Field(default=None, min_length=1)
    tts_voice_id: str | None = Field(default=None, min_length=1)
    tts_options: dict | None = Field(default=None)
    greeting: str | None = Field(default=None, max_length=MAX_GREETING_CHARS)
    first_speaker: str | None = Field(default=None)
    recording_enabled: bool | None = Field(default=None)
    tools_base_url: str | None = Field(default=None)
    tools_auth_secret: str | None = Field(default=None)


@contextmanager
def _conn(*, connect_timeout: float = 10.0) -> Iterator[psycopg.Connection]:
    """Process-local pooled checkout.

    Was a fresh ``psycopg.connect(..., connect_timeout=3)`` closed on every
    ``with`` exit — cold TLS to Supabase often exceeds 3s, causing intermittent
    ``ConnectionTimeout`` on machine/provider-capabilities.
    """
    try:
        with portal_db_connection(connect_timeout=connect_timeout) as conn:
            yield conn
    except psycopg.errors.ConnectionTimeout as exc:
        raise HTTPException(
            status_code=503,
            detail="database unreachable (connection timeout)",
        ) from exc


def _resolve_provider_fields(
    conn: psycopg.Connection,
    body: CreateAgentBody | UpdateAgentBody,
    *,
    current: dict | None,
) -> dict:
    """Wraps resolve_agent_provider_fields with the HTTP error mapping every route needs —
    ProviderValidationError -> 422 with its stable code, same pattern TenantAuthError/
    MachineAuthError already use below for their own exception types."""
    try:
        return resolve_agent_provider_fields(
            conn,
            agent_language=body.agent_language,
            stt_provider=body.stt_provider,
            stt_model=body.stt_model,
            stt_options=body.stt_options,
            llm_provider=body.llm_provider,
            llm_model=body.llm_model,
            llm_options=body.llm_options,
            tts_provider=body.tts_provider,
            tts_voice_id=body.tts_voice_id,
            tts_options=body.tts_options,
            voice_id=body.voice_id,
            current=current,
        )
    except ProviderValidationError as e:
        raise HTTPException(
            status_code=e.status, detail={"code": e.code, "reason": e.reason}
        ) from e


def _opening_from_body(
    body: CreateAgentBody | UpdateAgentBody, current: dict | None
) -> dict[str, str | None]:
    """Resolve greeting / first_speaker. Omit keeps current (PATCH); blank greeting clears."""
    try:
        if current is None:
            return {
                "greeting": normalize_greeting(body.greeting),
                "first_speaker": normalize_first_speaker(body.first_speaker),
            }
        greeting = (
            normalize_greeting(body.greeting)
            if body.greeting is not None
            else current.get("greeting")
        )
        first_speaker = (
            normalize_first_speaker(body.first_speaker)
            if body.first_speaker is not None
            else current.get("first_speaker")
        )
        return {"greeting": greeting, "first_speaker": first_speaker}
    except GreetingConfigError as e:
        raise HTTPException(
            status_code=422, detail={"code": e.code, "reason": e.reason}
        ) from e


def _recording_enabled_from_body(
    body: CreateAgentBody | UpdateAgentBody, current: dict | None
):
    """Create defaults false; PATCH omit keeps current."""
    if body.recording_enabled is not None:
        return bool(body.recording_enabled)
    if current is None:
        return False
    return queries._UNSET


def _tools_webhook_from_body(
    body: CreateAgentBody | UpdateAgentBody, current: dict | None
) -> dict:
    """Resolve tools_base_url / tools_auth_secret. Omit keeps current on PATCH; blank clears.

    P1-M4: effective tools_base_url always requires an effective tools_auth_secret.
    """
    try:
        if current is None:
            tools_base_url = normalize_tools_base_url(body.tools_base_url)
            tools_auth_secret = normalize_tools_auth_secret(body.tools_auth_secret)
            assert_tools_webhook_pair(tools_base_url, tools_auth_secret)
            return {
                "tools_base_url": tools_base_url,
                "tools_auth_secret": tools_auth_secret,
            }
        tools_base_url = (
            normalize_tools_base_url(body.tools_base_url)
            if body.tools_base_url is not None
            else queries._UNSET
        )
        tools_auth_secret = (
            normalize_tools_auth_secret(body.tools_auth_secret)
            if body.tools_auth_secret is not None
            else queries._UNSET
        )
        effective_url = (
            current.get("tools_base_url")
            if tools_base_url is queries._UNSET
            else tools_base_url
        )
        effective_secret = (
            current.get("tools_auth_secret")
            if tools_auth_secret is queries._UNSET
            else tools_auth_secret
        )
        assert_tools_webhook_pair(effective_url, effective_secret)
        return {
            "tools_base_url": tools_base_url,
            "tools_auth_secret": tools_auth_secret,
        }
    except ToolsWebhookError as e:
        raise HTTPException(
            status_code=e.status, detail={"code": e.code, "reason": e.reason}
        ) from e


def _require_tenant(
    authorization: str | None, request: Request | None = None
) -> dict:
    """Verify portal JWT (Bearer or HttpOnly cookie) and live membership (MISS-1 / P1-H6)."""
    from .portal_access import http_require_portal
    from .session_cookie import portal_token_from_request

    token = None
    if request is not None:
        token = portal_token_from_request(request, authorization)

    with _conn() as conn:
        if token:
            return http_require_portal(
                conn, token=token, jwt_secret=TENANT_PORTAL_JWT_SECRET
            )
        return http_require_portal(
            conn, authorization=authorization, jwt_secret=TENANT_PORTAL_JWT_SECRET
        )


def _require_owner(
    authorization: str | None, request: Request | None = None
) -> dict:
    """Like ``_require_tenant`` but requires live owner role (P1-C1)."""
    from .portal_access import http_require_owner
    from .session_cookie import portal_token_from_request

    token = None
    if request is not None:
        token = portal_token_from_request(request, authorization)

    with _conn() as conn:
        if token:
            return http_require_owner(
                conn, token=token, jwt_secret=TENANT_PORTAL_JWT_SECRET
            )
        return http_require_owner(
            conn, authorization=authorization, jwt_secret=TENANT_PORTAL_JWT_SECRET
        )


def _portal_session_response(result: dict) -> JSONResponse:
    """Return session JSON and set HttpOnly cookie (P1-H6)."""
    from .session_cookie import set_portal_session_cookie

    response = JSONResponse(result)
    token = result.get("token")
    if isinstance(token, str) and token:
        set_portal_session_cookie(response, token)
    return response


def _require_machine(
    conn: psycopg.Connection,
    *,
    x_tenant_id: str | None,
    x_timestamp: str | None,
    x_nonce: str | None,
    x_signature: str | None,
    action: str,
    body: dict,
    client_ip: str | None = None,
) -> None:
    if not x_tenant_id or not x_timestamp or not x_nonce or not x_signature:
        raise HTTPException(status_code=401, detail="missing signature headers")
    try:
        verify_machine_request(
            conn,
            _machine_secrets,
            tenant_id=x_tenant_id,
            ts=x_timestamp,
            nonce=x_nonce,
            action=action,
            body=body,
            signature=x_signature,
            client_ip=client_ip,
        )
    except MachineAuthError as e:
        raise HTTPException(status_code=e.status, detail=e.reason) from e


@app.get("/healthz")
async def tenant_portal_health():
    return {"status": "ok", "service": "uva-tenant-portal-api"}


@app.post("/portal/login")
def portal_login(body: TenantLoginBody, request: Request):
    """F-H14: this endpoint had no rate limit, throttle or lockout, and failures were never
    recorded anywhere - so credential guessing against the portal that can read a tenant's
    signing secret left no trace."""
    client_ip = request.client.host if request.client else None
    with _conn() as conn:
        try:
            assert_not_throttled(
                conn, realm="portal", identity=body.tenant_id, client_ip=client_ip
            )
        except LoginThrottled as e:
            raise HTTPException(
                status_code=e.status,
                detail="too many failed login attempts - try again later",
                headers={"Retry-After": str(e.retry_after_seconds)},
            ) from e

        try:
            result = tenant_login(
                conn,
                tenant_id=body.tenant_id,
                tenant_secret=body.tenant_secret,
                jwt_secret=TENANT_PORTAL_JWT_SECRET,
            )
        except TenantAuthError as e:
            record_attempt(
                conn,
                realm="portal",
                identity=body.tenant_id,
                client_ip=client_ip,
                successful=False,
                reason=e.reason,
            )
            conn.commit()
            raise HTTPException(status_code=e.status, detail=e.reason) from e

        record_attempt(
            conn,
            realm="portal",
            identity=body.tenant_id,
            client_ip=client_ip,
            successful=True,
        )
        conn.commit()
        return _portal_session_response(result)


@app.post("/portal/auth/supabase")
def portal_auth_supabase(body: SupabaseExchangeBody, request: Request):
    """Phase 1 human login: verify Supabase access_token → resolve/bootstrap membership
    → issue the same tenant-scoped portal JWT used by the rest of /portal/*.
    """
    client_ip = request.client.host if request.client else None
    try:
        claims = verify_supabase_access_token(body.access_token)
    except TenantAuthError as e:
        raise HTTPException(status_code=e.status, detail=e.reason) from e

    auth_user_id = str(claims["sub"])
    email = claims.get("email")
    if isinstance(email, str):
        email = email.strip() or None
    else:
        email = None
    throttle_id = (email or auth_user_id).lower()

    with _conn() as conn:
        try:
            assert_not_throttled(
                conn, realm="portal", identity=throttle_id, client_ip=client_ip
            )
        except LoginThrottled as e:
            raise HTTPException(
                status_code=e.status,
                detail="too many failed login attempts - try again later",
                headers={"Retry-After": str(e.retry_after_seconds)},
            ) from e

        try:
            result = exchange_supabase_user_for_portal_session(
                conn,
                auth_user_id=auth_user_id,
                email=email,
                jwt_secret=TENANT_PORTAL_JWT_SECRET,
            )
        except TenantAuthError as e:
            record_attempt(
                conn,
                realm="portal",
                identity=throttle_id,
                client_ip=client_ip,
                successful=False,
                reason=e.reason,
            )
            conn.commit()
            raise HTTPException(status_code=e.status, detail=e.reason) from e
        except psycopg.Error as e:
            conn.rollback()
            # Most common Phase 1 miss: migration 0034 not applied.
            raise HTTPException(
                status_code=503,
                detail=(
                    "tenant membership store unavailable — apply migration "
                    "0034_tenant_members.sql and retry"
                ),
            ) from e

        record_attempt(
            conn,
            realm="portal",
            identity=throttle_id,
            client_ip=client_ip,
            successful=True,
        )
        conn.commit()
        return _portal_session_response(result)


@app.post("/portal/auth/claim-tenant")
def portal_claim_tenant(body: ClaimTenantBody, request: Request):
    """Legacy tenants: prove HMAC ownership, attach this Supabase user as owner."""
    client_ip = request.client.host if request.client else None
    try:
        claims = verify_supabase_access_token(body.access_token)
    except TenantAuthError as e:
        raise HTTPException(status_code=e.status, detail=e.reason) from e

    auth_user_id = str(claims["sub"])
    email = claims.get("email")
    if isinstance(email, str):
        email = email.strip() or None
    else:
        email = None
    throttle_id = (email or auth_user_id).lower()

    with _conn() as conn:
        try:
            assert_not_throttled(
                conn, realm="portal", identity=throttle_id, client_ip=client_ip
            )
        except LoginThrottled as e:
            raise HTTPException(
                status_code=e.status,
                detail="too many failed login attempts - try again later",
                headers={"Retry-After": str(e.retry_after_seconds)},
            ) from e

        try:
            result = claim_existing_tenant_for_auth_user(
                conn,
                auth_user_id=auth_user_id,
                email=email,
                tenant_id=body.tenant_id,
                tenant_secret=body.tenant_secret,
                jwt_secret=TENANT_PORTAL_JWT_SECRET,
            )
        except TenantAuthError as e:
            record_attempt(
                conn,
                realm="portal",
                identity=throttle_id,
                client_ip=client_ip,
                successful=False,
                reason=e.reason,
            )
            conn.commit()
            raise HTTPException(status_code=e.status, detail=e.reason) from e

        record_attempt(
            conn,
            realm="portal",
            identity=throttle_id,
            client_ip=client_ip,
            successful=True,
            reason="claimed existing tenant",
        )
        conn.commit()
        return _portal_session_response(result)


@app.post("/portal/auth/logout")
def portal_auth_logout():
    """Clear the HttpOnly portal session cookie."""
    from .session_cookie import clear_portal_session_cookie

    response = JSONResponse({"ok": True})
    clear_portal_session_cookie(response)
    return response


@app.get("/portal/whoami")
def portal_whoami(
    request: Request, authorization: str | None = Header(default=None)
):
    """Session probe for cookie-auth dashboards (role without reading JWT in JS)."""
    claims = _require_tenant(authorization, request)
    return {
        "tenant_id": claims["sub"],
        "role": claims.get("role"),
        "auth_user_id": claims.get("auth_user_id"),
        "tenant_name": claims.get("tenant_name"),
    }


def _auth_user_id_from_claims(claims: dict) -> str:
    uid = claims.get("auth_user_id")
    if not uid:
        raise HTTPException(
            status_code=403,
            detail="session missing auth_user_id — sign out and sign in again",
        )
    return str(uid)


@app.get("/portal/members")
def portal_list_members(request: Request, authorization: str | None = Header(default=None)):
    claims = _require_tenant(authorization, request)
    with _conn() as conn:
        return list_members(conn, claims["sub"])


@app.post("/portal/members/invite")
def portal_invite_member(
    request: Request,
    body: InviteMemberBody,
    authorization: str | None = Header(default=None),
):
    """Owner invites a human to THIS tenant. Tenant id comes only from JWT ``sub``."""
    claims = _require_owner(authorization, request)
    inviter = _auth_user_id_from_claims(claims)
    # Ignore any tenant_id the client might try to smuggle — body has email only.
    with _conn() as conn:
        try:
            invited = invite_member_to_tenant(
                conn,
                tenant_id=claims["sub"],
                inviter_auth_user_id=inviter,
                email=body.email,
            )
            conn.commit()
            return invited
        except TenantAuthError as e:
            conn.rollback()
            raise HTTPException(status_code=e.status, detail=e.reason) from e


@app.get("/portal/agents")
def list_agents_route(request: Request, authorization: str | None = Header(default=None)):
    claims = _require_tenant(authorization, request)
    with _conn() as conn:
        return queries.list_agents(conn, claims["sub"])


@app.post("/portal/agents")
def create_agent_route(
    request: Request,
    body: CreateAgentBody,
    authorization: str | None = Header(default=None),
):
    claims = _require_owner(authorization, request)
    with _conn() as conn:
        # F-M26: nothing limited how many agents a tenant could create.
        existing = conn.execute(
            "select count(*) from agents where tenant_id = %s", (claims["sub"],)
        ).fetchone()
        if existing and existing[0] >= MAX_AGENTS_PER_TENANT:
            raise HTTPException(
                status_code=409,
                detail=f"agent limit reached ({MAX_AGENTS_PER_TENANT}) - delete an agent first",
            )
        resolved = _resolve_provider_fields(conn, body, current=None)
        opening = _opening_from_body(body, None)
        tools = _tools_webhook_from_body(body, None)
        created = queries.create_agent(
            conn,
            claims["sub"],
            name=body.name,
            prompt=body.prompt,
            voice_id=resolved["voice_id"],
            llm_model=resolved["llm_model"],
            agent_language=resolved["agent_language"],
            stt_provider=resolved["stt_provider"],
            stt_model=resolved["stt_model"],
            stt_options=resolved["stt_options"],
            llm_provider=resolved["llm_provider"],
            llm_options=resolved["llm_options"],
            tts_provider=resolved["tts_provider"],
            tts_voice_id=resolved["tts_voice_id"],
            tts_options=resolved["tts_options"],
            greeting=opening["greeting"],
            first_speaker=opening["first_speaker"],
            recording_enabled=_recording_enabled_from_body(body, None),
            tools_base_url=tools["tools_base_url"],
            tools_auth_secret=tools["tools_auth_secret"],
        )
        conn.commit()
        return created


@app.patch("/portal/agents/{agent_id}")
def update_agent_route(
    request: Request,
    agent_id: str,
    body: UpdateAgentBody,
    authorization: str | None = Header(default=None),
):
    claims = _require_owner(authorization, request)
    with _conn() as conn:
        current = queries.get_agent(conn, claims["sub"], agent_id)
        if current is None:
            raise HTTPException(status_code=404, detail="agent not found")
        resolved = _resolve_provider_fields(conn, body, current=current)
        opening = _opening_from_body(body, current)
        tools = _tools_webhook_from_body(body, current)
        try:
            updated = queries.update_agent(
                conn,
                claims["sub"],
                agent_id,
                name=body.name,
                prompt=body.prompt,
                voice_id=resolved["voice_id"],
                llm_model=resolved["llm_model"],
                agent_language=resolved["agent_language"],
                stt_provider=resolved["stt_provider"],
                stt_model=resolved["stt_model"],
                stt_options=resolved["stt_options"],
                llm_provider=resolved["llm_provider"],
                llm_options=resolved["llm_options"],
                tts_provider=resolved["tts_provider"],
                tts_voice_id=resolved["tts_voice_id"],
                tts_options=resolved["tts_options"],
                greeting=opening["greeting"],
                first_speaker=opening["first_speaker"],
                recording_enabled=_recording_enabled_from_body(body, current),
                tools_base_url=tools["tools_base_url"],
                tools_auth_secret=tools["tools_auth_secret"],
            )
            conn.commit()
            return updated
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/portal/provider-capabilities")
def provider_capabilities_route(request: Request, authorization: str | None = Header(default=None)):
    """Phase 4, ADR-036. Tenant JWT required (Phase 0's decision: matches the existing dual-route
    auth pattern for /portal + /machine rather than a new unauthenticated route). Only `enabled`
    combinations are ever returned — see provider_capabilities.py's own docstring."""
    _require_tenant(authorization, request)
    with _conn() as conn:
        return get_public_capabilities(conn)


class AllowedOriginsBody(BaseModel):
    """Browser origins allowed to start sessions for this tenant.

    Hosted mint rejects an empty allowlist (P1-H2). Local/dev still permits empty for
    convenience. Always set production dashboard + app origins before go-live.
    """

    allowed_origins: list[str] = Field(default_factory=list)


def _normalize_origin(request: Request, raw: str) -> str:
    """An Origin header is scheme://host[:port] with no path - match that exactly, or the
    mint's `origin not in allowed_origins` comparison silently never matches."""
    text = (raw or "").strip().rstrip("/")
    if not text:
        raise HTTPException(status_code=422, detail="origin must not be empty")
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail=f"origin must look like https://app.example.com (got {raw!r})",
        )
    if parsed.path or parsed.query or parsed.fragment:
        raise HTTPException(
            status_code=422,
            detail=f"origin must not include a path, query or fragment (got {raw!r})",
        )
    return f"{parsed.scheme}://{parsed.netloc}"


@app.put("/portal/credentials/allowed-origins")
def set_allowed_origins_route(
    request: Request,
    body: AllowedOriginsBody,
    authorization: str | None = Header(default=None),
):
    """Audit §3.1 / §7: the allowlist was displayed read-only and nothing could set it, so
    the mint's origin check ('if allowed_origins and origin not in allowed_origins') was
    dead code for every tenant."""
    claims = _require_owner(authorization, request)
    if len(body.allowed_origins) > queries.MAX_ALLOWED_ORIGINS:
        raise HTTPException(
            status_code=422,
            detail=f"at most {queries.MAX_ALLOWED_ORIGINS} origins",
        )
    origins = []
    for raw in body.allowed_origins:
        normalized = _normalize_origin(raw)
        if normalized not in origins:
            origins.append(normalized)
    with _conn() as conn:
        queries.set_allowed_origins(conn, claims["sub"], origins)
        conn.commit()
    return {
        "allowed_origins": origins,
        "enforced": bool(origins),
        "note": (
            "Origins are enforced on every browser mint. Hosted mint rejects an empty allowlist."
            if origins
            else (
                "Empty allowlist: hosted mint will reject browser sessions until you add "
                "origins. Local/dev still permits empty."
            )
        ),
    }


@app.get("/portal/credentials")
def credentials_route(request: Request, authorization: str | None = Header(default=None)):
    claims = _require_tenant(authorization, request)
    with _conn() as conn:
        try:
            creds = queries.get_credentials(conn, claims["sub"])
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # Owners see the raw HMAC on API Keys (always visible). Members stay masked.
    # Console rotation stays disabled separately (see rotate-secret).
    from .session_cookie import browser_secret_reveal_enabled

    if (
        browser_secret_reveal_enabled()
        and str(claims.get("role") or "").lower() == "owner"
    ):
        with _conn() as conn:
            try:
                creds["hmac_secret"] = queries.get_raw_secret(conn, claims["sub"])
            except ValueError:
                creds["hmac_secret"] = None
    return creds


@app.get("/portal/overview")
def overview_route(request: Request, authorization: str | None = Header(default=None)):
    """Aggregated Overview payload — one DB checkout instead of five browser round-trips."""
    claims = _require_tenant(authorization, request)
    with _conn() as conn:
        try:
            return queries.get_overview_snapshot(conn, claims["sub"])
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


# Console rotate is age-gated when break-glass is enabled. Standing HMAC visibility is not.
REVEAL_MAX_TOKEN_AGE_SEC = 300


def _require_fresh_tenant_token(claims: dict) -> None:
    issued_at = claims.get("iat")
    if issued_at is None:
        raise HTTPException(status_code=401, detail="token cannot be age-checked")
    age = time.time() - float(issued_at)
    if age > REVEAL_MAX_TOKEN_AGE_SEC:
        raise HTTPException(
            status_code=401,
            detail=(
                "log in again to rotate the signing secret "
                f"(token older than {REVEAL_MAX_TOKEN_AGE_SEC // 60} minutes)"
            ),
        )


@app.get("/portal/credentials/secret")
def credentials_secret_route(
    request: Request, authorization: str | None = Header(default=None)
):
    """Return raw HMAC for owners (default on). Opt out: ``PORTAL_ALLOW_BROWSER_SECRET_REVEAL=0``."""
    from .session_cookie import browser_secret_reveal_enabled

    if not browser_secret_reveal_enabled():
        raise HTTPException(
            status_code=410,
            detail=(
                "Browser secret reveal is disabled for this deployment. "
                "Ask an operator for the HMAC via a secure channel."
            ),
        )

    claims = _require_owner(authorization, request)
    client_ip = request.client.host if request.client else None
    with _conn() as conn:
        try:
            secret = queries.get_raw_secret(conn, claims["sub"])
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        record_attempt(
            conn,
            realm="portal-secret-reveal",
            identity=claims["sub"],
            client_ip=client_ip,
            successful=True,
            reason="hmac secret revealed",
        )
        conn.commit()
    return {"hmac_secret": secret}


@app.post("/portal/credentials/rotate-secret")
def rotate_secret_route(
    request: Request, authorization: str | None = Header(default=None)
):
    """Console HMAC rotate — **disabled by default**.

    Owners can view the current secret on API Keys; rotating is admin / break-glass only
    (``PORTAL_ALLOW_BROWSER_SECRET_ROTATE=1``). When disabled this route does not rotate.
    """
    from .session_cookie import browser_secret_rotate_enabled

    if not browser_secret_rotate_enabled():
        raise HTTPException(
            status_code=410,
            detail=(
                "Browser HMAC rotate is disabled. Copy the current secret from API Keys, "
                "or ask an AwaazLabs operator to rotate via admin."
            ),
        )

    claims = _require_owner(authorization, request)
    _require_fresh_tenant_token(claims)
    client_ip = request.client.host if request.client else None
    with _conn() as conn:
        try:
            new_secret = queries.rotate_own_secret(conn, claims["sub"])
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        record_attempt(
            conn,
            realm="portal-secret-rotate",
            identity=claims["sub"],
            client_ip=client_ip,
            successful=True,
            reason="hmac secret rotated (break-glass browser)",
        )
        conn.commit()
    return {
        "hmac_secret": new_secret,
        "warning": (
            "This value is shown once. Update every host backend that signs mint requests; "
            "the previous secret stops working immediately."
        ),
    }


@app.delete("/portal/agents/{agent_id}")
def archive_agent_route(request: Request, agent_id: str, authorization: str | None = Header(default=None)):
    """F-M13: retire an agent.

    Archive, not delete: sessions.agent_id cascades on delete, so removing the row would take
    the tenant's session and usage history with it. Archived agents disappear from the list,
    release any phone number assigned to them, and free a slot against MAX_AGENTS_PER_TENANT.
    Erasure of the personal data in those sessions is the retention job's job (F-C4).
    """
    claims = _require_owner(authorization, request)
    with _conn() as conn:
        live = queries.count_live_sessions_for_agent(conn, claims["sub"], agent_id)
        if live:
            raise HTTPException(
                status_code=409,
                detail=f"agent has {live} live session(s) - end them before archiving",
            )
        if not queries.archive_agent(conn, claims["sub"], agent_id):
            raise HTTPException(status_code=404, detail="agent not found")
        conn.commit()
    return {"id": agent_id, "archived": True}


@app.get("/portal/escalations")
def list_escalations_route(request: Request, 
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT),
    authorization: str | None = Header(default=None),
):
    """F-M12: escalations was write-only. worker/tools.py::escalate_to_human inserted rows
    that no API, UI or query could read back, so the feature produced records nobody could
    act on while caller phone numbers accumulated unseen."""
    claims = _require_tenant(authorization, request)
    with _conn() as conn:
        return queries.list_escalations(conn, claims["sub"], limit=limit)


@app.get("/portal/sessions")
def sessions_route(request: Request, 
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_LIMIT),
    authorization: str | None = Header(default=None),
):
    """Lean session list: summary + metadata, no transcript, no recording re-sign.

    Full transcript/recording are loaded via ``GET /portal/sessions/{session_id}``.
    """
    claims = _require_tenant(authorization, request)
    with _conn() as conn:
        return queries.list_recent_sessions(
            conn, claims["sub"], limit=limit, include_transcript=False
        )


@app.get("/portal/sessions/{session_id}")
def session_detail_route(request: Request, 
    session_id: str, authorization: str | None = Header(default=None)
):
    claims = _require_tenant(authorization, request)
    with _conn() as conn:
        session = queries.get_session(conn, claims["sub"], session_id)
        if not session:
            raise HTTPException(status_code=404, detail="session not found")
    return enrich_session_recording(session)


@app.post("/machine/sessions/get")
def machine_get_session_route(
    body: dict[str, Any] = Body(default_factory=dict),
    x_tenant_id: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    x_nonce: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
):
    """SDK/host CRM: fetch a session (incl. recording_url) by LiveKit room_name."""
    payload = body or {}
    room_name = str(payload.get("room_name") or payload.get("roomName") or "").strip()
    if not room_name:
        raise HTTPException(status_code=400, detail="room_name is required")
    with _conn() as conn:
        _require_machine(
            conn,
            x_tenant_id=x_tenant_id,
            x_timestamp=x_timestamp,
            x_nonce=x_nonce,
            x_signature=x_signature,
            action="session.get",
            body={"room_name": room_name},
        )
        session = queries.get_session_by_room(conn, x_tenant_id, room_name)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return enrich_session_recording(session)


@app.get("/portal/usage-summary")
def usage_summary_route(request: Request, 
    authorization: str | None = Header(default=None),
    month: str | None = Query(
        default=None,
        description="Optional calendar month as YYYY-MM. Default: current month.",
        pattern=r"^\d{4}-\d{2}$",
    ),
):
    """Calendar-month usage (1st through end of month). Optional `month=YYYY-MM` for history."""
    claims = _require_tenant(authorization, request)
    with _conn() as conn:
        try:
            return queries.usage_summary(conn, claims["sub"], month=month)
        except ValueError as e:
            detail = str(e)
            status = 400 if "month" in detail.lower() else 404
            raise HTTPException(status_code=status, detail=detail) from e


# --- Machine-auth agent management (existing tenants, no dashboard/JWT login required) ---
#
# Authenticated with the tenant's own HMAC secret (same secret used to sign /v1/session mint
# requests — see docs/MACHINE_AGENT_API_CONTRACT.md), NOT the tenant-portal JWT above. Intended for
# a client's own backend calling programmatically; never for a browser.


@app.post("/machine/agents")
def machine_create_agent_route(
    body: CreateAgentBody,
    x_tenant_id: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    x_nonce: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
):
    with _conn() as conn:
        _require_machine(
            conn,
            x_tenant_id=x_tenant_id,
            x_timestamp=x_timestamp,
            x_nonce=x_nonce,
            x_signature=x_signature,
            action="agent.create",
            # exclude_none=True (matches agent.update below): CreateAgentBody now has optional
            # provider/language fields (Phase 3, ADR-036) that default to None when omitted.
            # model_dump() without this would include those None-valued keys in the signed
            # payload, but the signing client (sdk-server, this file's own test suite) only ever
            # signs the fields it explicitly set — the mismatch silently broke every create-agent
            # HMAC signature the moment the first optional field was added. Caught by re-running
            # the existing machine-auth test suite, not assumed safe.
            body=body.model_dump(exclude_none=True),
        )
        resolved = _resolve_provider_fields(conn, body, current=None)
        opening = _opening_from_body(body, None)
        tools = _tools_webhook_from_body(body, None)
        created = queries.create_agent(
            conn,
            x_tenant_id,
            name=body.name,
            prompt=body.prompt,
            voice_id=resolved["voice_id"],
            llm_model=resolved["llm_model"],
            agent_language=resolved["agent_language"],
            stt_provider=resolved["stt_provider"],
            stt_model=resolved["stt_model"],
            stt_options=resolved["stt_options"],
            llm_provider=resolved["llm_provider"],
            llm_options=resolved["llm_options"],
            tts_provider=resolved["tts_provider"],
            tts_voice_id=resolved["tts_voice_id"],
            tts_options=resolved["tts_options"],
            greeting=opening["greeting"],
            first_speaker=opening["first_speaker"],
            recording_enabled=_recording_enabled_from_body(body, None),
            tools_base_url=tools["tools_base_url"],
            tools_auth_secret=tools["tools_auth_secret"],
        )
        conn.commit()
        return created


@app.get("/machine/provider-capabilities")
def machine_provider_capabilities_route(
    x_tenant_id: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    x_nonce: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
):
    """Phase 4, ADR-036 — machine-auth mirror of /portal/provider-capabilities, same content."""
    with _conn() as conn:
        _require_machine(
            conn,
            x_tenant_id=x_tenant_id,
            x_timestamp=x_timestamp,
            x_nonce=x_nonce,
            x_signature=x_signature,
            action="provider_capabilities.get",
            body={},
        )
        return get_public_capabilities(conn)


@app.get("/machine/agents")
def machine_list_agents_route(
    x_tenant_id: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    x_nonce: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
):
    with _conn() as conn:
        _require_machine(
            conn,
            x_tenant_id=x_tenant_id,
            x_timestamp=x_timestamp,
            x_nonce=x_nonce,
            x_signature=x_signature,
            action="agent.list",
            body={},
        )
        return queries.list_agents(conn, x_tenant_id)


@app.patch("/machine/agents/{agent_id}")
def machine_update_agent_route(
    agent_id: str,
    body: UpdateAgentBody,
    x_tenant_id: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    x_nonce: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
):
    with _conn() as conn:
        _require_machine(
            conn,
            x_tenant_id=x_tenant_id,
            x_timestamp=x_timestamp,
            x_nonce=x_nonce,
            x_signature=x_signature,
            action="agent.update",
            body=body.model_dump(exclude_none=True),
        )
        current = queries.get_agent(conn, x_tenant_id, agent_id)
        if current is None:
            raise HTTPException(status_code=404, detail="agent not found")
        resolved = _resolve_provider_fields(conn, body, current=current)
        opening = _opening_from_body(body, current)
        tools = _tools_webhook_from_body(body, current)
        try:
            updated = queries.update_agent(
                conn,
                x_tenant_id,
                agent_id,
                name=body.name,
                prompt=body.prompt,
                voice_id=resolved["voice_id"],
                llm_model=resolved["llm_model"],
                agent_language=resolved["agent_language"],
                stt_provider=resolved["stt_provider"],
                stt_model=resolved["stt_model"],
                stt_options=resolved["stt_options"],
                llm_provider=resolved["llm_provider"],
                llm_options=resolved["llm_options"],
                tts_provider=resolved["tts_provider"],
                tts_voice_id=resolved["tts_voice_id"],
                tts_options=resolved["tts_options"],
                greeting=opening["greeting"],
                first_speaker=opening["first_speaker"],
                recording_enabled=_recording_enabled_from_body(body, current),
                tools_base_url=tools["tools_base_url"],
                tools_auth_secret=tools["tools_auth_secret"],
            )
            conn.commit()
            return updated
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


app.include_router(telephony_router)
app.include_router(telephony_webhook_router)

from .test_studio import register_test_studio_routes  # noqa: E402

register_test_studio_routes(app, conn_factory=_conn)
