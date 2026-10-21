"""Multi-workspace regressions. SQL checks write only session-local temporary tables."""
from contextlib import contextmanager
import os
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from tenant_portal_api.auth import TenantAuthError, verify_tenant_jwt
from tenant_portal_api import membership as memberships


@pytest.fixture
def workspace_db():
    if os.environ.get("CI_UNIT_FORCE_OFFLINE") == "1" or not os.environ.get("SUPABASE_DB_URL"):
        pytest.skip("requires Postgres for isolated temporary-table checks")
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=10, prepare_threshold=None,
                         options="-c default_transaction_read_only=on") as conn:
        conn.execute("""create temp table tenants (
            id uuid primary key, name text, status text, hmac_secret_hash text)""")
        conn.execute("""create temp table tenant_members (
            tenant_id uuid, auth_user_id uuid, email text, role text,
            status text default 'active', created_at timestamptz default now(),
            can_view_api_keys boolean not null default false,
            constraint tenant_members_auth_user_unique unique (auth_user_id))""")
        migration = next((Path(__file__).resolve().parents[1] / "supabase/migrations").glob("*_multi_tenant_memberships.sql"))
        conn.execute(migration.read_text(encoding="utf-8").replace("public.tenant_members", "pg_temp.tenant_members"))
        tenant_a, tenant_b, tenant_c, owner_a, owner_b, member = [str(uuid.uuid4()) for _ in range(6)]
        for tid in [tenant_a, tenant_b, tenant_c]:
            conn.execute("insert into tenants values (%s, %s, 'active', 'hash')", (tid, tid))
        for tid, uid, role in [(tenant_a, owner_a, 'owner'), (tenant_b, owner_b, 'owner'),
                               (tenant_a, member, 'member')]:
            conn.execute("insert into tenant_members (tenant_id, auth_user_id, email, role) values (%s,%s,%s,%s)",
                         (tid, uid, f"{uid}@example.com", role))
        yield conn, tenant_a, tenant_b, tenant_c, owner_a, owner_b, member
        conn.rollback()


def test_invite_existing_user_to_second_workspace_and_resend(workspace_db, monkeypatch):
    conn, a, b, c, owner_a, owner_b, member = workspace_db
    email = f"{member}@example.com"
    sender = MagicMock(return_value={"id": member, "existing": True})
    monkeypatch.setattr(memberships, "invite_auth_user_by_email", sender)
    invited = memberships.invite_member_to_tenant(conn, tenant_id=b, inviter_auth_user_id=owner_b, email=email.upper())
    assert invited["tenant_id"] == b and invited["status"] == "invited"
    assert memberships.get_membership_by_auth_user(conn, member, a)["status"] == "active"
    assert memberships.get_membership_by_auth_user(conn, member, b)["can_view_api_keys"] is False
    resent = memberships.invite_member_to_tenant(conn, tenant_id=b, inviter_auth_user_id=owner_b, email=email)
    assert resent["resent"] is True
    assert conn.execute("select count(*) from tenant_members where auth_user_id=%s", (member,)).fetchone()[0] == 2
    sender.assert_called_with(email, tenant_id=b)
    session = memberships.exchange_supabase_user_for_portal_session(
        conn, auth_user_id=member, email=email, jwt_secret="multi-workspace-regression-key-32chars", tenant_id=b)
    assert verify_tenant_jwt(session["token"], "multi-workspace-regression-key-32chars")["sub"] == b
    with pytest.raises(TenantAuthError, match="already a member"):
        memberships.invite_member_to_tenant(conn, tenant_id=b, inviter_auth_user_id=owner_b, email=email)
    assert len(memberships.list_workspaces(conn, member)) == 2


def test_role_and_permission_are_independent_in_each_workspace(workspace_db):
    from tenant_portal_api.portal_access import enrich_claims_with_live_membership
    conn, a, b, c, owner_a, owner_b, member = workspace_db
    conn.execute("insert into tenant_members (tenant_id, auth_user_id, role, status) values (%s,%s,'member','invited')", (b, owner_a))
    claims = {"sub": b, "auth_user_id": owner_a, "role": "owner", "can_view_api_keys": True}
    assert enrich_claims_with_live_membership(conn, claims)["role"] == "member"
    assert claims["can_view_api_keys"] is False
    memberships.set_member_api_key_access(conn, tenant_id=b, auth_user_id=owner_a, allowed=True)
    assert enrich_claims_with_live_membership(conn, claims)["can_view_api_keys"] is True
    assert enrich_claims_with_live_membership(conn, {"sub": a, "auth_user_id": owner_a})["role"] == "owner"
    with pytest.raises(TenantAuthError):
        memberships.require_owner_on_tenant(conn, auth_user_id=owner_a, tenant_id=b)
    with pytest.raises(TenantAuthError):
        memberships.require_membership_on_tenant(conn, auth_user_id=owner_a, tenant_id=c)


def test_exchange_only_activates_selected_membership_and_rejects_nonmembership(workspace_db):
    conn, a, b, c, owner_a, owner_b, member = workspace_db
    conn.execute("update tenant_members set status='invited' where auth_user_id=%s", (member,))
    conn.execute("insert into tenant_members (tenant_id,auth_user_id,role,status) values (%s,%s,'member','invited')", (b, member))
    kwargs = dict(auth_user_id=member, email=None, jwt_secret="multi-workspace-regression-key-32chars")
    memberships.exchange_supabase_user_for_portal_session(conn, tenant_id=b, **kwargs)
    assert memberships.get_membership_by_auth_user(conn, member, a)["status"] == "invited"
    assert memberships.get_membership_by_auth_user(conn, member, b)["status"] == "active"
    with pytest.raises(TenantAuthError, match="not a member"):
        memberships.exchange_supabase_user_for_portal_session(conn, tenant_id=c, **kwargs)
    conn.execute("update tenants set status='suspended' where id=%s", (b,))
    with pytest.raises(TenantAuthError, match="suspended"):
        memberships.exchange_supabase_user_for_portal_session(conn, tenant_id=b, **kwargs)
    assert memberships.get_membership_by_auth_user(conn, member)["tenant_id"] == a
    assert [w["tenant_id"] for w in memberships.list_workspaces(conn, member)] == [a]


def test_migration_rejects_duplicate_membership_without_poisoning_transaction(workspace_db):
    conn, a, b, c, owner_a, owner_b, member = workspace_db
    with pytest.raises(psycopg.errors.UniqueViolation):
        with conn.transaction():
            conn.execute("insert into tenant_members (tenant_id,auth_user_id,role) values (%s,%s,'member')", (a, member))
    assert memberships.get_membership_by_auth_user(conn, member, a) is not None


def test_http_exchange_verifies_user_before_selecting_workspace(monkeypatch):
    import tenant_portal_api.app as api
    uid, tenant = str(uuid.uuid4()), str(uuid.uuid4())
    connection = MagicMock()
    @contextmanager
    def conn():
        yield connection
    monkeypatch.setattr(api, "_conn", conn)
    monkeypatch.setattr(api, "verify_supabase_access_token", lambda token: {"sub": uid, "email": "user@example.com"})
    monkeypatch.setattr(api, "assert_not_throttled", MagicMock())
    monkeypatch.setattr(api, "record_attempt", MagicMock())
    exchange = MagicMock(return_value={"tenant_id": tenant, "role": "member"})
    monkeypatch.setattr(api, "exchange_supabase_user_for_portal_session", exchange)
    client = TestClient(api.app, headers={"X-UVA-Portal": "1"})
    response = client.post("/portal/auth/supabase", json={"access_token": "verified-token", "tenant_id": tenant, "auth_user_id": "attacker"})
    assert response.status_code == 200
    assert exchange.call_args.kwargs["auth_user_id"] == uid
    assert exchange.call_args.kwargs["tenant_id"] == tenant
    exchange.side_effect = TenantAuthError(403, "not a member of this tenant")
    assert client.post("/portal/auth/supabase", json={"access_token": "verified-token", "tenant_id": tenant}).status_code == 403
    assert client.post("/portal/auth/supabase", json={"access_token": "verified-token", "tenant_id": "invalid"}).status_code == 422


@pytest.mark.parametrize("existing", [True, False])
def test_auth_emails_redirect_to_the_inviting_workspace(monkeypatch, existing):
    from tenant_portal_api import supabase_admin as admin
    uid, tenant = str(uuid.uuid4()), str(uuid.uuid4())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "offline-placeholder")
    monkeypatch.setenv("DASHBOARD_INVITE_REDIRECT_URL", "https://console.example.com/invite")
    monkeypatch.setattr(admin, "find_auth_user_id_by_email", lambda email: uid if existing else None)
    client = MagicMock()
    client.post.return_value.status_code = 200
    client.post.return_value.json.return_value = {"id": uid}
    client.__enter__.return_value = client
    monkeypatch.setattr(admin.httpx, "Client", lambda **kwargs: client)
    assert admin.invite_auth_user_by_email(" User@example.com ", tenant_id=tenant)["id"] == uid
    args, kwargs = client.post.call_args
    assert args[0].endswith("/recover" if existing else "/invite")
    assert kwargs["json"]["email"] == "user@example.com"
    redirect = urlsplit(kwargs["params"]["redirect_to"])
    assert redirect.path == "/invite"
    assert parse_qs(redirect.query)["tenant_id"] == [tenant]


def test_existing_auth_lookup_continues_past_one_thousand_accounts(monkeypatch):
    from tenant_portal_api import supabase_admin as admin
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "offline-placeholder")
    client = MagicMock()
    client.__enter__.return_value = client
    def get(url, *, headers, params):
        users = [{"id": str(i), "email": f"other-{i}@example.com"} for i in range(200)]
        if params["page"] == 6:
            users = [{"id": "found-user", "email": "target@example.com"}]
        response = MagicMock(status_code=200)
        response.json.return_value = {"users": users}
        return response
    client.get.side_effect = get
    monkeypatch.setattr(admin.httpx, "Client", lambda **kwargs: client)
    assert admin.find_auth_user_id_by_email("Target@example.com") == "found-user"
    assert client.get.call_count == 6
