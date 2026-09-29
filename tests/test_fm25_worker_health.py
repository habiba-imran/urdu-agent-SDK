"""F-M25 Phase E — worker health/readiness HTTP (no LiveKit room)."""

from __future__ import annotations

import json
from http.client import HTTPConnection

import pytest

from worker import health_http as hh


@pytest.fixture(autouse=True)
def _reset_health(monkeypatch: pytest.MonkeyPatch) -> None:
    hh.stop_health_server()
    hh.set_vad_ready(False)
    monkeypatch.delenv("UVA_WORKER_HEALTH_PORT", raising=False)
    monkeypatch.delenv("UVA_WORKER_HEALTH_BIND", raising=False)
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    yield
    hh.stop_health_server()
    hh.set_vad_ready(False)


def test_health_port_disabled_by_default() -> None:
    assert hh.health_port() is None


def test_health_port_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_WORKER_HEALTH_PORT", "8081")
    assert hh.health_port() == 8081
    monkeypatch.setenv("UVA_WORKER_HEALTH_PORT", "0")
    assert hh.health_port() is None


def test_liveness_payload() -> None:
    body = hh.liveness_payload()
    assert body["status"] == "ok"
    assert body["service"] == "uva-worker"


def test_readiness_unhealthy_without_creds_or_vad(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hh, "check_database", lambda: ("connected", True))
    body, code = hh.readiness_payload()
    assert code == 503
    assert body["status"] == "unhealthy"
    assert body["livekit"] == "missing_credentials"
    assert body["vad"] == "not_loaded"


def test_readiness_healthy_when_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret")
    hh.set_vad_ready(True)
    monkeypatch.setattr(hh, "check_database", lambda: ("connected", True))
    body, code = hh.readiness_payload()
    assert code == 200
    assert body["status"] == "healthy"
    assert body["livekit"] == "configured"
    assert body["vad"] == "loaded"
    assert body["database"] == "connected"


def test_readiness_unhealthy_when_db_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret")
    hh.set_vad_ready(True)
    monkeypatch.setattr(hh, "check_database", lambda: ("failed", False))
    body, code = hh.readiness_payload()
    assert code == 503
    assert body["database"] == "failed"


def test_health_server_serves_liveness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_WORKER_HEALTH_PORT", "18081")
    monkeypatch.setenv("UVA_WORKER_HEALTH_BIND", "127.0.0.1")
    thread = hh.start_health_server_if_configured()
    assert thread is not None
    conn = HTTPConnection("127.0.0.1", 18081, timeout=2)
    try:
        conn.request("GET", "/healthz")
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert data["status"] == "ok"
    finally:
        conn.close()
        hh.stop_health_server()
