"""Write-side audit helpers.

`record_mint_rejection` is called from the control-plane request path (control_plane/app.py) at
the moment a request is rejected — i.e. potentially from inside/just after a `MintError` raised
out of `mint.py`'s `with conn.transaction():` block, which rolls back everything in it (nonce
insert included — pre-existing behavior, untouched here). A rejection must be recorded regardless
of what happens to that transaction, so this opens its own short-lived autocommit connection
rather than reusing the caller's. Logging failure must never break the actual rejection response
the caller-facing tenant sees — but it is NOT silent: a failed audit write logs a WARNING (project
motto, AGENT_SYSTEM.md §9: "zero *silent* errors").

`record_admin_action` runs inside a normal (non-rollback-risk) successful admin request, so it
reuses the caller's connection.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dbconn import conn_kwargs  # noqa: E402

logger = logging.getLogger("admin.audit")


def _valid_uuid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        return None


def record_mint_rejection(tenant_id: str | None, status: int, reason: str) -> None:
    try:
        with psycopg.connect(
            **conn_kwargs(), autocommit=True, connect_timeout=5
        ) as conn:
            conn.execute(
                "insert into mint_rejections (tenant_id, status, reason) values (%s, %s, %s)",
                (_valid_uuid(tenant_id), status, reason),
            )
    except Exception as e:  # noqa: BLE001 — audit logging must never break the caller-facing response
        logger.warning("mint_rejections insert failed: %s", e)


def record_admin_action(
    conn: psycopg.Connection, *, admin_id: str, action: str, detail: dict | None = None
) -> None:
    conn.execute(
        "insert into admin_audit_log (admin_id, action, detail) values (%s, %s, %s)",
        (admin_id, action, json.dumps(detail) if detail is not None else None),
    )
