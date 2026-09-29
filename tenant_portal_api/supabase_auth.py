"""Supabase Auth JWT verification for the tenant portal (Phase 1).

Dashboard signs in with email/password via Supabase; the browser sends the
Supabase access_token here. We verify it and read ``sub`` (= auth.users.id) + email.

Modern Supabase projects sign user access tokens with **asymmetric** keys (ES256/RS256)
via JWKS. Legacy projects still use HS256 with the project JWT secret. We support both.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

import jwt as pyjwt
from jwt import PyJWKClient

from .auth import TenantAuthError

_log = logging.getLogger("tenant_portal_api.supabase_auth")


def _supabase_url() -> str:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    if not url:
        raise TenantAuthError(503, "SUPABASE_URL is not configured on the tenant portal")
    return url


def supabase_jwt_secret() -> str | None:
    value = (os.environ.get("SUPABASE_JWT_SECRET") or "").strip()
    return value or None


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    # Supabase Auth JWKS (JWT Signing Keys).
    return PyJWKClient(f"{_supabase_url()}/auth/v1/.well-known/jwks.json")


def verify_supabase_access_token(access_token: str) -> dict:
    """Return claims for a valid Supabase user access token."""
    token = (access_token or "").strip()
    if not token:
        raise TenantAuthError(401, "missing supabase access token")

    try:
        header = pyjwt.get_unverified_header(token)
    except pyjwt.PyJWTError as e:
        raise TenantAuthError(401, "invalid supabase token") from e

    alg = (header.get("alg") or "").upper()
    claims: dict | None = None
    last_err: Exception | None = None

    if alg in ("ES256", "RS256", "EdDSA") or header.get("kid"):
        try:
            key = _jwks_client().get_signing_key_from_jwt(token).key
            # leeway: local clock vs Supabase can be a few seconds off → "iat not yet valid"
            claims = pyjwt.decode(
                token,
                key,
                algorithms=[alg] if alg else ["ES256", "RS256"],
                audience="authenticated",
                leeway=60,
            )
        except Exception as e:
            last_err = e
            _log.warning("supabase JWKS verify failed: %s", e)

    if claims is None and alg in ("HS256", ""):
        secret = supabase_jwt_secret()
        if not secret:
            raise TenantAuthError(
                503,
                "SUPABASE_JWT_SECRET is not configured (needed for legacy HS256 tokens)",
            )
        try:
            claims = pyjwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
                leeway=60,
            )
        except pyjwt.PyJWTError as e:
            last_err = e

    if claims is None:
        _log.warning("supabase token rejected: %s", last_err)
        raise TenantAuthError(401, "invalid supabase token") from last_err

    sub = claims.get("sub")
    if not sub:
        raise TenantAuthError(401, "invalid supabase token")

    role = claims.get("role")
    if role and role not in ("authenticated", "service_role"):
        raise TenantAuthError(401, "invalid supabase token")

    return claims
