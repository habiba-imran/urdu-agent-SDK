"""Fixed, platform-owned tool functions (ADR-013 deferred pass, scope decided ADR-029).

NOT a rebuild of the old ported root-level `tools.py` (TechZone demo: search_products,
create_reservation, etc.) — that file queries tables (`products`, `customers`, `reservations`,
...) that were never part of this project's real schema and are not being added now (ADR-029:
this SDK's own spec gives a tenant only `(prompt, voiceId)`, no business-domain concept). These
two tools are deliberately minimal and domain-agnostic — every tenant's agent gets the same two,
regardless of what business they run.

Built on LiveKit's real function-calling API (`@function_tool`, typed mode — verified against
installed `livekit-agents` 1.6.5 source, not guessed): a `RunContext[AgentUserdata]`-typed first
parameter is auto-detected and excluded from the LLM-visible schema
(`llm/utils.py::function_arguments_to_pydantic_model`, `is_context_type(...)`); every other typed
parameter becomes a real tool argument. Handlers return their result directly — no
`result_callback`.

DB access matches `worker/usage.py`'s established, human-reviewed pattern: a trusted DB-owner
write via `dbconn.conn_kwargs()` (ADR-005), `tenant_id` always taken from `AgentUserdata` (itself
populated from the RLS-scoped `AgentConfig` at session-build time, never from tool-call
arguments), never from anything the model or the tenant prompt could influence.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg
from livekit.agents import RunContext
from livekit.agents.llm.tool_context import function_tool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dbconn import conn_kwargs  # noqa: E402


@dataclass
class AgentUserdata:
    """Per-session context threaded through AgentSession(userdata=...), read by tools via
    RunContext.userdata. Populated once at session-build time from data already RLS-verified
    (AgentConfig) — never from tenant prompt text or a tool argument."""

    tenant_id: str
    agent_id: str
    room_name: str
    # Set by end_conversation_summary so the shutdown path can record WHY the call ended.
    # Without it an agent-ended call lands in the DB as LiveKit's generic "user_initiated"
    # (its term for "closed via API"), which reads on the dashboard as if the caller hung up.
    ended_by_agent: bool = False


@function_tool
async def end_conversation_summary(
    ctx: RunContext[AgentUserdata], summary: str
) -> dict:
    """Call this ONLY when the conversation is genuinely over, AFTER you have already said your
    closing line to the caller. This HANGS UP — the caller cannot say anything else once you
    call it, so never call it mid-conversation or to acknowledge something.

    Args:
        summary: One sentence describing what the conversation was about.
    """
    ud = ctx.userdata
    with psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        conn.execute(
            "update sessions set summary = %s where room_name = %s and tenant_id = %s",
            (summary, ud.room_name, ud.tenant_id),
        )

    # Actually END the call. Before this, the tool only wrote a summary string despite its name:
    # the session stayed open, the agent sat there after its goodbye, and the session row stayed
    # `ended_at IS NULL` — so the dashboard kept showing a live call until the caller happened to
    # hang up (or forever, if they just closed the tab).
    #
    # `AgentSession.shutdown(drain=True)` is the public API for this (agent_session.py L1006-1007
    # -> `_close_soon(reason=USER_INITIATED, drain=drain)`); `drain=True` lets in-flight speech
    # finish via `AgentActivity.drain()` rather than cutting the audio mid-word. It is sync — it
    # schedules the close and returns, so this tool still returns its result to the LLM normally.
    #
    # Closing the session is what makes the rest work: it emits AgentSession's "close" event,
    # which worker/main.py turns into `JobContext.shutdown()`, which fires the shutdown callbacks
    # that close the session row and release the concurrency slot.
    ud.ended_by_agent = True
    session = getattr(ctx, "session", None)
    if session is not None:
        session.shutdown(drain=True)
    return {"status": "saved"}


@function_tool
async def escalate_to_human(
    ctx: RunContext[AgentUserdata], reason: str, contact_info: str | None = None
) -> dict:
    """Call this when the caller needs a human to follow up -- they asked for something you
    cannot resolve yourself, or explicitly asked to speak to a person.

    Args:
        reason: A short description of what the caller needs.
        contact_info: How to reach them, if they gave it (phone number, etc). Omit if not given.
    """
    ud = ctx.userdata
    with psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        row = conn.execute(
            "select id from sessions where room_name = %s and tenant_id = %s",
            (ud.room_name, ud.tenant_id),
        ).fetchone()
        session_id = row[0] if row else None
        conn.execute(
            "insert into escalations (tenant_id, session_id, reason, contact_info) "
            "values (%s, %s, %s, %s)",
            (ud.tenant_id, session_id, reason, contact_info),
        )
    return {"status": "escalated"}


FIXED_TOOLS = [end_conversation_summary, escalate_to_human]
