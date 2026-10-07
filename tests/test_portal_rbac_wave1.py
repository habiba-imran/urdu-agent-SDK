"""Wave 1: portal RBAC, live membership, hosted bootstrap gate."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import jwt as pyjwt
import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dbconn import conn_kwargs  # noqa: E402
from tenant_portal_api.auth import (  # noqa: E402
    TENANT_JWT_AUDIENCE,
    TENANT_JWT_ISSUER,
    TenantAuthError,
    issue_portal_session,
)
from tenant_portal_api.membership import (  # noqa: E402
    exchange_supabase_user_for_portal_session,
    get_membership_by_auth_user,
)
from tenant_portal_api.portal_access import (  # noqa: E402
    auto_bootstrap_enabled,
    enrich_claims_with_live_membership,
    require_owner_claims,
)


def _table_exists(conn: psycopg.Connection, name: str) -> bool:
    row = conn.execute(
        "select 1 from information_schema.tables where table_schema='public' and table_name=%s",
        (name,),
    ).fetchone()
    return row is not None


@pytest.fixture
def db():
    if not (os.environ.get("SUPABASE_DB_URL") or "").strip():
        pytest.skip("SUPABASE_DB_URL not configured")
    try:
        conn = psycopg.connect(**conn_kwargs())
    except (Exception, SystemExit) as exc:  # pragma: no cover — dbconn sys.exits if unset
        pytest.skip(f"database unavailable: {exc}")
    if not _table_exists(conn, "tenant_members"):
        conn.close()
        pytest.skip("apply migration 0034_tenant_members.sql first")
    yield conn
    conn.rollback()
    conn.close()


def test_auto_bootstrap_defaults(monkeypatch):
    monkeypatch.delenv("PORTAL_ALLOW_TENANT_BOOTSTRAP", raising=False)
    monkeypatch.setattr("tenant_portal_api.portal_access.is_hosted", lambda: False)
    assert auto_bootstrap_enabled() is True
    monkeypatch.setattr("tenant_portal_api.portal_access.is_hosted", lambda: True)
    assert auto_bootstrap_enabled() is False
    monkeypatch.setenv("PORTAL_ALLOW_TENANT_BOOTSTRAP", "1")
    assert auto_bootstrap_enabled() is True
    monkeypatch.setenv("PORTAL_ALLOW_TENANT_BOOTSTRAP", "0")
    monkeypatch.setattr("tenant_portal_api.portal_access.is_hosted", lambda: False)
    assert auto_bootstrap_enabled() is False


def test_hosted_bootstrap_blocked(db, monkeypatch):
    monkeypatch.setattr(
        "tenant_portal_api.portal_access.auto_bootstrap_enabled", lambda: False
    )
    auth_user_id = str(uuid.uuid4())
    with pytest.raises(TenantAuthError) as exc:
        exchange_supabase_user_for_portal_session(
            db,
            auth_user_id=auth_user_id,
            email=f"blocked-{auth_user_id[:8]}@example.com",
            jwt_secret="test-portal-jwt-secret",
        )
    assert exc.value.status == 403
    assert get_membership_by_auth_user(db, auth_user_id) is None


def test_member_cannot_pass_owner_gate(db, monkeypatch):
    monkeypatch.delenv("TENANT_SECRET_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(
        "tenant_portal_api.portal_access.auto_bootstrap_enabled", lambda: True
    )
    jwt_secret = "test-portal-jwt-secret"
    owner_id = str(uuid.uuid4())
    member_id = str(uuid.uuid4())

    owner_session = exchange_supabase_user_for_portal_session(
        db,
        auth_user_id=owner_id,
        email=f"owner-{owner_id[:8]}@example.com",
        jwt_secret=jwt_secret,
    )
    tenant_id = owner_session["tenant_id"]
    db.execute(
        """
        insert into tenant_members (tenant_id, auth_user_id, email, role, status)
        values (%s, %s, %s, 'member', 'active')
        """,
        (tenant_id, member_id, f"member-{member_id[:8]}@example.com"),
    )
    db.commit()

    member_session = issue_portal_session(
        db,
        tenant_id=tenant_id,
        jwt_secret=jwt_secret,
        auth_user_id=member_id,
        role="member",
    )
    claims = pyjwt.decode(
        member_session["token"],
        jwt_secret,
        algorithms=["HS256"],
        audience=TENANT_JWT_AUDIENCE,
        issuer=TENANT_JWT_ISSUER,
    )
    live = enrich_claims_with_live_membership(db, claims)
    assert live["role"] == "member"
    with pytest.raises(TenantAuthError) as exc:
        require_owner_claims(live)
    assert exc.value.status == 403


def test_revoked_membership_rejects_token(db, monkeypatch):
    monkeypatch.delenv("TENANT_SECRET_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(
        "tenant_portal_api.portal_access.auto_bootstrap_enabled", lambda: True
    )
    jwt_secret = "test-portal-jwt-secret"
    auth_user_id = str(uuid.uuid4())
    session = exchange_supabase_user_for_portal_session(
        db,
        auth_user_id=auth_user_id,
        email=f"gone-{auth_user_id[:8]}@example.com",
        jwt_secret=jwt_secret,
    )
    db.commit()
    claims = pyjwt.decode(
        session["token"],
        jwt_secret,
        algorithms=["HS256"],
        audience=TENANT_JWT_AUDIENCE,
        issuer=TENANT_JWT_ISSUER,
    )
    db.execute("delete from tenant_members where auth_user_id = %s", (auth_user_id,))
    db.commit()
    with pytest.raises(TenantAuthError) as exc:
        enrich_claims_with_live_membership(db, claims)
    assert exc.value.status == 401
