"""Unit tests for F-H18 Phase B session close helper (no network)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from worker.session_close import (
    SessionCloseResult,
    build_transcript,
    release_session_quota_slot,
)


class _FakeResult:
    def __init__(self, row: tuple | None) -> None:
        self._row = row

    def fetchone(self) -> tuple | None:
        return self._row


class FakeConn:
    """Minimal conn.execute mock that tracks SQL stages."""

    def __init__(
        self,
        *,
        close_row: tuple | None = ("sess-1",),
        fail_stage: str | None = None,
    ) -> None:
        self.close_row = close_row
        self.fail_stage = fail_stage
        self.executed: list[tuple[str, tuple | None]] = []
        self.quota_updates = 0
        self.usage_inserts = 0
        self.transcript_updates = 0
        self.minutes_upserts = 0

    def execute(self, sql: str, params: tuple | None = None) -> _FakeResult:
        self.executed.append((sql, params))
        low = sql.lower()

        if self.fail_stage == "close" and "ended_at is null" in low:
            raise RuntimeError("close boom")
        if self.fail_stage == "quota" and "concurrent_now" in low:
            raise RuntimeError("quota boom")
        if self.fail_stage == "transcript" and "transcript" in low:
            raise RuntimeError("transcript boom")
        if self.fail_stage == "usage" and (
            "usage_events" in low or "minutes_this_month" in low
        ):
            raise RuntimeError("usage boom")

        if "ended_at is null" in low and "returning id" in low:
            return _FakeResult(self.close_row)
        if "concurrent_now" in low:
            self.quota_updates += 1
            return _FakeResult(None)
        if "set transcript" in low:
            self.transcript_updates += 1
            return _FakeResult(None)
        if "usage_events" in low:
            self.usage_inserts += 1
            return _FakeResult(None)
        if "minutes_this_month" in low:
            self.minutes_upserts += 1
            return _FakeResult(None)
        # retention / information_schema probes etc.
        return _FakeResult(None)


def test_build_transcript_filters_and_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "worker.humanization.history.plain_text_for_history",
        lambda t: t.replace("*", ""),
    )
    msgs = [
        SimpleNamespace(role="user", text_content="hi", created_at=1),
        SimpleNamespace(role="assistant", text_content="*hello*", created_at=2),
        SimpleNamespace(role="system", text_content="skip", created_at=3),
        SimpleNamespace(role="user", text_content="  ", created_at=4),
    ]
    session = SimpleNamespace(history=SimpleNamespace(messages=lambda: msgs))
    out = build_transcript(session)
    assert out == [
        {"role": "user", "text": "hi", "at": 1},
        {"role": "assistant", "text": "hello", "at": 2},
    ]


def test_build_transcript_failure_returns_empty() -> None:
    session = SimpleNamespace(history=SimpleNamespace(messages=lambda: (_ for _ in ()).throw(RuntimeError("x"))))
    assert build_transcript(session) == []


def test_happy_path_closes_quota_usage_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "worker.session_retention.apply_retention_on_session_close",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "worker.usage.collect_model_usage",
        lambda _s: {"stt_sec": 1.0},
    )

    def _record_many(conn: Any, tenant_id: str, session_id: str | None, items: dict) -> int:
        # Mimic real inserts so FakeConn can count usage_events rows.
        for kind, qty in items.items():
            if qty and qty > 0:
                conn.execute(
                    "insert into usage_events (tenant_id, session_id, kind, qty) values (%s, %s, %s, %s)",
                    (tenant_id, session_id, kind, qty),
                )
        return sum(1 for v in items.values() if v and v > 0)

    monkeypatch.setattr("worker.usage.record_usage_many", _record_many)

    conn = FakeConn(close_row=("sess-1",))
    session = SimpleNamespace(
        history=SimpleNamespace(
            messages=lambda: [
                SimpleNamespace(role="user", text_content="hi", created_at=1),
            ]
        )
    )
    result = release_session_quota_slot(
        room_name="room-a",
        tenant_id="tenant-1",
        elapsed_sec=90,
        end_reason="normal",
        session_obj=session,
        conn=conn,
    )
    assert result == SessionCloseResult(
        closed=True,
        session_id="sess-1",
        quota_decremented=True,
        usage_events=2,  # stt_sec + agent_sec
        transcript_attached=True,
    )
    assert conn.quota_updates == 1
    assert conn.transcript_updates == 1
    assert conn.minutes_upserts == 1
    # Order: close before quota before transcript
    stages = []
    for sql, _ in conn.executed:
        low = sql.lower()
        if "ended_at is null" in low:
            stages.append("close")
        elif "concurrent_now" in low:
            stages.append("quota")
        elif "set transcript" in low:
            stages.append("transcript")
    assert stages[:3] == ["close", "quota", "transcript"]


def test_second_close_is_noop_no_double_quota() -> None:
    conn = FakeConn(close_row=None)  # already closed → no RETURNING row
    result = release_session_quota_slot(
        room_name="room-a",
        tenant_id="tenant-1",
        elapsed_sec=10,
        end_reason="normal",
        transcript=[],
        conn=conn,
    )
    assert result.closed is False
    assert result.quota_decremented is False
    assert result.usage_events == 0
    assert conn.quota_updates == 0
    assert conn.usage_inserts == 0
    assert conn.minutes_upserts == 0


def test_idempotent_two_calls_second_skips_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "worker.session_retention.apply_retention_on_session_close",
        lambda *a, **k: None,
    )
    monkeypatch.setattr("worker.usage.collect_model_usage", lambda _s: {})
    monkeypatch.setattr(
        "worker.usage.record_usage_many",
        lambda conn, tenant_id, session_id, items: 0,
    )

    # First call closes; second returns no row.
    class SeqConn(FakeConn):
        def __init__(self) -> None:
            super().__init__(close_row=("sess-1",))
            self._n = 0

        def execute(self, sql: str, params: tuple | None = None) -> _FakeResult:
            low = sql.lower()
            if "ended_at is null" in low and "returning id" in low:
                self._n += 1
                if self._n == 1:
                    return super().execute(sql, params)
                self.executed.append((sql, params))
                return _FakeResult(None)
            return super().execute(sql, params)

    conn = SeqConn()
    r1 = release_session_quota_slot(
        room_name="room-a",
        tenant_id="tenant-1",
        elapsed_sec=30,
        end_reason="normal",
        transcript=[],
        conn=conn,
    )
    r2 = release_session_quota_slot(
        room_name="room-a",
        tenant_id="tenant-1",
        elapsed_sec=30,
        end_reason="normal",
        transcript=[],
        conn=conn,
    )
    assert r1.closed and r1.quota_decremented
    assert not r2.closed and not r2.quota_decremented
    assert conn.quota_updates == 1


def test_transcript_failure_does_not_skip_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "worker.session_retention.apply_retention_on_session_close",
        lambda *a, **k: None,
    )
    monkeypatch.setattr("worker.usage.collect_model_usage", lambda _s: {})
    monkeypatch.setattr(
        "worker.usage.record_usage_many",
        lambda conn, tenant_id, session_id, items: 0,
    )

    conn = FakeConn(close_row=("sess-1",), fail_stage="transcript")
    result = release_session_quota_slot(
        room_name="room-a",
        tenant_id="tenant-1",
        elapsed_sec=5,
        end_reason="normal",
        transcript=[{"role": "user", "text": "x", "at": 1}],
        conn=conn,
    )
    assert result.closed is True
    assert result.quota_decremented is True
    assert result.transcript_attached is False
    assert conn.quota_updates == 1


def test_close_failure_logs_error_no_quota(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    conn = FakeConn(fail_stage="close")
    with caplog.at_level(logging.ERROR, logger="worker.session_close"):
        result = release_session_quota_slot(
            room_name="room-a",
            tenant_id="tenant-1",
            elapsed_sec=5,
            end_reason="normal",
            transcript=[],
            conn=conn,
        )
    assert result.closed is False
    assert result.quota_decremented is False
    assert any("stage=close_session failed" in r.message for r in caplog.records)


def test_missing_tenant_still_closes_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "worker.session_retention.apply_retention_on_session_close",
        lambda *a, **k: None,
    )
    conn = FakeConn(close_row=("sess-1",))
    result = release_session_quota_slot(
        room_name="room-a",
        tenant_id="",
        elapsed_sec=5,
        end_reason="normal",
        transcript=[],
        conn=conn,
    )
    assert result.closed is True
    assert result.quota_decremented is False
    assert conn.quota_updates == 0
    assert result.usage_events == 0


def test_quota_failure_still_attempts_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "worker.session_retention.apply_retention_on_session_close",
        lambda *a, **k: None,
    )
    monkeypatch.setattr("worker.usage.collect_model_usage", lambda _s: {})
    monkeypatch.setattr(
        "worker.usage.record_usage_many",
        lambda conn, tenant_id, session_id, items: 0,
    )
    conn = FakeConn(close_row=("sess-1",), fail_stage="quota")
    result = release_session_quota_slot(
        room_name="room-a",
        tenant_id="tenant-1",
        elapsed_sec=5,
        end_reason="normal",
        transcript=[],
        conn=conn,
    )
    assert result.closed is True
    assert result.quota_decremented is False
    assert result.transcript_attached is True
    assert conn.transcript_updates == 1
