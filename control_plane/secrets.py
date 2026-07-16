"""Per-tenant HMAC secret provider.

The tenant's RAW HMAC secret is TRUSTED-tier (31-GUIDE-SECURITY.md §2) and must never live in a DB
table — `tenants` stores only `hmac_secret_hash`. This abstracts WHERE the raw secret lives so the
mint logic is testable now and the production store (Supabase Vault / a secret manager / an
encrypted column) can be chosen later. That choice is an OPEN decision flagged at the Phase 2 gate.

Dev impl reads a JSON map from `CP_TENANT_SECRETS` in .env.local; tests inject a dict directly.
"""

from __future__ import annotations

import hashlib
import json
import os

from dotenv import dotenv_values


class SecretProvider:
    """Returns a tenant's raw HMAC secret, or None if none is provisioned."""

    def get(self, tenant_id: str) -> str | None:
        raise NotImplementedError


class DictSecretProvider(SecretProvider):
    """In-memory provider (tests, and a base for others)."""

    def __init__(self, mapping: dict[str, str] | None = None):
        self._m = dict(mapping or {})

    def set(self, tenant_id: str, secret: str) -> None:
        self._m[tenant_id] = secret

    def get(self, tenant_id: str) -> str | None:
        return self._m.get(tenant_id)


class EnvSecretProvider(DictSecretProvider):
    """Dev provider: CP_TENANT_SECRETS = {"<tenant_id>": "<secret>", ...} in .env.local."""

    def __init__(self, env_file: str = ".env.local"):
        # env var wins over the file, so a server process can be handed a secret map directly
        raw = (
            os.environ.get("CP_TENANT_SECRETS")
            or dotenv_values(env_file).get("CP_TENANT_SECRETS", "")
            or "{}"
        )
        try:
            mapping = json.loads(raw)
        except json.JSONDecodeError:
            mapping = {}
        super().__init__(mapping)


def secret_hash(secret: str) -> str:
    """The value stored in tenants.hmac_secret_hash — a fingerprint, never the secret itself."""
    return hashlib.sha256(secret.encode()).hexdigest()
