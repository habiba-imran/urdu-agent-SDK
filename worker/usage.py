"""Emit usage_events for a session (P3-T07). The billing truth — append-only.

A call writes stt_sec / tts_sec / llm_tokens / agent_sec rows. Written as the DB owner (a trusted
billing write that crosses tenants by design, ADR-005), not through RLS.

Sync on purpose (psycopg async cannot use Windows' ProactorEventLoop); the async worker calls this
via asyncio.to_thread.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dbconn import conn_kwargs  # noqa: E402

KINDS = ("stt_sec", "tts_sec", "llm_tokens", "agent_sec")


def record_usage(tenant_id: str, session_id: str | None, kind: str, qty: float) -> None:
    if kind not in KINDS:
        raise ValueError(f"bad usage kind {kind!r}; must be one of {KINDS}")
    with psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        conn.execute(
            "insert into usage_events (tenant_id, session_id, kind, qty) values (%s, %s, %s, %s)",
            (tenant_id, session_id, kind, qty),
        )
