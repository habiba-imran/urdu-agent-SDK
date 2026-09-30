"""Live portal access checks (Wave 1 / P1-C1 / MISS-1).

JWT signature alone is not enough: every human session must still map to an
active ``tenant_members`` row for the token's tenant, and the role used for
authorization is read from the database (not trusted from the JWT claim alone).

Legacy HMAC ``/portal/login`` tokens have no ``auth_user_id`` — those are treated
as owner-equivalent for ops/tests only.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg
from fastapi import HTTPException

from control_plane.runtime_env import is_hosted

from .auth import TenantAuthError, verify_tenant_jwt
from .membership import get_membership_by_auth_user


def auto_bootstrap_enabled() -> bool:
    """Whether a Supabase user with no membership may create a new tenant as owner.

    Hosted: off by default (P1-H1). Local/dev: on. Override with
    ``PORTAL_ALLOW_TENANT_BOOTSTRAP=1|0``.
    """
    flag = (os.environ.get("PORTAL_ALLOW_TENANT_BOOTSTRAP") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    return not is_hosted()


def enrich_claims_with_live_membership(
    conn: psycopg.Connection, claims: dict[str, Any]
) -> dict[str, Any]:
    """Mutate/return claims with live ``role``; raise TenantAuthError if membership gone."""
    tenant_id = str(claims.get("sub") or "")
    if not tenant_id:
        raise TenantAuthError(401, "invalid tenant token")

    auth_user_id = claims.get("auth_user_id")
    if not auth_user_id:
        # Legacy HMAC portal login — no human membership row.
        claims["role"] = "owner"
        claims["_legacy_hmac_session"] = True
        return claims

    membership = get_membership_by_auth_user(conn, str(auth_user_id))
    if membership is None or membership["tenant_id"] != tenant_id:
        raise TenantAuthError(401, "membership revoked or missing — sign in again")
    if membership.get("tenant_status") != "active":
        raise TenantAuthError(403, "tenant suspended")
    status = str(membership.get("status") or "active")
    if status not in {"active", "invited"}:
        raise TenantAuthError(403, "membership not active")

    claims["role"] = membership["role"]
    claims["auth_user_id"] = membership["auth_user_id"]
    return claims


def require_portal_claims(
    conn: psycopg.Connection,
    *,
    jwt_secret: str,
    authorization: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    raw = (token or "").strip()
    if not raw and authorization and authorization.startswith("Bearer "):
        raw = authorization[len("Bearer ") :].strip()
    if not raw:
        raise TenantAuthError(401, "missing bearer token")
    claims = verify_tenant_jwt(raw, jwt_secret)
    return enrich_claims_with_live_membership(conn, claims)


def require_owner_claims(claims: dict[str, Any]) -> dict[str, Any]:
    if claims.get("role") != "owner":
        raise TenantAuthError(403, "owner role required")
    return claims


def http_require_portal(
    conn: psycopg.Connection,
    *,
    jwt_secret: str,
    authorization: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    try:
        return require_portal_claims(
            conn,
            authorization=authorization,
            token=token,
            jwt_secret=jwt_secret,
        )
    except TenantAuthError as e:
        raise HTTPException(status_code=e.status, detail=e.reason) from e


def http_require_owner(
    conn: psycopg.Connection,
    *,
    jwt_secret: str,
    authorization: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    claims = http_require_portal(
        conn,
        authorization=authorization,
        token=token,
        jwt_secret=jwt_secret,
    )
    try:
        return require_owner_claims(claims)
    except TenantAuthError as e:
        raise HTTPException(status_code=e.status, detail=e.reason) from e
