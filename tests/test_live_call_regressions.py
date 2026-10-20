"""Offline regression evidence for the two English calls; no paid provider calls."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from livekit.agents import AgentSession, llm
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from test_humanization_observability_framework import SyntheticSink, SyntheticTTS
from worker.humanization.agent import AwaazAgent
from worker.humanization.policy import resolve_humanization_policy
from worker.humanization.runtime import HumanizationRuntime
from worker.humanization.turn_plan import conversational_signals
from worker.tools import AgentUserdata, end_conversation_summary
from worker.cartesia_spoken_output import SYSTEM_INSTRUCTIONS_BASE


class RefusingLLM(llm.LLM):
    """Scripted model output, not a semantic-quality evaluation of a live model."""
    def __init__(self, reply="I'm sorry, I can't provide that.", *, end_call=False):
        super().__init__()
        self.calls = 0
        self.reply = reply
        self.end_call = end_call
        self.contexts = []

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
        self.calls += 1
        self.contexts.append(chat_ctx.copy())
        return RefusingStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class RefusingStream(llm.LLMStream):
    async def _run(self):
        for text in self._llm.reply.split("|"):
            self._event_ch.send_nowait(llm.ChatChunk(id="fixture", delta=llm.ChoiceDelta(content=text)))
        if self._llm.end_call:
            from uuid import uuid4
            self._event_ch.send_nowait(llm.ChatChunk(id="fixture", delta=llm.ChoiceDelta(tool_calls=[
                llm.FunctionToolCall(name="end_conversation_summary", call_id="model_end_" + uuid4().hex,
                                     arguments=json.dumps({"summary": "Caller chose to finish."})),
            ])))


def make_runtime(language="en", channel="webrtc", policy="baseline"):
    return HumanizationRuntime(tenant_id="fixture_tenant", agent_id="fixture_agent",
                              session_id="fixture_room", language=language, channel=channel,
                              policy=resolve_humanization_policy(environ={"UVA_HUMANIZATION_POLICY_VERSION": policy}))


@pytest.mark.parametrize("text", [
    "Bye.", "No. That's all. Goodbye.", "No. That’s all. Good bye.", "Thank you, goodbye.",
    "شکریہ، خدا حافظ۔", "نہیں، بس اتنا ہی، اللہ حافظ۔", "Khuda hafiz", "Allah hafiz",
])
def test_local_delivery_cues_do_not_override_llm_ending_intent(text):
    rt = make_runtime()
    rt.observe("ground_unresolved", field_name="phone")
    rt.understand_turn("farewell", text)
    assert not rt.latest_signals.closing_intent
    assert rt.latest_plan.dialogue_act != "CLOSE"
    history = llm.ChatContext.empty()
    history.add_message(role="user", content=text)
    agent = AwaazAgent(instructions=SYSTEM_INSTRUCTIONS_BASE, humanization_runtime=rt)
    assert agent._conversational_stream(history, [end_conversation_summary], None) is None


@pytest.mark.parametrize("text", [
    "What does bye mean?", "Before I say goodbye, what are your hours?",
    "Bye, can you book Friday?", "Please tell my colleague goodbye.",
    "No, that's all wrong. Can you check Monday?", "خدا حافظ کہنے سے پہلے وقت بتائیں؟",
])
def test_farewell_mention_inside_another_request_does_not_close(text):
    assert not conversational_signals(text).closing_intent


@pytest.mark.parametrize("language,channel", [("en", "webrtc"), ("en", "telephony"), ("ur-PK", "webrtc"), ("mixed", "telephony")])
@pytest.mark.parametrize("policy", ["baseline", "conversational_v1"])
@pytest.mark.parametrize("text", ["Bye.", "That sorts it for me, cheers.", "I need to dash; let's leave it there.", "Shall we wrap up?", "اب اجازت دیں۔", "Hasta luego"])
def test_model_generated_goodbye_and_tool_close_after_playout(monkeypatch, language, channel, text, policy):
    async def run():
        events = []
        ud = AgentUserdata("fixture_tenant", "fixture_agent", "fixture_room")
        rt = make_runtime(language, channel, policy)
        ud.humanization_runtime = rt
        # The previously committed write must retain its truth through shutdown.
        rt.observe("tool_started", tool_call_id="prior_write")
        rt.observe("tool_result", tool_call_id="prior_write", outcome="SUCCESS", business_effect="committed", result_data={"booking": "fixture"})
        goodbye = "Take care, and enjoy the rest of your day." if language == "en" else "آپ کا دن اچھا گزرے، اپنا خیال رکھیے۔"
        model = RefusingLLM(goodbye, end_call=True)
        session = AgentSession(llm=model, tts=SyntheticTTS(), userdata=ud)
        sink = SyntheticSink()
        session.output.audio = sink
        closed = asyncio.Event()
        session.on("close", lambda event: (events.append("closed"), closed.set()))
        original_flush = sink.flush
        def flush():
            events.append("playout")
            original_flush()
        sink.flush = flush
        monkeypatch.setattr("worker.tools._save_conversation_summary", lambda **kw: events.append("summary"))
        rt.attach_session(session)
        agent = AwaazAgent(instructions=SYSTEM_INSTRUCTIONS_BASE, tools=[end_conversation_summary], humanization_runtime=rt)
        await session.start(agent, record=False)
        try:
            handle = session.generate_reply(user_input=text)
            await asyncio.wait_for(handle.wait_for_playout(), 5)
            await asyncio.wait_for(closed.wait(), 5)
            assert handle.exception() is None
            assert model.calls == 1  # No separate intent classifier or goodbye rewrite.
            assert any(SYSTEM_INSTRUCTIONS_BASE in m.text_content for m in model.contexts[0].messages() if m.role == "system")
            replies = [m.text_content for m in session.history.messages() if m.role == "assistant"]
            assert len(replies) == 1
            assert replies == [goodbye]
            assert not any("sorry" in reply or "can't" in reply for reply in replies)
            assert events.count("summary") == 1
            assert events.index("playout") < events.index("closed")
            assert ud.ended_by_agent
            assert rt.state.tool_state.calls["prior_write"].business_effect == "committed"
            assert rt.state.session_closed
        finally:
            await session.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("prior,text,should_close", [
    ("Anything else I can help you with?", "No, thank you", True),
    ("Should I book the appointment?", "No", False),
    ("Your appointment is booked.", "Thank you", False),
])
def test_contextual_completion_with_real_agent_session(monkeypatch, prior, text, should_close):
    async def run():
        model = RefusingLLM("Take care." if should_close else "Happy to help.", end_call=should_close)
        rt = make_runtime()
        ud = AgentUserdata("t", "a", "r", humanization_runtime=rt)
        session = AgentSession(llm=model, tts=SyntheticTTS(), userdata=ud)
        session.output.audio = SyntheticSink()
        closed = asyncio.Event()
        session.on("close", lambda ev: closed.set())
        agent = AwaazAgent(instructions=SYSTEM_INSTRUCTIONS_BASE,
                           tools=[end_conversation_summary], humanization_runtime=rt)
        monkeypatch.setattr("worker.tools._save_conversation_summary", lambda **kw: None)
        rt.attach_session(session)
        await session.start(agent, record=False)
        try:
            # Exercise a real spoken offer in the session history, not seeded text.
            offer = session.say(prior)
            await asyncio.wait_for(offer.wait_for_playout(), 5)
            speech = session.generate_reply(user_input=text)
            await asyncio.wait_for(speech.wait_for_playout(), 5)
            if should_close:
                await asyncio.wait_for(closed.wait(), 5)
                assert ud.ended_by_agent and model.calls == 1
            else:
                assert not closed.is_set() and not ud.ended_by_agent and model.calls == 1
            context_text = [m.text_content for m in model.contexts[0].messages()]
            assert prior in context_text and text in context_text
        finally:
            await session.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("text,language", [
    ("Are you an AI?", "en"), ("You don't sound like a human. Are you an AI?", "en"),
    ("Are you a human?", "en"), ("کیا آپ اے آئی ہیں؟", "ur-PK"),
])
def test_direct_ai_question_gets_truthful_identification_without_hangup(text, language):
    async def run():
        model = RefusingLLM("I'm one of the team members here.")
        ud = AgentUserdata("fixture_tenant", "fixture_agent", "fixture_room")
        rt = make_runtime(language)
        ud.humanization_runtime = rt
        session = AgentSession(llm=model, tts=SyntheticTTS(), userdata=ud)
        session.output.audio = SyntheticSink()
        agent = AwaazAgent(instructions="Adopt a receptionist persona.", tools=[end_conversation_summary], humanization_runtime=rt)
        await session.start(agent, record=False)
        try:
            handle = session.generate_reply(user_input=text)
            await asyncio.wait_for(handle.wait_for_playout(), 5)
            assert model.calls == 0 and not ud.ended_by_agent
            replies = [m.text_content for m in session.history.messages() if m.role == "assistant"]
            assert replies == ["I'm an AI assistant."] if language == "en" else replies == ["میں ایک اے آئی اسسٹنٹ ہوں۔"]
            assert rt.latest_plan.dialogue_act == "IDENTIFY_AI"
        finally:
            await session.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("markup", [
    '<emotion| value="calm"/>| Hi, thanks. <break| time="300ms"/> How can I help?',
    '[laugh|ter] Hi. spell(|ABC123) <emotion',
])
def test_baseline_partial_transcription_and_framework_history_are_canonical(markup):
    async def run():
        model = RefusingLLM(markup)
        provider_text = []
        class RecordingTTS(SyntheticTTS):
            def synthesize(self, text, **kwargs):
                provider_text.append(text)
                return super().synthesize(text, **kwargs)
        session = AgentSession(llm=model, tts=RecordingTTS())
        session.output.audio = SyntheticSink()
        agent = AwaazAgent(instructions="Fixture")
        await session.start(agent, record=False)
        try:
            # Every publication fragment must be plain, not only the final item.
            async def raw():
                for fragment in markup.split("|"):
                    yield fragment
            pieces = [p async for p in agent.transcription_node(raw(), NS())]
            assert pieces and all("<" not in p and "[laughter]" not in p and "spell(" not in p for p in pieces)
            handle = session.generate_reply(user_input="What are your hours?")
            await asyncio.wait_for(handle.wait_for_playout(), 5)
            replies = [m.text_content for m in session.history.messages() if m.role == "assistant"]
            assert replies and "<" not in replies[0] and "[laughter]" not in replies[0] and "spell(" not in replies[0]
            # The baseline TTS feed still receives its supported delivery controls.
            assert "emotion" in "".join(provider_text)
        finally:
            await session.aclose()
    asyncio.run(run())


def test_metrics_publication_is_explicit_and_configuration_is_logged(monkeypatch):
    from worker.latency import wire_turn_latency
    async def run():
        for enabled in (False, True):
            monkeypatch.setenv("UVA_PUBLISH_TURN_LATENCY", "1" if enabled else "0")
            session = AgentSession(llm=RefusingLLM("Opening fixture."), tts=SyntheticTTS(), userdata=AgentUserdata("t", "a", "r"))
            session.output.audio = SyntheticSink()
            room, logger = MagicMock(), MagicMock()
            agent = AwaazAgent(instructions="Fixture")
            snapshot = {"humanization_policy_version": "baseline", "delivery": {"policy_version": "baseline"}, "component_versions": {"streaming": "baseline"}}
            wire_turn_latency(session, room, logger, agent=agent, snapshot=snapshot)
            await session.start(agent, record=False)
            try:
                handle = session.generate_reply(user_input="What are your hours?")
                await asyncio.wait_for(handle.wait_for_playout(), 5)
                await asyncio.sleep(0)
                assert logger.info.call_args_list[0].args[1] is enabled
                rows = [json.loads(c.args[0]) for c in room.local_participant.publish_data.call_args_list if c.kwargs["topic"] == "turn_latency"]
                if enabled:
                    assert rows and rows[0]["stages"]["first_useful_llm_text"] is not None
                    assert rows[0]["stages"]["tts_first_audio"] is not None
                    assert rows[0]["ttsTtfbMs"] is not None
                    assert rows[0]["providerSnapshot"] == snapshot
                else:
                    assert not rows
            finally:
                await session.aclose()
    asyncio.run(run())



def test_closing_queues_behind_required_uninterruptible_disclosure(monkeypatch):
    async def run():
        ud = AgentUserdata("t", "a", "r")
        model = RefusingLLM("Wishing you a pleasant day.", end_call=True)
        session = AgentSession(llm=model, tts=SyntheticTTS(), userdata=ud)
        session.output.audio = SyntheticSink()
        closed = asyncio.Event()
        session.on("close", lambda event: closed.set())
        monkeypatch.setattr("worker.tools._save_conversation_summary", lambda **kw: None)
        agent = AwaazAgent(instructions="Fixture", tools=[end_conversation_summary], humanization_runtime=make_runtime())
        await session.start(agent, record=False)
        try:
            disclosure = session.say("This call is recorded.", allow_interruptions=False)
            closing = session.generate_reply(user_input="Bye.")
            await asyncio.wait_for(closing.wait_for_playout(), 5)
            await asyncio.wait_for(closed.wait(), 5)
            assert not disclosure.interrupted
            assert [m.text_content for m in session.history.messages() if m.role == "assistant"] == [
                "This call is recorded.", "Wishing you a pleasant day."
            ]
            assert model.calls == 1
        finally:
            await session.aclose()
    asyncio.run(run())


def test_question_that_mentions_goodbye_uses_normal_llm_without_hangup():
    async def run():
        ud = AgentUserdata("t", "a", "r")
        model = RefusingLLM("We open at nine.")
        session = AgentSession(llm=model, tts=SyntheticTTS(), userdata=ud)
        session.output.audio = SyntheticSink()
        agent = AwaazAgent(instructions="Fixture", tools=[end_conversation_summary], humanization_runtime=make_runtime())
        await session.start(agent, record=False)
        try:
            handle = session.generate_reply(user_input="Before I say goodbye, what are your hours?")
            await asyncio.wait_for(handle.wait_for_playout(), 5)
            assert model.calls == 1 and not ud.ended_by_agent
            assert [m.text_content for m in session.history.messages() if m.role == "assistant"] == ["We open at nine."]
        finally:
            await session.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("text", ["Bye.", "That's all.", "No thanks", "Can you say goodbye in Spanish?"])
def test_no_local_hangup_when_model_does_not_select_end_tool(text):
    async def run():
        model = RefusingLLM("Could you clarify what you need?")
        ud = AgentUserdata("t", "a", "r")
        session = AgentSession(llm=model, tts=SyntheticTTS(), userdata=ud)
        session.output.audio = SyntheticSink()
        closed = asyncio.Event()
        session.on("close", lambda ev: closed.set())
        agent = AwaazAgent(instructions=SYSTEM_INSTRUCTIONS_BASE, tools=[end_conversation_summary],
                           humanization_runtime=make_runtime())
        await session.start(agent, record=False)
        try:
            handle = session.generate_reply(user_input=text)
            await asyncio.wait_for(handle.wait_for_playout(), 5)
            assert model.calls == 1 and not ud.ended_by_agent and not closed.is_set()
            assert [m.text_content for m in session.history.messages() if m.role == "assistant"] == [model.reply]
        finally:
            await session.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("status", ["continued", "closing_speech_missing", "playout_incomplete"])
def test_unsuccessful_end_tool_returns_to_normal_model_continuation(status):
    history = llm.ChatContext.empty()
    history.add_message(role="user", content="I need to get going")
    history.items.append(llm.FunctionCallOutput(name="end_conversation_summary", call_id="old",
                                               output=json.dumps({"status": status, "callEnding": False}), is_error=False))
    agent = AwaazAgent(instructions=SYSTEM_INSTRUCTIONS_BASE)
    assert agent._conversational_stream(history, [end_conversation_summary], None) is None



@pytest.mark.parametrize("provider", ["cartesia", "rime", "elevenlabs", "uplift"])
@pytest.mark.parametrize("streaming", [False, True])
def test_identity_and_closing_use_existing_candidate_renderer_pipeline(provider, streaming, monkeypatch):
    from test_humanization_batch_b import context
    import worker.providers.registry as registry
    import worker.providers.tts.uplift as uplift
    monkeypatch.setenv("UVA_TTS_STREAMING_" + provider.upper(), "streaming_v1" if streaming else "baseline")
    async def run():
        monkeypatch.setattr(registry, "_build_tts", lambda cfg, **kwargs: SyntheticTTS())
        monkeypatch.setattr(uplift, "build", lambda *a, **kw: SyntheticTTS())
        monkeypatch.setattr("worker.tools._save_conversation_summary", lambda **kw: None)
        ud = AgentUserdata("t", "a", "r")
        language = "ur" if provider == "uplift" else "en"
        goodbye = "اپنا خیال رکھیے۔" if language == "ur" else "Take care and have a lovely day."
        model = RefusingLLM(goodbye, end_call=True)
        rt = make_runtime(language)
        ud.humanization_runtime = rt
        ctx = context(provider)
        ctx.runtime = rt
        session = AgentSession(llm=model, tts=SyntheticTTS(), userdata=ud,
                               tts_text_transforms=[], use_tts_aligned_transcript=False)
        session.output.audio = SyntheticSink()
        closed = asyncio.Event()
        session.on("close", lambda ev: closed.set())
        agent = AwaazAgent(instructions="Fixture", tools=[end_conversation_summary],
                           humanization_runtime=rt, delivery_context=ctx)
        await session.start(agent, record=False)
        try:
            identity = session.generate_reply(user_input="کیا آپ اے آئی ہیں؟" if language == "ur" else "Are you an AI?")
            await asyncio.wait_for(identity.wait_for_playout(), 5)
            closing = session.generate_reply(user_input="خدا حافظ۔" if language == "ur" else "Bye.")
            await asyncio.wait_for(closing.wait_for_playout(), 5)
            await asyncio.wait_for(closed.wait(), 5)
            assert identity.exception() is None and closing.exception() is None
            assert model.calls == 1 and ud.ended_by_agent
            replies = [m.text_content for m in session.history.messages() if m.role == "assistant"]
            assert replies == (["میں ایک اے آئی اسسٹنٹ ہوں۔", goodbye] if language == "ur"
                               else ["I'm an AI assistant.", goodbye])
            if streaming:
                assert any(p.llm_started and p.planned_chunks for p in agent.speech_plans)
        finally:
            await session.aclose()
    asyncio.run(run())
