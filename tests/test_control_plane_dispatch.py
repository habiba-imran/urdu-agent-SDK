"""Control-plane LiveKit dispatch scheduling — mint must not wait for job assign."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from control_plane import app as app_module  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_dispatch(monkeypatch):
    """Avoid touching real LiveKit / DB during unit tests."""
    monkeypatch.setattr(app_module, "_warm_dispatch_client", lambda: None)
    monkeypatch.setattr(app_module, "_shutdown_dispatch", lambda: None)
    yield


def test_with_dispatch_schedules_before_returning(monkeypatch):
    """create_dispatch must start before the mint response is handed back."""
    order: list[str] = []
    started = threading.Event()

    async def slow_dispatch(*_a, **_k):
        order.append("dispatch_started")
        started.set()
        await __import__("asyncio").sleep(0.05)
        order.append("dispatch_done")

    monkeypatch.setattr(app_module, "_dispatch_agent", slow_dispatch)
    # Watcher would call rollback on failure — keep it no-op for this test.
    monkeypatch.setattr(app_module, "_watch_dispatch", lambda *a, **k: None)

    res = app_module._with_dispatch(
        {"token": "t", "wsUrl": "wss://x", "roomName": "room-abc"},
        "tenant-1",
        "agent-1",
        greeting="hi",
    )
    order.append("mint_returned")

    assert res["roomName"] == "room-abc"
    assert res["refreshUrl"] == "/v1/session/refresh"
    assert started.wait(timeout=2.0), "dispatch should start immediately"
    assert order[0] == "dispatch_started"
    assert "mint_returned" in order
    deadline = time.monotonic() + 2.0
    while "dispatch_done" not in order and time.monotonic() < deadline:
        time.sleep(0.01)
    assert "dispatch_done" in order
    assert order.index("mint_returned") < order.index("dispatch_done")


def test_schedule_dispatch_starts_immediately(monkeypatch):
    gate = threading.Event()
    calls: list[dict] = []

    async def capture(room_name, *, tenant_id, agent_id, greeting=None, verified_caller_phone=None):
        calls.append(
            {
                "room_name": room_name,
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "greeting": greeting,
                "verified_caller_phone": verified_caller_phone,
            }
        )
        gate.set()

    monkeypatch.setattr(app_module, "_dispatch_agent", capture)
    monkeypatch.setattr(app_module, "_watch_dispatch", lambda *a, **k: None)

    t0 = time.monotonic()
    fut = app_module._schedule_dispatch(
        "room-xyz",
        "tid",
        "aid",
        greeting="Hello",
        verified_caller_phone="+15551212",
    )
    # Scheduling itself must be near-instant (no await of LiveKit).
    assert (time.monotonic() - t0) < 0.5
    assert gate.wait(timeout=2.0)
    assert fut is not None
    assert calls == [
        {
            "room_name": "room-xyz",
            "tenant_id": "tid",
            "agent_id": "aid",
            "greeting": "Hello",
            "verified_caller_phone": "+15551212",
        }
    ]


def test_watch_dispatch_rolls_back_on_failure(monkeypatch):
    rolled: list[tuple[str, str]] = []

    def fake_rollback(*, tenant_id, room_name, end_reason="dispatch_failed"):
        rolled.append((tenant_id, room_name, end_reason))

    monkeypatch.setattr(app_module, "_rollback_dispatched_session", fake_rollback)

    class BoomFuture:
        def result(self, timeout=None):
            raise RuntimeError("livekit down")

        def cancel(self):
            return True

    app_module._watch_dispatch(
        BoomFuture(),  # type: ignore[arg-type]
        room_name="room-fail",
        tenant_id="t1",
        agent_id="a1",
        started=time.monotonic(),
    )
    assert rolled == [("t1", "room-fail", "dispatch_failed")]


def test_session_endpoint_schedules_dispatch_without_background_tasks(monkeypatch):
    """Regression: mint path must not depend on FastAPI BackgroundTasks."""
    from contextlib import contextmanager
    import datetime
    import uuid

    from fastapi.testclient import TestClient

    scheduled: list[tuple] = []

    def fake_mint_session(**kwargs):
        return {
            "token": "token-123",
            "wsUrl": "wss://example.livekit.cloud",
            "roomName": "room-123",
        }

    def fake_schedule(room_name, tenant_id, agent_id, **kwargs):
        scheduled.append((room_name, tenant_id, agent_id, kwargs))
        return None

    @contextmanager
    def fake_mint_db_connection(*, connect_timeout: float = 10.0):
        yield object()

    monkeypatch.setattr(app_module, "mint_session", fake_mint_session)
    monkeypatch.setattr(app_module, "_schedule_dispatch", fake_schedule)
    monkeypatch.setattr(app_module, "_rate_limited", lambda tenant_id: False)
    monkeypatch.setattr(app_module, "mint_db_connection", fake_mint_db_connection)
    # Bypass IP rate limit helpers used by create_session
    monkeypatch.setattr(app_module, "_rate_limit_exceeded", lambda *a, **k: False)
    monkeypatch.setattr(app_module, "_rate_limit_record", lambda *a, **k: None)

    client = TestClient(app_module.app)
    ts = str(int(datetime.datetime.now(datetime.UTC).timestamp()))
    headers = {
        "X-Tenant-Id": "tenant-123",
        "X-Timestamp": ts,
        "X-Nonce": str(uuid.uuid4()),
        "X-Signature": "signed",
        "Origin": "https://host.example.com",
    }
    response = client.post(
        "/v1/session", json={"agent_id": "agent-123"}, headers=headers
    )
    assert response.status_code == 200
    assert scheduled == [
        ("room-123", "tenant-123", "agent-123", {"greeting": None, "verified_caller_phone": None})
    ]
