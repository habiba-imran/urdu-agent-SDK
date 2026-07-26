"""GATE — machine-auth agent management for existing tenants must reject every listed failure
mode and must reach the exact same tenant-scoped queries.* functions the JWT-authenticated
/portal/agents routes already use. Mirrors tests/test_mint.py's gate discipline for the analogous
HMAC-signed surface, and reuses tests/test_phase4_portal_api.py's tenant-seeding shape.

docs/MACHINE_AGENT_API_CONTRACT.md is the contract this file exercises.
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane.secrets import secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402
from tenant_portal_api import machine_auth  # noqa: E402
from tenant_portal_api.app import app  # noqa: E402
from tenant_portal_api.machine_auth import expected_signature, payload_hash  # noqa: E402


def _kw():
    try:
        return conn_kwargs()
    except SystemExit:
        pytest.skip("SUPABASE_DB_URL not configured in .env.local")


def _seed_machine_tenant():
    tenant_id = str(uuid.uuid4())
    secret = f"machine-secret-{uuid.uuid4()}"
    voice_id = f"voice-{uuid.uuid4()}"
    agent_id = str(uuid.uuid4())

    with psycopg.connect(**_kw(), autocommit=True) as conn:
        conn.execute(
            "insert into voices (id, display_name, enabled) values (%s, 'Machine Test Voice', true) "
            "on conflict (id) do nothing",
            (voice_id,),
        )
        conn.execute(
            "insert into tenants (id, name, hmac_secret, hmac_secret_hash, status, allowed_origins) "
            "values (%s, 'Machine Test Tenant', %s, %s, 'active', '{}')",
            (tenant_id, secret, secret_hash(secret)),
        )
        conn.execute(
            "insert into agents (id, tenant_id, name, prompt, voice_id, llm_model) "
            "values (%s, %s, 'Mahnoor', 'Helpful prompt', %s, 'gemini-2.5-flash')",
            (agent_id, tenant_id, voice_id),
        )
    return tenant_id, secret, voice_id, agent_id


def _cleanup_machine_tenant(tenant_id: str, voice_id: str):
    with psycopg.connect(**_kw(), autocommit=True) as conn:
        conn.execute("delete from used_nonces where tenant_id = %s", (tenant_id,))
        conn.execute("delete from agents where tenant_id = %s", (tenant_id,))
        conn.execute("delete from quota_state where tenant_id = %s", (tenant_id,))
        conn.execute("delete from tenants where id = %s", (tenant_id,))
        conn.execute("delete from voices where id = %s", (voice_id,))


@pytest.fixture
def env():
    tenant_id, secret, voice_id, agent_id = _seed_machine_tenant()
    machine_auth._hits.pop(
        tenant_id, None
    )  # isolate the in-memory rate limiter across tests
    yield {
        "tenant_id": tenant_id,
        "secret": secret,
        "voice_id": voice_id,
        "agent_id": agent_id,
    }
    _cleanup_machine_tenant(tenant_id, voice_id)
    machine_auth._hits.pop(tenant_id, None)


def _headers(*, tenant_id, secret, action, body, ts=None, nonce=None, signature=None):
    ts = ts if ts is not None else str(int(time.time()))
    nonce = nonce or str(uuid.uuid4())
    sig = (
        signature
        if signature is not None
        else expected_signature(
            secret, tenant_id, ts, nonce, action, payload_hash(body)
        )
    )
    return {
        "X-Tenant-Id": tenant_id,
        "X-Timestamp": ts,
        "X-Nonce": nonce,
        "X-Signature": sig,
    }


def test_happy_path_create_agent(env):
    client = TestClient(app)
    body = {
        "name": "Support Agent",
        "prompt": "Answer politely",
        "voice_id": env["voice_id"],
        "llm_model": "gemini-2.5-flash",
    }
    headers = _headers(
        tenant_id=env["tenant_id"],
        secret=env["secret"],
        action="agent.create",
        body=body,
    )
    res = client.post("/machine/agents", json=body, headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Support Agent"


def test_happy_path_list_agents(env):
    client = TestClient(app)
    headers = _headers(
        tenant_id=env["tenant_id"], secret=env["secret"], action="agent.list", body={}
    )
    res = client.get("/machine/agents", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["id"] == env["agent_id"]


def test_happy_path_update_agent(env):
    client = TestClient(app)
    body = {"name": "Renamed Agent"}
    headers = _headers(
        tenant_id=env["tenant_id"],
        secret=env["secret"],
        action="agent.update",
        body=body,
    )
    res = client.patch(f"/machine/agents/{env['agent_id']}", json=body, headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Renamed Agent"


def test_wrong_signature_401(env):
    client = TestClient(app)
    body = {
        "name": "X",
        "prompt": "p",
        "voice_id": env["voice_id"],
        "llm_model": "gemini-2.5-flash",
    }
    headers = _headers(
        tenant_id=env["tenant_id"],
        secret=env["secret"],
        action="agent.create",
        body=body,
        signature="deadbeef",
    )
    res = client.post("/machine/agents", json=body, headers=headers)
    assert res.status_code == 401


def test_timestamp_outside_window_401(env):
    client = TestClient(app)
    old_ts = str(int(time.time()) - 61)
    headers = _headers(
        tenant_id=env["tenant_id"],
        secret=env["secret"],
        action="agent.list",
        body={},
        ts=old_ts,
    )
    res = client.get("/machine/agents", headers=headers)
    assert res.status_code == 401


def test_nonce_replay_401(env):
    client = TestClient(app)
    nonce = str(uuid.uuid4())
    headers = _headers(
        tenant_id=env["tenant_id"],
        secret=env["secret"],
        action="agent.list",
        body={},
        nonce=nonce,
    )
    first = client.get("/machine/agents", headers=headers)
    assert first.status_code == 200
    second = client.get("/machine/agents", headers=headers)
    assert second.status_code == 401


def test_tampered_body_after_signing_401(env):
    """Signature is bound to the payload hash — changing the body after signing must invalidate it,
    proving a captured request can't be replayed with a different prompt/voice/model."""
    client = TestClient(app)
    signed_body = {
        "name": "X",
        "prompt": "original prompt",
        "voice_id": env["voice_id"],
        "llm_model": "gemini-2.5-flash",
    }
    headers = _headers(
        tenant_id=env["tenant_id"],
        secret=env["secret"],
        action="agent.create",
        body=signed_body,
    )
    tampered_body = dict(signed_body, prompt="a completely different prompt")
    res = client.post("/machine/agents", json=tampered_body, headers=headers)
    assert res.status_code == 401


def test_suspended_tenant_403(env):
    with psycopg.connect(**_kw(), autocommit=True) as conn:
        conn.execute(
            "update tenants set status = 'suspended' where id = %s", (env["tenant_id"],)
        )
    client = TestClient(app)
    headers = _headers(
        tenant_id=env["tenant_id"], secret=env["secret"], action="agent.list", body={}
    )
    res = client.get("/machine/agents", headers=headers)
    assert res.status_code == 403


def test_update_agent_of_another_tenant_404_idor(env):
    other_tenant_id, other_secret, other_voice_id, _ = _seed_machine_tenant()
    machine_auth._hits.pop(other_tenant_id, None)
    try:
        client = TestClient(app)
        body = {"name": "Hijacked"}
        headers = _headers(
            tenant_id=env["tenant_id"],
            secret=env["secret"],
            action="agent.update",
            body=body,
        )
        # env's tenant signs a request but targets an agent belonging to the OTHER tenant
        res = client.patch(
            f"/machine/agents/{env['agent_id']}", json=body, headers=headers
        )
        assert res.status_code == 200  # sanity: env's own agent works

        cross_headers = _headers(
            tenant_id=other_tenant_id,
            secret=other_secret,
            action="agent.update",
            body=body,
        )
        cross = client.patch(
            f"/machine/agents/{env['agent_id']}", json=body, headers=cross_headers
        )
        assert cross.status_code == 404
    finally:
        _cleanup_machine_tenant(other_tenant_id, other_voice_id)
        machine_auth._hits.pop(other_tenant_id, None)


def test_rate_limited_429(env, monkeypatch):
    client = TestClient(app)
    fake_time = 1000000.0
    monkeypatch.setattr(time, "time", lambda: fake_time)
    last_status = None
    for _ in range(machine_auth.MACHINE_RATE_LIMIT_PER_MIN + 1):
        headers = _headers(
            tenant_id=env["tenant_id"],
            secret=env["secret"],
            action="agent.list",
            body={},
        )
        last_status = client.get("/machine/agents", headers=headers).status_code
    assert last_status == 429


def test_missing_headers_401(env):
    client = TestClient(app)
    res = client.get("/machine/agents")
    assert res.status_code == 401
