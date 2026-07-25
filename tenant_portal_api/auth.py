"""Tenant portal auth.

Separate from both control-plane mint auth and super-admin auth:
- control-plane auth proves a host backend can mint a room token
- admin auth proves a super-admin may inspect the whole system
- tenant portal auth proves ONE tenant may manage only its own agents/data

The MVP login uses the existing tenant credential pair: tenant_id + tenant HMAC secret.
That keeps the trust boundary explicit without inventing a brand-new identity product in this
phase. The browser/portal never receives provider secrets; it exchanges the tenant secret once
for a tenant-portal JWT and uses that JWT on subsequent requests.
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


def login(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    tenant_secret: str,
    jwt_secret: str,
    now: int | None = None,
) -> dict:
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

    tid, name, status, stored_hash = row
    if status != "active":
        raise TenantAuthError(403, "tenant suspended")

    provided_hash = secret_hash(tenant_secret)
    if not stored_hash or not hmac.compare_digest(provided_hash, stored_hash):
        raise TenantAuthError(401, "invalid credentials")

    now_dt = (
        datetime.datetime.fromtimestamp(now, tz=datetime.UTC)
        if now is not None
        else datetime.datetime.now(datetime.UTC)
    )
    claims = {
        "sub": str(tid),
        "aud": TENANT_JWT_AUDIENCE,
        "iss": TENANT_JWT_ISSUER,
        "tenant_name": name,
        "iat": now_dt,
        "exp": now_dt + datetime.timedelta(seconds=TENANT_JWT_TTL_SEC),
    }
    token = pyjwt.encode(claims, jwt_secret, algorithm="HS256")
    return {
        "token": token,
        "tenant_id": str(tid),
        "tenant_name": name,
        "expires_in": TENANT_JWT_TTL_SEC,
    }


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
