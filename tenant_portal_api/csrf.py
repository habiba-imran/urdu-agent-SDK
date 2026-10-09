"""CSRF defense for cookie-authenticated ``/portal/*`` mutating requests (A-02).

The portal session cookie is ``SameSite=None; Secure`` on hosted so a cross-site
dashboard can call the API. That also means a cross-site HTML form POST from any
page a logged-in owner visits will send the cookie. JSON body routes reject
``application/x-www-form-urlencoded`` with 422, but body-less POSTs
(``/telnyx/reverify``, ``/numbers/sync``, ``/numbers/{id}/disable``, …) do not.

Defense (either is enough):
1. ``Origin`` / ``Referer`` host matches ``TENANT_PORTAL_ORIGINS``, or
2. Custom header ``X-UVA-Portal: 1`` (browsers cannot set custom headers on
   simple form navigations; the dashboard ``fetch`` always sends it).

``/machine/*`` (HMAC) and ``/webhooks/*`` are out of scope.
"""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

PORTAL_CSRF_HEADER = "X-UVA-Portal"
PORTAL_CSRF_HEADER_VALUE = "1"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def origin_from_url(value: str | None) -> str | None:
    """Return ``scheme://netloc`` or None when the value is not an absolute URL."""
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    # Origin header is already scheme://host[:port] with no path.
    if "://" not in raw and raw.startswith("/") is False and " " not in raw:
        # Some proxies pass bare origins; accept scheme-less only when it looks like host:port
        return None
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def request_origin(request: Request) -> str | None:
    origin = origin_from_url(request.headers.get("origin"))
    if origin:
        return origin
    return origin_from_url(request.headers.get("referer"))


def csrf_header_ok(request: Request) -> bool:
    return (request.headers.get(PORTAL_CSRF_HEADER) or "").strip() == PORTAL_CSRF_HEADER_VALUE


def origin_allowed(origin: str | None, allowed_origins: list[str] | tuple[str, ...]) -> bool:
    if not origin:
        return False
    allowed = {o.strip().lower().rstrip("/") for o in allowed_origins if o and o.strip()}
    return origin.rstrip("/") in allowed


def portal_csrf_ok(request: Request, allowed_origins: list[str] | tuple[str, ...]) -> bool:
    """True when a mutating ``/portal/*`` request is allowed through."""
    if csrf_header_ok(request):
        return True
    return origin_allowed(request_origin(request), allowed_origins)


class PortalCsrfMiddleware(BaseHTTPMiddleware):
    """Reject mutating ``/portal/*`` requests that lack Origin allowlist or CSRF header."""

    def __init__(self, app: ASGIApp, allowed_origins: list[str] | tuple[str, ...]) -> None:
        super().__init__(app)
        self.allowed_origins = list(allowed_origins)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path or ""
        method = (request.method or "GET").upper()
        if (
            method not in _SAFE_METHODS
            and path.startswith("/portal/")
            and not portal_csrf_ok(request, self.allowed_origins)
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "CSRF check failed: send Origin/Referer matching "
                        "TENANT_PORTAL_ORIGINS, or header X-UVA-Portal: 1"
                    )
                },
            )
        return await call_next(request)
