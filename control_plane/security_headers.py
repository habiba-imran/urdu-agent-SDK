"""Baseline security response headers for every FastAPI service (F-M10).

No service set CSP, HSTS, X-Frame-Options or X-Content-Type-Options. CSP matters most here:
it is the main mitigation for the XSS chain in F-C6, where one injected script in the
dashboard can read the tenant's signing secret out of localStorage.

These are JSON APIs, so the policy can be as strict as "this document may load nothing at
all" — with one exception for the services that serve the interactive API docs or a static
sandbox page, which need their own scripts and styles.

Applied by control_plane, tenant_portal_api and admin. The dashboard is a separate Next.js
app; its headers belong in dashboard/next.config.js.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# A JSON API never needs to load or embed anything.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

# Swagger UI / ReDoc and the dev sandbox page pull their assets from a CDN and use inline
# styles. Only served where docs are deliberately enabled (F-M6), which is not production.
DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json", "/static")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add the baseline headers to every response.

    `hsts` should stay False for services reachable over plain HTTP in development —
    a max-age of a year pinned against localhost is painful to undo in a browser.
    """

    def __init__(self, app, *, hsts: bool = True, docs_enabled: bool = False) -> None:
        super().__init__(app)
        self._hsts = hsts
        self._docs_enabled = docs_enabled

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        is_doc_page = self._docs_enabled and path.startswith(_DOC_PATHS)

        response.headers.setdefault(
            "Content-Security-Policy", DOCS_CSP if is_doc_page else API_CSP
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # Session mints and credential reads must never be stored by a proxy or the browser.
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
