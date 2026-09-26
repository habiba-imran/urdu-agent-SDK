"""F-C6 — tenant HMAC signing secrets are encrypted at rest.

`tenants.hmac_secret` held the raw signing credential in plaintext while the schema comment,
control_plane/secrets.py and the Phase 1 doc all claimed "hash ONLY, never the secret", so a
database dump was every tenant's permanent credential.

This cannot be a hash — the value has to be handed back to the host that signs with it — so
it is encryption, and the tests that matter are: it round-trips, a wrong key fails CLOSED
rather than falling through to something else, and the rollout never leaves minting broken.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane import secret_crypto  # noqa: E402


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv(secret_crypto.ENV_VAR, "unit-test-tenant-key")


def test_round_trip(key):
    secret = "tenant-signing-secret-value"
    blob = secret_crypto.encrypt_tenant_secret(secret)
    assert blob.startswith(secret_crypto.PREFIX)
    assert secret not in blob
    assert secret_crypto.decrypt_tenant_secret(blob) == secret


def test_each_ciphertext_is_distinct(key):
    a = secret_crypto.encrypt_tenant_secret("same")
    b = secret_crypto.encrypt_tenant_secret("same")
    assert a != b
    assert secret_crypto.decrypt_tenant_secret(a) == secret_crypto.decrypt_tenant_secret(b)


def test_wrong_key_raises_rather_than_returning_garbage(key, monkeypatch):
    blob = secret_crypto.encrypt_tenant_secret("tenant-secret")
    monkeypatch.setenv(secret_crypto.ENV_VAR, "a-different-key")
    with pytest.raises(secret_crypto.TenantSecretCryptoError):
        secret_crypto.decrypt_tenant_secret(blob)


def test_tampering_is_detected(key):
    blob = secret_crypto.encrypt_tenant_secret("tenant-secret")
    tampered = blob[:-3] + ("AAA" if not blob.endswith("AAA") else "BBB")
    with pytest.raises(secret_crypto.TenantSecretCryptoError):
        secret_crypto.decrypt_tenant_secret(tampered)


def test_missing_key_cannot_open_an_encrypted_value(key, monkeypatch):
    """The dangerous case: the key was removed but ciphertext remains. It must raise, not
    silently behave as if the tenant had no secret."""
    blob = secret_crypto.encrypt_tenant_secret("tenant-secret")
    monkeypatch.delenv(secret_crypto.ENV_VAR, raising=False)
    with pytest.raises(secret_crypto.TenantSecretCryptoError):
        secret_crypto.decrypt_tenant_secret(blob)


def test_encryption_is_inactive_without_a_key(monkeypatch):
    """Rollout: with no key configured, writers keep using the plaintext column instead of
    failing — a deploy that has not had the key added yet must not take minting down."""
    monkeypatch.delenv(secret_crypto.ENV_VAR, raising=False)
    assert secret_crypto.is_enabled() is False
    assert secret_crypto.encrypt_tenant_secret("x") is None


def test_plaintext_values_pass_through(key):
    """Mid-rollout the same column can hold a plaintext secret written by an older service."""
    assert secret_crypto.decrypt_tenant_secret("raw-plaintext") == "raw-plaintext"
    assert secret_crypto.decrypt_tenant_secret(None) is None
    assert secret_crypto.looks_encrypted("raw-plaintext") is False


# --------------------------------------------------------------------- database-backed


import os  # noqa: E402

requires_db = pytest.mark.skipif(
    not os.environ.get("SUPABASE_DB_URL"), reason="SUPABASE_DB_URL not configured"
)


@requires_db
def test_provider_prefers_ciphertext_and_fails_closed_on_a_wrong_key(key, monkeypatch):
    """The mint must never fall back to another value when a ciphertext will not open."""
    import psycopg
    from dbconn import conn_kwargs

    from control_plane.secrets_db import DbSecretProvider

    tenant_id = str(uuid.uuid4())
    secret = "the-real-signing-secret"
    blob = secret_crypto.encrypt_tenant_secret(secret)

    with psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        if (
            conn.execute(
                "select 1 from information_schema.columns "
                "where table_name='tenants' and column_name='hmac_secret_enc'"
            ).fetchone()
            is None
        ):
            pytest.skip("0033 not applied to this database")
        conn.execute(
            "insert into tenants (id, name, hmac_secret, hmac_secret_enc, hmac_secret_hash) "
            "values (%s, %s, null, %s, 'h')",
            (tenant_id, f"enc-test-{tenant_id[:8]}", blob),
        )
        try:
            provider = DbSecretProvider()
            assert provider.get(tenant_id) == secret

            # Wrong key: no secret, rather than a different one.
            monkeypatch.setenv(secret_crypto.ENV_VAR, "wrong-key")
            provider.invalidate(tenant_id)
            assert provider.get(tenant_id) is None
        finally:
            conn.execute("delete from tenants where id = %s", (tenant_id,))


@requires_db
def test_plaintext_row_still_resolves_during_rollout(key):
    """A tenant not yet migrated keeps minting."""
    import psycopg
    from dbconn import conn_kwargs

    from control_plane.secrets_db import DbSecretProvider

    tenant_id = str(uuid.uuid4())
    with psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        conn.execute(
            "insert into tenants (id, name, hmac_secret, hmac_secret_hash) "
            "values (%s, %s, %s, 'h')",
            (tenant_id, f"plain-test-{tenant_id[:8]}", "still-plaintext"),
        )
        try:
            assert DbSecretProvider().get(tenant_id) == "still-plaintext"
        finally:
            conn.execute("delete from tenants where id = %s", (tenant_id,))
