"""Deny-list scrubber for Sentry events (M7-F01).

Drops Authorization / Cookie / signature headers and redacts common secret-shaped
keys in extras/contexts so mint failures cannot ship HMAC material to Sentry.
"""

from __future__ import annotations

from typing import Any

_REDACT = "[redacted]"
_HEADER_DENY = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-signature",
        "x-api-key",
        "telnyx-signature-ed25519",
    }
)
_KEY_HINTS = ("secret", "password", "token", "authorization", "cookie", "api_key", "apikey")


def _scrub_mapping(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = {}
    for key, value in data.items():
        key_l = str(key).lower()
        if any(h in key_l for h in _KEY_HINTS):
            out[key] = _REDACT
        elif isinstance(value, dict):
            out[key] = _scrub_mapping(value)
        elif isinstance(value, list):
            out[key] = [_scrub_mapping(v) for v in value]
        else:
            out[key] = value
    return out


def before_send(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                k: (_REDACT if str(k).lower() in _HEADER_DENY else v)
                for k, v in headers.items()
            }
        if "data" in request:
            request["data"] = _scrub_mapping(request.get("data"))
        if "cookies" in request:
            request["cookies"] = _REDACT
    if "extra" in event:
        event["extra"] = _scrub_mapping(event.get("extra"))
    if "contexts" in event:
        event["contexts"] = _scrub_mapping(event.get("contexts"))
    return event
