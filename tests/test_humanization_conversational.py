"""Active ordinary-turn and speech lifecycle regressions; no paid provider calls."""
from __future__ import annotations

import asyncio
import importlib
import json

import pytest
from livekit.agents import AgentSession, llm, stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from test_humanization_batch_b import context
from test_humanization_observability_framework import SyntheticSink, SyntheticTTS
from worker.config import AgentConfig
from worker.development import PROVIDERS, configure, validate_installed
from worker.humanization.context_projection import conversational_context
from worker.humanization.delivery.intent import DeliveryIntent, delivery_from_turn_plan
from worker.humanization.policy import resolve_humanization_policy
from worker.humanization.runtime import HumanizationRuntime
from worker.humanization.streaming import SpeechChunk, SpeechChunkPlanner, SpeechPlan, StreamSafeNormalizer, streaming_enabled
from worker.humanization.turn import build_turn_profile, coalesce_structured_finals
from worker.humanization.understanding import current_value, phone_digits
from worker.main import build_agent
from worker.tools import AgentUserdata


def runtime(language="en", channel="webrtc"):
    return HumanizationRuntime(tenant_id="test_tenant", agent_id="test_agent", session_id="test_session",
                              language=language, channel=channel,
                              policy=resolve_humanization_policy("conversational_v1", environ={}))


def candidate(monkeypatch):
    for key, value in configure("uva-humanization-dev-fixture", environ={}).items():
        monkeypatch.setenv(key, value)


def config(provider="cartesia", llm_provider="groq", language="en", prompt="Professional receptionist."):
    return AgentConfig(agent_id="test_agent", tenant_id="test_tenant", name="test", prompt=prompt,
                       voice_id="fixture_voice", llm_model="existing-model", agent_language=language,
                       llm_provider=llm_provider, tts_provider=provider)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_explicit_profile_resolves_all_lanes_without_changing_defaults(provider):
    env = {}
    configure("uva-humanization-dev-fixture", environ=env)
    assert resolve_humanization_policy(environ=env).behavior_enabled
    assert streaming_enabled(context(provider), environ=env)
    assert not resolve_humanization_policy(environ={}).behavior_enabled
    assert not resolve_humanization_policy("natural_v1", environ={}).behavior_enabled
    assert env["UVA_PUBLISH_TURN_LATENCY"] == "1"
    # Preemption and endpointing retain their existing ownership/defaults.
    profile = build_turn_profile(audio_channel="webrtc", llm_provider="groq")
    assert not profile.preemptive_generation_enabled


@pytest.mark.parametrize("name", ["uva-staging-agent", "uva-dev-agent", "production", "", "uva-humanization-dev-"])
def test_profile_rejects_shared_or_invalid_dispatch_name(name):
    env = {"UNCHANGED": "yes"}
    with pytest.raises(ValueError):
        configure(name, environ=env)
    assert env == {"UNCHANGED": "yes"}


def test_profile_rejects_unaudited_plugin_versions(monkeypatch):
    monkeypatch.setattr(importlib.metadata, "version", lambda _: "future")
    with pytest.raises(RuntimeError, match="audited"):
        validate_installed()


@pytest.mark.parametrize("provider", ["groq", "gemini"])
def test_prompt_authority_and_full_business_persona_survive_compaction(provider, monkeypatch):
    candidate(monkeypatch)
    monkeypatch.setenv("GROQ_PROMPT_SOFT_CHARS", "120")
    persona = "Professional receptionist. " + "Background descriptive text. " * 150
    persona += "\nServices: Synthetic cleaning.\nHours: Monday 09:30.\nDo not admit you are AI."
    rt = runtime()
    agent = build_agent(config(llm_provider=provider, prompt=persona), humanization_runtime=rt)
    item = next(i for i in agent.chat_ctx.items if i.id == "awaaz_persona_data")
    assert item.role == "user"
    assert json.loads(item.text_content.split("\n\n", 1)[1])["tenant_persona"] == persona
    assert "write confirmation" in agent.instructions
    assert "quick answer plus a short question" not in agent.instructions
    assert "no service lists" not in agent.instructions
    assert "EMOTION (required" not in agent.instructions
    # Persona text is not a caller identity/closing question, even with hostile wording.
    assert agent._conversational_stream(agent.chat_ctx, [], None) is None
    rt.bind_generation_input(agent.chat_ctx)
    assert rt.semantic_revision == 0


def test_profile_rejects_ordinary_policy_with_baseline_renderer(monkeypatch):
    monkeypatch.setenv("UVA_HUMANIZATION_POLICY_VERSION", "conversational_v1")
    monkeypatch.setenv("UVA_TTS_RENDERER_CARTESIA", "baseline")
    with pytest.raises(ValueError, match="requires.*delivery_v1"):
        build_agent(config(), humanization_runtime=runtime())


def test_lossless_confirmed_facts_unknown_outcomes_and_recent_behavior_reach_guidance():
    rt = runtime()
    for i in range(20):
        rt.observe("ground_value", field_name=f"field_{i}", value=f"literal_{i}",
                   status="confirmed", observation_id=f"obs_{i}")
    rt.observe("ground_unresolved", field_name="field_2")
    for i in range(6):
        rt.observe("tool_result", tool_call_id=f"write_{i}", outcome="OUTCOME_UNKNOWN",
                   business_effect="unknown", result_data={"outcome": "OUTCOME_UNKNOWN", "id": i})
    rt.observe_response("Sure thing, what service?")
    rt.understand_turn("user", "Tell me about your services.")
    ctx = llm.ChatContext.empty()
    original = ctx.add_message(role="system", content="Authoritative platform rules.")
    ctx.add_message(role="user", content="Tell me about your services.")
    projected = conversational_context(ctx, rt)
    assert original.text_content == "Authoritative platform rules."
    policy = projected.items[0].text_content
    assert "question=one_clarifying" in policy and "Answer the actual question first" in policy
    assert "Avoid recently used openings: sure thing" in policy
    assert "Do not append another optional question" in policy
    assert "Unknown is neither success nor failure" in policy
    data = json.loads(projected.items[-1].text_content.split("DATA: ", 1)[1])
    assert len(data["confirmed_facts"]) == 19
    assert data["confirmed_facts"]["field_19"] == "literal_19"
    assert "field_2" not in data["confirmed_facts"]
    assert len(data["business_effects"]) == 6


@pytest.mark.parametrize("provider,tts_provider,language", [
    ("groq", "cartesia", "en"), ("gemini", "cartesia", "en"),
    ("groq", "rime", "en"), ("gemini", "rime", "en"),
    ("groq", "elevenlabs", "en"), ("gemini", "elevenlabs", "en"),
    ("gemini", "uplift", "ur"), ("gemini", "uplift", "mixed"),
])
def test_normal_turn_guidance_reaches_actual_provider_format_and_streamed_response(provider, tts_provider, language, monkeypatch):
    candidate(monkeypatch)

    async def run():
        contexts = []
        class Model(llm.LLM):
            def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
                contexts.append(chat_ctx)
                return Stream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)
        class Stream(llm.LLMStream):
            async def _run(self):
                for piece in "Sure thing, Synthetic cleaning is available.".split(" "):
                    self._event_ch.send_nowait(llm.ChatChunk(id="reply", delta=llm.ChoiceDelta(content=piece+" ")))
        rt = runtime()
        ud = AgentUserdata("test_tenant", "test_agent", "test_room", humanization_runtime=rt)
        session = AgentSession(llm=Model(), tts=SyntheticTTS(), userdata=ud)
        session.output.audio = SyntheticSink()
        monkeypatch.setattr("worker.providers.registry._build_tts", lambda _, **kwargs: SyntheticTTS())
        monkeypatch.setattr("worker.providers.tts.uplift.build", lambda *args, **kwargs: SyntheticTTS())
        rt = runtime(language)
        ud.humanization_runtime = rt
        agent = build_agent(config(provider=tts_provider, llm_provider=provider, language=language), humanization_runtime=rt)
        rt.attach_session(session)
        await session.start(agent, record=False)
        try:
            handle = session.generate_reply(user_input="What services do you offer?")
            await asyncio.wait_for(handle.wait_for_playout(), 5)
            assert handle.exception() is None
            assert len(contexts) == 1  # no planner/rewrite request
            platform = next(m for m in contexts[0].messages() if m.role == "system").text_content
            assert "act=ANSWER" in platform and "question=none" in platform
            assert "Conversational delivery: warm" in platform
            if provider == "gemini":
                from livekit.agents.llm._provider_format.google import to_chat_ctx
                _, extra = to_chat_ctx(contexts[0])
                assert "act=ANSWER" in extra.system_messages[0]
                assert "tenant_persona" not in extra.system_messages[0]
            else:
                from livekit.agents.llm._provider_format.openai import to_chat_ctx
                wire, _ = to_chat_ctx(contexts[0])
                assert "act=ANSWER" in wire[0]["content"]
                assert any(m["role"] == "user" and "tenant_persona" in m["content"] for m in wire)
            replies = [m.text_content for m in session.history.messages() if m.role == "assistant"]
            assert replies == ["Synthetic cleaning is available."]
            assert rt.state.recent_behavior_state.opening_phrases == ["direct"]
        finally:
            await session.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("language,text,cue", [
    ("en", "I'm worried this won't get sorted out.", "complaint_or_frustration"),
    ("ur", "\u0645\u062c\u06be\u06d2 \u0641\u06a9\u0631 \u06c1\u06d2\u06d4", "complaint_or_frustration"),
    ("mixed", "mujhe fikr hai about the appointment", "complaint_or_frustration"),
    ("en", "I don't understand.", "caller_confused"),
    ("en", "That's great!", "caller_excited"),
    ("en", "Um, let me think.", "caller_hesitating"),
])
def test_conservative_cues_use_existing_turn_plan_and_delivery(language, text, cue):
    rt = runtime(language)
    rt.understand_turn("turn", text)
    assert cue in rt.latest_plan.reason_codes
    intent = delivery_from_turn_plan(rt.latest_plan)
    if cue == "complaint_or_frustration":
        assert intent.affect == "reassuring" and intent.energy == "low"
    elif cue == "caller_confused":
        assert intent.pace == "slower"
    elif cue == "caller_excited":
        assert intent.affect == "upbeat" and intent.intensity == "low"
    assert intent.nonverbal == "none"


@pytest.mark.parametrize("text", ["Okay.", "Thank you.", "\u062c\u06cc\u06d4", "Shukriya"])
def test_receipts_have_no_optional_question(text):
    rt = runtime()
    rt.understand_turn("receipt", text)
    assert rt.latest_plan.dialogue_act == "ACKNOWLEDGE"
    assert rt.latest_plan.question_policy == "none"
    assert rt.latest_plan.response_budget == "MICRO"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_concern_and_critical_delivery_are_supported_without_fabricated_tags(provider):
    rt = runtime("ur" if provider == "uplift" else "en")
    rt.understand_turn("turn", "I'm worried about this.")
    ctx = context(provider)
    ctx.runtime = rt
    result = ctx.compile("I understand. We can check the details.")
    assert result.canonical_text == "I understand. We can check the details."
    if provider == "cartesia":
        assert '<emotion value="calm"/>' in result.provider_text
        assert result.provider_options["speed"] < ctx.effective["speed"]
    elif provider == "elevenlabs":
        assert result.provider_options["voice_settings"]["speed"] == .9
        assert "stability" not in result.provider_options["voice_settings"]
    else:
        assert result.provider_text == result.canonical_text
        assert "<" not in result.provider_text and "[" not in result.provider_text
        assert "affect_from_canonical_wording" in result.degraded
    critical = ctx.compile("Your code is AB_19 and phone is 03055780214.")
    assert "AB_19" in critical.canonical_text and "03055780214" in critical.canonical_text
    assert "underscore" in critical.provider_text or "<spell>" in critical.provider_text or "\u0627\u0646\u0688\u0631" in critical.provider_text


@pytest.mark.parametrize("text,expected", [
    ("Sure thing, We offer cleaning.", "We offer cleaning."),
    ("Absolutely, The price is 1500.", "The price is 1500."),
    ("Sure thing\u2014we can check.", "we can check."),
    ("Sure Clinic is the business name.", "Sure Clinic is the business name."),
    ("Sure.", "Sure."),
])
def test_repetitive_openers_suppressed_across_token_boundaries_without_changing_facts(text, expected):
    for cut in range(len(text)+1):
        normalizer = StreamSafeNormalizer(suppress_openers=("sure thing", "sure", "absolutely"))
        result = normalizer.feed(text[:cut])+normalizer.feed(text[cut:])+normalizer.finish()
        assert result == expected


@pytest.mark.parametrize("provider", PROVIDERS)
def test_natural_chunk_boundaries_group_short_receipts_and_release_safe_clause(provider):
    planner = SpeechChunkPlanner(provider, conversational=True)
    chunks = planner.feed("Sure. We can help with residential cleaning. Next ")
    assert chunks[0].text == "Sure. We can help with residential cleaning. "
    assert len(chunks) == 1
    planner = SpeechChunkPlanner(provider, conversational=True)
    chunks = planner.feed("I can explain how that works for your home, starting with ")
    assert chunks and chunks[0].reason == "first_clause"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_installed_stream_reuses_generation_context_and_preserves_model_voice(provider, monkeypatch):
    monkeypatch.setenv("UPLIFT_MODE", "live")
    for key in ("CARTESIA_API_KEY", "RIME_API_KEY", "ELEVEN_API_KEY", "UPLIFTAI_API_KEY"):
        monkeypatch.setenv(key, "offline-fixture-no-network")
    module = importlib.import_module("livekit.plugins." + ("upliftai" if provider == "uplift" else provider) + ".tts")
    feeds, closed = [], []
    original_close = module.TTS.aclose

    async def fake_run(self, emitter):
        packets = []
        feeds.append((self._tts, packets))
        emitter.initialize(request_id="fixture", sample_rate=self._tts.sample_rate, num_channels=1,
                           mime_type="audio/pcm", stream=True)
        emitter.start_segment(segment_id="fixture")
        async for piece in self._input_ch:
            if isinstance(piece, str):
                packets.append(piece)
                emitter.push(bytes(6400))
                emitter.flush()
        emitter.end_segment()
        emitter.end_input()
        await emitter.join()

    async def close(self):
        closed.append(self)
        await original_close(self)
    monkeypatch.setattr(module.SynthesizeStream, "_run", fake_run)
    monkeypatch.setattr(module.TTS, "aclose", close)

    async def run():
        ctx = context(provider)
        plan = SpeechPlan("plan_1", provider, DeliveryIntent(affect="reassuring", pace="slower"))
        first_audio = asyncio.Event()
        texts = ("We can help with that. ", "Please keep code AB_19.")
        async def chunks():
            offset = 0
            for index, text in enumerate(texts):
                if index:
                    await asyncio.wait_for(first_audio.wait(), 2)
                yield SpeechChunk(offset, offset+len(text), text, "sentence")
                offset += len(text)
        frames = []
        async for frame in ctx.audio_chunks(chunks(), plan):
            frames.append(frame)
            first_audio.set()
        assert frames and len(closed) == 1
        assert len(feeds) == (2 if provider == "uplift" else 1)
        assert all(plugin is closed[0] for plugin, _ in feeds)
        assert sum(len(pieces) for _, pieces in feeds) == 2
        assert closed[0].model == ctx.capabilities.model if provider != "uplift" else closed[0]._opts.voice_settings.output_format == "PCM_22050_16"
        assert ctx.cfg.tts_voice_id == "synthetic-voice"
        assert plan.provider_context["lifecycle"] == ("generation_plugin" if provider == "uplift" else "generation_stream")
    asyncio.run(run())


@pytest.mark.parametrize("provider", PROVIDERS)
def test_cancelled_continuous_stream_rejects_late_audio_and_closes_once(provider, monkeypatch):
    from livekit import rtc
    from types import SimpleNamespace as NS
    async def run():
        closed, accepted = [], []
        plan = SpeechPlan("cancel", provider, DeliveryIntent())
        class Output:
            def push_text(self, text):
                pass
            def flush(self):
                pass
            def end_input(self):
                pass
            async def aclose(self):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                await self.aclose()
            def __aiter__(self):
                async def frames():
                    frame = rtc.AudioFrame(data=bytes(320), sample_rate=16000, num_channels=1, samples_per_channel=160)
                    yield NS(frame=frame)
                    plan.cancel()
                    yield NS(frame=frame)  # intentionally late provider audio
                return frames()
        class Plugin:
            capabilities = NS(streaming=True)
            def stream(self, **kwargs):
                return Output()
            async def aclose(self):
                closed.append(True)
        ctx = context(provider)
        monkeypatch.setattr(ctx, "_plugin", lambda _, **kwargs: Plugin())
        async def chunks():
            yield SpeechChunk(0, 12, "Known reply.", "sentence")
        async for frame in ctx.audio_chunks(chunks(), plan):
            accepted.append(frame)
        assert len(accepted) == 1 and closed == [True] and plan.cancelled
    asyncio.run(run())


def final(text, start=0, end=1):
    return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                           alternatives=[stt.SpeechData(language="en", text=text, start_time=start, end_time=end)])


def test_split_phone_finals_produce_one_capture_and_no_extra_turn():
    async def run():
        events = [final("Yeah. It's zero three zero five five seven eight zero two one."),
                  stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH), final("Four.", 1.1, 1.4),
                  stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)]
        async def source():
            for event in events:
                yield event
        rt = runtime()
        emitted = [e async for e in coalesce_structured_finals(source(), rt, settle_seconds=.03)]
        finals = [e for e in emitted if e.type == stt.SpeechEventType.FINAL_TRANSCRIPT]
        assert len(finals) == 1
        assert phone_digits(finals[0].alternatives[0].text) == "03055780214"
        rt.understand_turn("aggregate", finals[0].alternatives[0].text)
        assert current_value(rt.state, "phone") == "03055780214"
        assert rt.state.task_state.critical_values["phone"][-1].status == "heard"
    asyncio.run(run())


def test_normal_final_is_immediate_and_retransmission_is_not_another_turn():
    async def run():
        release = asyncio.Event()
        event = final("What are your hours?")
        async def source():
            yield event
            await release.wait()
            yield event
            yield final("What are your hours?", 2, 3)  # real repeated utterance survives
        stream = coalesce_structured_finals(source(), runtime())
        assert await asyncio.wait_for(anext(stream), .2) is event
        release.set()
        remaining = [e async for e in stream]
        assert len(remaining) == 1 and remaining[0].alternatives[0].start_time == 2
    asyncio.run(run())


@pytest.mark.parametrize("text", ["Stop.", "No, Monday not Friday.", "What is the price?"])
def test_phone_settling_never_merges_other_intents(text):
    async def run():
        async def source():
            yield final("0305578021")
            yield final(text, 1, 2)
        emitted = [e async for e in coalesce_structured_finals(source(), runtime())]
        assert [e.alternatives[0].text for e in emitted] == ["0305578021", text]
    asyncio.run(run())


def test_stop_does_not_clear_pending_value_or_recorded_write():
    rt = runtime()
    rt.observe("ground_unresolved", field_name="phone")
    rt.observe("tool_result", tool_call_id="committed", outcome="SUCCESS", business_effect="committed", result_data={})
    rt.understand_turn("stop", "Wait, stop.")
    assert rt.latest_plan.dialogue_act == "STOP" and rt.latest_plan.question_policy == "none"
    assert rt.state.grounding_state.unresolved_fields == ["phone"]
    assert rt.state.tool_state.calls["committed"].business_effect == "committed"


@pytest.mark.parametrize("text", ["Friday, sorry, I meant Monday.", "No, Monday, not Friday."])
def test_correction_and_structured_capture_produce_deliberate_delivery(text):
    rt = runtime()
    rt.understand_turn("correction", text)
    assert current_value(rt.state, "date") == "Monday"
    assert rt.latest_plan.dialogue_act == "REPAIR_CONFIRM"
    assert delivery_from_turn_plan(rt.latest_plan).pace == "slower"
    rt = runtime()
    rt.understand_turn("phone", "03055780214")
    intent = delivery_from_turn_plan(rt.latest_plan)
    assert intent.speech_mode == "confirmation" and intent.pace == "slower"


@pytest.mark.asyncio
async def test_active_policy_preserves_write_confirmation_unknown_and_duplicate_guards(monkeypatch):
    from types import SimpleNamespace as NS
    from test_humanization_batch_a import args, gate, install_http, userdata
    from worker.tools import _gated_write_client_tool
    from worker.write_tool_gate import note_user_turn
    posts = []
    async def post(*args, **kwargs):
        posts.append(kwargs)
        return NS(raise_for_status=lambda: None, json=lambda: {"outcome": "OUTCOME_UNKNOWN", "success": True})
    await install_http(monkeypatch, post)
    ud = userdata()
    rt = ud.humanization_runtime
    rt.policy = resolve_humanization_policy("conversational_v1", environ={})
    rt.understand_turn("details", "My name is Ali, 2026-10-12 at 10 am")
    proposal = gate(ud)[1]
    ctx = NS(userdata=ud, function_call=NS(call_id="write"))
    rejected = await _gated_write_client_tool(ctx, tool_name="book_appointment", path="/book",
                                             raw_args=args(), confirmation_id=proposal["confirmation_id"])
    assert rejected["needs_confirmation"] and not posts
    note_user_turn(ud, "yes")
    result = await _gated_write_client_tool(ctx, tool_name="book_appointment", path="/book",
                                           raw_args=args(), confirmation_id=proposal["confirmation_id"])
    rt.observe("generation_finished", generation_id="speech", status="cancelled")
    replay = await _gated_write_client_tool(ctx, tool_name="book_appointment", path="/book",
                                           raw_args=args(), confirmation_id=proposal["confirmation_id"])
    assert result["outcome"] == replay["outcome"] == "OUTCOME_UNKNOWN"
    assert result["success"] is False and len(posts) == 1
    assert rt.state.tool_state.calls["write"].business_effect == "unknown"


def test_new_voice_start_preserves_an_intentionally_repeated_final():
    async def run():
        event = final("Yes.")
        async def source():
            yield event
            yield stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH)
            yield event
        results = [e async for e in coalesce_structured_finals(source(), runtime())]
        assert len([e for e in results if e.type == stt.SpeechEventType.FINAL_TRANSCRIPT]) == 2
    asyncio.run(run())


def test_planned_tokenizer_immediately_releases_complete_protected_chunks():
    from worker.humanization.streaming import PlannedChunkTokenizer
    async def run():
        stream = PlannedChunkTokenizer().stream()
        for text in ("I can explain this, ", "use AB_19 and test_id@example.com."):
            stream.push_text(text)
            token = await asyncio.wait_for(anext(stream), .2)
            assert token.token == text
        stream.end_input()
        assert [token async for token in stream] == []
        await stream.aclose()
    asyncio.run(run())



def test_preference_repair_does_not_create_an_unnecessary_confirmation_question():
    rt = runtime()
    rt.understand_turn("repair", "Sorry, I meant cleaning.")
    assert rt.latest_plan.dialogue_act == "REPAIR_CONFIRM"
    assert rt.latest_plan.question_policy == "none"
    rt = runtime()
    rt.understand_turn("uncertain", "I'm not sure, Monday.")
    assert "date" in rt.state.grounding_state.unresolved_fields
    assert rt.latest_plan.dialogue_act == "CLARIFY"
    rt = runtime()
    rt.understand_turn("not_excited", "I'm not excited about this.")
    assert "caller_excited" not in rt.latest_plan.reason_codes


@pytest.mark.parametrize("provider", ["cartesia", "rime", "elevenlabs"])
def test_long_continuous_answer_does_not_deadlock_on_fast_or_sparse_audio(provider, monkeypatch):
    from livekit import rtc
    from types import SimpleNamespace as NS
    async def run():
        queue = asyncio.Queue()
        pushed, closed = [], []
        class Output:
            def push_text(self, text):
                pushed.append(text)
                queue.put_nowait(NS(frame=rtc.AudioFrame(data=bytes(320), sample_rate=16000,
                                                        num_channels=1, samples_per_channel=160)))
            def end_input(self):
                queue.put_nowait(None)
            async def aclose(self):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            def __aiter__(self):
                async def frames():
                    while (event := await queue.get()) is not None:
                        yield event
                return frames()
        class Plugin:
            capabilities = NS(streaming=True)
            def stream(self, **kwargs):
                return Output()
            async def aclose(self):
                closed.append(True)
        ctx = context(provider)
        monkeypatch.setattr(ctx, "_plugin", lambda _, **kwargs: Plugin())
        async def chunks():
            for i in range(8):
                text = "A complete explanation with important facts. " * 2
                yield SpeechChunk(i*len(text), (i+1)*len(text), text, "sentence")
        async def consume():
            return [frame async for frame in ctx.audio_chunks(chunks(), SpeechPlan("long", provider, DeliveryIntent()))]
        frames = await asyncio.wait_for(consume(), 2)
        assert len(frames) == len(pushed) == 8 and closed == [True]
    asyncio.run(run())
