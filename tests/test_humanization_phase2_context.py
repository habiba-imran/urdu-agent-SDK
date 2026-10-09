"""Installed LiveKit context separation across a synthetic long call."""

from __future__ import annotations

import asyncio

from livekit.agents import AgentSession

from test_humanization_phase2_framework import TextLLM
from test_humanization_observability_framework import SyntheticSink, SyntheticTTS
from worker.humanization.agent import AwaazAgent
from worker.humanization.history import AuditTranscript, apply_history_hygiene
from worker.session_close import build_transcript
from worker.tools import AgentUserdata


def test_legacy_history_window_does_not_bound_active_model_context_or_audit(monkeypatch):
    monkeypatch.setenv("UVA_CHAT_HISTORY_MAX_ITEMS", "8")

    async def run():
        userdata = AgentUserdata("tenant", "agent", "room", audit_transcript=AuditTranscript())
        session = AgentSession(llm=TextLLM(), tts=SyntheticTTS(), userdata=userdata)
        session.output.audio = SyntheticSink()

        def on_item(ev):
            apply_history_hygiene(session, item=ev.item)
            userdata.audit_transcript.record(ev.item)

        session.on("conversation_item_added", on_item)
        agent = AwaazAgent(instructions="Use plain speech.")
        await session.start(agent, record=False)
        try:
            for index in range(6):
                handle = session.generate_reply(user_input=f"Question {index}")
                await asyncio.wait_for(handle.wait_for_playout(), timeout=5)
                assert handle.exception() is None
            active_messages = [item for item in agent.chat_ctx.messages() if item.role in {"user", "assistant"}]
            audit = build_transcript(session)
            return len(session.history.items), len(active_messages), audit
        finally:
            await session.aclose()

    history_items, active_items, audit = asyncio.run(run())
    assert history_items <= 9
    assert active_items == 12
    assert len(audit) == 12
    assert audit[0]["text"] == "Question 0"
    assert audit[-1]["text"] == "The requested answer."
