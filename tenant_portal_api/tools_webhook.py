"""Validate tenant-supplied tools webhook URLs (SSRF-aware, local-dev friendly)."""

from __future__ import annotations

from urllib.parse import urlparse

_MAX_URL_LEN = 2048
_MAX_SECRET_LEN = 512


class ToolsWebhookError(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.status = 422


def normalize_tools_base_url(raw: str | None) -> str | None:
    """Return a stripped base URL with no trailing slash, or None to clear/unset."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if len(text) > _MAX_URL_LEN:
        raise ToolsWebhookError("invalid_tools_base_url", "tools_base_url is too long")

    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        raise ToolsWebhookError(
            "invalid_tools_base_url",
            "tools_base_url must use http or https",
        )
    if not parsed.netloc or parsed.username or parsed.password:
        raise ToolsWebhookError(
            "invalid_tools_base_url",
            "tools_base_url must include a host and must not embed credentials",
        )
    if parsed.query or parsed.fragment:
        raise ToolsWebhookError(
            "invalid_tools_base_url",
            "tools_base_url must not include query or fragment",
        )
    # Path allowed (e.g. https://api.example.com/uva) — strip trailing slash only.
    path = (parsed.path or "").rstrip("/")
    base = f"{parsed.scheme}://{parsed.netloc}{path}"
    return base


def normalize_tools_auth_secret(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if len(text) > _MAX_SECRET_LEN:
        raise ToolsWebhookError(
            "invalid_tools_auth_secret", "tools_auth_secret is too long"
        )
    return text
