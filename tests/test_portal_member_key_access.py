"""Offline HTTP authorization regressions; no real users, DB writes or credentials."""
from contextlib import contextmanager
import os
from pathlib import Path
import time
import uuid
from unittest.mock import MagicMock

import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient

from control_plane.secret_crypto import TenantSecretCryptoError
from tenant_portal_api.auth import TENANT_JWT_AUDIENCE, TENANT_JWT_ISSUER, TenantAuthError


@pytest.fixture
def portal(monkeypatch):
    import tenant_portal_api.app as api

    signing_key = "offline-member-key-access-test-key"
    monkeypatch.setattr(api, "TENANT_PORTAL_JWT_SECRET", signing_key)
    monkeypatch.setenv("PORTAL_ALLOW_BROWSER_SECRET_REVEAL", "1")
    tenant = str(uuid.uuid4())
    owner, member, outsider = (str(uuid.uuid4()) for _ in range(3))
    memberships = {
        uid: {"tenant_id": tenant, "auth_user_id": uid, "role": role,
              "tenant_status": "active", "status": "active", "can_view_api_keys": False}
        for uid, role in [(owner, "owner"), (member, "member")]
    }
    memberships[outsider] = {**memberships[member], "tenant_id": str(uuid.uuid4()), "auth_user_id": outsider}
    monkeypatch.setattr("tenant_portal_api.portal_access.get_membership_by_auth_user",
                        lambda conn, uid, tid=None: memberships.get(uid) if tid is None or (memberships.get(uid) or {}).get('tenant_id') == tid else None)
    connection = MagicMock()

    @contextmanager
    def conn(**kwargs):
        yield connection

    monkeypatch.setattr(api, "_conn", conn)
    audit = MagicMock()
    monkeypatch.setattr(api, "record_attempt", audit)
    metadata = {"tenant_id": tenant, "publishable_key": tenant,
                "hmac_secret": "must-not-leak", "hmac_secret_hash": "must-not-leak-hash",
                "hmac_secret_enc": "must-not-leak-ciphertext",
                "secret_provisioned": True, "allowed_origins": []}
    monkeypatch.setattr(api.queries, "get_credentials", lambda *args: dict(metadata))
    monkeypatch.setattr(api.queries, "get_overview_snapshot", lambda *args: {"credentials": dict(metadata)})
    raw = MagicMock(return_value="offline-dummy-signing-secret")
    monkeypatch.setattr(api.queries, "get_raw_secret", raw)

    def token(uid, **overrides):
        claims = {"sub": tenant, "auth_user_id": uid, "role": "owner",
                  "can_view_api_keys": True, "iat": int(time.time()),
                  "exp": int(time.time()) + 3600,
                  "aud": TENANT_JWT_AUDIENCE, "iss": TENANT_JWT_ISSUER, **overrides}
        return {"Authorization": "Bearer " + jwt.encode(claims, signing_key, algorithm="HS256")}

    client = TestClient(api.app, headers={"X-UVA-Portal": "1"})
    return api, client, memberships, token, owner, member, outsider, raw, audit, connection


def test_grant_and_revoke_take_effect_with_the_same_existing_token(portal):
    api, client, members, token, owner, member, outsider, raw, audit, connection = portal
    headers = token(member)  # Deliberately forged stale owner/grant claims; DB wins.
    for path in ["/portal/credentials", "/portal/overview"]:
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        data = response.json()
        data = data.get("credentials", data)
        assert data["publishable_key"] is None
        assert data["can_view_api_keys"] is False
        assert "hmac_secret" not in data and "hmac_secret_hash" not in data
        assert "hmac_secret_enc" not in data
    assert client.get("/portal/credentials/secret", headers=headers).status_code == 403
    raw.assert_not_called()

    members[member]["can_view_api_keys"] = True
    response = client.get("/portal/credentials/secret", headers=headers)
    assert response.status_code == 403
    raw.assert_not_called()
    for path in ["/portal/credentials", "/portal/overview"]:
        metadata = client.get(path, headers=headers).json()
        metadata = metadata.get("credentials", metadata)
        assert metadata["publishable_key"] == members[member]["tenant_id"]
        assert metadata["secret_reveal_enabled"] is False

    # Approval never makes a member an owner or lets them approve themselves.
    target = f"/portal/members/{member}/api-key-access"
    assert client.patch(target, headers=headers, json={"can_view_api_keys": True}).status_code == 403
    members[member]["can_view_api_keys"] = False
    assert client.get("/portal/credentials/secret", headers=headers).status_code == 403


def test_owner_can_grant_revoke_but_cannot_target_other_tenants_or_owners(portal):
    api, client, members, token, owner, member, outsider, raw, audit, connection = portal
    # Exercise the real scoped membership UPDATE helper behind the HTTP route.
    def execute(sql, params):
        allowed, tenant_id, uid = params
        target = members.get(uid)
        row = None
        if target and target["tenant_id"] == tenant_id and target["role"] == "member":
            target["can_view_api_keys"] = allowed
            row = (uid, allowed)
        result = MagicMock()
        result.fetchone.return_value = row
        return result
    connection.execute.side_effect = execute
    for allowed in [True, False]:
        response = client.patch(f"/portal/members/{member}/api-key-access", headers=token(owner),
                                json={"can_view_api_keys": allowed, "tenant_id": members[outsider]["tenant_id"]})
        assert response.status_code == 200
        assert members[member]["can_view_api_keys"] is allowed
    for uid in [owner, outsider, str(uuid.uuid4())]:
        response = client.patch(f"/portal/members/{uid}/api-key-access", headers=token(owner),
                                json={"can_view_api_keys": True})
        assert response.status_code == 404
    assert client.patch(f"/portal/members/{member}/api-key-access", headers=token(owner),
                        json={"can_view_api_keys": "false"}).status_code == 422
    connection.commit.assert_called()


def test_revoked_or_cross_tenant_membership_cannot_reveal(portal):
    api, client, members, token, owner, member, outsider, raw, audit, connection = portal
    assert client.get("/portal/credentials/secret", headers=token(outsider)).status_code == 401
    del members[member]
    assert client.get("/portal/credentials/secret", headers=token(member)).status_code == 401
    raw.assert_not_called()


def test_missing_migration_has_actionable_error(portal):
    api, client, members, token, owner, member, outsider, raw, audit, connection = portal
    connection.execute.side_effect = psycopg.errors.UndefinedColumn("missing permission column")
    response = client.patch(f"/portal/members/{member}/api-key-access", headers=token(owner),
                            json={"can_view_api_keys": True})
    assert response.status_code == 503
    assert "migration" in response.json()["detail"]
    connection.rollback.assert_called_once()


def test_owner_reveal_disabled_and_crypto_errors_are_explained(portal, monkeypatch):
    api, client, members, token, owner, member, outsider, raw, audit, connection = portal
    monkeypatch.setenv("PORTAL_ALLOW_BROWSER_SECRET_REVEAL", "0")
    metadata = client.get("/portal/credentials", headers=token(owner)).json()
    assert metadata["can_view_api_keys"] is True
    assert metadata["secret_reveal_enabled"] is False
    assert client.get("/portal/credentials/secret", headers=token(owner)).status_code == 410
    raw.assert_not_called()
    monkeypatch.setenv("PORTAL_ALLOW_BROWSER_SECRET_REVEAL", "1")
    raw.side_effect = TenantSecretCryptoError("private backend diagnostic")
    response = client.get("/portal/credentials/secret", headers=token(owner))
    assert response.status_code == 503
    assert "encryption key" in response.json()["detail"]
    assert "private backend diagnostic" not in response.text
    audit.assert_not_called()


def test_owner_can_reveal_secret_with_audit_and_no_store(portal):
    api, client, members, token, owner, member, outsider, raw, audit, connection = portal
    response = client.get("/portal/credentials/secret", headers=token(owner))
    assert response.status_code == 200
    assert response.json()["hmac_secret"] == "offline-dummy-signing-secret"
    assert response.headers["cache-control"] == "no-store"
    assert audit.call_args.kwargs["identity"] == owner
    assert "offline-dummy-signing-secret" not in str(audit.call_args)


def test_reveal_default_applies_on_hosted_deployments(monkeypatch):
    from tenant_portal_api.session_cookie import browser_secret_reveal_enabled
    monkeypatch.setattr("tenant_portal_api.session_cookie.is_hosted", lambda: True)
    monkeypatch.delenv("PORTAL_ALLOW_BROWSER_SECRET_REVEAL", raising=False)
    assert browser_secret_reveal_enabled() is True


def test_permission_sql_and_migration_in_temporary_postgres_tables():
    """Use real Postgres with session-local tables; public data is read-only."""
    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn or os.environ.get("CI_UNIT_FORCE_OFFLINE") == "1":
        pytest.skip("temporary-table Postgres check requires a database connection")
    from tenant_portal_api.membership import (
        get_membership_by_auth_user, list_members, set_member_api_key_access,
    )
    from tenant_portal_api.portal_access import enrich_claims_with_live_membership

    tenant, other_tenant, owner, member, outsider = (str(uuid.uuid4()) for _ in range(5))
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on") as conn:
        # Temporary tables shadow the real tables for these unqualified queries.
        conn.execute("create temp table tenants (id uuid primary key, name text, status text)")
        conn.execute("""create temp table tenant_members (
            tenant_id uuid, auth_user_id uuid, email text, role text,
            status text default 'active', created_at timestamptz default now())""")
        conn.execute("insert into tenants values (%s, 'test', 'active'), (%s, 'other', 'active')", (tenant, other_tenant))
        for tid, uid, role in [(tenant, owner, 'owner'), (tenant, member, 'member'), (other_tenant, outsider, 'member')]:
            conn.execute("insert into tenant_members (tenant_id, auth_user_id, role) values (%s, %s, %s)", (tid, uid, role))

        # Old schema fails closed while waiting for deployment of the migration.
        assert get_membership_by_auth_user(conn, member)["can_view_api_keys"] is False
        migration = next((Path(__file__).resolve().parents[1] / "supabase/migrations").glob("*_member_api_key_access.sql"))
        conn.execute(migration.read_text(encoding="utf-8").replace("public.tenant_members", "pg_temp.tenant_members"))
        assert get_membership_by_auth_user(conn, member)["can_view_api_keys"] is False
        assert {m['auth_user_id']: m['can_view_api_keys'] for m in list_members(conn, tenant)} == {owner: True, member: False}
        claims = {"sub": tenant, "auth_user_id": member, "role": "owner", "can_view_api_keys": True}
        assert enrich_claims_with_live_membership(conn, claims)["can_view_api_keys"] is False
        for allowed in [True, False]:
            set_member_api_key_access(conn, tenant_id=tenant, auth_user_id=member, allowed=allowed)
            assert enrich_claims_with_live_membership(conn, claims)["can_view_api_keys"] is allowed
        for uid in [owner, outsider]:
            with pytest.raises(TenantAuthError):
                set_member_api_key_access(conn, tenant_id=tenant, auth_user_id=uid, allowed=True)
        conn.rollback()

