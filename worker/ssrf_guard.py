"""Request-time SSRF checks for worker → tenant tools webhooks (P1-H4).

Save-time validation in ``tenant_portal_api.tools_webhook`` cannot defeat DNS
rebinding. Immediately before each POST we resolve again, reject internal
ranges when hosted, and prefer connecting to a pinned public address.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse, urlunparse

from control_plane.runtime_env import is_hosted

logger = logging.getLogger("uva.worker.ssrf")

_BLOCKED_SUFFIXES = (
    ".internal",
    ".local",
    ".localdomain",
    ".localhost",
    ".cluster.local",
    ".svc",
    ".svc.cluster.local",
)
_BLOCKED_NAMES = frozenset({"localhost", "metadata", "metadata.google.internal"})


class ToolsSsrfError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _is_internal_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (
            isinstance(ip, ipaddress.IPv6Address)
            and ip.ipv4_mapped is not None
            and _is_internal_address(ip.ipv4_mapped)
        )
    )


def _resolve_ips(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        raise ToolsSsrfError(f"tools URL host could not be resolved: {host}") from e
    out: list[str] = []
    for info in infos:
        address = info[4][0]
        cleaned = address.split("%")[0]
        if cleaned not in out:
            out.append(cleaned)
    if not out:
        raise ToolsSsrfError(f"tools URL host resolved to no addresses: {host}")
    return out


def prepare_tools_post_url(url: str, *, hosted: bool | None = None) -> tuple[str, dict[str, str]]:
    """Return ``(request_url, extra_headers)`` safe for the worker to POST.

    When hosted, rejects internal hostnames / IPs. Pins the first public A/AAAA
    into the URL and sets ``Host`` (and SNI via httpx extensions for HTTPS).
    Local/dev keeps loopback/private usable without pinning.
    """
    if hosted is None:
        hosted = is_hosted()

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ToolsSsrfError("tools URL must be http or https")
    if hosted and scheme != "https":
        raise ToolsSsrfError("hosted tools webhooks must use https")

    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise ToolsSsrfError("tools URL missing host")

    if host in _BLOCKED_NAMES or host.endswith(_BLOCKED_SUFFIXES):
        if hosted:
            raise ToolsSsrfError("tools URL must not use an internal hostname")
        return url, {}

    literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None

    if literal is not None:
        if hosted and _is_internal_address(literal):
            raise ToolsSsrfError("tools URL must not point at a private or link-local address")
        return url, {}

    if hosted and "." not in host:
        raise ToolsSsrfError("tools URL must use a fully qualified public hostname")

    if not hosted:
        # Dev: allow private targets; still re-resolve if we can, but do not pin.
        try:
            for addr in _resolve_ips(host):
                ip = ipaddress.ip_address(addr)
                if _is_internal_address(ip):
                    return url, {}
        except ToolsSsrfError:
            return url, {}
        return url, {}

    public_ips: list[str] = []
    for addr in _resolve_ips(host):
        ip = ipaddress.ip_address(addr)
        if _is_internal_address(ip):
            raise ToolsSsrfError(
                "tools URL currently resolves to a private/link-local address"
            )
        public_ips.append(addr)

    pin = public_ips[0]
    port = parsed.port or (443 if scheme == "https" else 80)
    if ":" in pin:
        netloc = f"[{pin}]:{port}"
    else:
        netloc = f"{pin}:{port}"
    pinned = urlunparse(
        (scheme, netloc, parsed.path or "/", parsed.params, parsed.query, parsed.fragment)
    )
    extra = {"Host": host}
    logger.debug("ssrf_pin host=%s ip=%s", host, pin)
    return pinned, extra
