"""Phase 2 tests — DB secret provider, admin secret rotation, and masked credentials read model."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import psycopg  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402
from control_plane.secrets import DictSecretProvider  # noqa: E402
from control_plane.secrets_db import DbSecretProvider  # noqa: E402
from admin.queries import rotate_tenant_secret, get_tenant_credentials_masked  # noqa: E402


def test_db_secret_provider_fallback():
    """Verify DbSecretProvider queries DB first, then falls back to env/dict fallback."""
    fallback = DictSecretProvider({"fallback-tenant-id": "fallback-secret-123"})
    provider = DbSecretProvider(env_fallback=fallback)

    # Fallback lookup
    assert provider.get("fallback-tenant-id") == "fallback-secret-123"
    assert provider.get("non-existent-tenant") is None


def test_db_secret_provider_live_db():
    """Verify DbSecretProvider reads raw hmac_secret from Supabase tenants table."""
    t_id = str(uuid.uuid4())
    raw_secret = f"test-secret-{uuid.uuid4()}"

    try:
        with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
            conn.execute(
                """
                INSERT INTO tenants (id, name, hmac_secret, hmac_secret_hash, status)
                VALUES (%s, 'Test DB Secret Tenant', %s, 'hash', 'active')
                """,
                (t_id, raw_secret),
            )

        provider = DbSecretProvider()
        retrieved = provider.get(t_id)
        assert retrieved == raw_secret
    finally:
        with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
            conn.execute("DELETE FROM tenants WHERE id = %s", (t_id,))


def test_admin_secret_rotation_and_masked_credentials():
    """Verify rotate_tenant_secret and get_tenant_credentials_masked query functions."""
    t_id = str(uuid.uuid4())
    initial_secret = f"initial-secret-{uuid.uuid4()}"

    try:
        with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
            conn.execute(
                """
                INSERT INTO tenants (id, name, hmac_secret, hmac_secret_hash, status)
                VALUES (%s, 'Test Rotation Tenant', %s, 'initial-hash', 'active')
                """,
                (t_id, initial_secret),
            )

            # Test secret rotation
            new_secret = rotate_tenant_secret(conn, t_id)
            assert new_secret != initial_secret
            assert len(new_secret) > 20

            # Test DB provider picks up new rotated secret immediately
            provider = DbSecretProvider()
            assert provider.get(t_id) == new_secret

            # Test masked credentials query (never exposes raw secret)
            creds = get_tenant_credentials_masked(conn, t_id)
            assert creds["tenant_id"] == t_id
            assert creds["has_raw_secret"] is True
            assert creds["secret_masked"] == "••••••••••••••••••••••••••••••••"
            assert "hmac_secret" not in creds
    finally:
        with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
            conn.execute("DELETE FROM tenants WHERE id = %s", (t_id,))
