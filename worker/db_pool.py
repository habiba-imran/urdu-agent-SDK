"""Process-local DB connection reuse for the worker hot path.

Cross-region Supabase pooler TLS often costs 1–3s per ``psycopg.connect``. Opening a
fresh TCP/TLS session on every config/stale lookup dominated ``build_ms`` / stale-check
timings. One locked connection per OS process avoids that without adding ``psycopg_pool``.

Safe for Windows THREAD job runners: the lock serializes checkouts so two jobs never
share a connection concurrently. Callers must use short transactions (``set local`` is OK).
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from scripts.dbconn import conn_kwargs
except ImportError:
    from dbconn import conn_kwargs  # type: ignore # noqa: E402

logger = logging.getLogger("worker.db_pool")

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


def reset_worker_db_pool() -> None:
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
    )
    return _cached


def _normalize_idle(conn: Connection) -> None:
    """Leave the connection IDLE for the next checkout (clear aborted tx / leftovers)."""
    try:
        status = conn.info.transaction_status
    except Exception:
        return
    # psycopg.pq.TransactionStatus.IDLE == 0
    if int(status) != 0:
        try:
            conn.rollback()
        except Exception:
            pass


@contextmanager
def worker_db_connection(*, connect_timeout: float = 5.0) -> Iterator[Connection]:
    """Checkout the process-local connection for the duration of the ``with`` block."""
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


def worker_db_execute(
    sql: str,
    params: tuple[Any, ...] | None = None,
    *,
    connect_timeout: float = 5.0,
) -> Any:
    """Run a single statement on the pooled connection; return ``cursor.fetchone()``."""
    with worker_db_connection(connect_timeout=connect_timeout) as conn:
        return conn.execute(sql, params).fetchone()
