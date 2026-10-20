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
import time
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
_last_used_at = 0.0
_IDLE_CHECK_SECONDS = 30.0


def _drop_cached_unlocked() -> None:
    global _cached, _last_used_at
    conn = _cached
    _cached = None
    _last_used_at = 0.0
    if conn is None:
        return
    try:
        conn.close()
    except Exception as exc:
        logger.warning("stage=db_pool_close failed err=%s", exc)


def reset_worker_db_pool() -> None:
    """Close and forget the cached connection (tests / fork hygiene)."""
    with _lock:
        _drop_cached_unlocked()


def _ensure_connection(connect_timeout: float) -> Connection:
    global _cached, _last_used_at
    if _cached is not None and not _cached.closed:
        if time.monotonic() - _last_used_at < _IDLE_CHECK_SECONDS:
            return _cached
        # Remote idle disconnects need not mark ``closed`` until the next I/O.
        # Probe before lending the connection, so a stale socket cannot consume
        # the caller's first config read. Never replay the borrower's SQL/writes.
        try:
            _cached.execute("select 1").fetchone()
        except (psycopg.OperationalError, psycopg.InterfaceError):
            _drop_cached_unlocked()
        else:
            _last_used_at = time.monotonic()
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
    _last_used_at = time.monotonic()
    return _cached


def _normalize_idle(conn: Connection) -> None:
    """Leave the connection IDLE for the next checkout (clear aborted tx / leftovers)."""
    try:
        status = conn.info.transaction_status
    except Exception as exc:
        logger.warning("stage=db_pool_tx_status failed err=%s", exc)
        return
    # psycopg.pq.TransactionStatus.IDLE == 0
    if int(status) != 0:
        try:
            conn.rollback()
        except Exception as exc:
            logger.warning("stage=db_pool_rollback failed err=%s", exc)


@contextmanager
def worker_db_connection(*, connect_timeout: float = 5.0) -> Iterator[Connection]:
    """Checkout the process-local connection for the duration of the ``with`` block."""
    global _last_used_at
    with _lock:
        try:
            conn = _ensure_connection(connect_timeout)
        except Exception:
            _drop_cached_unlocked()
            raise
        try:
            yield conn
            _normalize_idle(conn)
            _last_used_at = time.monotonic()
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
