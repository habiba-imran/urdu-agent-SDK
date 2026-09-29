"""The tenant-portal JWT signing secret — one resolution path for the whole service.

F-C1: ``telephony_routes.py`` used to read ``os.environ`` directly with a hardcoded
``"mock_jwt_secret_for_tests"`` fallback, while ``app.py`` resolved a real secret from
``.env.local``. The two disagreed whenever the secret was not a process env var: tokens the
portal issued were rejected, and tokens anyone could forge with the published fallback string
were accepted for every ``/portal/telephony/*`` route. Both now call this module.

F-H13: the old resolver generated a secret and appended it to ``.env.local`` at import time.
In a container that either crashes (read-only filesystem) or silently rotates on every deploy,
invalidating every issued session. Generation is now local-development only; a hosted service
with no secret configured fails to start with an explicit message instead.
"""

from __future__ import annotations

import logging
import os
import secrets as _pysecrets
import sys
from pathlib import Path

from dotenv import dotenv_values

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from control_plane.runtime_env import (  # noqa: E402
    is_hosted,
    require_hosted_config,
)

ENV_VAR = "TENANT_PORTAL_JWT_SECRET"
_ENV_PATH = _ROOT / ".env.local"
_logger = logging.getLogger("tenant_portal_api.jwt_secret")

_cached: str | None = None


def reset_cache() -> None:
    """Forget the resolved secret (tests change the environment between cases)."""
    global _cached
    _cached = None


def portal_jwt_secret() -> str:
    """Resolve the portal JWT secret, or raise in a hosted environment with none set.

    Order: process environment, then ``.env.local`` (local dev), then — local dev only —
    generate one and persist it so restarts keep issued tokens valid.
    """
    global _cached
    if _cached is not None:
        return _cached

    value = os.environ.get(ENV_VAR) or dotenv_values(_ENV_PATH).get(ENV_VAR)
    if value and value.strip():
        _cached = value.strip()
        return _cached

    if is_hosted():
        require_hosted_config(
            ENV_VAR,
            why=(
                "It signs tenant-portal session tokens; without it the portal cannot "
                "verify its own tokens and telephony routes would fall back to a "
                "well-known value."
            ),
        )

    generated = _pysecrets.token_hex(32)
    try:
        with open(_ENV_PATH, "a", encoding="utf-8") as handle:
            handle.write(
                "\n# auto-generated for local development by "
                "tenant_portal_api/jwt_secret.py — never used in a hosted environment\n"
                f"{ENV_VAR}={generated}\n"
            )
        _logger.warning(
            "%s was not set — generated one for local development and wrote it to %s",
            ENV_VAR,
            _ENV_PATH.name,
        )
    except OSError as exc:
        # Read-only or otherwise unwritable: keep the in-process value so a local run still
        # works, but say so — tokens will not survive a restart.
        _logger.warning(
            "%s was not set and %s is not writable (%s) — using an in-memory secret; "
            "tokens will be invalidated on restart",
            ENV_VAR,
            _ENV_PATH.name,
            exc,
        )
    _cached = generated
    return _cached
