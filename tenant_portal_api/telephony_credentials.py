"""Telephony provider credential reference encoding.

Uses the existing telephony credential reference columns with an application
encryption key from TELEPHONY_CREDENTIAL_ENCRYPTION_KEY. The raw provider key is
only present transiently in process memory while handling a trusted backend
request.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode

_PREFIX = "enc:v1:"


def encrypt_provider_secret(secret: str) -> str:
    if not secret:
        raise _missing_credentials("Provider credential is empty.")
    master = _master_key()
    nonce = os.urandom(16)
    plaintext = secret.encode("utf-8")
    ciphertext = _xor(plaintext, _keystream(_derive(master, b"enc"), nonce, len(plaintext)))
    tag = hmac.new(_derive(master, b"mac"), nonce + ciphertext, hashlib.sha256).digest()
    payload = {
        "nonce": _b64(nonce),
        "ciphertext": _b64(ciphertext),
        "tag": _b64(tag),
    }
    return _PREFIX + _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def decrypt_provider_secret(secret_ref: str | None) -> str:
    if not secret_ref:
        raise _missing_credentials("Tenant provider credential reference is missing.")
    if not secret_ref.startswith(_PREFIX):
        raise _missing_credentials("Tenant provider credential reference is not supported.")

    master = _master_key()
    try:
        payload = json.loads(_unb64(secret_ref[len(_PREFIX) :]).decode("utf-8"))
        nonce = _unb64(payload["nonce"])
        ciphertext = _unb64(payload["ciphertext"])
        tag = _unb64(payload["tag"])
    except Exception as exc:
        raise _missing_credentials("Tenant provider credential reference is invalid.") from exc

    expected = hmac.new(_derive(master, b"mac"), nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, tag):
        raise _missing_credentials("Tenant provider credential reference failed integrity verification.")

    plaintext = _xor(ciphertext, _keystream(_derive(master, b"enc"), nonce, len(ciphertext)))
    return plaintext.decode("utf-8")


def _master_key() -> bytes:
    value = os.getenv("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    if not value:
        raise _missing_credentials("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY is not configured.")
    return hashlib.sha256(value.encode("utf-8")).digest()


def _derive(master: bytes, purpose: bytes) -> bytes:
    return hmac.new(master, b"telephony-provider-credential:" + purpose, hashlib.sha256).digest()


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
