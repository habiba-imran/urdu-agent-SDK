"""Phase 1: Supabase → tenant_members → portal JWT (no live Supabase required)."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt as pyjwt
import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dbconn import conn_kwargs  # noqa: E402
from tenant_portal_api.auth import TENANT_JWT_AUDIENCE, TENANT_JWT_ISSUER  # noqa: E402
from tenant_portal_api.membership import (  # noqa: E402
    exchange_supabase_user_for_portal_session,
    get_membership_by_auth_user,
)


def _table_exists(conn: psycopg.Connection, name: str) -> bool:
    row = conn.execute(
        "select 1 from information_schema.tables where table_schema='public' and table_name=%s",
        (name,),
    ).fetchone()
    return row is not None


@pytest.fixture
def db():
    try:
        conn = psycopg.connect(**conn_kwargs())
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"database unavailable: {exc}")
    if not _table_exists(conn, "tenant_members"):
        conn.close()
        pytest.skip("apply migration 0034_tenant_members.sql first")
    yield conn
    conn.rollback()
    conn.close()


def test_first_supabase_user_bootstraps_tenant_and_owner(db, monkeypatch):
    monkeypatch.delenv("TENANT_SECRET_ENCRYPTION_KEY", raising=False)
    auth_user_id = str(uuid.uuid4())
    email = f"owner-{auth_user_id[:8]}@example.com"
    jwt_secret = "test-portal-jwt-secret"

    session = exchange_supabase_user_for_portal_session(
        db,
        auth_user_id=auth_user_id,
        email=email,
        jwt_secret=jwt_secret,
    )
    db.commit()

    assert session["tenant_id"]
    assert session["tenant_name"]
    assert session["role"] == "owner"
    assert session["token"]

    claims = pyjwt.decode(
        session["token"],
        jwt_secret,
        algorithms=["HS256"],
        audience=TENANT_JWT_AUDIENCE,
        issuer=TENANT_JWT_ISSUER,
    )
    assert claims["sub"] == session["tenant_id"]
    assert claims["auth_user_id"] == auth_user_id
    assert claims["role"] == "owner"

    membership = get_membership_by_auth_user(db, auth_user_id)
    assert membership is not None
    assert membership["tenant_id"] == session["tenant_id"]
    assert membership["role"] == "owner"

    # Second login must NOT create another tenant.
    again = exchange_supabase_user_for_portal_session(
        db,
        auth_user_id=auth_user_id,
        email=email,
        jwt_secret=jwt_secret,
    )
    db.commit()
    assert again["tenant_id"] == session["tenant_id"]


def test_invited_member_reuses_existing_tenant(db, monkeypatch):
    monkeypatch.delenv("TENANT_SECRET_ENCRYPTION_KEY", raising=False)
    owner_id = str(uuid.uuid4())
    member_id = str(uuid.uuid4())
    jwt_secret = "test-portal-jwt-secret"

    owner = exchange_supabase_user_for_portal_session(
        db,
        auth_user_id=owner_id,
        email=f"owner-{owner_id[:8]}@example.com",
        jwt_secret=jwt_secret,
    )
    db.commit()

    # Phase 2 will do this via invite API; Phase 1 proves the membership model.
    db.execute(
        """
        insert into tenant_members (tenant_id, auth_user_id, email, role)
        values (%s, %s, %s, 'member')
        """,
        (owner["tenant_id"], member_id, f"member-{member_id[:8]}@example.com"),
    )
    db.commit()

    member = exchange_supabase_user_for_portal_session(
        db,
        auth_user_id=member_id,
        email=f"member-{member_id[:8]}@example.com",
        jwt_secret=jwt_secret,
    )
    db.commit()
    assert member["tenant_id"] == owner["tenant_id"]
    assert member["role"] == "member"


def test_verify_supabase_access_token_roundtrip(monkeypatch):
    from tenant_portal_api.supabase_auth import verify_supabase_access_token

    secret = "supabase-jwt-test-secret"
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)
    auth_user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    token = pyjwt.encode(
        {
            "sub": auth_user_id,
            "email": "a@example.com",
            "role": "authenticated",
            "aud": "authenticated",
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        secret,
        algorithm="HS256",
    )
    claims = verify_supabase_access_token(token)
    assert claims["sub"] == auth_user_id
    assert claims["email"] == "a@example.com"
