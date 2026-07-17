"""Supabase data access layer.

🔴 REMOVED IN PHASE 7 (ADR-022, 2026-07-18): ``get_client()`` used to lazily construct a real,
live Supabase client authenticated with ``SUPABASE_SERVICE_ROLE_KEY`` — a credential that bypasses
RLS by design (ADR-005). ``worker/`` never imports this module or ``tools.py`` (grep-confirmed,
docs/40-ADR.md ADR-022), so that client was live-capable, RLS-bypassing, dead code: reachable only
through the ADR-013-deferred, already-broken (old-schema) CER harness, never through any served
path. Removed rather than left sitting there "for later" per explicit instruction. The public API
surface below (``DBTimeout``, ``get_client``, ``timed_read``, ``fire_and_forget``, and the
``record_*``/``_insert_*``/``_end_*`` functions) is kept so ``import db`` / ``from db import
DBTimeout`` (tools.py, tests/helpers*.py) still succeed at import time — only ``get_client()``'s
BODY changed, from "silently connect with a live RLS-bypassing credential" to "raise loudly and
explain why." A real client, scoped correctly for whatever this module's next form needs, is
ADR-013's job when that pass actually happens — not something to quietly reintroduce as a
side-effect of some other change.

Latency rules (STEP 3), unchanged from before removal, apply again once a real client returns:
- READS inside tools go through ``timed_read`` — 2.5 s asyncio timeout so a slow network
  can never stall the voice loop; callers catch ``DBTimeout`` and speak a graceful fallback.
- Conversation/metrics WRITES go through ``fire_and_forget`` — scheduled with
  ``asyncio.create_task`` and never awaited inside the response path.
- Tool writes that must return an id (reservation/ticket/callback) are awaited but happen
  during the spoken filler line, off the first-audio critical path (see DECISIONS.md D8).
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

from loguru import logger

import config  # TOOL_READ_TIMEOUT_SECS only — SUPABASE_SERVICE_ROLE_KEY no longer read here


class DBTimeout(Exception):
    """A Supabase read exceeded the tool read timeout."""


class DBClientRemoved(Exception):
    """get_client()'s live, service_role-backed client was removed in Phase 7 (ADR-022) — see
    this module's docstring. Reintroducing a real client is ADR-013's deferred tools.py pass."""


async def get_client():
    """REMOVED — see module docstring and docs/40-ADR.md ADR-022. Always raises."""
    raise DBClientRemoved(
        "db.py's live service_role-backed Supabase client was intentionally removed in "
        "Phase 7 (ADR-022) — it was unreachable dead code (worker/ never imports this "
        "module) carrying a live, RLS-bypassing credential. Not reintroduced here; the "
        "ADR-013-deferred tools.py rework is where a properly-scoped replacement belongs."
    )


async def timed_read(coro: Coroutine, what: str = "read") -> Any:
    """Await a Supabase read with the 2.5 s tool timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=config.TOOL_READ_TIMEOUT_SECS)
    except asyncio.TimeoutError as e:
        logger.warning(
            f"Supabase {what} timed out after {config.TOOL_READ_TIMEOUT_SECS}s"
        )
        raise DBTimeout(what) from e


def fire_and_forget(coro: Coroutine, what: str = "write"):
    """Schedule a Supabase write without awaiting it in the response path."""

    async def _run():
        try:
            await coro
        except Exception as e:
            logger.error(f"fire-and-forget {what} failed: {e}")

    asyncio.create_task(_run(), name=f"db-{what}")


# --- Conversation persistence -------------------------------------------------


async def _insert_conversation(conversation_id: str, channel: str):
    client = await get_client()
    await (
        client.table("conversations")
        .insert({"id": conversation_id, "channel": channel})
        .execute()
    )


def record_conversation_start(conversation_id: str, channel: str = "webrtc"):
    fire_and_forget(
        _insert_conversation(conversation_id, channel), "conversation-start"
    )


async def _end_conversation(conversation_id: str, summary: str | None):
    client = await get_client()
    patch: dict[str, Any] = {"ended_at": "now()"}
    if summary:
        patch["summary"] = summary
    await (
        client.table("conversations").update(patch).eq("id", conversation_id).execute()
    )


def record_conversation_end(conversation_id: str, summary: str | None = None):
    fire_and_forget(_end_conversation(conversation_id, summary), "conversation-end")


async def _insert_message(conversation_id: str, role: str, content: str):
    client = await get_client()
    await (
        client.table("messages")
        .insert({"conversation_id": conversation_id, "role": role, "content": content})
        .execute()
    )


def record_message(conversation_id: str, role: str, content: str):
    if content and content.strip():
        fire_and_forget(
            _insert_message(conversation_id, role, content.strip()), "message"
        )


async def _insert_turn_metrics(row: dict):
    client = await get_client()
    await client.table("turn_metrics").insert(row).execute()


def record_turn_metrics(row: dict):
    fire_and_forget(_insert_turn_metrics(row), "turn-metrics")
