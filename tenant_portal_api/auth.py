"""Tenant portal auth.

Separate from both control-plane mint auth and super-admin auth:
- control-plane auth proves a host backend can mint a room token
- admin auth proves a super-admin may inspect the whole system
- tenant portal auth proves ONE tenant may manage only its own agents/data

Phase 1 human login is Supabase email/password → portal JWT (see membership.py).
The legacy ``login`` helper (tenant_id + HMAC) remains for tests / ops tooling only —
the dashboard no longer uses it.
"""

from __future__ import annotations

import datetime
import hmac

import jwt as pyjwt
import psycopg

from control_plane.secrets import secret_hash

TENANT_JWT_AUDIENCE = "tenant-portal"
TENANT_JWT_ISSUER = "uva-tenant-portal"
TENANT_JWT_TTL_SEC = 8 * 3600


class TenantAuthError(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(f"{status}: {reason}")
        self.status = status
        self.reason = reason


def issue_portal_session(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    jwt_secret: str,
    auth_user_id: str | None = None,
    role: str | None = None,
    now: int | None = None,
) -> dict:
    """Issue a tenant-scoped portal JWT. ``sub`` remains the tenant UUID so existing
    /portal/* routes keep working unchanged.
    """
    row = conn.execute(
        "select id, name, status from tenants where id = %s",
        (tenant_id,),
    ).fetchone()
    if row is None:
        raise TenantAuthError(401, "invalid credentials")
    tid, name, status = row
    if status != "active":
        raise TenantAuthError(403, "tenant suspended")

    now_dt = (
        datetime.datetime.fromtimestamp(now, tz=datetime.UTC)
        if now is not None
        else datetime.datetime.now(datetime.UTC)
    )
    claims: dict = {
        "sub": str(tid),
        "aud": TENANT_JWT_AUDIENCE,
        "iss": TENANT_JWT_ISSUER,
        "tenant_name": name,
        "iat": now_dt,
        "exp": now_dt + datetime.timedelta(seconds=TENANT_JWT_TTL_SEC),
    }
    if auth_user_id:
        claims["auth_user_id"] = str(auth_user_id)
    if role:
        claims["role"] = role

    token = pyjwt.encode(claims, jwt_secret, algorithm="HS256")
    return {
        "token": token,
        "tenant_id": str(tid),
        "tenant_name": name,
        "expires_in": TENANT_JWT_TTL_SEC,
    }


def login(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    tenant_secret: str,
    jwt_secret: str,
    now: int | None = None,
) -> dict:
    """Legacy HMAC login — kept for automated tests. Dashboard uses Supabase exchange."""
    row = conn.execute(
        """
        select id, name, status, hmac_secret_hash
        from tenants
        where id = %s
        """,
        (tenant_id,),
    ).fetchone()
    if row is None:
        raise TenantAuthError(401, "invalid credentials")

    tid, _name, status, stored_hash = row
    if status != "active":
        raise TenantAuthError(403, "tenant suspended")

    provided_hash = secret_hash(tenant_secret)
    if not stored_hash or not hmac.compare_digest(provided_hash, stored_hash):
        raise TenantAuthError(401, "invalid credentials")

    return issue_portal_session(
        conn, tenant_id=str(tid), jwt_secret=jwt_secret, now=now
    )


def verify_tenant_jwt(token: str, jwt_secret: str) -> dict:
    try:
        claims = pyjwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience=TENANT_JWT_AUDIENCE,
            issuer=TENANT_JWT_ISSUER,
        )
    except pyjwt.PyJWTError as e:
        raise TenantAuthError(401, "invalid tenant token") from e

    if "video" in claims:
        raise TenantAuthError(401, "invalid tenant token")
    return claims
