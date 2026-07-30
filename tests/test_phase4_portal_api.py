from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane.secrets import secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402
from tenant_portal_api.app import app  # noqa: E402


def _seed_portal_tenant():
    tenant_id = str(uuid.uuid4())
    secret = f"tenant-secret-{uuid.uuid4()}"
    voice_id = f"voice-{uuid.uuid4()}"
    agent_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
        conn.execute(
            """
            insert into voices (id, display_name, enabled)
            values (%s, 'Portal Test Voice', true)
            on conflict (id) do nothing
            """,
            (voice_id,),
        )
        conn.execute(
            """
            insert into tenants (id, name, hmac_secret, hmac_secret_hash, status, allowed_origins)
            values (%s, 'Portal Test Tenant', %s, %s, 'active', array['http://localhost:3000'])
            """,
            (tenant_id, secret, secret_hash(secret)),
        )
        conn.execute(
            """
            insert into quota_state (tenant_id, concurrent_now, minutes_this_month)
            values (%s, 1, 12)
            """,
            (tenant_id,),
        )
        conn.execute(
            """
            insert into agents (id, tenant_id, name, prompt, voice_id, llm_model)
            values (%s, %s, 'Mahnoor', 'Helpful prompt', %s, 'gemini-2.5-flash')
            """,
            (agent_id, tenant_id, voice_id),
        )
        conn.execute(
            """
            insert into sessions (id, tenant_id, agent_id, room_name, duration_sec, end_reason, ended_at)
            values (%s, %s, %s, %s, 31, 'normal', now())
            """,
            (session_id, tenant_id, agent_id, f"room-{uuid.uuid4()}"),
        )
        conn.execute(
            """
            insert into usage_events (tenant_id, session_id, kind, qty)
            values
            (%s, %s, 'agent_sec', 31),
            (%s, %s, 'stt_sec', 7)
            """,
            (tenant_id, session_id, tenant_id, session_id),
        )
    return tenant_id, secret, voice_id, agent_id


def _cleanup_portal_tenant(tenant_id: str, voice_id: str):
    with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
        conn.execute("delete from usage_events where tenant_id = %s", (tenant_id,))
        conn.execute("delete from sessions where tenant_id = %s", (tenant_id,))
        conn.execute("delete from quota_state where tenant_id = %s", (tenant_id,))
        conn.execute("delete from tenants where id = %s", (tenant_id,))
        conn.execute("delete from voices where id = %s", (voice_id,))


def test_portal_login_and_scoped_routes():
    tenant_id, secret, voice_id, agent_id = _seed_portal_tenant()
    client = TestClient(app)

    try:
        login = client.post(
            "/portal/login", json={"tenant_id": tenant_id, "tenant_secret": secret}
        )
        assert login.status_code == 200
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        agents = client.get("/portal/agents", headers=headers)
        assert agents.status_code == 200
        data = agents.json()
        assert len(data) == 1
        assert data[0]["id"] == agent_id

        creds = client.get("/portal/credentials", headers=headers)
        assert creds.status_code == 200
        assert creds.json()["tenant_id"] == tenant_id
        assert creds.json()["publishable_key"] == tenant_id

        sessions = client.get("/portal/sessions", headers=headers)
        assert sessions.status_code == 200
        assert len(sessions.json()) == 1

        usage = client.get("/portal/usage-summary", headers=headers)
        assert usage.status_code == 200
        usage_json = usage.json()
        assert usage_json["quota"]["minutes_this_month"] == 12.0
        assert any(row["kind"] == "agent_sec" for row in usage_json["totals"])

        # Calendar-month bounds, not a rolling "last N days" window (regression: this endpoint
        # used to take ?days=30 and had no notion of a calendar month at all).
        today = date.today()
        assert usage_json["period_start"] == today.replace(day=1).isoformat()
        next_month = today.replace(day=28) + timedelta(days=4)
        expected_end = next_month.replace(day=1)
        assert usage_json["period_end"] == expected_end.isoformat()
        # the seeded session's usage_events row (inserted `now()` above) must fall inside it
        assert (
            usage_json["period_start"] <= today.isoformat() < usage_json["period_end"]
        )
    finally:
        _cleanup_portal_tenant(tenant_id, voice_id)


def test_portal_credentials_secret_reveal():
    """The credentials-tab 'view/copy HMAC secret' action returns the tenant's OWN raw secret.

    Scoped by claims["sub"] from the caller's own verified portal JWT — same boundary as every
    other /portal/* route, just returning the real value instead of get_credentials' masked one.
    """
    tenant_id, secret, voice_id, _ = _seed_portal_tenant()
    client = TestClient(app)

    try:
        login = client.post(
            "/portal/login", json={"tenant_id": tenant_id, "tenant_secret": secret}
        )
        token = login.json()["token"]

        revealed = client.get(
            "/portal/credentials/secret", headers={"Authorization": f"Bearer {token}"}
        )
        assert revealed.status_code == 200
        assert revealed.json()["hmac_secret"] == secret

        no_auth = client.get("/portal/credentials/secret")
        assert no_auth.status_code == 401
    finally:
        _cleanup_portal_tenant(tenant_id, voice_id)


def test_stale_open_session_is_not_reported_live():
    """An open session past the staleness bound must NOT read as live.

    Regression: the dashboard showed "13 live calls" for a tenant whose oldest open session was
    96 hours old. `sessions` rows are opened by the mint and closed only by worker/main.py's
    shutdown callback, so any ungraceful worker exit leaks a row with ended_at IS NULL forever.
    `live` used to be exactly `ended_at is None`, which reported every leaked row as an active
    call. Asserts all three states off ONE query, so a regression in any direction fails.
    """
    tenant_id, secret, voice_id, agent_id = _seed_portal_tenant()
    fresh_id, stale_id = str(uuid.uuid4()), str(uuid.uuid4())

    with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
        # open, started 2 min ago -> genuinely live
        conn.execute(
            """
            insert into sessions (id, tenant_id, agent_id, room_name, started_at)
            values (%s, %s, %s, %s, now() - interval '2 minutes')
            """,
            (fresh_id, tenant_id, agent_id, f"room-{uuid.uuid4()}"),
        )
        # open, started 96 h ago -> leaked, must not be live (the exact production shape)
        conn.execute(
            """
            insert into sessions (id, tenant_id, agent_id, room_name, started_at)
            values (%s, %s, %s, %s, now() - interval '96 hours')
            """,
            (stale_id, tenant_id, agent_id, f"room-{uuid.uuid4()}"),
        )

    client = TestClient(app)
    try:
        login = client.post(
            "/portal/login", json={"tenant_id": tenant_id, "tenant_secret": secret}
        )
        token = login.json()["token"]
        rows = client.get(
            "/portal/sessions", headers={"Authorization": f"Bearer {token}"}
        )
        assert rows.status_code == 200
        by_id = {r["id"]: r for r in rows.json()}

        fresh = by_id[fresh_id]
        assert fresh["live"] is True, "a 2-minute-old open session must be live"
        assert fresh["stale"] is False

        stale = by_id[stale_id]
        assert stale["live"] is False, "a 96-hour-old open session must NOT be live"
        assert stale["stale"] is True, (
            "it must be surfaced as stale, not silently 'ended'"
        )

        # the pre-seeded cleanly-ended session is neither live nor stale
        ended = next(r for r in by_id.values() if r["ended_at"] is not None)
        assert ended["live"] is False
        assert ended["stale"] is False

        # and the count the Overview card renders is now 1, not 2
        assert sum(1 for r in by_id.values() if r["live"]) == 1
    finally:
        _cleanup_portal_tenant(tenant_id, voice_id)


def test_portal_create_and_update_agent():
    tenant_id, secret, voice_id, _ = _seed_portal_tenant()
    client = TestClient(app)

    try:
        login = client.post(
            "/portal/login", json={"tenant_id": tenant_id, "tenant_secret": secret}
        )
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        created = client.post(
            "/portal/agents",
            headers=headers,
            json={
                "name": "Support Agent",
                "prompt": "Answer politely",
                "voice_id": voice_id,
                "llm_model": "gemini-2.5-flash",
            },
        )
        assert created.status_code == 200
        created_json = created.json()
        assert created_json["name"] == "Support Agent"

        updated = client.patch(
            f"/portal/agents/{created_json['id']}",
            headers=headers,
            json={"name": "Updated Support Agent"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Updated Support Agent"
    finally:
        _cleanup_portal_tenant(tenant_id, voice_id)
