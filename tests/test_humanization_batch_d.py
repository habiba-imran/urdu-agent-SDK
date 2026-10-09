"""Fast-track D: small parameterized P0 suite; no paid sockets/acoustic claims."""

from __future__ import annotations
import asyncio
import logging
from types import SimpleNamespace as NS
import pytest
from livekit.agents import Agent, llm, stt
from worker.humanization.agent import AwaazAgent
from worker.humanization.coordinator import TurnCoordinator, overlap_enabled
from worker.humanization.delivery.renderers import LanguageProfile, ChannelProfile
from worker.humanization.delivery.intent import DeliveryIntent
from worker.humanization.delivery.pronunciation import PronunciationPlan
from worker.humanization.history import reconcile_interrupted_context, AuditTranscript
from worker.humanization.orchestrator import execution_plan, failure
from worker.humanization.streaming import HeardState, SpeechPlan, SpeechChunk
from worker.provider_retries import bounded_provider_stream, wire_provider_failure
from worker.session_opening import (
    opening_state,
    bind_opening_transport,
    await_playback_ready,
    apply_session_opening,
)
from worker.telephony_runtime import transport_diagnostics
from worker.tools import end_conversation_summary
from test_humanization_batch_a import runtime
from test_session_opening import _cfg


@pytest.mark.parametrize(
    "text,language",
    [(x, "en") for x in ("wait", "stop", "no", "hold on", "Stop please")]
    + [(x, "ur") for x in ("نہیں", "رکیں", "رکو", "nahi", "nahin")],
)
def test_critical_takeover_is_never_filtered(text, language):
    coordinator = TurnCoordinator(state="AGENT_SPEAKING")
    assert (
        coordinator.decide_overlap(
            text, agent_speaking=True, duration=0.1, language=language
        )
        == "YIELD"
    )


@pytest.mark.parametrize(
    "text,language",
    [(x, "en") for x in ("mhm", "yeah", "right", "okay", "hmm")]
    + [(x, "ur") for x in ("ji", "haan", "acha", "جی", "ہاں", "اچھا")],
)
def test_listener_feedback_depends_on_timing_speaking_and_semantic_state(
    text, language
):
    c = TurnCoordinator(state="AGENT_SPEAKING")
    assert (
        c.decide_overlap(text, agent_speaking=True, duration=0.2, language=language)
        == "CONTINUE"
    )
    for duration in (None, 1.0):
        assert (
            c.decide_overlap(
                text, agent_speaking=True, duration=duration, language=language
            )
            == "YIELD"
        )
    assert (
        c.decide_overlap(
            text,
            agent_speaking=True,
            duration=0.2,
            language=language,
            awaiting_answer=True,
        )
        == "YIELD"
    )
    c.state = "LISTENING"
    assert (
        c.decide_overlap(text, agent_speaking=False, duration=0.2, language=language)
        == "YIELD"
    )
    c.state = "AGENT_SPEAKING"
    assert (
        c.decide_overlap(
            text + " but change the date",
            agent_speaking=True,
            duration=0.2,
            language=language,
        )
        == "YIELD"
    )


@pytest.mark.parametrize(
    "resumed,canonical,heard,expected",
    [
        (True, "Long cancelled speech.", "", "resume"),
        (False, "First clause. Next clause.", "First clause. ", "restart_short_clause"),
        (
            False,
            "This is a very long unfinished clause containing far more than twelve separate words for the caller to understand",
            "",
            "replan",
        ),
    ],
)
def test_false_interruption_selects_explicit_recovery(
    resumed, canonical, heard, expected
):
    c = TurnCoordinator(state="INTERRUPTION_CANDIDATE")
    strategy, text = c.recover_false(
        resumed=resumed, canonical=canonical, heard_prefix=heard
    )
    assert strategy == expected and c.overlap_decision == "RECOVER_FALSE"
    assert not text or "sorry" not in text.lower()


def test_heard_prefix_uses_only_real_text_or_completed_chunk_evidence():
    canonical = "First clause. Unheard suffix."
    heard = HeardState()
    heard.observe(canonical, playback_position=99)
    assert heard.prefix == ""  # even elapsed/output duration alone cannot guess words
    heard.observe(canonical, synchronized_transcript="First clause.")
    assert heard.context_text(canonical) == "First clause."
    for fabricated in ("First clause. Unheard suffix. invented", "Unheard suffix."):
        heard.observe(canonical, synchronized_transcript=fabricated)
        assert heard.prefix == "First clause."
    chunk = SpeechChunk(0, 14, "First clause. ", "sentence")
    chunk_heard = HeardState()
    chunk_heard.observe(canonical, completed_chunks=(chunk,))
    assert chunk_heard.prefix == chunk.text and chunk_heard.source == "completed_chunks"


def test_unheard_suffix_is_removed_only_from_model_input_and_audit_survives():
    ctx = llm.ChatContext.empty()
    msg = ctx.add_message(
        role="assistant", content="First clause. Unheard suffix.", interrupted=True
    )
    ctx.add_message(role="user", content="Wait")
    plan = SpeechPlan(
        "g",
        "uplift",
        DeliveryIntent(),
        canonical_text=msg.text_content,
        history_references=(msg.id,),
    )
    plan.heard.observe(plan.canonical_text, synchronized_transcript="First clause.")
    audit = AuditTranscript()
    audit.record(msg)
    reduced = reconcile_interrupted_context(ctx, [plan])
    assert reduced.items[0].text_content == "First clause."
    assert ctx.items[0].text_content == "First clause. Unheard suffix."
    assert audit.turns()[0]["text"] == "First clause. Unheard suffix."
    unknown = reconcile_interrupted_context(ctx)
    assert not unknown.items[0].text_content


@pytest.mark.parametrize(
    "language,locale,script",
    [
        ("en", "en", "latin"),
        ("ur", "ur_pk", "urdu_with_literal_entities"),
        ("ur_pk_mixed", "ur_pk_mixed", "urdu_with_literal_entities"),
    ],
)
def test_language_profile_semantics_and_function_bank(language, locale, script):
    profile = LanguageProfile(language)
    assert profile.locale == locale and profile.script == script
    for function in (
        "SHORT_RECEIPT",
        "TOOL_ACK_CHECK",
        "REPAIR_CONFIRM",
        "FALSE_INTERRUPT_RECOVERY",
    ):
        phrase = profile.phrase(function)
        assert phrase and "<" not in phrase and "[" not in phrase
    assert (
        "Preserve literal" in profile.instructions
        or "business terms" in profile.instructions
    )
    assert "fillers" in profile.instructions
    rt = runtime()
    rt.language_profile = profile
    rt.understand_turn("u", "Friday 3 pm")
    assert rt.state.task_state.critical_values["date"][-1].value == "Friday"


def test_phrase_cooldown_and_session_isolation():
    rt = runtime()
    assert rt.functional_phrase("TOOL_ACK_CHECK", now=0)
    assert rt.functional_phrase("TOOL_ACK_CHECK", now=1) is None
    assert rt.functional_phrase("TOOL_ACK_CHECK", now=12)
    assert runtime().functional_phrase("TOOL_ACK_CHECK", now=1)
    assert rt.state.recent_behavior_state.phrase_at == {"TOOL_ACK_CHECK": 12}


@pytest.mark.parametrize(
    "channel,kind,lead", [("webrtc", "WEBRTC", 2000), ("telephony", "TELEPHONY", 1000)]
)
def test_channel_changes_only_acoustic_intent(channel, kind, lead):
    from worker.humanization.delivery.pronunciation import plan_pronunciation

    profile = ChannelProfile(channel)
    assert profile.kind == kind and profile.audio_lead_ms == lead
    plan = plan_pronunciation("Code AB_19.")
    result = profile.delivery(DeliveryIntent(), plan)
    assert result.pace == ("slower" if kind == "TELEPHONY" and plan.spans else "normal")
    assert profile.delivery(DeliveryIntent(), PronunciationPlan()).affect == "neutral"


def test_transport_codec_is_unknown_without_negotiated_evidence():
    values = transport_diagnostics(
        {"telephony": {"direction": "inbound", "tts_sample_rate": 22050}}
    )
    assert values["codec"] == "UNKNOWN" and values["provider"] == "UNKNOWN"
    assert values["direction"] == "inbound" and values["rtt_ms"] is None


class Bus:
    def __init__(self):
        self.events = {}

    def on(self, event, callback):
        self.events.setdefault(event, []).append(callback)

    def off(self, event, callback):
        self.events[event].remove(callback)

    def emit(self, event, arg):
        for callback in list(self.events.get(event, [])):
            callback(arg)


def fake_session():
    session = Bus()
    session.userdata = NS(
        humanization_runtime=runtime(), recording_may_start=False, opening_active=False
    )
    session.shutdowns = []
    session.shutdown = lambda **kwargs: session.shutdowns.append(kwargs)
    session.user_state = "listening"
    return session


def test_connected_room_is_not_playback_ready_and_blocked_can_unlock():
    async def run():
        room = Bus()
        caller = NS(identity="caller", kind="standard", attributes={})
        room.remote_participants = {"caller": caller}
        sent = []

        async def publish(data, **kwargs):
            sent.append(data)

        room.local_participant = NS(publish_data=publish)
        session = fake_session()
        bind_opening_transport(session, room, "webrtc")
        assert opening_state(session).phase == "PLAYBACK_NOT_READY"
        assert not await await_playback_ready(session, timeout=0.01)
        room.emit(
            "data_received",
            NS(
                participant=caller,
                data=b'{"type":"awaaz_playback_state","ready":false}',
            ),
        )
        assert opening_state(session).playback_ready is False
        room.emit(
            "data_received",
            NS(
                participant=caller, data=b'{"type":"awaaz_playback_state","ready":true}'
            ),
        )
        assert await await_playback_ready(session, timeout=0.01)
        assert opening_state(session).caller_heard is None
        session.emit("close", NS())

    asyncio.run(run())


@pytest.mark.parametrize("first_speaker", ["agent", "user"])
def test_disclosure_precedes_ordinary_greeting_and_remains_locked(
    first_speaker, monkeypatch
):
    from worker.recording_disclosure import speak_recording_disclosure_if_needed

    monkeypatch.setattr(
        "worker.recording_disclosure.persist_recording_consent", lambda **kwargs: True
    )

    async def run():
        session = fake_session()
        session.userdata.recording_may_start = True
        calls = []
        callbacks = []

        class Handle:
            interrupted = False

            async def wait_for_playout(self):
                assert opening_state(session).phase == "DISCLOSURE_PLAYING"
                assert session.userdata.recording_consent_status == "pending"

            def add_done_callback(self, callback):
                callbacks.append(callback)

        def say(text, **kwargs):
            calls.append((text, kwargs))
            return Handle()

        session.say = say
        assert await speak_recording_disclosure_if_needed(
            session, agent_language="en", room_name="r"
        )
        assert session.userdata.recording_consent_status == "granted"
        await apply_session_opening(
            session,
            _cfg(greeting="Hello.", first_speaker=first_speaker),
            logging.getLogger("test"),
        )
        assert calls[0][1]["allow_interruptions"] is False
        if first_speaker == "agent":
            assert calls[1][1]["allow_interruptions"] is True
            assert opening_state(session).phase == "GREETING_PLAYING"
            callbacks[-1](Handle())
        assert opening_state(session).phase == "INTERACTIVE"
        assert opening_state(session).caller_heard is None

    asyncio.run(run())


@pytest.mark.parametrize("provider", ["cartesia", "rime", "elevenlabs", "uplift"])
def test_greeting_cache_includes_new_policy_and_selected_provider(
    provider, monkeypatch
):
    from worker.greeting_cache import make_greeting_cache_key
    from test_humanization_batch_b import context

    monkeypatch.setenv("UVA_TTS_RENDERER_" + provider.upper(), "delivery_v1")
    common = dict(
        agent_id="a",
        tenant_id="t",
        tts_provider=provider,
        provider_voice_id="v",
        greeting_text="Hello.",
        audio_channel="webrtc",
        language="en",
    )
    new = make_greeting_cache_key(**common)
    assert new != make_greeting_cache_key(**common, policy_version="baseline")
    assert new != make_greeting_cache_key(**common, renderer_version="future")
    assert new != make_greeting_cache_key(**{**common, "audio_channel": "telephony"})
    assert new != make_greeting_cache_key(**{**common, "tenant_id": "other"})
    result = context(provider).compile("Hello.", greeting=True)
    assert result.canonical_text == "Hello."


@pytest.mark.parametrize("stage", ["LLM", "TTS"])
def test_progress_deadline_yields_terminal_outcome_without_claiming_fallback(stage):
    async def run():
        session = fake_session()
        closed = []

        async def stalled():
            try:
                await asyncio.sleep(1)
                yield "too late"
            finally:
                closed.append(True)

        with pytest.raises(TimeoutError):
            async for _ in bounded_provider_stream(
                stalled(), NS(session=session), stage, timeout=0.01
            ):
                pass
        assert session.shutdowns == [{"drain": False}]
        assert (
            session.userdata.humanization_runtime.failure_outcome["spokenFallback"]
            is False
        )
        assert closed

    asyncio.run(run())


def test_stt_unavailable_is_terminal_and_tool_dependency_is_truthful():
    async def run():
        room = NS(
            local_participant=NS(publish_data=lambda *args, **kwargs: asyncio.sleep(0))
        )
        session = fake_session()
        wire_provider_failure(session, room)
        error = type("STTError", (), {})()
        session.emit("error", NS(error=error))
        await asyncio.sleep(0)
        assert session.userdata.humanization_runtime.failure_outcome["stage"] == "STT"
        assert session.shutdowns == [{"drain": False}]
        assert (
            failure(TimeoutError(), write=False, dispatched=True).outcome
            == "DEPENDENCY_TIMEOUT"
        )
        assert (
            failure(TimeoutError(), write=True, dispatched=True).outcome
            == "OUTCOME_UNKNOWN"
        )

    asyncio.run(run())


def test_committed_write_and_audit_survive_session_close_and_late_completion():
    rt = runtime()
    plan = execution_plan("book_appointment", "write1", 0)
    from worker.humanization.orchestrator import ToolResult

    rt.tools.complete(
        plan,
        ToolResult("SUCCESS", business_effect="committed", data={"bookingId": "AB_19"}),
    )
    rt.observe("session_closed")
    assert rt.state.tool_state.calls["write1"].business_effect == "committed"
    late = execution_plan("book_appointment", "write2", 0)
    rt.tools.complete(late, ToolResult("SUCCESS", business_effect="committed"))
    assert rt.state.tool_state.calls["write2"].business_effect == "committed"
    assert rt.state.session_closed


def test_goodbye_waits_for_final_playout_after_commit_and_removes_silent_tail(
    monkeypatch,
):
    async def run():
        session = fake_session()
        session.options = NS(session_close_transcript_timeout=2.0)
        session.userdata.tenant_id = "t"
        session.userdata.room_name = "r"
        calls = []

        def save(**kwargs):
            calls.append("committed")

        monkeypatch.setattr("worker.tools._save_conversation_summary", save)

        async def wait():
            calls.append("playout")
            assert calls[0] == "committed"

        result = await end_conversation_summary(
            NS(userdata=session.userdata, session=session, wait_for_playout=wait),
            summary="Finished",
        )
        assert result["outcome"] == "SUCCESS" and calls == ["committed", "playout"]
        assert session.options.session_close_transcript_timeout == 0
        assert session.shutdowns == [{"drain": True}]

    asyncio.run(run())


def test_default_off_rollbacks_and_no_adaptive_promotion(monkeypatch):
    from worker.humanization.turn import build_turn_profile
    from worker.session_opening import opening_gate_enabled

    monkeypatch.delenv("UVA_OVERLAP_POLICY", raising=False)
    monkeypatch.delenv("UVA_OPENING_POLICY", raising=False)
    assert not overlap_enabled() and not opening_gate_enabled()
    monkeypatch.setenv("UVA_OVERLAP_POLICY", "overlap_v1")
    profile = build_turn_profile(audio_channel="webrtc", agent_language="ur")
    assert profile.resume_false_interruption and profile.interruption_mode != "adaptive"


def test_stt_public_hook_tolerates_short_feedback_but_yields_to_stop(monkeypatch):
    async def run():
        rt = runtime()
        rt.overlap_enabled = True
        rt.coordinator.state = "AGENT_SPEAKING"
        events = [
            stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(language="en", text=text, start_time=0, end_time=0.2)
                ],
            )
            for text in ("yeah", "stop")
        ]

        async def source():
            for event in events:
                yield event

        monkeypatch.setattr(Agent, "stt_node", lambda *args: source())
        session = fake_session()
        interrupts = []
        session.interrupt = lambda: interrupts.append(True)
        agent = AwaazAgent(instructions="test", humanization_runtime=rt)
        monkeypatch.setattr(AwaazAgent, "session", property(lambda self: session))
        accepted = [event async for event in agent.stt_node(None, None)]
        assert [event.alternatives[0].text for event in accepted] == ["stop"]
        assert interrupts == [True]

    asyncio.run(run())


@pytest.mark.parametrize(
    "resumed,strategy", [(True, "resume"), (False, "restart_short_clause")]
)
def test_recovery_public_handler_executes_once_without_apology(
    resumed, strategy, monkeypatch
):
    rt = runtime()
    rt.overlap_enabled = True
    session = fake_session()
    calls = []
    session.say = lambda text, **kwargs: calls.append(text)
    session.generate_reply = lambda **kwargs: calls.append(kwargs)
    agent = AwaazAgent(instructions="test", humanization_runtime=rt)
    monkeypatch.setattr(AwaazAgent, "session", property(lambda self: session))
    plan = SpeechPlan(
        "g", "rime", DeliveryIntent(), canonical_text="Continue this clause."
    )
    plan.cancel()
    agent.speech_plans.append(plan)
    agent.recover_false_interruption(NS(resumed=resumed))
    agent.recover_false_interruption(NS(resumed=resumed))
    assert rt.coordinator.recovery_strategy == strategy
    assert calls == ([] if resumed else ["Continue this clause."])


def test_baseline_cancelled_speech_replans_without_replaying_writes(monkeypatch):
    rt = runtime()
    rt.overlap_enabled = True
    rt.last_speech_handle = NS(interrupted=True)
    session = fake_session()
    calls = []
    session.generate_reply = lambda **kwargs: calls.append(kwargs)
    agent = AwaazAgent(instructions="test", humanization_runtime=rt)
    monkeypatch.setattr(AwaazAgent, "session", property(lambda self: session))
    agent.recover_false_interruption(NS(resumed=False))
    assert calls[0]["tool_choice"] == "none"
    assert "Do not apologize" in calls[0]["instructions"]


def test_empty_tts_is_a_terminal_error_and_closes_stream():
    async def run():
        session = fake_session()
        closed = []

        async def empty():
            try:
                if False:
                    yield None
            finally:
                closed.append(True)

        with pytest.raises(RuntimeError, match="no useful output"):
            async for _ in bounded_provider_stream(empty(), NS(session=session), "TTS"):
                pass
        assert closed and session.shutdowns == [{"drain": False}]

    asyncio.run(run())


def test_cache_timeout_retains_single_flight_and_clones_each_waiter(monkeypatch):
    from worker.greeting_cache import (
        GreetingAudioCache,
        start_greeting_synthesis,
        await_greeting_frames,
    )
    from livekit import rtc

    async def run():
        store = GreetingAudioCache()
        key = ("a", "rime", "v", "text", "webrtc", "policy")
        gate = asyncio.Event()
        calls = []
        frame = rtc.AudioFrame(
            data=bytes(320), sample_rate=16000, num_channels=1, samples_per_channel=160
        )

        async def synth(*args, **kwargs):
            calls.append(True)
            await gate.wait()
            return [frame]

        monkeypatch.setattr("worker.greeting_cache.synthesize_greeting_frames", synth)
        first = start_greeting_synthesis(tts=None, key=key, text="Hello.", cache=store)
        assert (
            start_greeting_synthesis(tts=None, key=key, text="Hello.", cache=store)
            is first
        )
        assert await await_greeting_frames(key, timeout=0.01, cache=store) is None
        assert not first.cancelled() and calls == [True]
        gate.set()
        await first
        a = await await_greeting_frames(key, timeout=0.01, cache=store)
        b = await await_greeting_frames(key, timeout=0.01, cache=store)
        assert a[0] is not b[0]

    asyncio.run(run())


def test_real_framework_output_evidence_is_separate_from_synthesis(monkeypatch):
    from livekit.agents import AgentSession
    from test_humanization_batch_b import context
    from test_humanization_observability_framework import SyntheticSink, SyntheticTTS

    async def run():
        monkeypatch.setenv("UVA_TTS_STREAMING_RIME", "streaming_v1")
        rt = runtime()
        rt.playback_ready = True
        ctx = context("rime")
        ctx.runtime = rt

        monkeypatch.setattr(ctx, "_plugin", lambda rendered, **kwargs: SyntheticTTS())
        session = AgentSession(tts=SyntheticTTS(), userdata=NS(humanization_runtime=rt))
        session.output.audio = SyntheticSink()
        agent = AwaazAgent(
            instructions="Plain speech.", humanization_runtime=rt, delivery_context=ctx
        )
        rt.attach_session(session)
        await session.start(agent, record=False)
        agent.bind_playback_evidence()
        try:
            handle = session.say("Hello. Next clause.")
            await asyncio.wait_for(handle.wait_for_playout(), 3)
            plan = agent.speech_plans[-1]
            assert plan.synthesis_completed
            assert plan.heard.prefix == plan.canonical_text
            assert plan.heard.source == "completed_chunks"
            assert plan.heard.playback_position is not None
        finally:
            await session.aclose()

    asyncio.run(run())
