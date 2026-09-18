"""Unit tests for tenant portal DB connection reuse."""

from __future__ import annotations

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

    assert len(connects) == 1
    assert connects[0] == 10
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
