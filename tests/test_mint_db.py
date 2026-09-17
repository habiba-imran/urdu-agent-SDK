"""Unit tests for control_plane mint DB connection reuse."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from control_plane import mint_db


def test_mint_db_connection_reuses_cached_conn(monkeypatch):
    mint_db.reset_mint_db_pool()
    connects: list[float] = []

    fake = MagicMock()
    fake.closed = False
    fake.info = SimpleNamespace(transaction_status=0)
    fake.close = MagicMock()

    def fake_connect(**kwargs):
        connects.append(kwargs.get("connect_timeout", 0))
        return fake

    monkeypatch.setattr(mint_db.psycopg, "connect", fake_connect)
    monkeypatch.setattr(mint_db, "conn_kwargs", lambda: {"host": "example"})

    with mint_db.mint_db_connection(connect_timeout=3) as conn1:
        assert conn1 is fake
    with mint_db.mint_db_connection(connect_timeout=3) as conn2:
        assert conn2 is fake

    assert len(connects) == 1
    mint_db.reset_mint_db_pool()
    assert fake.close.called


def test_mint_db_connection_drops_on_error(monkeypatch):
    mint_db.reset_mint_db_pool()
    connects = 0

    class BoomConn:
        closed = False
        info = SimpleNamespace(transaction_status=0)

        def close(self):
            self.closed = True

    def fake_connect(**_kwargs):
        nonlocal connects
        connects += 1
        return BoomConn()

    monkeypatch.setattr(mint_db.psycopg, "connect", fake_connect)
    monkeypatch.setattr(mint_db, "conn_kwargs", lambda: {"host": "example"})

    try:
        with mint_db.mint_db_connection(connect_timeout=2) as conn:
            assert conn is not None
            raise RuntimeError("mint failed")
    except RuntimeError:
        pass

    # After error the cache is dropped; next checkout opens again.
    assert connects == 1
    with mint_db.mint_db_connection(connect_timeout=2):
        pass
    assert connects == 2
    mint_db.reset_mint_db_pool()
