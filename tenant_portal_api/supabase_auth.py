"""Supabase Auth JWT verification for the tenant portal (Phase 1).

Dashboard signs in with email/password via Supabase; the browser sends the
Supabase access_token here. We verify it with the project JWT secret and read
``sub`` (= auth.users.id) + email.
"""

from __future__ import annotations

import os

import jwt as pyjwt

from .auth import TenantAuthError


def supabase_jwt_secret() -> str:
    value = (os.environ.get("SUPABASE_JWT_SECRET") or "").strip()
    if not value:
        raise TenantAuthError(
            503,
            "SUPABASE_JWT_SECRET is not configured on the tenant portal",
        )
    return value


def verify_supabase_access_token(access_token: str) -> dict:
    """Return claims for a valid Supabase user access token.

    Expects the standard Supabase HS256 JWT (Settings → API → JWT Secret).
    """
    token = (access_token or "").strip()
    if not token:
        raise TenantAuthError(401, "missing supabase access token")

    try:
        claims = pyjwt.decode(
            token,
            supabase_jwt_secret(),
            algorithms=["HS256"],
            audience="authenticated",
        )
    except pyjwt.PyJWTError as e:
        raise TenantAuthError(401, "invalid supabase token") from e

    sub = claims.get("sub")
    if not sub:
        raise TenantAuthError(401, "invalid supabase token")

    role = claims.get("role")
    if role and role not in ("authenticated", "service_role"):
        # Reject anon / unexpected roles; humans are "authenticated".
        raise TenantAuthError(401, "invalid supabase token")

    return claims
