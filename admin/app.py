"""FastAPI super-admin portal backend (docs/26-PHASE-6-ADMIN.md).

A COMPLETELY SEPARATE FastAPI app from control_plane/app.py — different module, meant to run as
its own process on its own port (e.g. `uvicorn admin.app:app --port 8001`) with its own CORS
allowlist. The SDK's client bundle never imports or references anything under `admin/` (verified:
`grep -rE "admin" sdk/src sdk/dist` -> no path/route match — see tests/test_admin.py), so
"admin portal is NOT reachable from the SDK's origin" (GATE 6 line 4) holds by construction: no
tenant-facing code path ever knows this app exists, and its CORS allowlist (`ADMIN_PORTAL_ORIGINS`)
is a fixed, separately-configured value that is never derived from — and therefore can never
silently include — any tenant's `tenants.allowed_origins` entry.

Auth: every route except /admin/login requires `Authorization: Bearer <admin JWT>`
(admin/auth.py::verify_admin_jwt) — a LiveKit tenant AccessToken fails this both on signature
(different secret) and shape (no `aud`, has `video`). Every successful call records one
admin_audit_log row (GATE 6 line 3) via admin/audit.py::record_admin_action.
"""

from __future__ import annotations

import os
import secrets as _pysecrets
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from scripts.dbconn import conn_kwargs
except ImportError:
    from dbconn import conn_kwargs  # type: ignore # noqa: E402


from .audit import record_admin_action  # noqa: E402
from .auth import AdminAuthError, login as admin_login, verify_admin_jwt  # noqa: E402
from . import queries  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _ROOT / ".env.local"


def _admin_is_hosted() -> bool:
    """Local copy of control_plane.runtime_env.is_hosted — the admin image deliberately does
    not vendor control_plane/ (docker/admin.Dockerfile copies admin/ + scripts/dbconn.py)."""
    truthy = {"1", "true", "yes", "on"}
    hosted_names = {"production", "prod", "staging", "preview"}
    explicit = (os.environ.get("UVA_ENV") or "").strip().lower()
    if explicit:
        return explicit in hosted_names
    if (os.environ.get("RENDER") or "").strip().lower() in truthy:
        return True
    return (os.environ.get("ENVIRONMENT") or "").strip().lower() in hosted_names


def _ensure_admin_jwt_secret() -> str:
    """Read ADMIN_JWT_SECRET from the environment, then .env.local.

    F-H13: this used to generate a secret and append it to .env.local at import time. In a
    container that either crashes (read-only filesystem) or silently rotates the signing key
    on every deploy, invalidating every admin session. Generation is now local-development
    only; a hosted service with no ADMIN_JWT_SECRET refuses to start.
    """
    env = dotenv_values(_ENV_PATH)
    val = os.environ.get("ADMIN_JWT_SECRET") or env.get("ADMIN_JWT_SECRET")
    if val:
        return val
    if _admin_is_hosted():
        raise RuntimeError(
            "ADMIN_JWT_SECRET must be set when running in a hosted environment. It signs "
            "admin session tokens; auto-generating one would rotate on every deploy and "
            "invalidate every session. Set it in the service environment, or set "
            "UVA_ENV=development if this really is a local machine."
        )
    generated = _pysecrets.token_hex(32)
    with open(_ENV_PATH, "a", encoding="utf-8") as f:
        f.write(
            "\n# auto-generated for local development by admin/app.py - "
            "never used in a hosted environment\n"
            f"ADMIN_JWT_SECRET={generated}\n"
        )
    return generated


ADMIN_JWT_SECRET = _ensure_admin_jwt_secret()
_DEFAULT_ADMIN_ORIGINS = "http://localhost:5173"
ADMIN_PORTAL_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ADMIN_PORTAL_ORIGINS", dotenv_values(_ENV_PATH).get("ADMIN_PORTAL_ORIGINS", "")
    ).split(",")
    if o.strip()
] or [_DEFAULT_ADMIN_ORIGINS]

app = FastAPI(title="UVA super-admin portal")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ADMIN_PORTAL_ORIGINS,  # fixed allowlist, never a tenant origin, never "*"
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/healthz")
def admin_health():
    """Minimal liveness probe for super-admin service."""
    return {"status": "ok", "service": "uva-admin"}


class LoginBody(BaseModel):
    email: str
    password: str
    totp_code: str


def _conn() -> psycopg.Connection:
    return psycopg.connect(**conn_kwargs(), connect_timeout=10)


def _require_admin(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[len("Bearer ") :]
    try:
        return verify_admin_jwt(token, ADMIN_JWT_SECRET)
    except AdminAuthError as e:
        raise HTTPException(status_code=e.status, detail=e.reason) from e


@app.post("/admin/login")
def login_route(body: LoginBody):
    try:
        with _conn() as conn:
            return admin_login(
                conn,
                email=body.email,
                password=body.password,
                totp_code=body.totp_code,
                jwt_secret=ADMIN_JWT_SECRET,
            )
    except AdminAuthError as e:
        raise HTTPException(status_code=e.status, detail=e.reason) from e


@app.get("/admin/tenants")
def tenants_route(authorization: str | None = Header(default=None)):
    claims = _require_admin(authorization)
    with _conn() as conn:
        rows = queries.list_tenants(conn)
        record_admin_action(conn, admin_id=claims["sub"], action="list_tenants")
        conn.commit()
        return rows


@app.get("/admin/agents")
def agents_route(authorization: str | None = Header(default=None)):
    claims = _require_admin(authorization)
    with _conn() as conn:
        rows = queries.list_agents(conn)
        record_admin_action(conn, admin_id=claims["sub"], action="list_agents")
        conn.commit()
        return rows


@app.get("/admin/sessions")
def sessions_route(
    tenant_id: str | None = None, authorization: str | None = Header(default=None)
):
    claims = _require_admin(authorization)
    with _conn() as conn:
        rows = queries.list_sessions(conn, tenant_id=tenant_id)
        record_admin_action(
            conn,
            admin_id=claims["sub"],
            action="list_sessions",
            detail={"tenant_id": tenant_id},
        )
        conn.commit()
        return rows


@app.get("/admin/usage")
def usage_route(authorization: str | None = Header(default=None)):
    claims = _require_admin(authorization)
    with _conn() as conn:
        rows = queries.usage_by_tenant_day_kind(conn)
        record_admin_action(conn, admin_id=claims["sub"], action="usage")
        conn.commit()
        return rows


@app.get("/admin/quota")
def quota_route(authorization: str | None = Header(default=None)):
    claims = _require_admin(authorization)
    with _conn() as conn:
        rows = queries.quota_near_cap(conn)
        record_admin_action(conn, admin_id=claims["sub"], action="quota")
        conn.commit()
        return rows


@app.get("/admin/concurrency")
def concurrency_route(authorization: str | None = Header(default=None)):
    claims = _require_admin(authorization)
    with _conn() as conn:
        data = queries.live_concurrency(conn)
        record_admin_action(conn, admin_id=claims["sub"], action="concurrency")
        conn.commit()
        return data


@app.get("/admin/blockers")
def blockers_route(authorization: str | None = Header(default=None)):
    claims = _require_admin(authorization)
    with _conn() as conn:
        rows = queries.blockers(conn)
        record_admin_action(conn, admin_id=claims["sub"], action="blockers")
        conn.commit()
        return rows


@app.post("/admin/tenants/{tenant_id}/rotate-secret")
def rotate_secret_route(
    tenant_id: str, authorization: str | None = Header(default=None)
):
    """Admin-only secret rotation: generates a new HMAC secret for tenant_id,
    stores it in DB, and returns the raw secret ONCE.
    """
    claims = _require_admin(authorization)
    with _conn() as conn:
        try:
            new_secret = queries.rotate_tenant_secret(conn, tenant_id)
            record_admin_action(
                conn,
                admin_id=claims["sub"],
                action=f"rotate_secret:{tenant_id}",
            )
            conn.commit()
            return {
                "tenant_id": tenant_id,
                "new_hmac_secret": new_secret,
                "warning": "Store this secret securely now. It will never be displayed again.",
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))


@app.get("/admin/tenants/{tenant_id}/credentials")
def tenant_credentials_route(
    tenant_id: str, authorization: str | None = Header(default=None)
):
    """Admin-only masked credential view for a tenant."""
    claims = _require_admin(authorization)
    with _conn() as conn:
        try:
            creds = queries.get_tenant_credentials_masked(conn, tenant_id)
            record_admin_action(
                conn,
                admin_id=claims["sub"],
                action=f"read_credentials:{tenant_id}",
            )
            conn.commit()
            return creds
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
