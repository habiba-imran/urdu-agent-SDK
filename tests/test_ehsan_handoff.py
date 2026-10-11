"""Ehsan handoff regressions. Local fakes exercise actual auth and route boundaries."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from tenant_portal_api import machine_auth
from worker.tools import AgentUserdata
from worker.write_tool_gate import (
    is_affirmative_utterance,
    note_user_turn,
    set_verified_caller_phone,
)

PORTAL = importlib.import_module("tenant_portal_api.app")
TENANT = "11111111-2222-3333-4444-555555555555"
SECRET = "test-only-handoff-secret"


class Conn:
    def __init__(self):
        self.nonces = set()
        self.row = None
        self.status = "active"

    def execute(self, query, values=()):
        if query.startswith("select status from tenants"):
            self.row = (self.status,) if values[0] == TENANT else None
        elif query.startswith("insert into used_nonces"):
            if values in self.nonces:
                raise psycopg.errors.UniqueViolation("fixture duplicate nonce")
            self.nonces.add(values)
            self.row = None
        elif "count(*) from agents" in query:
            self.row = (0,)
        else:
            raise AssertionError("unexpected database query: " + query)
        return self

    def fetchone(self):
        return self.row

    def commit(self):
        pass


@pytest.fixture
def portal(monkeypatch):
    conn = Conn()

    @contextmanager
    def checkout(**kwargs):
        yield conn

    monkeypatch.setattr(PORTAL, "_conn", checkout)
    monkeypatch.setattr(
        PORTAL,
        "_machine_secrets",
        type("Secrets", (), {"get": lambda self, tenant: SECRET})(),
    )
    machine_auth._hits.clear()
    monkeypatch.setattr(
        PORTAL,
        "_resolve_provider_fields",
        lambda *a, **k: {
            "voice_id": "fixture",
            "llm_model": "existing",
            "agent_language": "ur",
            "stt_provider": "gladia",
            "stt_model": "default",
            "stt_options": {},
            "llm_provider": "gemini",
            "llm_options": {},
            "tts_provider": "uplift",
            "tts_voice_id": "fixture",
            "tts_options": {},
        },
    )
    monkeypatch.setattr(
        PORTAL.queries, "create_agent", lambda conn, tenant, **kw: {"id": "agent", **kw}
    )
    monkeypatch.setattr(PORTAL.queries, "get_agent", lambda *a: {"id": "agent"})
    monkeypatch.setattr(
        PORTAL.queries,
        "update_agent",
        lambda conn, tenant, aid, **kw: {"id": aid, "name": kw["name"]},
    )
    monkeypatch.setattr(PORTAL.queries, "list_agents", lambda *a: [{"id": "agent"}])
    monkeypatch.setattr(PORTAL, "get_public_capabilities", lambda *a: {"languages": []})
    yield TestClient(PORTAL.app), conn
    machine_auth._hits.clear()


def headers(raw, action, *, version="raw-body-v1", nonce=None):
    ts, nonce = str(int(time.time())), nonce or str(uuid.uuid4())
    digest = (
        hashlib.sha256(raw or b"{}").hexdigest()
        if version == "raw-body-v1"
        else machine_auth.payload_hash(json.loads(raw or b"{}"))
    )
    return {
        "Content-Type": "application/json",
        "X-Tenant-Id": TENANT,
        "X-Timestamp": ts,
        "X-Nonce": nonce,
        "X-Signature-Version": version,
        "X-Signature": machine_auth.expected_signature(
            SECRET, TENANT, ts, nonce, action, digest
        ),
    }


@pytest.mark.parametrize(
    "method,path,action",
    [
        ("POST", "/machine/agents", "agent.create"),
        ("PATCH", "/machine/agents/agent", "agent.update"),
    ],
)
@pytest.mark.parametrize(
    "extras",
    [
        {"future_field": "signed"},
        {"greeting": None},
        {"llm_options": {"epsilon": 1e-7}},
        {"llm_options": {"\U0001f600": 2, "\uff21": 1}},
    ],
)
def test_raw_signed_fields_survive_schema_projection(
    portal, method, path, action, extras
):
    client, _ = portal
    body = {
        "name": "Fixture",
        "prompt": "\u0622\u067e",
        "voice_id": "fixture",
        **extras,
    }
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    response = client.request(method, path, content=raw, headers=headers(raw, action))
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("extras", [{"future_field": 7}, {"greeting": None}, {}])
def test_legacy_verification_uses_received_object_without_injected_defaults(
    portal, extras
):
    client, _ = portal
    raw = json.dumps(
        {"name": "Fixture", "prompt": "test", "voice_id": "fixture", **extras}
    ).encode()
    auth = headers(raw, "agent.create", version="canonical-json-v1")
    auth.pop("X-Signature-Version")  # published old clients send no version header
    response = client.post("/machine/agents", content=raw, headers=auth)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "replacement", [b" ", b',"future_field":7', b',"greeting":null']
)
def test_raw_body_tampering_rejected_before_nonce_or_mutation(portal, replacement):
    client, conn = portal
    raw = b'{"name":"Fixture","prompt":"test","voice_id":"fixture","llm_model":"gemini-2.5-flash"}'
    altered = raw[:-1] + replacement + b"}"
    response = client.post(
        "/machine/agents", content=altered, headers=headers(raw, "agent.create")
    )
    assert response.status_code == 401
    assert not conn.nonces


@pytest.mark.parametrize(
    "path,action",
    [
        ("/machine/agents", "agent.list"),
        ("/machine/provider-capabilities", "provider_capabilities.get"),
    ],
)
def test_empty_get_and_nonce_replay_preserved(portal, path, action):
    client, _ = portal
    auth = headers(b"", action)
    assert client.get(path, headers=auth).status_code == 200
    assert client.get(path, headers=auth).status_code == 401


def test_unknown_signature_version_fails_closed(portal):
    client, conn = portal
    auth = headers(b"", "agent.list", version="canonical-json-v1")
    auth["X-Signature-Version"] = "unknown"
    assert client.get("/machine/agents", headers=auth).status_code == 401
    assert not conn.nonces


def test_csrf_header_allows_login_without_disabling_missing_header_rejection(
    portal, monkeypatch
):
    client, _ = portal
    monkeypatch.setattr(PORTAL, "assert_not_throttled", lambda *a, **kw: None)
    monkeypatch.setattr(PORTAL, "record_attempt", lambda *a, **kw: None)
    monkeypatch.setattr(
        PORTAL,
        "tenant_login",
        lambda *a, **kw: {"token": "fixture-token", "tenant_id": TENANT},
    )
    body = {"tenant_id": TENANT, "tenant_secret": SECRET}
    assert client.post("/portal/login", json=body).status_code == 403
    assert (
        client.post(
            "/portal/login", json=body, headers={"X-UVA-Portal": "1"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "text",
    [
        "don't book it",
        "dont book it",
        "please don't book it",
        "don't do it",
        "never mind, don't book it",
        "hold on, don't book it yet",
        "don\u2019t book it",
        "yes, don't book it",
        "no, cancel it",
        "nahi karo",
    ],
)
@pytest.mark.asyncio
async def test_refusal_cannot_dispatch_proposed_write(text, monkeypatch):
    from types import SimpleNamespace
    from worker import tools

    posts = []

    async def post(*a, **kw):
        posts.append(kw)
        return {"success": True}

    monkeypatch.setattr(tools, "_post_client_tool", post)
    ud = AgentUserdata(
        tenant_id="t",
        agent_id="a",
        room_name="r",
        tools_base_url="https://example.test",
    )
    set_verified_caller_phone(ud, "+923001234567")
    ctx = SimpleNamespace(userdata=ud)
    args = {
        "customer_name": "Ali",
        "customer_phone": "+923001234567",
        "slot_start_time": "2026-10-12T10:00:00",
    }
    proposal = await tools.book_appointment.__wrapped__(ctx, **args)
    assert proposal["needs_confirmation"]
    note_user_turn(ud, text)
    assert not is_affirmative_utterance(text)
    result = await tools.book_appointment.__wrapped__(
        ctx, **args, confirmation_id=proposal["confirmation_id"]
    )
    assert result.get("success") is not True
    assert posts == [] and not ud.write_gate.heard_affirmative


@pytest.mark.parametrize(
    "fault", ["action", "signature", "timestamp", "tenant", "inactive"]
)
def test_raw_mode_retains_authentication_gates(portal, fault):
    client, conn = portal
    raw = b"{}"
    auth = headers(raw, "agent.list")
    if fault == "action":
        auth = headers(raw, "agent.create")
    elif fault == "signature":
        auth["X-Signature"] = "0" * 64
    elif fault == "timestamp":
        auth["X-Timestamp"] = str(int(time.time()) - 10000)
        auth["X-Signature"] = machine_auth.expected_signature(
            SECRET,
            TENANT,
            auth["X-Timestamp"],
            auth["X-Nonce"],
            "agent.list",
            machine_auth.payload_hash(raw),
        )
    elif fault == "tenant":
        auth["X-Tenant-Id"] = "different-tenant"
    else:
        conn.status = "inactive"
    assert client.get("/machine/agents", headers=auth).status_code == (
        403 if fault == "inactive" else 401
    )


@pytest.mark.parametrize("client_kind", ["agents", "telephony"])
def test_actual_javascript_wire_signed_request_is_accepted(
    portal, monkeypatch, client_kind
):
    # This uses compiled SDKs and their actual serialization, not Python's JSON encoder.
    root = Path(__file__).resolve().parents[1]
    package = "sdk-server" if client_kind == "agents" else "telephony"
    if not shutil.which("node") or not (root / package / "dist/index.js").exists():
        pytest.skip(
            "build sdk-server and telephony before cross-language contract tests"
        )
    common = {
        "tenantId": TENANT,
        "tenantSecret": SECRET,
        "baseUrl": "https://example.test",
        "signatureVersion": "raw-body-v1",
    }
    script = (
        "import { "
        + ("AwaazLabsUvaAgentsClient" if client_kind == "agents" else "TelephonyClient")
        + " as Client } from './"
        + package
        + "/dist/index.js';\n"
    )
    script += "const capture = async (url, init) => { console.log(JSON.stringify({url, ...init})); return new Response('{}'); };\n"
    if client_kind == "agents":
        script += (
            "globalThis.fetch = capture; const client = new Client("
            + json.dumps(common)
            + ");\n"
        )
        script += "await client.createAgent({name:'Fixture',prompt:'\\u0622\\u067e',voiceId:'fixture',greeting:null,llmOptions:{epsilon:1e-7,'\\ud83d\\ude00':2,'\\uff21':1}});"
        action = "agent.create"
    else:
        script += (
            "const client = new Client({..."
            + json.dumps(common)
            + ",fetch:capture});\n"
        )
        script += "await client.listManagedPhoneNumbers({limit:1e-7,cursor:'\\u0622\\u067e\\ud83d\\ude00'});"
        action = "telephony.managed_numbers.list"
        from tenant_portal_api import telephony_routes

        conn = portal[1]
        monkeypatch.setattr(telephony_routes, "get_db", lambda: conn)
        monkeypatch.setattr(
            telephony_routes,
            "_secrets",
            type("Secrets", (), {"get": lambda self, tenant: SECRET})(),
        )
        monkeypatch.setattr(
            telephony_routes._service,
            "list_managed_numbers",
            lambda *a, **kw: {"numbers": []},
        )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        timeout=30,
    )
    wire = json.loads(result.stdout)
    raw = wire["body"].encode("utf-8")
    assert b"1e-7" in raw  # known Python-vs-JavaScript legacy canonicalization mismatch
    assert wire["headers"]["X-Signature"] == machine_auth.expected_signature(
        SECRET,
        TENANT,
        wire["headers"]["X-Timestamp"],
        wire["headers"]["X-Nonce"],
        action,
        machine_auth.payload_hash(raw),
    )
    response = portal[0].request(
        wire["method"],
        wire["url"].removeprefix("https://example.test"),
        content=raw,
        headers=wire["headers"],
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "kind,source,expected,summary",
    [
        ("assertion", "def test_canary():\n    assert 1 == 2\n", 1, "1 failed"),
        (
            "paid_socket",
            "import socket\ndef test_canary():\n    socket.getaddrinfo('paid-provider.invalid', 443)\n",
            0,
            "1 skipped",
        ),
    ],
)
def test_offline_guard_reports_real_failures_but_blocks_paid_network(
    tmp_path, kind, source, expected, summary
):
    # Copy the real hook into a project with no .env.local; no configured DB/keys are read.
    isolated = tmp_path / kind
    tests = isolated / "tests"
    tests.mkdir(parents=True)
    shutil.copyfile(Path(__file__).with_name("conftest.py"), tests / "conftest.py")
    (tests / "test_canary.py").write_text(source, encoding="utf-8")
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(
            token in k.upper()
            for token in (
                "SUPABASE",
                "API_KEY",
                "GROQ",
                "GEMINI",
                "OPENAI",
                "CARTESIA",
                "GLADIA",
                "DEEPGRAM",
                "UPLIFT",
                "RIME",
                "ELEVENLABS",
            )
        )
    }
    env["PYTEST_ADDOPTS"] = ""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        cwd=isolated,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert summary in result.stdout


@pytest.mark.parametrize(
    "filename", ["test_portal_supabase_auth.py", "test_portal_members_invite.py"]
)
def test_missing_database_configuration_skips_fixture_setup(filename, monkeypatch):
    # Exercise fixture setup directly; never use this checkout's configured remote database.
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location("handoff_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def absent():
        raise SystemExit("SUPABASE_DB_URL not configured")

    def forbidden(*args, **kwargs):
        raise AssertionError("missing-config test must never connect to a database")

    monkeypatch.setattr(module, "conn_kwargs", absent)
    monkeypatch.setattr(module.psycopg, "connect", forbidden)
    with pytest.raises(pytest.skip.Exception, match="database unavailable"):
        next(module.db.__wrapped__())


@pytest.mark.parametrize("version", ["canonical-json-v1", "raw-body-v1"])
@pytest.mark.parametrize("field", ["room_name", "roomName"])
def test_session_lookup_verifies_actual_request_including_room_alias(
    portal, monkeypatch, version, field
):
    client, _ = portal
    monkeypatch.setattr(
        PORTAL.queries,
        "get_session_by_room",
        lambda conn, tenant, room: {"room_name": room},
    )
    raw = json.dumps({field: "fixture-room"}).encode()
    response = client.post(
        "/machine/sessions/get",
        content=raw,
        headers=headers(raw, "session.get", version=version),
    )
    assert response.status_code == 200, response.text
    assert response.json()["room_name"] == "fixture-room"
