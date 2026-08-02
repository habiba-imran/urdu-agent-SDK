"""P6 GATE — the super-admin portal: separate auth, real SQL-backed views, audit log, CORS
isolation from the SDK's origin. Exercises admin.auth/admin.queries/admin.audit directly against
the live dev DB (the security contract), plus end-to-end checks through the FastAPI app.
docs/26-PHASE-6-ADMIN.md GATE 6.
"""

from __future__ import annotations

import datetime
import json
import sys
import uuid
from pathlib import Path

import pytest

try:
    import jwt as pyjwt
    import psycopg
except ImportError:  # pragma: no cover
    pytest.skip("psycopg/pyjwt not installed", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from admin.auth import (  # noqa: E402
    ADMIN_JWT_AUDIENCE,
    ADMIN_JWT_ISSUER,
    AdminAuthError,
    login,
    provision_admin,
    verify_admin_jwt,
)
from admin.security import (  # noqa: E402
    hash_password,
    random_base32_secret,
    totp_now,
    totp_verify,
    verify_password,
)
from admin import queries  # noqa: E402
from admin.audit import record_admin_action, record_mint_rejection  # noqa: E402
from control_plane.secrets import secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402

ADMIN_SECRET = "admin-jwt-test-secret-0123456789012345678901"  # >=32 bytes
LK_SECRET = (
    "livekit-tenant-secret-01234567890123456789012"  # a DIFFERENT secret, deliberately
)


def _kw():
    try:
        return conn_kwargs()
    except SystemExit:
        pytest.skip("SUPABASE_DB_URL not configured in .env.local")


@pytest.fixture
def env():
    conn = psycopg.connect(**_kw(), autocommit=True)
    email = f"test-admin-{uuid.uuid4()}@example.com"
    password = "correct horse battery staple 42"
    totp_secret = random_base32_secret()
    admin_id = provision_admin(
        conn, email=email, password=password, totp_secret=totp_secret
    )

    t = str(uuid.uuid4())
    ag = str(uuid.uuid4())
    sess = str(uuid.uuid4())
    conn.execute(
        "insert into tenants (id, name, hmac_secret_hash, max_concurrent, max_minutes_month) "
        "values (%s,'admin-test',%s,2,100)",
        (t, secret_hash("x")),
    )
    conn.execute(
        "insert into agents (id, tenant_id, name, prompt, voice_id) "
        "values (%s,%s,'ag','p','v_meklc281')",
        (ag, t),
    )
    conn.execute(
        "insert into sessions (id, tenant_id, agent_id, room_name, ended_at, duration_sec, end_reason) "
        "values (%s,%s,%s,%s, now(), 65, 'normal')",
        (sess, t, ag, f"admin-test-room-{uuid.uuid4()}"),
    )
    conn.execute(
        "insert into usage_events (tenant_id, session_id, kind, qty) values (%s,%s,'agent_sec',65)",
        (t, sess),
    )
    conn.execute(
        "insert into quota_state (tenant_id, concurrent_now, minutes_this_month) values (%s,1,5)",
        (t,),
    )

    data = {
        "conn": conn,
        "admin_id": admin_id,
        "email": email,
        "password": password,
        "totp_secret": totp_secret,
        "tenant_id": t,
        "agent_id": ag,
        "session_id": sess,
    }
    yield data

    for tab in ("mint_rejections",):
        conn.execute(f"delete from {tab} where tenant_id = %s", (t,))
    for tab in ("usage_events", "sessions", "quota_state", "agents"):
        conn.execute(f"delete from {tab} where tenant_id = %s", (t,))
    conn.execute("delete from tenants where id = %s", (t,))
    conn.execute("delete from admin_audit_log where admin_id = %s", (admin_id,))
    conn.execute("delete from admin_users where id = %s", (admin_id,))
    conn.close()


# --- P6-T01: auth is separate, MFA required, JWTs are cryptographically/structurally distinct ---


def test_login_wrong_password_401(env):
    with pytest.raises(AdminAuthError) as e:
        login(
            env["conn"],
            email=env["email"],
            password="wrong",
            totp_code=totp_now(env["totp_secret"]),
            jwt_secret=ADMIN_SECRET,
        )
    assert e.value.status == 401


def test_login_wrong_totp_401(env):
    with pytest.raises(AdminAuthError) as e:
        login(
            env["conn"],
            email=env["email"],
            password=env["password"],
            totp_code="000000",
            jwt_secret=ADMIN_SECRET,
        )
    assert e.value.status == 401


def test_login_unknown_email_401(env):
    with pytest.raises(AdminAuthError) as e:
        login(
            env["conn"],
            email="nobody@example.com",
            password="x",
            totp_code="000000",
            jwt_secret=ADMIN_SECRET,
        )
    assert e.value.status == 401


def test_login_success_returns_verifiable_token(env):
    res = login(
        env["conn"],
        email=env["email"],
        password=env["password"],
        totp_code=totp_now(env["totp_secret"]),
        jwt_secret=ADMIN_SECRET,
    )
    assert res["admin_id"] == env["admin_id"]
    claims = verify_admin_jwt(res["token"], ADMIN_SECRET)
    assert claims["sub"] == env["admin_id"]
    assert claims["aud"] == ADMIN_JWT_AUDIENCE


def test_totp_is_mandatory_not_optional(env):
    """admin_users.totp_secret is NOT NULL at the schema level; a row cannot exist without one."""
    row = (
        env["conn"]
        .execute(
            "select totp_secret from admin_users where id = %s", (env["admin_id"],)
        )
        .fetchone()
    )
    assert row[0]  # non-empty


def test_password_hash_is_pbkdf2_not_plaintext(env):
    row = (
        env["conn"]
        .execute(
            "select password_hash from admin_users where id = %s", (env["admin_id"],)
        )
        .fetchone()
    )
    assert row[0].startswith("pbkdf2_sha256$")
    assert env["password"] not in row[0]


def test_totp_verify_rejects_stale_code_outside_window(env):
    old_code = totp_now(
        env["totp_secret"], at=datetime.datetime.now().timestamp() - 600
    )
    assert totp_verify(env["totp_secret"], old_code) is False


def test_password_verify_helper_roundtrip():
    h = hash_password("hunter2-but-longer")
    assert verify_password("hunter2-but-longer", h)
    assert not verify_password("wrong", h)


def test_admin_jwt_cannot_be_used_as_a_tenant_jwt(env):
    """GATE 6 line 2, direction A: an admin token, handed to code expecting a LiveKit tenant
    token (verified with LIVEKIT_API_SECRET, no audience/issuer constraint — the real shape
    control_plane never checks 'aud' at all, it trusts the LiveKit SDK's own verification), fails
    signature verification because it was signed with a DIFFERENT secret."""
    res = login(
        env["conn"],
        email=env["email"],
        password=env["password"],
        totp_code=totp_now(env["totp_secret"]),
        jwt_secret=ADMIN_SECRET,
    )
    with pytest.raises(pyjwt.PyJWTError):
        pyjwt.decode(res["token"], LK_SECRET, algorithms=["HS256"])


def test_tenant_jwt_cannot_be_used_as_an_admin_jwt(env):
    """GATE 6 line 2, direction B: a real LiveKit AccessToken (control_plane/mint.py's exact
    shape: iss=<api key>, video grants, no aud) is rejected by verify_admin_jwt — both because
    it's signed with a different secret AND because it lacks aud='admin-portal'/carries `video`."""
    from livekit import api

    tenant_token = (
        api.AccessToken("devkey", LK_SECRET)
        .with_identity(str(uuid.uuid4()))
        .with_ttl(datetime.timedelta(seconds=120))
        .with_metadata(json.dumps({"tenant_id": env["tenant_id"]}))
        .with_grants(
            api.VideoGrants(
                room_join=True, room="r1", can_publish=True, can_subscribe=True
            )
        )
        .to_jwt()
    )
    with pytest.raises(AdminAuthError) as e:
        verify_admin_jwt(tenant_token, ADMIN_SECRET)
    assert e.value.status == 401
    # even granting (unrealistically) that the secrets happened to match, the structural check
    # (no `video` grants allowed in an admin token) still rejects it:
    same_secret_tenant_token = (
        api.AccessToken("devkey", ADMIN_SECRET)
        .with_identity(str(uuid.uuid4()))
        .with_ttl(datetime.timedelta(seconds=120))
        .with_grants(api.VideoGrants(room_join=True, room="r1"))
        .to_jwt()
    )
    with pytest.raises(AdminAuthError):
        verify_admin_jwt(same_secret_tenant_token, ADMIN_SECRET)


def test_forged_admin_jwt_wrong_secret_rejected():
    forged = pyjwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": ADMIN_JWT_AUDIENCE,
            "iss": ADMIN_JWT_ISSUER,
            "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
        },
        "totally-wrong-secret-guessed-by-an-attacker-0000",
        algorithm="HS256",
    )
    with pytest.raises(AdminAuthError):
        verify_admin_jwt(forged, ADMIN_SECRET)


# --- P6-T02..T05: every dashboard number is a real SQL query (GATE 6 line 1) ---


def test_list_tenants_matches_live_row(env):
    rows = queries.list_tenants(env["conn"])
    row = next(r for r in rows if r["id"] == env["tenant_id"])
    assert row["concurrent_now"] == 1
    assert row["minutes_this_month"] == 5.0


def test_list_agents_rolls_up_real_usage_events(env):
    rows = queries.list_agents(env["conn"])
    row = next(r for r in rows if r["id"] == env["agent_id"])
    assert row["total_agent_sec"] == 65.0
    assert row["tenant_id"] == env["tenant_id"]


def test_list_sessions_scoped_to_tenant(env):
    rows = queries.list_sessions(env["conn"], tenant_id=env["tenant_id"])
    assert len(rows) == 1
    assert rows[0]["id"] == env["session_id"]
    assert rows[0]["duration_sec"] == 65
    assert rows[0]["live"] is False


def test_usage_aggregation_equals_raw_sql_over_usage_events(env):
    """GATE 6 line 1, literally: independently re-aggregate usage_events by hand and assert the
    admin.queries function returns the identical number — not a re-implementation that could
    silently diverge, a direct comparison."""
    raw = (
        env["conn"]
        .execute(
            "select sum(qty) from usage_events where tenant_id = %s and kind = 'agent_sec'",
            (env["tenant_id"],),
        )
        .fetchone()[0]
    )
    rows = queries.usage_by_tenant_day_kind(env["conn"])
    row = next(
        r
        for r in rows
        if r["tenant_id"] == env["tenant_id"] and r["kind"] == "agent_sec"
    )
    assert row["total_qty"] == float(raw)


def test_usage_cost_estimate_uses_the_one_published_figure(env):
    rows = queries.usage_by_tenant_day_kind(env["conn"])
    row = next(
        r
        for r in rows
        if r["tenant_id"] == env["tenant_id"] and r["kind"] == "agent_sec"
    )
    expected = round((65.0 / 60.0) * 0.0044, 6)
    assert row["cost_usd"] == expected


def test_usage_cost_not_invented_for_unpublished_kinds(env):
    """stt_sec/tts_sec/llm_tokens have no published $/unit anywhere in 10-SPEC.md — cost_usd must
    be None for them, never a made-up number (anti-hallucination rule 8.3)."""
    env["conn"].execute(
        "insert into usage_events (tenant_id, session_id, kind, qty) values (%s,%s,'stt_sec',10)",
        (env["tenant_id"], env["session_id"]),
    )
    rows = queries.usage_by_tenant_day_kind(env["conn"])
    row = next(
        r for r in rows if r["tenant_id"] == env["tenant_id"] and r["kind"] == "stt_sec"
    )
    assert row["cost_usd"] is None


def test_quota_near_cap_flags_tenant_over_threshold(env):
    rows = queries.quota_near_cap(
        env["conn"], threshold=0.4
    )  # 1/2 concurrent = 0.5 >= 0.4
    assert any(r["tenant_id"] == env["tenant_id"] for r in rows)


def test_quota_near_cap_excludes_tenant_under_threshold(env):
    rows = queries.quota_near_cap(env["conn"], threshold=0.99)
    assert not any(r["tenant_id"] == env["tenant_id"] for r in rows)


def test_live_concurrency_reflects_quota_state(env):
    data = queries.live_concurrency(env["conn"])
    assert data["total_concurrent_now"] >= 1
    assert (
        "UNVERIFIED-BY-US" in data["livekit_cap_note"]
    )  # ADR-014 honesty check, not a number we invented


def test_blockers_view_reflects_real_mint_rejection(env):
    record_mint_rejection(env["tenant_id"], 429, "concurrent cap reached")
    rows = queries.blockers(env["conn"])
    row = next(
        r for r in rows if r["tenant_id"] == env["tenant_id"] and r["status"] == 429
    )
    assert row["count"] >= 1


def test_blockers_view_records_unknown_tenant_as_null_not_a_crash(env):
    """An unknown-tenant 401 (control_plane/mint.py raises before any tenant row is confirmed to
    exist) must still be logged — with a NULL tenant_id, not silently dropped or crashing."""
    record_mint_rejection("not-a-valid-uuid", 401, "unknown tenant")
    rows = (
        env["conn"]
        .execute(
            "select count(*) from mint_rejections where tenant_id is null and reason = 'unknown tenant'"
        )
        .fetchone()
    )
    assert rows[0] >= 1


# --- P6-T06: every admin action writes an audit log row (GATE 6 line 3) ---


def test_admin_action_writes_audit_log(env):
    before = (
        env["conn"]
        .execute(
            "select count(*) from admin_audit_log where admin_id = %s",
            (env["admin_id"],),
        )
        .fetchone()[0]
    )
    record_admin_action(
        env["conn"], admin_id=env["admin_id"], action="list_tenants", detail={"x": 1}
    )
    env["conn"].commit() if hasattr(env["conn"], "commit") else None
    after = (
        env["conn"]
        .execute(
            "select count(*) from admin_audit_log where admin_id = %s",
            (env["admin_id"],),
        )
        .fetchone()[0]
    )
    assert after == before + 1


# --- end-to-end through the FastAPI app ---


def test_endpoint_requires_auth_and_logs_action(env, monkeypatch):
    from fastapi.testclient import TestClient

    from admin import app as admin_app_module

    monkeypatch.setattr(admin_app_module, "ADMIN_JWT_SECRET", ADMIN_SECRET)
    client = TestClient(admin_app_module.app)

    no_auth = client.get("/admin/tenants")
    assert no_auth.status_code == 401

    login_res = client.post(
        "/admin/login",
        json={
            "email": env["email"],
            "password": env["password"],
            "totp_code": totp_now(env["totp_secret"]),
        },
    )
    assert login_res.status_code == 200
    token = login_res.json()["token"]

    before = (
        env["conn"]
        .execute(
            "select count(*) from admin_audit_log where admin_id = %s and action = 'list_tenants'",
            (env["admin_id"],),
        )
        .fetchone()[0]
    )

    ok = client.get("/admin/tenants", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert any(t["id"] == env["tenant_id"] for t in ok.json())

    after = (
        env["conn"]
        .execute(
            "select count(*) from admin_audit_log where admin_id = %s and action = 'list_tenants'",
            (env["admin_id"],),
        )
        .fetchone()[0]
    )
    assert after == before + 1  # GATE 6 line 3, through the real HTTP path


def test_endpoint_rejects_a_real_tenant_jwt(env, monkeypatch):
    """GATE 6 line 2, end-to-end: hit a protected admin route with a real LiveKit tenant token."""
    from fastapi.testclient import TestClient
    from livekit import api

    from admin import app as admin_app_module

    monkeypatch.setattr(admin_app_module, "ADMIN_JWT_SECRET", ADMIN_SECRET)
    client = TestClient(admin_app_module.app)

    tenant_token = (
        api.AccessToken("devkey", LK_SECRET)
        .with_identity(str(uuid.uuid4()))
        .with_ttl(datetime.timedelta(seconds=120))
        .with_grants(api.VideoGrants(room_join=True, room="r1"))
        .to_jwt()
    )
    r = client.get(
        "/admin/tenants", headers={"Authorization": f"Bearer {tenant_token}"}
    )
    assert r.status_code == 401


def test_cors_does_not_echo_an_arbitrary_tenant_origin(monkeypatch):
    """GATE 6 line 4 (partial, machine-checkable half): the admin app's CORS policy is a fixed
    allowlist that never reflects an arbitrary Origin header, so a tenant/host-platform page
    embedding the SDK could not read a response even if it somehow discovered this API's URL."""
    from fastapi.testclient import TestClient

    from admin import app as admin_app_module

    client = TestClient(admin_app_module.app)
    r = client.get(
        "/admin/tenants",
        headers={"Origin": "https://some-tenant-host-platform.example"},
    )
    assert r.headers.get("access-control-allow-origin") is None


def test_sdk_bundle_never_references_admin():
    """GATE 6 line 4 (the other half): the SDK's source/dist never names anything under admin/,
    so no tenant-facing code path can even discover the portal's existence."""
    root = Path(__file__).resolve().parent.parent
    hits = []
    for sub in ("sdk/src", "sdk/dist"):
        d = root / sub
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if f.is_file() and f.suffix in (".ts", ".tsx", ".js", ".d.ts"):
                text = f.read_text(encoding="utf-8", errors="ignore")
                if "/admin/" in text or "admin_" in text:
                    hits.append(str(f))
    assert hits == []


def test_sdk_bundle_never_references_agents_server():
    """The browser SDK (@awaazlabs-uva/voice) must never reference the server-only @awaazlabs-uva/agents package —
    that package holds the tenant HMAC secret, and importing it into a browser bundle would leak
    it. Mirrors test_sdk_bundle_never_references_admin's isolation check."""
    root = Path(__file__).resolve().parent.parent
    hits = []
    for sub in ("sdk/src", "sdk/dist"):
        d = root / sub
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if f.is_file() and f.suffix in (".ts", ".tsx", ".js", ".d.ts"):
                text = f.read_text(encoding="utf-8", errors="ignore")
                if (
                    "sdk-server" in text
                    or "@awaazlabs-uva/agents" in text
                    or "@uva/agents" in text
                    or "AwaazLabsUvaAgentsClient" in text
                    or "UvaAgentsClient" in text
                ):
                    hits.append(str(f))
    assert hits == []
