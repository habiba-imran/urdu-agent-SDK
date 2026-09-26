"""F-M7 — telephony provider credentials use a vetted AEAD, not hand-rolled crypto.

The previous scheme was an HMAC keystream XORed over the plaintext with a separate HMAC tag,
keyed by a bare sha256 of the env value with no KDF or salt — unreviewed custom crypto in a
codebase that already depends on `cryptography` for Ed25519 webhook signatures.

Existing rows must keep working, so v1 stays readable; new writes are v2 (AES-256-GCM,
HKDF, per-record salt).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setenv("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY", "unit-test-master-key")
    monkeypatch.setenv("TELEPHONY_PROVIDER_MODE", "real")
    monkeypatch.setenv("UVA_ENV", "development")


def test_round_trip():
    from tenant_portal_api.telephony_credentials import (
        decrypt_provider_secret,
        encrypt_provider_secret,
    )

    secret = "KEY0123456789abcdef-telnyx"
    blob = encrypt_provider_secret(secret)
    assert blob.startswith("enc:v2:")
    assert secret not in blob
    assert decrypt_provider_secret(blob) == secret


def test_each_encryption_is_distinct():
    """Random salt and nonce per record: the same secret must not produce the same blob."""
    from tenant_portal_api.telephony_credentials import encrypt_provider_secret

    assert encrypt_provider_secret("same-secret") != encrypt_provider_secret("same-secret")


def test_tampering_is_detected():
    """AEAD: any modification fails authentication rather than decrypting to garbage."""
    from tenant_portal_api.telephony_credentials import (
        decrypt_provider_secret,
        encrypt_provider_secret,
    )
    from tenant_portal_api.telephony_errors import TelephonyError

    blob = encrypt_provider_secret("KEY-abc")
    flipped = blob[:-2] + ("AA" if not blob.endswith("AA") else "BB")
    with pytest.raises(TelephonyError):
        decrypt_provider_secret(flipped)


def test_a_different_master_key_cannot_decrypt(monkeypatch):
    from tenant_portal_api.telephony_credentials import (
        decrypt_provider_secret,
        encrypt_provider_secret,
    )
    from tenant_portal_api.telephony_errors import TelephonyError

    blob = encrypt_provider_secret("KEY-abc")
    monkeypatch.setenv("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY", "a-different-master-key")
    with pytest.raises(TelephonyError):
        decrypt_provider_secret(blob)


def test_v1_rows_are_still_readable():
    """Existing stored credentials must survive the change."""
    import base64
    import hashlib
    import hmac
    import json

    from tenant_portal_api.telephony_credentials import decrypt_provider_secret

    # Rebuild a v1 blob exactly as the old implementation did.
    master = hashlib.sha256(
        os.environ["TELEPHONY_CREDENTIAL_ENCRYPTION_KEY"].encode()
    ).digest()

    def derive(purpose: bytes) -> bytes:
        return hmac.new(
            master, b"telephony-provider-credential:" + purpose, hashlib.sha256
        ).digest()

    def keystream(key: bytes, nonce: bytes, size: int) -> bytes:
        blocks, counter = [], 0
        while sum(len(b) for b in blocks) < size:
            blocks.append(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
            counter += 1
        return b"".join(blocks)[:size]

    def b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii")

    secret = "legacy-provider-key"
    nonce = b"0123456789abcdef"
    plaintext = secret.encode()
    ciphertext = bytes(
        a ^ b for a, b in zip(plaintext, keystream(derive(b"enc"), nonce, len(plaintext)))
    )
    tag = hmac.new(derive(b"mac"), nonce + ciphertext, hashlib.sha256).digest()
    payload = json.dumps(
        {"nonce": b64(nonce), "ciphertext": b64(ciphertext), "tag": b64(tag)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    v1_blob = "enc:v1:" + b64(payload)

    assert decrypt_provider_secret(v1_blob) == secret


def test_missing_master_key_is_a_clear_failure(monkeypatch):
    from tenant_portal_api.telephony_credentials import encrypt_provider_secret
    from tenant_portal_api.telephony_errors import TelephonyError

    monkeypatch.delenv("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(TelephonyError) as excinfo:
        encrypt_provider_secret("KEY-abc")
    assert "TELEPHONY_CREDENTIAL_ENCRYPTION_KEY" in str(excinfo.value)
