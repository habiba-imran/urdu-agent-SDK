"""F-C7 Phase F harness: hostile / unsolicited write-tool calls must not POST.

This is the deterministic half of F.1 (plan: adapt live injection *or* a harness).
It does not call a paid LLM. It invokes the real gated write tools the way an
injected persona could force the model to call them on turn one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from worker.tools import AgentUserdata, book_appointment, cancel_appointment
from worker.write_tool_gate import note_user_turn, set_verified_caller_phone


def _ud(**kwargs) -> AgentUserdata:
    base = dict(
        tenant_id="t1",
        agent_id="a1",
        room_name="room-injection",
        tools_base_url="http://example.test",
    )
    base.update(kwargs)
    return AgentUserdata(**base)


@pytest.mark.asyncio
async def test_hostile_first_turn_book_does_not_post(monkeypatch):
    posts: list[dict] = []

    async def fake_post(ctx, *, path, payload, tool_name, idempotency_key=None):
        posts.append({"tool_name": tool_name, "path": path})
        return {"success": True}

    monkeypatch.setattr("worker.tools._post_client_tool", fake_post)
    ud = _ud()
    ctx = SimpleNamespace(userdata=ud)

    # Hostile persona: book immediately with attacker-chosen phone — propose only.
    out = await book_appointment.__wrapped__(
        ctx,
        customer_name="Attacker",
        customer_phone="+15551234567",
        slot_start_time="2026-09-18T10:00:00",
    )
    assert out.get("needs_confirmation") is True
    assert posts == []


@pytest.mark.asyncio
async def test_hostile_same_turn_confirm_does_not_post(monkeypatch):
    posts: list[dict] = []

    async def fake_post(ctx, *, path, payload, tool_name, idempotency_key=None):
        posts.append({"tool_name": tool_name})
        return {"success": True}

    monkeypatch.setattr("worker.tools._post_client_tool", fake_post)
    ud = _ud()
    ctx = SimpleNamespace(userdata=ud)

    propose = await book_appointment.__wrapped__(
        ctx,
        customer_name="Attacker",
        customer_phone="+15551234567",
        slot_start_time="2026-09-18T10:00:00",
    )
    # Same LLM turn double-call with confirmation_id — must not POST.
    out = await book_appointment.__wrapped__(
        ctx,
        customer_name="Attacker",
        customer_phone="+15551234567",
        slot_start_time="2026-09-18T10:00:00",
        confirmation_id=propose["confirmation_id"],
    )
    assert out.get("success") is False
    assert posts == []


@pytest.mark.asyncio
async def test_hostile_cancel_other_phone_does_not_post(monkeypatch):
    posts: list[dict] = []

    async def fake_post(ctx, *, path, payload, tool_name, idempotency_key=None):
        posts.append({"tool_name": tool_name})
        return {"success": True}

    monkeypatch.setattr("worker.tools._post_client_tool", fake_post)
    ud = _ud()
    set_verified_caller_phone(ud, "+923001111111")
    ctx = SimpleNamespace(userdata=ud)

    out = await cancel_appointment.__wrapped__(
        ctx,
        customer_phone="+923009999999",  # injection: cancel someone else
    )
    assert out.get("success") is False
    assert "match" in (out.get("error") or "").lower() or "verified" in (
        out.get("error") or ""
    ).lower()
    assert posts == []


@pytest.mark.asyncio
async def test_hostile_cancel_without_identity_does_not_post(monkeypatch):
    posts: list[dict] = []

    async def fake_post(ctx, *, path, payload, tool_name, idempotency_key=None):
        posts.append({"tool_name": tool_name})
        return {"success": True}

    monkeypatch.setattr("worker.tools._post_client_tool", fake_post)
    ud = _ud()  # no verified_caller_phone (browser without A.4)
    ctx = SimpleNamespace(userdata=ud)

    out = await cancel_appointment.__wrapped__(
        ctx,
        customer_phone="+923001234567",
    )
    assert out.get("success") is False
    assert posts == []


@pytest.mark.asyncio
async def test_legitimate_confirm_after_user_turn_posts_once(monkeypatch):
    posts: list[dict] = []

    async def fake_post(ctx, *, path, payload, tool_name, idempotency_key=None):
        posts.append(
            {
                "tool_name": tool_name,
                "idempotency_key": idempotency_key,
            }
        )
        return {"success": True, "voiceSummary": "booked"}

    monkeypatch.setattr("worker.tools._post_client_tool", fake_post)
    ud = _ud()
    ctx = SimpleNamespace(userdata=ud)

    propose = await book_appointment.__wrapped__(
        ctx,
        customer_name="Ali",
        customer_phone="+923001234567",
        slot_start_time="2026-09-18T10:00:00",
    )
    note_user_turn(ud)  # caller said yes
    out = await book_appointment.__wrapped__(
        ctx,
        customer_name="Ali",
        customer_phone="+923001234567",
        slot_start_time="2026-09-18T10:00:00",
        confirmation_id=propose["confirmation_id"],
    )
    assert out.get("success") is True
    assert len(posts) == 1
    assert posts[0]["idempotency_key"]
