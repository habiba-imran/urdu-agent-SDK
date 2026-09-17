"""Process-local DB connection reuse for control-plane session mint.

Remote Supabase pooler TLS often costs 1–3s per fresh ``psycopg.connect``. Mint used
to open a new TCP/TLS session on every ``POST /v1/session``, which dominated
``room_connected`` when LiveKit join was otherwise healthy.

One locked connection per OS process (same pattern as ``worker.db_pool``). Safe under
FastAPI's sync-threadpool mint handlers: the lock serializes checkouts.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger("control_plane.mint_db")

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


def reset_mint_db_pool() -> None:
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
def mint_db_connection(*, connect_timeout: float = 10.0) -> Iterator[Connection]:
    """Checkout the process-local mint connection for the duration of the ``with`` block."""
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
