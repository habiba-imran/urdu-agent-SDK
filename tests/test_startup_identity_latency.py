"""Caller ownership must not block WebRTC startup or the real-time event loop."""
from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace as NS

import pytest

from worker.main import _bind_verified_caller_phone
from worker.tools import AgentUserdata


def session():
    return NS(userdata=AgentUserdata("test-tenant", "test-agent", "test-room"))


@pytest.mark.asyncio
async def test_browser_without_phone_never_opens_database(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("Browser caller without phone metadata must not touch the DB")
    monkeypatch.setattr("worker.db_pool.worker_db_connection", forbidden)
    s = session()
    await _bind_verified_caller_phone(s, md={}, room_name="test-room")
    assert s.userdata.verified_caller_phone is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mint,attributes", [
    ({"verified_caller_phone": "+923001234567"}, {}),
    ({}, {"sip.phoneNumber": "+923001234567"}),
])
async def test_trusted_metadata_resolves_without_database(monkeypatch, mint, attributes):
    monkeypatch.setattr("worker.db_pool.worker_db_connection", lambda **kw: pytest.fail("Unexpected DB"))
    s = session()
    await _bind_verified_caller_phone(s, md=mint, participant=NS(attributes=attributes, metadata=""), room_name="test-room")
    assert s.userdata.verified_caller_phone == "+923001234567"


@pytest.mark.asyncio
async def test_sip_database_fallback_runs_off_audio_loop(monkeypatch):
    loop_thread = threading.get_ident()
    entered = threading.Event()
    @contextmanager
    def connection(**kwargs):
        assert threading.get_ident() != loop_thread
        entered.set()
        time.sleep(.08)
        yield NS(execute=lambda *a: NS(fetchone=lambda: ("inbound", "+923001234567", "+15550001111")))
    monkeypatch.setattr("worker.db_pool.worker_db_connection", connection)
    s = session()
    task = asyncio.create_task(_bind_verified_caller_phone(s, md={"telephony_call_id": "test-call"}, room_name="telephony-test"))
    while not entered.is_set():
        await asyncio.sleep(.001)
    assert not task.done()
    await task
    assert s.userdata.verified_caller_phone == "+923001234567"


@pytest.mark.asyncio
async def test_failed_sip_lookup_leaves_ownership_unknown(monkeypatch):
    def unavailable(**kwargs):
        raise RuntimeError("fixture DB unavailable")
    monkeypatch.setattr("worker.db_pool.worker_db_connection", unavailable)
    s = session()
    await _bind_verified_caller_phone(s, md={}, room_name="telephony-test")
    assert s.userdata.verified_caller_phone is None
