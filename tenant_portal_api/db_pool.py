"""Process-local DB connection reuse for the tenant portal API.

Remote Supabase pooler TLS often costs multiple seconds per fresh connect. Portal
routes used ``psycopg.connect(..., connect_timeout=3)`` and closed the socket on
every ``with _conn()`` exit — intermittent ``ConnectionTimeout`` on
``/machine/provider-capabilities`` from high-RTT networks.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import Connection

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from scripts.dbconn import conn_kwargs
except ImportError:
    from dbconn import conn_kwargs  # type: ignore # noqa: E402

_lock = threading.Lock()
_cached: Connection | None = None


def _drop_cached_unlocked() -> None:
    global _cached
    conn = _cached
    _cached = None
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass


def reset_portal_db_pool() -> None:
    """Close and forget the cached connection (tests / fork hygiene)."""
    with _lock:
        _drop_cached_unlocked()


def _ensure_connection(connect_timeout: float) -> Connection:
    global _cached
    if _cached is not None and not _cached.closed:
        return _cached
    _drop_cached_unlocked()
    _cached = psycopg.connect(
        **conn_kwargs(),
        connect_timeout=connect_timeout,
        autocommit=True,
        # Supabase transaction pooler (port 6543) does not support prepared
        # statements across checkouts — reuse otherwise raises DuplicatePreparedStatement.
        prepare_threshold=None,
    )
    return _cached


def _normalize_idle(conn: Connection) -> None:
    try:
        status = conn.info.transaction_status
    except Exception:
        return
    if int(status) != 0:
        try:
            conn.rollback()
        except Exception:
            pass


@contextmanager
def portal_db_connection(*, connect_timeout: float = 10.0) -> Iterator[Connection]:
    """Checkout the process-local portal connection for the duration of the ``with`` block."""
    with _lock:
        try:
            conn = _ensure_connection(connect_timeout)
        except Exception:
            _drop_cached_unlocked()
            raise
        try:
            yield conn
            _normalize_idle(conn)
        except Exception:
            _drop_cached_unlocked()
            raise
