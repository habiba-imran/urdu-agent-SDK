from __future__ import annotations

import sys
import uuid
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane.secrets import secret_hash
from dbconn import conn_kwargs
from tenant_portal_api.app import app


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
