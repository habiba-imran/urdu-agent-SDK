"""Unit tests for tenant portal DB connection reuse."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from tenant_portal_api import db_pool


def test_portal_db_connection_reuses_cached_conn(monkeypatch):
    db_pool.reset_portal_db_pool()
    connects: list[float] = []

    fake = MagicMock()
    fake.closed = False
    fake.info = SimpleNamespace(transaction_status=0)
    fake.close = MagicMock()

    def fake_connect(**kwargs):
        connects.append(kwargs.get("connect_timeout", 0))
        return fake

    monkeypatch.setattr(db_pool.psycopg, "connect", fake_connect)
    monkeypatch.setattr(db_pool, "conn_kwargs", lambda: {"host": "example"})

    with db_pool.portal_db_connection(connect_timeout=10) as conn1:
        assert conn1 is fake
    with db_pool.portal_db_connection(connect_timeout=10) as conn2:
        assert conn2 is fake

    # First checkout opens one socket synchronously; background fill may add more.
    assert len(connects) >= 1
    assert connects[0] == 10
    time.sleep(0.05)
    assert 1 <= len(connects) <= db_pool._POOL_SIZE
    db_pool.reset_portal_db_pool()
    assert fake.close.called


def test_portal_db_connection_disables_prepared_statements(monkeypatch):
    db_pool.reset_portal_db_pool()
    seen: dict = {}

    fake = MagicMock()
    fake.closed = False
    fake.info = SimpleNamespace(transaction_status=0)
    fake.close = MagicMock()

    def fake_connect(**kwargs):
        seen.update(kwargs)
        return fake

    monkeypatch.setattr(db_pool.psycopg, "connect", fake_connect)
    monkeypatch.setattr(db_pool, "conn_kwargs", lambda: {"host": "example"})

    with db_pool.portal_db_connection(connect_timeout=10):
        pass

    assert seen.get("prepare_threshold") is None
    db_pool.reset_portal_db_pool()


def test_first_checkout_does_not_block_on_full_pool(monkeypatch):
    """Regression: serial warm of all 4 sockets made first Overview paint wait ~10s."""
    db_pool.reset_portal_db_pool()
    sync_opens = {"n": 0}

    def fake_connect(**kwargs):
        sync_opens["n"] += 1
        # Background opens would also call this; first checkout must return after 1.
        fake = MagicMock()
        fake.closed = False
        fake.info = SimpleNamespace(transaction_status=0)
        fake.close = MagicMock()
        return fake

    monkeypatch.setattr(db_pool.psycopg, "connect", fake_connect)
    monkeypatch.setattr(db_pool, "conn_kwargs", lambda: {"host": "example"})

    with db_pool.portal_db_connection(connect_timeout=10) as conn:
        assert conn is not None
        # Only the synchronous first connection has completed at checkout time.
        assert sync_opens["n"] == 1

    db_pool.reset_portal_db_pool()
