"""Unit tests for F-C4 Phase D retention + purge helpers (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from worker.session_retention import (
    apply_retention_on_session_close,
    reset_retention_column_probes,
    retention_days_from_env,
)


@pytest.fixture(autouse=True)
def _reset_probes() -> None:
    reset_retention_column_probes()


def test_retention_days_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UVA_RECORDING_RETENTION_DAYS", raising=False)
    assert retention_days_from_env() == 30


def test_retention_days_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_RECORDING_RETENTION_DAYS", "14")
    assert retention_days_from_env() == 14


def test_retention_days_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_RECORDING_RETENTION_DAYS", "nope")
    assert retention_days_from_env() == 30
    monkeypatch.setenv("UVA_RECORDING_RETENTION_DAYS", "0")
    assert retention_days_from_env() == 30


def test_apply_retention_updates_telephony_and_optional_sessions() -> None:
    executed: list[tuple[str, tuple]] = []

    class FakeConn:
        def execute(self, sql: str, params: tuple | None = None):
            executed.append((sql, params or ()))
            # information_schema probes
            if "information_schema.columns" in sql and params:
                table, col = params[0], params[1]
                if table == "sessions" and col == "retention_until":
                    return SimpleNamespace(fetchone=lambda: (1,))
                if table == "escalations" and col == "retention_until":
                    return SimpleNamespace(fetchone=lambda: (1,))
                return SimpleNamespace(fetchone=lambda: None)
            return SimpleNamespace(fetchone=lambda: None, rowcount=1)

    apply_retention_on_session_close(
        FakeConn(),
        room_name="room-a",
        session_id="11111111-1111-1111-1111-111111111111",
        retention_days=7,
    )
    assert any("telephony_calls" in sql for sql, _ in executed)
    assert any(
        "update sessions" in sql.lower() and "retention_until" in sql for sql, _ in executed
    )
    assert any("escalations" in sql for sql, _ in executed)
    tele = next(p for sql, p in executed if "telephony_calls" in sql)
    assert tele[0] == "7"
    assert tele[1] == "room-a"


def test_apply_retention_skips_sessions_when_column_missing() -> None:
    executed: list[str] = []

    class FakeConn:
        def execute(self, sql: str, params: tuple | None = None):
            executed.append(sql)
            if "information_schema.columns" in sql:
                return SimpleNamespace(fetchone=lambda: None)  # no sessions/escalations cols
            return SimpleNamespace(fetchone=lambda: None, rowcount=0)

    apply_retention_on_session_close(
        FakeConn(),
        room_name="room-b",
        session_id="11111111-1111-1111-1111-111111111111",
        retention_days=30,
    )
    assert any("telephony_calls" in sql for sql in executed)
    assert not any(
        sql.strip().lower().startswith("update sessions") for sql in executed
    )


def test_purge_delete_storage_object_handles_none() -> None:
    from scripts.purge_expired_session_media import delete_storage_object

    assert delete_storage_object(None, "a/b.ogg") is False
    assert delete_storage_object(None, "") is True

    removed: list[list[str]] = []

    class Bucket:
        def remove(self, paths: list[str]) -> None:
            removed.append(paths)

    class Storage:
        def from_(self, _name: str) -> Bucket:
            return Bucket()

    assert delete_storage_object(Storage(), "t/r.ogg") is True
    assert removed == [["t/r.ogg"]]


def test_purge_session_and_telephony_row_sql() -> None:
    from scripts.purge_expired_session_media import (
        PurgeTarget,
        purge_session_row,
        purge_telephony_row,
        redact_escalations_for_session,
    )

    executed: list[tuple[str, tuple]] = []

    class FakeConn:
        def execute(self, sql: str, params: tuple | None = None):
            executed.append((sql, params or ()))
            if "information_schema.columns" in sql:
                if params and params[1] == "redacted_at" and params[0] == "sessions":
                    return SimpleNamespace(fetchone=lambda: (1,))
                return SimpleNamespace(fetchone=lambda: None)
            return SimpleNamespace(rowcount=2)

    purge_session_row(
        FakeConn(),
        PurgeTarget(
            kind="session",
            row_id="11111111-1111-1111-1111-111111111111",
            room_name="r",
            storage_path="t/r.ogg",
            session_id="11111111-1111-1111-1111-111111111111",
        ),
    )
    assert any("transcript = null" in sql for sql, _ in executed)

    executed.clear()
    purge_telephony_row(
        FakeConn(),
        PurgeTarget(
            kind="telephony",
            row_id="22222222-2222-2222-2222-222222222222",
            room_name="r",
            storage_path="t/r.ogg",
        ),
    )
    assert any("telephony_calls" in sql for sql, _ in executed)

    executed.clear()
    n = redact_escalations_for_session(
        FakeConn(), "11111111-1111-1111-1111-111111111111"
    )
    assert n == 2
    assert any("contact_info = null" in sql for sql, _ in executed)


def test_purge_skips_db_when_storage_delete_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import purge_expired_session_media as purge

    monkeypatch.setattr(purge, "conn_kwargs", lambda: {})
    monkeypatch.setattr(purge, "_supabase_storage", lambda: object())
    monkeypatch.setattr(purge, "delete_storage_object", lambda storage, path: False)
    monkeypatch.setattr(
        purge,
        "select_session_targets",
        lambda conn, *, limit: [
            purge.PurgeTarget(
                kind="session",
                row_id="11111111-1111-1111-1111-111111111111",
                room_name="r",
                storage_path="t/r.ogg",
                session_id="11111111-1111-1111-1111-111111111111",
            )
        ],
    )
    monkeypatch.setattr(purge, "select_telephony_targets", lambda conn, *, limit: [])

    purged: list[str] = []

    def _no_purge_session(conn, target):
        purged.append(target.row_id)

    monkeypatch.setattr(purge, "purge_session_row", _no_purge_session)

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            if "information_schema" in sql:
                return SimpleNamespace(fetchone=lambda: (1,))
            return SimpleNamespace(fetchone=lambda: None, rowcount=0)

        def rollback(self):
            return None

    monkeypatch.setattr(
        purge.psycopg,
        "connect",
        lambda **kwargs: FakeConn(),
    )

    stats = purge.run_purge(dry_run=False, limit=10)
    assert stats.storage_failed >= 1
    assert purged == []
    assert stats.sessions_purged == 0
