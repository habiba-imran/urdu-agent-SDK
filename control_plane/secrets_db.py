"""Database-backed secret provider — reads raw HMAC secrets from tenants.hmac_secret column.

Replaces static EnvSecretProvider in production while preserving backwards compatibility
via env fallback for existing development tenants.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from scripts.dbconn import conn_kwargs
except ImportError:
    from dbconn import conn_kwargs  # type: ignore # noqa: E402

from .secrets import SecretProvider


class DbSecretProvider(SecretProvider):
    """Reads the raw HMAC secret for a tenant_id from the DB tenants.hmac_secret column.

    Falls back to env_fallback (e.g. EnvSecretProvider) if secret is not found in DB
    or if DB connection fails, ensuring zero-downtime migration.
    """

    def __init__(self, env_fallback: Optional[SecretProvider] = None):
        self._fallback = env_fallback

    def get(self, tenant_id: str) -> Optional[str]:
        if not tenant_id:
            return None

        # 1. Try DB lookup
        try:
            with psycopg.connect(**conn_kwargs(), connect_timeout=5) as conn:
                row = conn.execute(
                    "SELECT hmac_secret FROM tenants WHERE id = %s AND status = 'active'",
                    (tenant_id,),
                ).fetchone()
                if row and row[0]:
                    return row[0]
        except Exception:
            pass  # DB lookup failure or column missing — fall through to fallback

        # 2. Fallback to EnvSecretProvider if provided
        if self._fallback:
            return self._fallback.get(tenant_id)

        return None
