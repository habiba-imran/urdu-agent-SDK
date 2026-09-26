"""Encryption at rest for tenant HMAC signing secrets (F-C6).

`tenants.hmac_secret` held the raw signing credential in plaintext, while
`0001_schema.sql`, `control_plane/secrets.py` and `docs/21-PHASE-1-SUPABASE.md` all still
claimed "hash ONLY, never the secret". Anyone with a database dump had every tenant's
permanent signing credential.

Design constraints this has to respect:

* **Rollout cannot break minting.** Readers try the encrypted column first and fall back to
  the plaintext column, so a database that has not been migrated yet keeps working, and a
  service that has not been given the key keeps working too (loudly).
* **It must be reversible per tenant.** Unlike a password, this value has to be given back
  to the host that signs with it, so a hash is not an option — it is encryption, not
  digesting.
* Same primitives as the telephony credential store (F-M7): AES-256-GCM with HKDF-SHA256
  and a per-record salt, from `cryptography`, which is already a dependency.

Key: ``TENANT_SECRET_ENCRYPTION_KEY``. When it is absent, encryption is simply not active —
`encrypt_tenant_secret` returns None and callers keep using the plaintext column. That is
deliberate: a deploy that has not had the key added yet must not take the mint down. Once
the key is set and `scripts/encrypt_tenant_secrets.py` has run with `--finalize`, the
plaintext column is empty and only the ciphertext remains.
"""

from __future__ import annotations

import base64
import logging
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ENV_VAR = "TENANT_SECRET_ENCRYPTION_KEY"
PREFIX = "tenc:v1:"
_SALT_LEN = 16
_NONCE_LEN = 12
_AAD = b"uva-tenant-hmac-secret"

_log = logging.getLogger("control_plane.secret_crypto")


class TenantSecretCryptoError(Exception):
    """Raised when a stored ciphertext cannot be decrypted (wrong key, or tampering)."""


def encryption_key() -> str | None:
    value = (os.environ.get(ENV_VAR) or "").strip()
    return value or None


def is_enabled() -> bool:
    return encryption_key() is not None


def _derive(master: str, salt: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"uva-tenant-hmac-secret-v1",
    ).derive(master.encode("utf-8"))


def encrypt_tenant_secret(secret: str) -> str | None:
    """Return the ciphertext for storage, or None when encryption is not configured."""
    master = encryption_key()
    if master is None or not secret:
        return None
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(_derive(master, salt)).encrypt(
        nonce, secret.encode("utf-8"), _AAD
    )
    return PREFIX + base64.urlsafe_b64encode(salt + nonce + ciphertext).decode("ascii")


def looks_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def decrypt_tenant_secret(stored: str | None) -> str | None:
    """Decrypt a stored value. Returns None for an empty value.

    A value that is not in the encrypted format is returned unchanged — during rollout the
    same column can legitimately hold a plaintext secret written by an older service.
    """
    if not stored:
        return None
    if not looks_encrypted(stored):
        return stored
    master = encryption_key()
    if master is None:
        raise TenantSecretCryptoError(
            f"{ENV_VAR} is not set but this tenant's secret is encrypted; the mint cannot "
            "verify signatures without the key"
        )
    try:
        blob = base64.urlsafe_b64decode(stored[len(PREFIX) :].encode("ascii"))
        salt, nonce = blob[:_SALT_LEN], blob[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
        ciphertext = blob[_SALT_LEN + _NONCE_LEN :]
        return AESGCM(_derive(master, salt)).decrypt(nonce, ciphertext, _AAD).decode("utf-8")
    except Exception as exc:  # wrong key, truncated value, tampering
        raise TenantSecretCryptoError(
            "stored tenant secret could not be decrypted"
        ) from exc
