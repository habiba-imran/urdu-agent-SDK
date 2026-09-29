"""Process-local DB connection pool for the tenant portal API.

Remote Supabase pooler TLS often costs multiple seconds per fresh connect. A single
locked connection made Overview's parallel GETs run serially. A small pool lets
agents/credentials/usage/sessions overlap without reconnecting every request.
"""

from __future__ import annotations

import queue
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

# Overview fans out ~4 portal GETs; keep a few warm sockets for overlap.
_POOL_SIZE = 4
_lock = threading.Lock()
_pool: queue.Queue[Connection] | None = None
_created = 0


def _open_connection(connect_timeout: float) -> Connection:
    return psycopg.connect(
        **conn_kwargs(),
        connect_timeout=connect_timeout,
        autocommit=True,
        # Supabase transaction pooler (port 6543) does not support prepared
        # statements across checkouts — reuse otherwise raises DuplicatePreparedStatement.
        prepare_threshold=None,
    )


def _ensure_pool(connect_timeout: float) -> queue.Queue[Connection]:
    global _pool, _created
    with _lock:
        if _pool is None:
            _pool = queue.Queue(maxsize=_POOL_SIZE)
            _created = 0
        while _created < _POOL_SIZE:
            _pool.put(_open_connection(connect_timeout))
            _created += 1
        return _pool


def _drop_all() -> None:
    global _pool, _created
    with _lock:
        q = _pool
        _pool = None
        _created = 0
    if q is None:
        return
    while True:
        try:
            conn = q.get_nowait()
        except queue.Empty:
            break
        try:
            conn.close()
        except Exception:
            pass


def reset_portal_db_pool() -> None:
    """Close and forget pooled connections (tests / fork hygiene)."""
    _drop_all()


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
    """Checkout a pooled portal connection for the duration of the ``with`` block."""
    pool = _ensure_pool(connect_timeout)
    try:
        conn = pool.get(timeout=30.0)
    except queue.Empty as exc:
        raise TimeoutError("portal db pool exhausted") from exc

    if conn.closed:
        try:
            conn = _open_connection(connect_timeout)
        except Exception:
            pool.put(_open_connection(connect_timeout))
            raise

    try:
        yield conn
        _normalize_idle(conn)
        pool.put(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        try:
            pool.put(_open_connection(connect_timeout))
        except Exception:
            pass
        raise
