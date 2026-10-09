"""HttpOnly portal session cookie (Wave 2 / P1-H6).

The dashboard used to keep the portal JWT in ``localStorage``, which is readable by
any XSS. Auth responses now also set an HttpOnly cookie; ``/portal/*`` accepts either
``Authorization: Bearer`` (tests / machine tools / in-memory dashboard fallback) or
the cookie (browser).

Cross-site hosted dashboards (e.g. Vercel → Render) need ``SameSite=None; Secure``.
Same-host local (``localhost:3000`` → ``localhost:8002``) works with ``SameSite=Lax``.
``localhost`` vs ``127.0.0.1`` is cross-site — cookies alone will not stick; the
dashboard keeps an in-memory Bearer for that case (still not localStorage).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Response
from starlette.requests import Request

from control_plane.runtime_env import is_hosted

from .auth import TENANT_JWT_TTL_SEC

PORTAL_SESSION_COOKIE = "uva_portal_session"


def browser_secret_reveal_enabled() -> bool:
    """Whether owners may fetch the raw HMAC via audited ``GET …/credentials/secret``.

    A-03: hosted defaults **off** (one XSS must not equal the signing secret). Local
    defaults **on** for host-backend wiring. Explicit env always wins.
    ``GET /portal/credentials`` never returns the raw secret regardless of this flag.
    """
    flag = (os.environ.get("PORTAL_ALLOW_BROWSER_SECRET_REVEAL") or "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    if flag in {"1", "true", "yes", "on"}:
        return True
    return not is_hosted()


def browser_secret_rotate_enabled() -> bool:
    """Whether ``POST /portal/credentials/rotate-secret`` may run from the browser.

    Default **off** — rotation is admin / out-of-band only. Break-glass:
    ``PORTAL_ALLOW_BROWSER_SECRET_ROTATE=1``.
    """
    flag = (os.environ.get("PORTAL_ALLOW_BROWSER_SECRET_ROTATE") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _cookie_flags() -> dict[str, Any]:
    if is_hosted():
        return {"secure": True, "samesite": "none"}
    # Local HTTP: Secure cookies are dropped by the browser.
    return {"secure": False, "samesite": "lax"}


def set_portal_session_cookie(response: Response, token: str) -> None:
    flags = _cookie_flags()
    response.set_cookie(
        key=PORTAL_SESSION_COOKIE,
        value=token,
        max_age=TENANT_JWT_TTL_SEC,
        httponly=True,
        path="/",
        secure=bool(flags["secure"]),
        samesite=str(flags["samesite"]),
    )


def clear_portal_session_cookie(response: Response) -> None:
    flags = _cookie_flags()
    response.delete_cookie(
        key=PORTAL_SESSION_COOKIE,
        path="/",
        secure=bool(flags["secure"]),
        samesite=str(flags["samesite"]),
    )


def portal_token_from_request(
    request: Request, authorization: str | None
) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
        if token:
            return token
    cookie = request.cookies.get(PORTAL_SESSION_COOKIE)
    if cookie and cookie.strip():
        return cookie.strip()
    return None
