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
from dataclasses import dataclass, field
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
    # Additive, Phase 2 of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).
    # Defaults match Phase 1's DB backfill (0016) exactly, so any EXISTING caller that
    # constructs AgentConfig with only the original 6 fields (e.g. tests/test_worker.py's
    # test_persona_injected_as_data_not_system_instructions / test_build_agent_wires_fixed_tools
    # — real pre-existing tests, must not be edited to accommodate this) keeps working unchanged.
    # `tts_voice_id` can be NULL for an agent created after migration 0016 but before Phase 3's
    # app-layer sync ships — callers must resolve `tts_voice_id or voice_id`, never assume it's
    # populated (see 0016_agents_provider_fields.sql's own comment).
    agent_language: str = "ur"
    stt_provider: str = "gladia"
    stt_model: str = "default"
    stt_options: dict = field(default_factory=dict)
    llm_provider: str = "gemini"
    llm_options: dict = field(default_factory=dict)
    tts_provider: str = "uplift"
    tts_voice_id: str | None = None
    tts_options: dict = field(default_factory=dict)
    # Tenant session opening. greeting is UNTRUSTED (TTS input only). first_speaker defaults
    # to "agent" so existing AgentConfig(...) callers keep the current greet-immediately behavior.
    greeting: str | None = None
    first_speaker: str = "agent"


def load_agent_config(agent_id: str, tenant_id: str) -> AgentConfig:
    """Read this tenant's agent, RLS-scoped. Raises AgentNotFound if it isn't the tenant's."""
    claims = json.dumps({"tenant_id": tenant_id})
    with psycopg.connect(**conn_kwargs(), connect_timeout=10) as conn:
        cur = conn.cursor()
        cur.execute("set local role authenticated")
        cur.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
        cur.execute(
            "select id, tenant_id, name, prompt, voice_id, llm_model, "
            "agent_language, stt_provider, stt_model, stt_options, "
            "llm_provider, llm_options, tts_provider, tts_voice_id, tts_options, "
            "greeting, first_speaker "
            "from agents where id = %s",
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
        agent_language=row[6],
        stt_provider=row[7],
        stt_model=row[8],
        stt_options=row[9],
        llm_provider=row[10],
        llm_options=row[11],
        tts_provider=row[12],
        tts_voice_id=row[13],
        tts_options=row[14],
        greeting=row[15],
        first_speaker=row[16] or "agent",
    )
