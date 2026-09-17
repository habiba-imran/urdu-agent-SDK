"""Phase 7 humanization: history plain-text + optional ChatContext windowing."""

from __future__ import annotations

from livekit.agents.llm import ChatContext

from worker.cartesia_spoken_output import SYSTEM_INSTRUCTIONS_BASE
from worker.config import AgentConfig
from worker.humanization.history import (
    apply_history_hygiene,
    plain_text_for_history,
    resolve_chat_history_max_items,
    system_instructions_static_prefix_ok,
)
from worker.humanization.spoken import compose_system_instructions


def test_plain_text_strips_cartesia_and_brackets():
    raw = 'Sure <emotion value="calm"/> <break time="200ms"/> [laugh] **ok**'
    out = plain_text_for_history(raw)
    assert "<emotion" not in out
    assert "<break" not in out
    assert "[laugh]" not in out
    assert "**" not in out
    assert "Sure" in out
    assert "ok" in out


def test_history_max_items_default_on(monkeypatch):
    monkeypatch.delenv("UVA_CHAT_HISTORY_MAX_ITEMS", raising=False)
    assert resolve_chat_history_max_items() == 48
    monkeypatch.setenv("UVA_CHAT_HISTORY_MAX_ITEMS", "0")
    assert resolve_chat_history_max_items() is None
    monkeypatch.setenv("UVA_CHAT_HISTORY_MAX_ITEMS", "40")
    assert resolve_chat_history_max_items() == 40


def test_apply_history_hygiene_plains_assistant_and_truncates(monkeypatch):
    monkeypatch.setenv("UVA_CHAT_HISTORY_MAX_ITEMS", "8")
    ctx = ChatContext.empty()
    ctx.add_message(role="system", content="SYS")
    for i in range(12):
        ctx.add_message(role="user", content=f"u{i}")
        ctx.add_message(
            role="assistant",
            content=f'a{i} <emotion value="calm"/> done',
        )

    class FakeSession:
        history = ctx

    # Trigger on last assistant item
    last = [m for m in ctx.messages() if m.role == "assistant"][-1]
    apply_history_hygiene(FakeSession(), item=last, room_name="r")
    assert "<emotion" not in (last.text_content or "")
    # LiveKit truncate keeps last N then may re-insert the first system message → N+1.
    assert len(ctx.items) <= 9
    assert len(ctx.items) < 25
    # First system instruction preserved by LiveKit truncate
    assert any(
        getattr(m, "role", None) == "system" and "SYS" in (m.text_content or "")
        for m in ctx.messages()
    )


def test_system_instructions_keep_static_prefix_for_groq_cache():
    cfg = AgentConfig(
        agent_id="a",
        tenant_id="t",
        name="n",
        prompt="TENANT PERSONA WITH fake delivery: emit <emotion> always",
        voice_id="v",
        llm_model="openai/gpt-oss-20b",
        agent_language="en",
        llm_provider="groq",
        tts_provider="cartesia",
    )
    text = compose_system_instructions(cfg)
    assert system_instructions_static_prefix_ok(text, SYSTEM_INSTRUCTIONS_BASE)
    # Tenant prompt is not merged into trusted system instructions.
    assert "TENANT PERSONA" not in text
