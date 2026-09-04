"""Fixed, platform-owned tool functions (ADR-013 / ADR-029).

Platform lifecycle tools (end / escalate) always register.
Client business tools (RAG/FAQ + scheduling) register only when the agent has a
``tools_base_url`` (or local-dev env fallback). Docstrings + SYSTEM_INSTRUCTIONS
gate *when* the LLM may call them so greeting turns stay tool-free and fast.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import psycopg
from livekit.agents import RunContext
from livekit.agents.llm.tool_context import function_tool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dbconn import conn_kwargs  # noqa: E402

# Tight budgets: tool RTT sits on the critical path before the second LLM+TTS turn.
_TOOL_TIMEOUT = httpx.Timeout(connect=1.0, read=4.0, write=2.0, pool=1.0)
_TOOL_LIMITS = httpx.Limits(max_keepalive_connections=8, max_connections=16)
_RAG_RESULT_MAX_CHARS = 1000

_http_client: httpx.AsyncClient | None = None
_http_client_loop_id: int | None = None


@dataclass
class AgentUserdata:
    """Per-session context from RLS-verified AgentConfig — never from tool args."""

    tenant_id: str
    agent_id: str
    room_name: str
    ended_by_agent: bool = False
    latency_tracker: Any = None
    tools_base_url: str | None = None
    tools_auth_secret: str | None = None


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
    cannot resolve yourself, or explicitly asked to speak to a person. Speak a short spoken
    line first (you are getting them help), THEN call this tool — never sit in silence.

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


def _env_tools_base_url() -> str | None:
    raw = (os.getenv("UVA_TOOLS_BASE_URL") or "").strip()
    return raw.rstrip("/") if raw else None


def _env_tools_auth_secret() -> str | None:
    secret = (os.getenv("TOOL_GATEWAY_SECRET") or "").strip()
    return secret or None


def resolve_tools_base_url(agent_url: str | None) -> str | None:
    raw = (agent_url or "").strip().rstrip("/") or None
    return raw or _env_tools_base_url()


def resolve_tools_auth_secret(agent_secret: str | None) -> str | None:
    raw = (agent_secret or "").strip() or None
    return raw or _env_tools_auth_secret()


def _tool_gateway_headers(secret: str | None) -> dict[str, str]:
    if not secret:
        return {}
    return {"x-tool-gateway-secret": secret}


async def _shared_http_client() -> httpx.AsyncClient:
    """Reuse one keep-alive client per event loop (avoids TLS handshake each tool call)."""
    global _http_client, _http_client_loop_id
    loop_id = id(asyncio.get_running_loop())
    if (
        _http_client is None
        or _http_client.is_closed
        or _http_client_loop_id != loop_id
    ):
        if _http_client is not None and not _http_client.is_closed:
            try:
                await _http_client.aclose()
            except Exception:
                pass
        _http_client = httpx.AsyncClient(timeout=_TOOL_TIMEOUT, limits=_TOOL_LIMITS)
        _http_client_loop_id = loop_id
    return _http_client


def _slim_tool_result(body: Any) -> dict:
    """Cut tool JSON before the second LLM turn — voiceSummary + essentials only."""
    if not isinstance(body, dict):
        return {"result": body}

    out: dict[str, Any] = {}
    if body.get("voiceSummary"):
        out["voiceSummary"] = body["voiceSummary"]
    for key in ("success", "available", "error", "confirmationCode", "found"):
        if key in body:
            out[key] = body[key]

    result = body.get("result")
    if isinstance(result, str):
        text = result.strip()
        if len(text) > _RAG_RESULT_MAX_CHARS:
            text = text[:_RAG_RESULT_MAX_CHARS].rstrip() + "…"
        out["result"] = text
    elif result is not None and "voiceSummary" not in out:
        out["result"] = result

    slots = body.get("slots") or body.get("availableSlots") or body.get("offeredSlots")
    if isinstance(slots, list) and slots:
        slim_slots: list[Any] = []
        for slot in slots[:4]:
            if isinstance(slot, dict):
                slim_slots.append(
                    {
                        k: slot[k]
                        for k in (
                            "startTime",
                            "start_time",
                            "label",
                            "display",
                            "voiceLabel",
                        )
                        if k in slot
                    }
                    or slot
                )
            else:
                slim_slots.append(slot)
        out["slots"] = slim_slots

    return out or {"success": body.get("success", True)}


async def _post_client_tool(
    ctx: RunContext[AgentUserdata],
    *,
    path: str,
    payload: dict[str, Any],
    tool_name: str,
) -> dict:
    ud = ctx.userdata
    base = resolve_tools_base_url(ud.tools_base_url)
    if not base:
        return {"error": f"{tool_name} is not configured for this agent"}

    secret = resolve_tools_auth_secret(ud.tools_auth_secret)
    tracker = getattr(ud, "latency_tracker", None)
    t0 = time.monotonic()
    url = f"{base}{path}"
    body: dict[str, Any] = {
        "tenant_id": ud.tenant_id,
        "agent_id": ud.agent_id,
        **payload,
    }
    try:
        client = await _shared_http_client()
        response = await client.post(
            url,
            headers=_tool_gateway_headers(secret),
            json=body,
        )
        response.raise_for_status()
        raw = response.json()
    except Exception as exc:
        return {"error": f"{tool_name} failed: {exc}", "success": False}
    finally:
        if tracker is not None:
            duration_ms = int(round((time.monotonic() - t0) * 1000))
            tracker.record_tool_duration(tool_name, duration_ms)

    return _slim_tool_result(raw)


@function_tool
async def lookup_business_info(ctx: RunContext[AgentUserdata], query: str) -> dict:
    """Look up FAQ, policies, hours, pricing, or document facts from the business knowledge base.

    Call ONLY for a specific factual question you cannot answer from your persona text.
    Do NOT call for greetings, small talk, appointment booking, or availability.

    Args:
        query: The caller's factual question in their own words (keep it short).
    """
    return await _post_client_tool(
        ctx,
        path="/api/tools/lookup_business_info",
        payload={"query": query},
        tool_name="lookup_business_info",
    )


@function_tool
async def check_availability(
    ctx: RunContext[AgentUserdata],
    date: str,
    time_of_day: str = "any",
    service_name: str | None = None,
) -> dict:
    """Check live calendar availability for a booking date.

    Call ONLY when the caller asks what times are open, or right before offering slots.
    Do NOT call for general hours questions (use lookup_business_info or persona instead).
    Do NOT call until you have at least a preferred date (YYYY-MM-DD or clear relative date).

    Args:
        date: Preferred date as YYYY-MM-DD when possible.
        time_of_day: morning, afternoon, evening, or any.
        service_name: Service type if the caller named one; omit if unknown.
    """
    payload: dict[str, Any] = {
        "date": date,
        "time_of_day": time_of_day or "any",
        "hold_offered_slots": True,
    }
    if service_name:
        payload["service_name"] = service_name
    return await _post_client_tool(
        ctx,
        path="/api/tools/check_availability",
        payload=payload,
        tool_name="check_availability",
    )


@function_tool
async def book_appointment(
    ctx: RunContext[AgentUserdata],
    customer_name: str,
    customer_phone: str,
    slot_start_time: str,
    service_name: str | None = None,
) -> dict:
    """Book a confirmed appointment slot on the live calendar.

    Call ONLY after the caller confirmed the exact slot and you have name + phone.
    Do NOT call to "check" availability — use check_availability first.
    Do NOT claim a booking succeeded unless this tool returns success.

    Args:
        customer_name: Caller's name as confirmed.
        customer_phone: Caller's phone as confirmed (digits).
        slot_start_time: ISO start time of the chosen slot from check_availability.
        service_name: Service if known.
    """
    payload: dict[str, Any] = {
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "slot_start_time": slot_start_time,
    }
    if service_name:
        payload["service_name"] = service_name
    return await _post_client_tool(
        ctx,
        path="/api/tools/book_slot",
        payload=payload,
        tool_name="book_appointment",
    )


@function_tool
async def reschedule_appointment(
    ctx: RunContext[AgentUserdata],
    customer_phone: str,
    new_slot_start_time: str,
    existing_date: str | None = None,
    service_name: str | None = None,
) -> dict:
    """Move an existing appointment to a new slot.

    Call ONLY when the caller wants to change an existing booking and you have their phone
    plus the new slot time. Prefer check_availability first for the new day.

    Args:
        customer_phone: Phone on the existing booking.
        new_slot_start_time: ISO start time of the new slot.
        existing_date: Original appointment date if known (YYYY-MM-DD).
        service_name: Service if known.
    """
    payload: dict[str, Any] = {
        "customer_phone": customer_phone,
        "new_slot_start_time": new_slot_start_time,
    }
    if existing_date:
        payload["existing_date"] = existing_date
    if service_name:
        payload["service_name"] = service_name
    return await _post_client_tool(
        ctx,
        path="/api/tools/reschedule_appointment",
        payload=payload,
        tool_name="reschedule_appointment",
    )


@function_tool
async def cancel_appointment(
    ctx: RunContext[AgentUserdata],
    customer_phone: str,
    existing_date: str | None = None,
    reason: str | None = None,
) -> dict:
    """Cancel an existing appointment.

    Call ONLY when the caller clearly wants to cancel and you have their phone.
    Do NOT call for rescheduling — use reschedule_appointment.

    Args:
        customer_phone: Phone on the booking.
        existing_date: Appointment date if known (YYYY-MM-DD).
        reason: Optional short cancellation reason.
    """
    payload: dict[str, Any] = {"customer_phone": customer_phone}
    if existing_date:
        payload["existing_date"] = existing_date
    if reason:
        payload["reason"] = reason
    return await _post_client_tool(
        ctx,
        path="/api/tools/cancel_appointment",
        payload=payload,
        tool_name="cancel_appointment",
    )


FIXED_TOOLS = [end_conversation_summary, escalate_to_human]

CLIENT_TOOLS = [
    lookup_business_info,
    check_availability,
    book_appointment,
    reschedule_appointment,
    cancel_appointment,
]


def session_tools(*, tools_base_url: str | None = None) -> list[Any]:
    """Lifecycle tools always; RAG + scheduling only when a tools gateway is configured."""
    tools: list[Any] = list(FIXED_TOOLS)
    if resolve_tools_base_url(tools_base_url):
        tools.extend(CLIENT_TOOLS)
    return tools
