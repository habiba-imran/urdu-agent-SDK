"""Database-backed secret provider — reads raw HMAC secrets from tenants.hmac_secret column.

Replaces static EnvSecretProvider in production while preserving backwards compatibility
via env fallback for existing development tenants.
"""

from __future__ import annotations

import os
import logging
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

from .secret_crypto import (
    ENV_VAR as SECRET_KEY_ENV,
    TenantSecretCryptoError,
    decrypt_tenant_secret,
    is_enabled as is_encryption_enabled,
)
from .secrets import SecretProvider

_log = logging.getLogger("control_plane.secrets_db")


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

        # 1. Try DB lookup. F-C6: prefer the encrypted column, fall back to the plaintext
        # one so a database that has not been migrated (or a service that has not been given
        # TENANT_SECRET_ENCRYPTION_KEY yet) keeps minting.
        try:
            with psycopg.connect(**conn_kwargs(), connect_timeout=5) as conn:
                try:
                    row = conn.execute(
                        "SELECT hmac_secret_enc, hmac_secret FROM tenants WHERE id = %s",
                        (tenant_id,),
                    ).fetchone()
                    encrypted, plaintext = (row[0], row[1]) if row else (None, None)
                except psycopg.errors.UndefinedColumn:
                    # 0033 not applied yet.
                    conn.rollback()
                    row = conn.execute(
                        "SELECT hmac_secret FROM tenants WHERE id = %s",
                        (tenant_id,),
                    ).fetchone()
                    encrypted, plaintext = None, (row[0] if row else None)

                secret = None
                if encrypted:
                    try:
                        secret = decrypt_tenant_secret(encrypted)
                    except TenantSecretCryptoError:
                        # Never fall through to the plaintext column here: if a ciphertext
                        # exists but cannot be opened, the key is wrong or the row was
                        # tampered with, and quietly signing with something else would hide
                        # that.
                        _log.error(
                            "tenant %s has an encrypted secret that could not be decrypted "
                            "- check %s",
                            tenant_id,
                            SECRET_KEY_ENV,
                            exc_info=True,
                        )
                        return None
                elif plaintext:
                    secret = plaintext
                    if is_encryption_enabled():
                        _log.warning(
                            "tenant %s still stores a PLAINTEXT signing secret - run "
                            "scripts/encrypt_tenant_secrets.py (F-C6)",
                            tenant_id,
                        )
                if secret:
                    self._write_cache(tenant_id, secret)
                    return secret
        except Exception:
            # F-M1: silently falling back to the env map hides a DB outage AND means
            # authentication quietly runs on a possibly stale secret set (see F-M29).
            _log.warning(
                "tenant secret DB lookup failed for %s — using env fallback",
                tenant_id,
                exc_info=True,
            )

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

    def invalidate(self, tenant_id: str) -> None:
        """Drop one tenant's cached secret (F-M29).

        The mint calls this when a signature fails: the usual cause is a rotation that
        happened inside the cache window, and re-reading turns a minute of 401s into a
        single extra query. Rotation in another process cannot notify this one, so the
        cache TTL still bounds how long a withdrawn secret keeps working — set
        CP_DB_SECRET_CACHE_TTL_SEC=0 to disable caching entirely.
        """
        with self._lock:
            self._cache.pop(tenant_id, None)

    def invalidate_all(self) -> None:
        with self._lock:
            self._cache.clear()

    def _write_cache(self, tenant_id: str, value: str | None) -> None:
        if self._cache_ttl_sec <= 0:
            return
        with self._lock:
            self._cache[tenant_id] = (time.monotonic() + self._cache_ttl_sec, value)
