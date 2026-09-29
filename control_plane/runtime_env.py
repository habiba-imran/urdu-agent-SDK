"""Is this process running on a hosted deployment, or on a developer's machine?

Several Wave 2 security fixes need the same distinction: a default that is a convenience
locally (auto-generated signing key, permissive CORS, mock auth switch, public /docs) is a
hole in production. Rather than hope every service remembers, they all ask this module and
fail fast when a required value is missing in a hosted environment.

Detection, in order:
- ``UVA_ENV`` — explicit override: ``production`` / ``staging`` / ``development``.
- ``RENDER`` — set by the platform (same signal worker/recording_policy.py already uses).
- ``ENVIRONMENT`` — already read by control_plane for Sentry.

Absent all three the process is treated as local development, which is the safe default for
a developer's laptop and the unsafe one for a server — so deployments must set at least one.
docker/*.Dockerfile set UVA_ENV=production for exactly that reason.
"""

from __future__ import annotations

import os

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_HOSTED_NAMES = frozenset({"production", "prod", "staging", "preview"})


def _clean(name: str) -> str:
    return (os.environ.get(name) or "").strip().lower()


def is_hosted() -> bool:
    """True when this process is a deployed service rather than local development."""
    explicit = _clean("UVA_ENV")
    if explicit:
        return explicit in _HOSTED_NAMES
    if _clean("RENDER") in _TRUTHY:
        return True
    return _clean("ENVIRONMENT") in _HOSTED_NAMES


def environment_name() -> str:
    """Best-effort label for logs and error messages."""
    for var in ("UVA_ENV", "ENVIRONMENT"):
        value = _clean(var)
        if value:
            return value
    if _clean("RENDER") in _TRUTHY:
        return "render"
    return "development"


def resolve_allowed_origins(
    raw: str,
    *,
    hosted: bool,
    dev_defaults: list[str],
    var_name: str,
    why: str,
) -> tuple[list[str], bool]:
    """Turn a comma-separated origin allowlist into (origins, allow_credentials).

    Empty in a hosted environment is a configuration error, not "allow everything"
    (F-C3). Empty locally falls back to the usual dev ports. Credentials are never
    combined with a wildcard: browsers reject that pair, and honouring it would be a
    blanket cross-origin grant.
    """
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if not origins:
        if hosted:
            require_hosted_config(var_name, why=why)
        origins = list(dev_defaults)
    return origins, "*" not in origins


def require_hosted_config(var_name: str, *, why: str) -> None:
    """Raise a clear startup error for a value that must be set in a hosted environment."""
    raise RuntimeError(
        f"{var_name} must be set when running in a hosted environment "
        f"(detected: {environment_name()}). {why} "
        f"Set {var_name} in the service's environment, or set UVA_ENV=development "
        f"if this really is a local machine."
    )
