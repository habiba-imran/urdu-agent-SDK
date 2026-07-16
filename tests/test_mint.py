"""P2 GATE — the token mint must reject every listed failure mode and mint only scoped tokens.

Exercises control_plane.mint.mint_session directly against the live dev DB (the security contract),
plus one end-to-end check through the FastAPI endpoint. docs/22-PHASE-2-CONTROL-PLANE.md GATE 2.
"""

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

from control_plane.mint import TTL_SEC, MintError, expected_signature, mint_session  # noqa: E402
from control_plane.secrets import DictSecretProvider, secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402

LK_KEY = "devkey"
LK_SECRET = "devsecret0123456789012345678901234567"  # >=32 bytes
LK_URL = "wss://example.livekit.cloud"
SECRET = "tenant-A-hmac-secret"


def _kw():
    try:
        return conn_kwargs()
    except SystemExit:
        pytest.skip("SUPABASE_DB_URL not configured in .env.local")


@pytest.fixture
def env():
    conn = psycopg.connect(**_kw(), autocommit=True)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    ag_a, ag_b = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute(
        "insert into tenants (id, name, hmac_secret_hash, max_concurrent, max_minutes_month, allowed_origins) "
        "values (%s,'A',%s,2,100,%s), (%s,'B',%s,2,100,%s)",
        (a, secret_hash(SECRET), ["https://a.example"], b, secret_hash("b-secret"), []),
    )
    conn.execute(
        "insert into agents (id, tenant_id, name, prompt, voice_id) "
        "values (%s,%s,'ag','p','v_meklc281'), (%s,%s,'ag','p','v_meklc281')",
        (ag_a, a, ag_b, b),
    )
    data = {
        "conn": conn,
        "a": a,
        "b": b,
        "agent_a": ag_a,
        "agent_b": ag_b,
        "secrets": DictSecretProvider({a: SECRET, b: "b-secret"}),
    }
    yield data
    for t in ("used_nonces", "sessions", "quota_state", "agents"):
        conn.execute(f"delete from {t} where tenant_id in (%s, %s)", (a, b))
    conn.execute("delete from tenants where id in (%s, %s)", (a, b))
    conn.close()


def _req(
    env,
    *,
    tenant=None,
    agent=None,
    ts=None,
    nonce=None,
    secret=None,
    origin="https://a.example",
    sig=None,
):
    tenant = tenant or env["a"]
    agent = agent or env["agent_a"]
    ts = (
        ts
        if ts is not None
        else str(int(datetime.datetime.now(datetime.UTC).timestamp()))
    )
    nonce = nonce or str(uuid.uuid4())
    secret = secret or SECRET
    signature = (
        sig if sig is not None else expected_signature(secret, tenant, ts, nonce, agent)
    )
    return {
        "conn": env["conn"],
        "secrets": env["secrets"],
        "livekit_key": LK_KEY,
        "livekit_secret": LK_SECRET,
        "livekit_url": LK_URL,
        "tenant_id": tenant,
        "ts": ts,
        "nonce": nonce,
        "agent_id": agent,
        "signature": signature,
        "origin": origin,
    }


def _decode(token):
    return pyjwt.decode(
        token, LK_SECRET, algorithms=["HS256"], options={"verify_exp": False}
    )


def test_happy_path_mints_token_scoped_to_one_room(env):
    res = mint_session(**_req(env))
    assert res["roomName"] and res["token"] and res["wsUrl"] == LK_URL
    v = _decode(res["token"])["video"]
    assert v["roomJoin"] is True
    assert v["room"] == res["roomName"]  # bound to exactly the minted room, no other
    assert not v.get("roomAdmin") and not v.get("roomCreate") and not v.get("roomList")
    assert json.loads(_decode(res["token"])["metadata"])["tenant_id"] == env["a"]


def test_wrong_signature_401(env):
    with pytest.raises(MintError) as e:
        mint_session(**_req(env, sig="deadbeef"))
    assert e.value.status == 401


def test_timestamp_61s_old_401(env):
    old = str(int(datetime.datetime.now(datetime.UTC).timestamp()) - 61)
    with pytest.raises(MintError) as e:
        mint_session(**_req(env, ts=old))
    assert e.value.status == 401


def test_replayed_nonce_401(env):
    n = str(uuid.uuid4())
    mint_session(**_req(env, nonce=n))  # first use succeeds
    with pytest.raises(MintError) as e:
        mint_session(**_req(env, nonce=n))
    assert e.value.status == 401


def test_agent_of_another_tenant_403_idor(env):
    with pytest.raises(MintError) as e:
        mint_session(**_req(env, agent=env["agent_b"]))
    assert e.value.status == 403


def test_suspended_tenant_403(env):
    env["conn"].execute(
        "update tenants set status='suspended' where id=%s", (env["a"],)
    )
    with pytest.raises(MintError) as e:
        mint_session(**_req(env))
    assert e.value.status == 403


def test_over_concurrent_cap_429(env):
    env["conn"].execute(
        "insert into quota_state (tenant_id, concurrent_now) values (%s, 2) "
        "on conflict (tenant_id) do update set concurrent_now = 2",
        (env["a"],),
    )
    with pytest.raises(MintError) as e:
        mint_session(**_req(env))
    assert e.value.status == 429


def test_over_monthly_minutes_429(env):
    env["conn"].execute(
        "insert into quota_state (tenant_id, minutes_this_month) values (%s, 100) "
        "on conflict (tenant_id) do update set minutes_this_month = 100",
        (env["a"],),
    )
    with pytest.raises(MintError) as e:
        mint_session(**_req(env))
    assert e.value.status == 429


def test_wrong_origin_403(env):
    with pytest.raises(MintError) as e:
        mint_session(**_req(env, origin="https://evil.example"))
    assert e.value.status == 403


def test_token_expires_at_120s(env):
    claims = _decode(mint_session(**_req(env))["token"])
    start = claims.get("nbf", claims.get("iat"))
    assert start is not None
    assert claims["exp"] - start == TTL_SEC == 120


def test_endpoint_maps_success_and_bad_signature(env, monkeypatch):
    from fastapi.testclient import TestClient

    from control_plane import app as app_module

    monkeypatch.setattr(app_module, "_secrets", env["secrets"])
    monkeypatch.setattr(app_module, "_LK_KEY", LK_KEY)
    monkeypatch.setattr(app_module, "_LK_SECRET", LK_SECRET)
    monkeypatch.setattr(app_module, "_LK_URL", LK_URL)
    client = TestClient(app_module.app)

    ts = str(int(datetime.datetime.now(datetime.UTC).timestamp()))
    nonce = str(uuid.uuid4())
    sig = expected_signature(SECRET, env["a"], ts, nonce, env["agent_a"])
    headers = {
        "X-Tenant-Id": env["a"],
        "X-Timestamp": ts,
        "X-Nonce": nonce,
        "X-Signature": sig,
        "Origin": "https://a.example",
    }
    ok = client.post("/v1/session", json={"agent_id": env["agent_a"]}, headers=headers)
    assert ok.status_code == 200 and ok.json()["roomName"]

    headers["X-Signature"] = "bad"
    headers["X-Nonce"] = str(uuid.uuid4())
    bad = client.post("/v1/session", json={"agent_id": env["agent_a"]}, headers=headers)
    assert bad.status_code == 401
