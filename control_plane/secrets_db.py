"""Database-backed secret provider — reads raw HMAC secrets from tenants.hmac_secret column.

Replaces static EnvSecretProvider in production while preserving backwards compatibility
via env fallback for existing development tenants.
"""

from __future__ import annotations

import os
import threading
import time
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
        self._cache_ttl_sec = max(0, int(os.environ.get("CP_DB_SECRET_CACHE_TTL_SEC", "60") or "60"))
        self._cache: dict[str, tuple[float, str | None]] = {}
        self._lock = threading.RLock()

    def get(self, tenant_id: str) -> Optional[str]:
        if not tenant_id:
            return None

        cached = self._read_cache(tenant_id)
        if cached is not None:
            return cached

        # 1. Try DB lookup
        try:
            with psycopg.connect(**conn_kwargs(), connect_timeout=5) as conn:
                row = conn.execute(
                    "SELECT hmac_secret FROM tenants WHERE id = %s",
                    (tenant_id,),
                ).fetchone()
                if row and row[0]:
                    secret = row[0]
                    self._write_cache(tenant_id, secret)
                    return secret
        except Exception:
            pass  # DB lookup failure or column missing — fall through to fallback

        # 2. Fallback to EnvSecretProvider if provided
        if self._fallback:
            secret = self._fallback.get(tenant_id)
            if secret is not None:
                self._write_cache(tenant_id, secret)
            return secret

        return None

    def _read_cache(self, tenant_id: str) -> Optional[str] | None:
        if self._cache_ttl_sec <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(tenant_id)
            if not cached:
                return None
            expires_at, value = cached
            if expires_at <= now:
                self._cache.pop(tenant_id, None)
                return None
            return value

    def _write_cache(self, tenant_id: str, value: str | None) -> None:
        if self._cache_ttl_sec <= 0:
            return
        with self._lock:
            self._cache[tenant_id] = (time.monotonic() + self._cache_ttl_sec, value)
