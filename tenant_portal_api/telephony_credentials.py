"""Telephony provider credential reference encoding.

Uses the existing telephony credential reference columns with an application
encryption key from TELEPHONY_CREDENTIAL_ENCRYPTION_KEY. The raw provider key is
only present transiently in process memory while handling a trusted backend
request.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import hmac
import json
import os
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from tenant_portal_api.telephony_config import is_mock_provider_mode

from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode

_log = logging.getLogger("tenant_portal_api.telephony_credentials")

_PREFIX = "enc:v1:"  # legacy: HMAC keystream + HMAC tag, kept readable for existing rows
_PREFIX_V2 = "enc:v2:"  # AES-256-GCM with HKDF and a per-record salt
_SALT_LEN = 16
_NONCE_LEN = 12
_AAD = b"uva-telephony-provider-credential"



def encrypt_provider_secret(secret: str) -> str:
    """Encrypt a provider API key for storage (F-M7).

    AES-256-GCM from `cryptography` — already a dependency of this service, used for the
    Ed25519 webhook signatures — with a per-record random salt and HKDF key derivation.

    The previous scheme (still readable below as v1) was an HMAC keystream XORed over the
    plaintext with a separate HMAC tag: unreviewed custom crypto, in a codebase that already
    had a vetted AEAD available, with the key taken as a bare sha256 of the env value and no
    KDF or salt at all.
    """
    if not secret:
        raise _missing_credentials("Provider credential is empty.")
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    key = _derive_key_v2(_master_secret(), salt)
    ciphertext = AESGCM(key).encrypt(nonce, secret.encode("utf-8"), _AAD)
    return _PREFIX_V2 + _b64(salt + nonce + ciphertext)


_LEGACY_PREFIX = "enc:legacy:"


def decrypt_provider_secret(secret_ref: str | None) -> str:
    if not secret_ref:
        raise _missing_credentials("Tenant provider credential reference is missing.")
    if is_mock_provider_mode() and not secret_ref.startswith(_PREFIX) and not secret_ref.startswith(_LEGACY_PREFIX):
        return secret_ref
    if secret_ref.startswith(_LEGACY_PREFIX):
        # Backward compatible decoding for legacy prefix format
        try:
            return base64.b64decode(secret_ref[len(_LEGACY_PREFIX) :].encode("utf-8")).decode("utf-8")
        except Exception:
            if is_mock_provider_mode():
                return secret_ref[len(_LEGACY_PREFIX) :]
            raise _missing_credentials("Legacy provider credential reference is invalid.")
    if secret_ref.startswith(_PREFIX_V2):
        try:
            blob = _unb64(secret_ref[len(_PREFIX_V2) :])
            salt, nonce = blob[:_SALT_LEN], blob[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
            ciphertext = blob[_SALT_LEN + _NONCE_LEN :]
            key = _derive_key_v2(_master_secret(), salt)
            return AESGCM(key).decrypt(nonce, ciphertext, _AAD).decode("utf-8")
        except TelephonyError:
            raise
        except Exception as exc:
            raise _missing_credentials(
                "Tenant provider credential reference failed integrity verification."
            ) from exc

    if not secret_ref.startswith(_PREFIX):
        raise _missing_credentials(
            "Tenant provider credential reference format is not supported."
        )

    try:
        master = _master_key()
        payload = json.loads(_unb64(secret_ref[len(_PREFIX) :]).decode("utf-8"))
        nonce = _unb64(payload["nonce"])
        ciphertext = _unb64(payload["ciphertext"])
        tag = _unb64(payload["tag"])

        expected = hmac.new(
            _derive(master, b"mac"), nonce + ciphertext, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, tag):
            raise _missing_credentials(
                "Tenant provider credential reference failed integrity verification."
            )

        plaintext = _xor(
            ciphertext, _keystream(_derive(master, b"enc"), nonce, len(ciphertext))
        )
        return plaintext.decode("utf-8")
    except Exception as exc:
        if is_mock_provider_mode():
            return secret_ref[len(_PREFIX) :]
        if isinstance(exc, TelephonyError):
            raise exc
        raise _missing_credentials(
            "Tenant provider credential reference is invalid."
        ) from exc


def reencrypt_legacy_provider_secrets(conn: Any) -> int:
    """Upgrade legacy, raw or v1 references in telephony_connections to the v2 AEAD format.

    Safe to run repeatedly: rows already at v2 are not selected.
    """
    if conn is None or is_mock_provider_mode():
        return 0
    rows = conn.execute(
        """
        select id, encrypted_api_key_ref from telephony_connections
        where encrypted_api_key_ref is not null and encrypted_api_key_ref not like %s
        """,
        (f"{_PREFIX_V2}%",),
    ).fetchall()
    migrated = 0
    for row in rows:
        conn_id, old_ref = row[0], row[1]
        try:
            raw_secret = decrypt_provider_secret(old_ref)
            new_ref = encrypt_provider_secret(raw_secret)
            conn.execute(
                "update telephony_connections set encrypted_api_key_ref = %s, updated_at = now() where id = %s",
                (new_ref, conn_id),
            )
            migrated += 1
        except Exception:
            # F-M1: a connection whose secret could not be re-encrypted stays on the old
            # key. Silently counting on is how a half-migrated credential set goes unnoticed.
            _log.warning(
                "telephony credential re-encryption failed for connection %s",
                conn_id,
                exc_info=True,
            )
    return migrated




def _master_secret() -> str:
    value = os.getenv("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    if not value:
        raise _missing_credentials(
            "TELEPHONY_CREDENTIAL_ENCRYPTION_KEY is not configured."
        )
    return value


def _derive_key_v2(master: str, salt: bytes) -> bytes:
    """HKDF-SHA256 with a per-record salt (F-M7: v1 used a bare sha256 of the env value)."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"uva-telephony-provider-credential-v2",
    ).derive(master.encode("utf-8"))


def _master_key() -> bytes:
    value = os.getenv("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    if not value:
        raise _missing_credentials(
            "TELEPHONY_CREDENTIAL_ENCRYPTION_KEY is not configured."
        )
    return hashlib.sha256(value.encode("utf-8")).digest()


def _derive(master: bytes, purpose: bytes) -> bytes:
    return hmac.new(
        master, b"telephony-provider-credential:" + purpose, hashlib.sha256
    ).digest()


def _keystream(key: bytes, nonce: bytes, size: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    while sum(len(block) for block in blocks) < size:
        counter_bytes = counter.to_bytes(4, "big")
        blocks.append(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:size]


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _missing_credentials(message: str) -> TelephonyError:
    return TelephonyError(
        status=503,
        code=TelephonyErrorCode.PROVIDER_CREDENTIALS_MISSING,
        message=message,
    )
