"""Idle connection recovery happens before lending, never by replaying a write."""
from types import SimpleNamespace as NS

import psycopg
import pytest

from worker import db_pool


class Connection:
    def __init__(self, *, stale=False):
        self.closed = False
        self.stale = stale
        self.queries = []
        self.info = NS(transaction_status=0)

    def execute(self, sql):
        self.queries.append(sql)
        if self.stale:
            raise psycopg.OperationalError("fixture: remotely closed while idle")
        return NS(fetchone=lambda: (1,))

    def close(self):
        self.closed = True


@pytest.fixture
def pool(monkeypatch):
    db_pool.reset_worker_db_pool()
    clock = NS(now=100.0)
    made = []
    monkeypatch.setattr(db_pool.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(db_pool, "conn_kwargs", lambda: {})

    def connect(**kwargs):
        assert kwargs["autocommit"] is True
        assert kwargs["prepare_threshold"] is None
        conn = Connection()
        made.append(conn)
        return conn

    monkeypatch.setattr(db_pool.psycopg, "connect", connect)
    yield clock, made
    db_pool.reset_worker_db_pool()


def test_hot_reuse_does_not_add_a_health_round_trip(pool):
    clock, made = pool
    with db_pool.worker_db_connection() as first:
        pass
    clock.now += 10
    with db_pool.worker_db_connection() as second:
        assert second is first
    assert len(made) == 1
    assert first.queries == []


def test_idle_healthy_connection_is_checked_and_reused(pool):
    clock, made = pool
    with db_pool.worker_db_connection() as first:
        pass
    clock.now += 31
    with db_pool.worker_db_connection() as second:
        assert second is first
    assert first.queries == ["select 1"]
    assert len(made) == 1


def test_remote_idle_disconnect_recovers_before_borrower_write(pool):
    clock, made = pool
    with db_pool.worker_db_connection() as first:
        pass
    first.stale = True
    clock.now += 31
    with db_pool.worker_db_connection() as usable:
        usable.execute("fixture business write")
    assert first.closed
    assert first.queries == ["select 1"]
    assert len(made) == 2
    assert made[1].queries == ["fixture business write"]


def test_borrower_failure_is_never_replayed(pool):
    _, made = pool
    with pytest.raises(psycopg.OperationalError):
        with db_pool.worker_db_connection() as conn:
            conn.stale = True
            conn.execute("fixture business write")
    assert len(made) == 1
    assert made[0].queries == ["fixture business write"]
    assert made[0].closed
    assert db_pool._cached is None


def test_failed_reconnect_does_not_run_borrower_code(pool, monkeypatch):
    clock, _ = pool
    with db_pool.worker_db_connection() as first:
        pass
    first.stale = True
    clock.now += 31

    def unavailable(**kwargs):
        raise psycopg.OperationalError("fixture reconnect unavailable")

    monkeypatch.setattr(db_pool.psycopg, "connect", unavailable)
    with pytest.raises(psycopg.OperationalError):
        with db_pool.worker_db_connection():
            pytest.fail("Must not yield a failed connection")
    assert db_pool._cached is None
