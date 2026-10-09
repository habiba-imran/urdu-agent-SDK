"""Phase 2 AwaazAgent through the installed AgentSession speech pipeline."""

from __future__ import annotations

import asyncio

from livekit.agents import Agent, AgentSession, llm
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from test_humanization_observability_framework import SyntheticSink, SyntheticTTS
from worker.humanization.agent import AwaazAgent
from worker.humanization.policy import resolve_humanization_policy
from worker.humanization.runtime import HumanizationRuntime
from worker.tools import AgentUserdata


class TextLLM(llm.LLM):
    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
        return TextStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class TextStream(llm.LLMStream):
    async def _run(self):
        self._event_ch.send_nowait(llm.ChatChunk(id="reply", delta=llm.ChoiceDelta(content="The requested answer.")))


def test_baseline_and_awaaz_agent_produce_same_synthetic_audio_and_history():
    async def run(agent_type):
        ud = AgentUserdata("tenant", "agent", "room")
        session = AgentSession(llm=TextLLM(), tts=SyntheticTTS(), userdata=ud)
        sink = SyntheticSink()
        session.output.audio = sink
        runtime = None
        if agent_type is AwaazAgent:
            runtime = HumanizationRuntime(
                tenant_id="tenant", agent_id="agent", session_id="room", language="en",
                channel="webrtc", policy=resolve_humanization_policy(environ={}),
            )
            ud.humanization_runtime = runtime
            runtime.attach_session(session)
        agent = agent_type(instructions="Use plain speech.")
        await session.start(agent, record=False)
        try:
            handle = session.generate_reply(user_input="Question")
            await asyncio.wait_for(handle.wait_for_playout(), timeout=5)
            assert handle.exception() is None
            result = [(m.role, m.text_content) for m in session.history.messages() if m.role in {"user", "assistant"}]
            return sink.frames, result, runtime
        finally:
            await session.aclose()

    baseline_frames, baseline_history, _ = asyncio.run(run(Agent))
    awaaz_frames, awaaz_history, runtime = asyncio.run(run(AwaazAgent))
    assert baseline_frames == awaaz_frames and baseline_frames > 0
    assert baseline_history == awaaz_history
    assert runtime is not None and runtime.state.session_closed
    assert runtime.policy.effective_version == "baseline"
