"""Supabase data access layer.

Latency rules (STEP 3):
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

from supabase import AsyncClient, create_async_client  # supabase v2 API

import config

_client: AsyncClient | None = None
_client_lock = asyncio.Lock()


class DBTimeout(Exception):
    """A Supabase read exceeded the tool read timeout."""


async def get_client() -> AsyncClient:
    """Lazily create the shared async Supabase client (service role)."""
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = await create_async_client(
                    config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY
                )
    return _client


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
