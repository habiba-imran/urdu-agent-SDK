"""Transaction-local limits work with direct, session and transaction poolers."""
from contextlib import contextmanager, nullcontext
import psycopg


@contextmanager
def bounded_transaction(conn):
    with conn.transaction() if hasattr(conn, "transaction") else nullcontext():
        if isinstance(conn, psycopg.Connection):
            conn.execute("set local statement_timeout = '10s'")
            conn.execute("set local lock_timeout = '5s'")
        yield
