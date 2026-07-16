"""Load a tenant's agent config for a worker session — RLS-scoped (docs/23-PHASE-3-WORKER.md).

The agent's ``prompt`` is UNTRUSTED tenant text (31-GUIDE-SECURITY.md §4): it is returned as DATA
and must go into the assistant persona slot only — never concatenated into our system instructions
or a tool definition. The read is RLS-scoped (the Supabase ``authenticated`` role + a ``tenant_id``
JWT claim), so an agent_id that does not belong to the tenant is invisible and raises
``AgentNotFound`` — a worker-layer IDOR guard on top of the mint's.

Sync on purpose: psycopg async cannot run on Windows' ProactorEventLoop. The async worker calls this
via ``asyncio.to_thread`` (see worker/main.py), which keeps the DB read off the event loop and works
on every platform.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dbconn import conn_kwargs  # noqa: E402


class AgentNotFound(Exception):
    """The agent_id is not visible to this tenant (wrong tenant, or it does not exist)."""


@dataclass(frozen=True)
class AgentConfig:
    agent_id: str
    tenant_id: str
    name: str
    prompt: (
        str  # UNTRUSTED tenant text — persona slot ONLY, never our instructions/tools
    )
    voice_id: str
    llm_model: str


def load_agent_config(agent_id: str, tenant_id: str) -> AgentConfig:
    """Read this tenant's agent, RLS-scoped. Raises AgentNotFound if it isn't the tenant's."""
    claims = json.dumps({"tenant_id": tenant_id})
    with psycopg.connect(**conn_kwargs(), connect_timeout=10) as conn:
        cur = conn.cursor()
        cur.execute("set local role authenticated")
        cur.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
        cur.execute(
            "select id, tenant_id, name, prompt, voice_id, llm_model from agents where id = %s",
            (agent_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise AgentNotFound(f"agent {agent_id} not visible to tenant {tenant_id}")
    return AgentConfig(
        agent_id=str(row[0]),
        tenant_id=str(row[1]),
        name=row[2],
        prompt=row[3],
        voice_id=row[4],
        llm_model=row[5],
    )
