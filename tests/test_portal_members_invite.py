"""Phase 2: invite member → same tenant; member cannot invent another tenant_id."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import jwt as pyjwt
import psycopg
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dbconn import conn_kwargs  # noqa: E402
from tenant_portal_api.app import app  # noqa: E402
from tenant_portal_api.auth import (  # noqa: E402
    TENANT_JWT_AUDIENCE,
    TENANT_JWT_ISSUER,
    issue_portal_session,
)
from tenant_portal_api.membership import (  # noqa: E402
    exchange_supabase_user_for_portal_session,
    get_membership_by_auth_user,
    invite_member_to_tenant,
)


def _table_ready(conn: psycopg.Connection) -> bool:
    row = conn.execute(
        "select 1 from information_schema.tables where table_schema='public' and table_name='tenant_members'"
    ).fetchone()
    return bool(row)


@pytest.fixture
def db():
    try:
        conn = psycopg.connect(**conn_kwargs())
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"database unavailable: {exc}")
    if not _table_ready(conn):
        conn.close()
        pytest.skip("apply migration 0034_tenant_members.sql first")
    yield conn
    conn.rollback()
    conn.close()


def test_invite_links_member_to_owner_tenant_without_new_tenant(db, monkeypatch):
    monkeypatch.delenv("TENANT_SECRET_ENCRYPTION_KEY", raising=False)
    jwt_secret = "test-portal-jwt-secret-phase2"
    owner_id = str(uuid.uuid4())
    member_auth_id = str(uuid.uuid4())
    member_email = f"member-{member_auth_id[:8]}@example.com"

    owner = exchange_supabase_user_for_portal_session(
        db,
        auth_user_id=owner_id,
        email=f"owner-{owner_id[:8]}@example.com",
        jwt_secret=jwt_secret,
    )
    db.commit()
    tenant_a = owner["tenant_id"]

    def _fake_invite(email: str):
        assert email == member_email
        return {"id": member_auth_id, "email": email, "existing": False}

    monkeypatch.setattr(
        "tenant_portal_api.membership.invite_auth_user_by_email", _fake_invite
    )

    invited = invite_member_to_tenant(
        db,
        tenant_id=tenant_a,
        inviter_auth_user_id=owner_id,
        email=member_email,
    )
    db.commit()
    assert invited["tenant_id"] == tenant_a
    assert invited["role"] == "member"
    assert invited["auth_user_id"] == member_auth_id

    # Count tenants created for this owner path — member login must not add one.
    before = db.execute("select count(*) from tenants").fetchone()[0]
    member_session = exchange_supabase_user_for_portal_session(
        db,
        auth_user_id=member_auth_id,
        email=member_email,
        jwt_secret=jwt_secret,
    )
    db.commit()
    after = db.execute("select count(*) from tenants").fetchone()[0]

    assert member_session["tenant_id"] == tenant_a
    assert member_session["role"] == "member"
    assert after == before

    claims = pyjwt.decode(
        member_session["token"],
        jwt_secret,
        algorithms=["HS256"],
        audience=TENANT_JWT_AUDIENCE,
        issuer=TENANT_JWT_ISSUER,
    )
    assert claims["sub"] == tenant_a
    assert claims["auth_user_id"] == member_auth_id

    membership = get_membership_by_auth_user(db, member_auth_id)
    assert membership is not None
    assert membership["tenant_id"] == tenant_a
    assert membership["role"] == "member"


def test_member_cannot_invite(db, monkeypatch):
    monkeypatch.delenv("TENANT_SECRET_ENCRYPTION_KEY", raising=False)
    jwt_secret = "test-portal-jwt-secret-phase2"
    owner_id = str(uuid.uuid4())
    member_id = str(uuid.uuid4())

    owner = exchange_supabase_user_for_portal_session(
        db,
        auth_user_id=owner_id,
        email=f"owner-{owner_id[:8]}@example.com",
        jwt_secret=jwt_secret,
    )
    db.commit()

    monkeypatch.setattr(
        "tenant_portal_api.membership.invite_auth_user_by_email",
        lambda email: {"id": member_id, "email": email, "existing": False},
    )
    invite_member_to_tenant(
        db,
        tenant_id=owner["tenant_id"],
        inviter_auth_user_id=owner_id,
        email=f"member-{member_id[:8]}@example.com",
    )
    db.commit()

    from tenant_portal_api.auth import TenantAuthError

    with pytest.raises(TenantAuthError) as exc:
        invite_member_to_tenant(
            db,
            tenant_id=owner["tenant_id"],
            inviter_auth_user_id=member_id,
            email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        )
    assert exc.value.status == 403


def test_http_invite_uses_jwt_sub_not_body_tenant(db, monkeypatch):
    """Frontend cannot pick another tenant_id — body is email-only; JWT sub wins."""
    monkeypatch.delenv("TENANT_SECRET_ENCRYPTION_KEY", raising=False)
    jwt_secret = "test-portal-jwt-secret-phase2"
    # App uses TENANT_PORTAL_JWT_SECRET from env — patch issue path via real secret
    # by minting with the same secret the app loaded.
    from tenant_portal_api import app as portal_app

    portal_secret = portal_app.TENANT_PORTAL_JWT_SECRET

    owner_id = str(uuid.uuid4())
    owner = exchange_supabase_user_for_portal_session(
        db,
        auth_user_id=owner_id,
        email=f"owner-{owner_id[:8]}@example.com",
        jwt_secret=portal_secret,
    )
    db.commit()
    tenant_a = owner["tenant_id"]

    # Decoy tenant the client might try to target (must not be used).
    decoy = str(uuid.uuid4())
    db.execute(
        """
        insert into tenants (id, name, hmac_secret_hash, status, max_concurrent, max_minutes_month, allowed_origins)
        values (%s, 'decoy', 'x', 'active', 2, 100, array['http://localhost:3000'])
        """,
        (decoy,),
    )
    db.commit()

    member_auth_id = str(uuid.uuid4())
    monkeypatch.setattr(
        "tenant_portal_api.membership.invite_auth_user_by_email",
        lambda email: {"id": member_auth_id, "email": email, "existing": False},
    )

    token = issue_portal_session(
        db,
        tenant_id=tenant_a,
        jwt_secret=portal_secret,
        auth_user_id=owner_id,
        role="owner",
    )["token"]

    client = TestClient(app)
    # Even if a client smuggles tenant_id in JSON, InviteMemberBody ignores it.
    resp = client.post(
        "/portal/members/invite",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": f"b-{member_auth_id[:8]}@example.com", "tenant_id": decoy},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == tenant_a
    assert body["tenant_id"] != decoy

    membership = get_membership_by_auth_user(db, member_auth_id)
    assert membership["tenant_id"] == tenant_a
