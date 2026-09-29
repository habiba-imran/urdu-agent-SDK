"""Validate tenant-supplied tools webhook URLs (F-H8).

The worker POSTs to this URL from inside the platform network, carrying
``x-tool-gateway-secret``. The module said "SSRF-aware" while checking only the scheme,
embedded credentials and query string — cloud metadata (169.254.169.254), loopback, private
ranges and ``.internal`` hostnames were all accepted, and ``http://`` sent the gateway secret
in cleartext.

What this can and cannot do: it rejects addresses that are obviously internal, and refuses a
hostname that currently resolves into a private range. It cannot defeat DNS rebinding — a
name that resolves publicly now and privately at request time — because the check and the
request happen at different moments in different processes. Closing that needs the worker to
resolve, pin and connect to the same address; noted in the audit's residual list, not
solvable here.

Local development stays usable: with UVA_ENV unset (see control_plane/runtime_env.py) the
loopback and private-range rules are relaxed, because pointing an agent at a tool server on
your own machine is the normal way to develop one.
"""

from __future__ import annotations

import ipaddress
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from control_plane.runtime_env import is_hosted  # noqa: E402

_MAX_URL_LEN = 2048
_MAX_SECRET_LEN = 512

# Hostname suffixes that only ever resolve inside a private network.
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


class ToolsWebhookError(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.status = 422


def _is_internal_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Anything that is not a normal, routable public address.

    is_private covers RFC1918 and unique-local; the rest are the ranges that reach a cloud
    instance's own metadata service, the host itself, or the local segment.
    """
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # 169.254.0.0/16 — cloud metadata lives here
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None
            and _is_internal_address(ip.ipv4_mapped))
    )


def _reject(reason: str) -> None:
    raise ToolsWebhookError("invalid_tools_base_url", reason)


def _check_host(host: str, *, hosted: bool) -> None:
    host = host.strip().rstrip(".").lower()
    if not host:
        _reject("tools_base_url must include a host")

    # Literal IP address?
    literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None

    if literal is not None:
        if _is_internal_address(literal) and hosted:
            _reject(
                "tools_base_url must not point at a private, loopback or link-local "
                "address (cloud metadata and internal services are not reachable targets)"
            )
        return

    if host in _BLOCKED_NAMES or host.endswith(_BLOCKED_SUFFIXES):
        if hosted:
            _reject("tools_base_url must not use an internal hostname")
        return

    if "." not in host and hosted:
        # A bare label only resolves through internal search domains.
        _reject("tools_base_url must use a fully qualified public hostname")

    if not hosted:
        return

    # Best-effort resolution check. A failure to resolve is NOT fatal: the tenant may be
    # configuring a host that does not exist yet, and this validator must not become an
    # outage when DNS is slow.
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return
    for info in infos:
        address = info[4][0]
        try:
            resolved = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            continue
        if _is_internal_address(resolved):
            _reject(
                f"tools_base_url resolves to an internal address ({resolved}); "
                "the worker would be sending your gateway secret inside the platform network"
            )


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
    hosted = is_hosted()

    if parsed.scheme not in ("http", "https"):
        _reject("tools_base_url must use http or https")
    # F-H8: http sends x-tool-gateway-secret in cleartext. Allowed locally only.
    if parsed.scheme == "http" and hosted:
        _reject(
            "tools_base_url must use https - the tool gateway secret is sent on every "
            "request and would travel in cleartext"
        )
    if not parsed.netloc or parsed.username or parsed.password:
        _reject("tools_base_url must include a host and must not embed credentials")
    if parsed.query or parsed.fragment:
        _reject("tools_base_url must not include query or fragment")

    try:
        hostname = parsed.hostname or ""
    except ValueError:  # malformed IPv6 literal
        hostname = ""
    _check_host(hostname, hosted=hosted)

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
