"""F-H9 — lifecycle tools must not call sync psycopg on the event loop.

Focused unit tests (no real DB). Run explicitly until Ehsan whitelists this file:

    python -m pytest tests/test_tools_lifecycle_db.py -q
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker.tools import (  # noqa: E402
    AgentUserdata,
    _insert_escalation,
    _save_conversation_summary,
    end_conversation_summary,
    escalate_to_human,
)


class _FakeSession:
    def __init__(self) -> None:
        self.shutdown_calls: list[dict] = []

    def shutdown(self, **kwargs) -> None:
        self.shutdown_calls.append(kwargs)


class _FakeRunContext:
    def __init__(self, userdata: AgentUserdata, session=None) -> None:
        self.userdata = userdata
        self.session = session


@pytest.fixture
def userdata() -> AgentUserdata:
    return AgentUserdata(
        tenant_id="tenant-test",
        agent_id="agent-test",
        room_name="room-test",
    )


def test_end_conversation_summary_offloads_db_via_to_thread(monkeypatch, userdata):
    to_thread_fns: list[object] = []
    save_calls: list[dict] = []

    def fake_save(**kwargs) -> None:
        save_calls.append(kwargs)

    async def fake_to_thread(fn, /, *args, **kwargs):
        to_thread_fns.append(fn)
        return fn(*args, **kwargs)

    monkeypatch.setattr("worker.tools._save_conversation_summary", fake_save)
    monkeypatch.setattr("worker.tools.asyncio.to_thread", fake_to_thread)

    fake_session = _FakeSession()
    ctx = _FakeRunContext(userdata, session=fake_session)
    result = asyncio.run(
        end_conversation_summary(ctx, summary="caller asked about pricing")
    )

    assert result == {"status": "saved"}
    assert to_thread_fns == [fake_save]
    assert save_calls == [
        {
            "summary": "caller asked about pricing",
            "room_name": "room-test",
            "tenant_id": "tenant-test",
        }
    ]
    assert fake_session.shutdown_calls == [{"drain": True}]
    assert userdata.ended_by_agent is True


def test_escalate_to_human_offloads_db_via_to_thread(monkeypatch, userdata):
    to_thread_fns: list[object] = []
    insert_calls: list[dict] = []

    def fake_insert(**kwargs) -> None:
        insert_calls.append(kwargs)

    async def fake_to_thread(fn, /, *args, **kwargs):
        to_thread_fns.append(fn)
        return fn(*args, **kwargs)

    monkeypatch.setattr("worker.tools._insert_escalation", fake_insert)
    monkeypatch.setattr("worker.tools.asyncio.to_thread", fake_to_thread)

    ctx = _FakeRunContext(userdata)
    result = asyncio.run(
        escalate_to_human(ctx, reason="wants a callback", contact_info="0300-1234567")
    )

    assert result == {"status": "escalated"}
    assert to_thread_fns == [fake_insert]
    assert insert_calls == [
        {
            "reason": "wants a callback",
            "contact_info": "0300-1234567",
            "room_name": "room-test",
            "tenant_id": "tenant-test",
        }
    ]
    assert userdata.ended_by_agent is False


def test_sync_helpers_use_psycopg_connect_not_on_async_path(monkeypatch):
    """Helpers themselves still use sync connect — that is fine when run via to_thread."""
    fake_conn = MagicMock()
    fake_conn.__enter__.return_value = fake_conn
    fake_conn.__exit__.return_value = None
    fake_conn.execute.return_value = fake_conn
    fake_conn.fetchone.return_value = ("session-id",)

    connect = MagicMock(return_value=fake_conn)
    monkeypatch.setattr("worker.tools.psycopg.connect", connect)

    _save_conversation_summary(
        summary="s", room_name="r", tenant_id="t"
    )
    _insert_escalation(
        reason="r", contact_info=None, room_name="r", tenant_id="t"
    )

    assert connect.call_count == 2
