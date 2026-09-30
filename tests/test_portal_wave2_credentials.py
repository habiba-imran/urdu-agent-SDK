"""Wave 2 / P1-H6: HMAC visible to owners; console rotate off; HttpOnly session cookie."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def test_browser_secret_reveal_defaults_on(monkeypatch):
    monkeypatch.delenv("PORTAL_ALLOW_BROWSER_SECRET_REVEAL", raising=False)
    from tenant_portal_api.session_cookie import browser_secret_reveal_enabled

    assert browser_secret_reveal_enabled() is True
    monkeypatch.setenv("PORTAL_ALLOW_BROWSER_SECRET_REVEAL", "0")
    assert browser_secret_reveal_enabled() is False
    monkeypatch.setenv("PORTAL_ALLOW_BROWSER_SECRET_REVEAL", "1")
    assert browser_secret_reveal_enabled() is True


def test_browser_secret_rotate_defaults_off(monkeypatch):
    monkeypatch.delenv("PORTAL_ALLOW_BROWSER_SECRET_ROTATE", raising=False)
    from tenant_portal_api.session_cookie import browser_secret_rotate_enabled

    assert browser_secret_rotate_enabled() is False
    monkeypatch.setenv("PORTAL_ALLOW_BROWSER_SECRET_ROTATE", "1")
    assert browser_secret_rotate_enabled() is True


def test_credentials_include_hmac_for_owners_by_default(monkeypatch):
    """Owners always get raw HMAC on GET /portal/credentials (reveal default on)."""
    monkeypatch.delenv("PORTAL_ALLOW_BROWSER_SECRET_REVEAL", raising=False)
    monkeypatch.setenv("TENANT_PORTAL_JWT_SECRET", "wave2-test-portal-jwt-secret-32b")

    from tests.test_phase4_portal_api import _cleanup_portal_tenant, _seed_portal_tenant
    from tenant_portal_api.app import app

    tenant_id, secret, voice_id, _ = _seed_portal_tenant()
    client = TestClient(app)
    try:
        login = client.post(
            "/portal/login", json={"tenant_id": tenant_id, "tenant_secret": secret}
        )
        assert login.status_code == 200
        token = login.json()["token"]
        assert "uva_portal_session" in login.cookies

        creds = client.get(
            "/portal/credentials",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert creds.status_code == 200
        body = creds.json()
        assert body["hmac_secret"] == secret

        revealed = client.get(
            "/portal/credentials/secret",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revealed.status_code == 200
        assert revealed.json()["hmac_secret"] == secret
    finally:
        _cleanup_portal_tenant(tenant_id, voice_id)


def test_credentials_secret_returns_410_when_reveal_disabled(monkeypatch):
    monkeypatch.setenv("PORTAL_ALLOW_BROWSER_SECRET_REVEAL", "0")
    monkeypatch.setenv("TENANT_PORTAL_JWT_SECRET", "wave2-test-portal-jwt-secret-32b")

    from tests.test_phase4_portal_api import _cleanup_portal_tenant, _seed_portal_tenant
    from tenant_portal_api.app import app

    tenant_id, secret, voice_id, _ = _seed_portal_tenant()
    client = TestClient(app)
    try:
        login = client.post(
            "/portal/login", json={"tenant_id": tenant_id, "tenant_secret": secret}
        )
        token = login.json()["token"]

        revealed = client.get(
            "/portal/credentials/secret",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revealed.status_code == 410
        assert "disabled" in revealed.json()["detail"].lower()

        creds = client.get(
            "/portal/credentials",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert creds.status_code == 200
        assert "hmac_secret" not in creds.json() or creds.json().get("hmac_secret") is None
    finally:
        _cleanup_portal_tenant(tenant_id, voice_id)


def test_portal_cookie_authenticates_whoami(monkeypatch):
    monkeypatch.setenv("TENANT_PORTAL_JWT_SECRET", "wave2-test-portal-jwt-secret-32b")

    from tests.test_phase4_portal_api import _cleanup_portal_tenant, _seed_portal_tenant
    from tenant_portal_api.app import app
    from tenant_portal_api.session_cookie import PORTAL_SESSION_COOKIE

    tenant_id, secret, voice_id, _ = _seed_portal_tenant()
    client = TestClient(app)
    try:
        login = client.post(
            "/portal/login", json={"tenant_id": tenant_id, "tenant_secret": secret}
        )
        assert login.status_code == 200
        cookie = login.cookies.get(PORTAL_SESSION_COOKIE)
        assert cookie

        # Cookie only — no Authorization header.
        who = client.get("/portal/whoami")
        assert who.status_code == 200
        body = who.json()
        assert body["tenant_id"] == tenant_id
        assert body["role"] == "owner"

        logout = client.post("/portal/auth/logout")
        assert logout.status_code == 200
        gone = client.get("/portal/whoami")
        assert gone.status_code == 401
    finally:
        _cleanup_portal_tenant(tenant_id, voice_id)


def test_rotate_returns_410_by_default_and_does_not_rotate(monkeypatch):
    """Console rotate stays disabled; must not discard the secret."""
    monkeypatch.delenv("PORTAL_ALLOW_BROWSER_SECRET_ROTATE", raising=False)
    monkeypatch.setenv("TENANT_PORTAL_JWT_SECRET", "wave2-test-portal-jwt-secret-32b")

    from tests.test_phase4_portal_api import _cleanup_portal_tenant, _seed_portal_tenant
    from tenant_portal_api.app import app

    tenant_id, secret, voice_id, _ = _seed_portal_tenant()
    client = TestClient(app)
    try:
        login = client.post(
            "/portal/login", json={"tenant_id": tenant_id, "tenant_secret": secret}
        )
        token = login.json()["token"]
        rotated = client.post(
            "/portal/credentials/rotate-secret",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rotated.status_code == 410
        assert "disabled" in rotated.json()["detail"].lower()

        # Old secret still works — we must not have rotated without delivering the new value.
        relogin = client.post(
            "/portal/login", json={"tenant_id": tenant_id, "tenant_secret": secret}
        )
        assert relogin.status_code == 200
    finally:
        _cleanup_portal_tenant(tenant_id, voice_id)


def test_rotate_break_glass_returns_one_shot_secret(monkeypatch):
    monkeypatch.setenv("PORTAL_ALLOW_BROWSER_SECRET_ROTATE", "1")
    monkeypatch.setenv("TENANT_PORTAL_JWT_SECRET", "wave2-test-portal-jwt-secret-32b")

    from tests.test_phase4_portal_api import _cleanup_portal_tenant, _seed_portal_tenant
    from tenant_portal_api.app import app

    tenant_id, secret, voice_id, _ = _seed_portal_tenant()
    client = TestClient(app)
    try:
        login = client.post(
            "/portal/login", json={"tenant_id": tenant_id, "tenant_secret": secret}
        )
        token = login.json()["token"]
        rotated = client.post(
            "/portal/credentials/rotate-secret",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rotated.status_code == 200
        body = rotated.json()
        assert body["hmac_secret"]
        assert body["hmac_secret"] != secret
        assert "once" in body["warning"].lower()
    finally:
        _cleanup_portal_tenant(tenant_id, voice_id)


def test_member_cannot_rotate_secret(monkeypatch):
    """P1-C1: members must get 403 on owner credential mutations (even if break-glass on)."""
    import uuid

    import psycopg

    monkeypatch.setenv("PORTAL_ALLOW_BROWSER_SECRET_ROTATE", "1")
    monkeypatch.setattr(
        "tenant_portal_api.portal_access.auto_bootstrap_enabled", lambda: True
    )

    from dbconn import conn_kwargs
    from tenant_portal_api import app as portal_app
    from tenant_portal_api.app import app
    from tenant_portal_api.auth import issue_portal_session
    from tenant_portal_api.membership import exchange_supabase_user_for_portal_session

    try:
        conn = psycopg.connect(**conn_kwargs())
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"database unavailable: {exc}")

    # Must match the module-level secret the HTTP routes verify against.
    jwt_secret = portal_app.TENANT_PORTAL_JWT_SECRET
    owner_id = str(uuid.uuid4())
    member_id = str(uuid.uuid4())
    tenant_id = None
    try:
        owner_session = exchange_supabase_user_for_portal_session(
            conn,
            auth_user_id=owner_id,
            email=f"owner-{owner_id[:8]}@example.com",
            jwt_secret=jwt_secret,
        )
        tenant_id = owner_session["tenant_id"]
        conn.execute(
            """
            insert into tenant_members (tenant_id, auth_user_id, email, role, status)
            values (%s, %s, %s, 'member', 'active')
            """,
            (tenant_id, member_id, f"member-{member_id[:8]}@example.com"),
        )
        conn.commit()
        member_session = issue_portal_session(
            conn,
            tenant_id=tenant_id,
            jwt_secret=jwt_secret,
            auth_user_id=member_id,
            role="member",
        )
        client = TestClient(app)
        rotated = client.post(
            "/portal/credentials/rotate-secret",
            headers={"Authorization": f"Bearer {member_session['token']}"},
        )
        assert rotated.status_code == 403
    finally:
        if tenant_id:
            conn.execute("delete from tenant_members where tenant_id = %s", (tenant_id,))
            conn.execute("delete from tenants where id = %s", (tenant_id,))
            conn.commit()
        conn.close()


def test_dashboard_csp_blocks_script_attrs():
    cfg = (ROOT / "dashboard" / "next.config.js").read_text(encoding="utf-8")
    assert "script-src-attr 'none'" in cfg


def test_credentials_page_shows_hmac_without_rotate():
    page = (ROOT / "dashboard" / "src" / "app" / "credentials" / "page.tsx").read_text(
        encoding="utf-8"
    )
    assert "hmacSecret" in page
    assert "Copy HMAC secret" in page or "handleCopyHmacSecret" in page
    assert "rotateCredentialSecret" not in page
    assert "Rotate secret" not in page
    assert "/claim" not in page
    api = (ROOT / "dashboard" / "src" / "lib" / "portalApi.ts").read_text(encoding="utf-8")
    assert "rotateCredentialSecret" not in api
    assert "/portal/credentials/rotate-secret" not in api
