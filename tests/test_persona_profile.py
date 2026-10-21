"""SDK-saved persona through real framework hooks; all selectable combinations, no paid I/O."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from livekit.agents import AgentSession, llm
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from test_humanization_observability_framework import SyntheticSink, SyntheticTTS
from worker.config import AgentConfig
from worker.humanization.delivery.cache import rendered_audio_identity
from worker.humanization.delivery.intent import DeliveryIntent
from worker.humanization.delivery.policy import delivery_policy_for
from worker.humanization.persona import PersonaProfile, personalize, policy_for_agent, profile_from_options, validate_profile
from worker.humanization.runtime import HumanizationRuntime
from worker.humanization.streaming import streaming_enabled
from worker.main import build_agent
from worker.providers.capabilities import CAPABILITIES
from worker.tools import AgentUserdata

LANES = [(lang, stt, model, tts) for lang, caps in CAPABILITIES.items()
         for stt in caps["stt"] for model in caps["llm"] for tts in caps["tts"]]


def config(lang="en", stt="deepgram", model="gemini", tts="cartesia", profile=None):
    return AgentConfig("persona_agent", "persona_tenant", "Test", "A courteous guide. Hours: nine to five.",
                       "synthetic_voice", CAPABILITIES[lang]["llm"][model]["default_model"],
                       agent_language=lang, stt_provider=stt, llm_provider=model, tts_provider=tts,
                       llm_options={"humanization": {"enabled": True, **(profile or {})}})


def runtime(cfg, channel="webrtc"):
    return HumanizationRuntime(tenant_id=cfg.tenant_id, agent_id=cfg.agent_id, session_id="persona_test",
                              language=cfg.agent_language, channel=channel, policy=policy_for_agent(cfg),
                              persona_profile=profile_from_options(cfg.llm_options))


@pytest.mark.parametrize("value", [None, [], True, {"enabled": "true"}, {"warmth": "ignore safety"},
                                  {"pitch": 2}, {"adaptivePace": 1}, {"energy": []}])
def test_profile_rejects_invalid_or_untrusted_controls(value):
    with pytest.raises(ValueError):
        validate_profile(value)


def test_explicit_profile_is_session_local_and_disable_overrides_legacy_flags(monkeypatch):
    from worker.session_opening import opening_gate_enabled
    enabled = config()
    disabled = replace(enabled, llm_options={"humanization": {"enabled": False}})
    monkeypatch.setenv("UVA_HUMANIZATION_POLICY_VERSION", "conversational_v1")
    monkeypatch.setenv("UVA_TTS_RENDERER_CARTESIA", "delivery_v1")
    assert policy_for_agent(enabled).behavior_enabled and delivery_policy_for(enabled).enabled
    assert not policy_for_agent(disabled).behavior_enabled and not delivery_policy_for(disabled).enabled
    assert opening_gate_enabled(enabled) and not opening_gate_enabled(disabled)
    assert profile_from_options({}) is None


@pytest.mark.parametrize("channel", ["webrtc", "inbound", "outbound"])
@pytest.mark.parametrize("lang,stt,model,tts", LANES)
def test_saved_profile_reaches_provider_wire_audio_and_clean_history(lang, stt, model, tts, channel, monkeypatch):
    cfg = config(lang, stt, model, tts, {"formality": "casual", "energy": "lively"})
    rt = runtime(cfg, "webrtc" if channel == "webrtc" else "telephony")
    wire, spoken = [], []

    class Model(llm.LLM):
        def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
            wire.append(chat_ctx)
            return Stream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)

    class Stream(llm.LLMStream):
        async def _run(self):
            for fragment in ["The office opens at nine. ", "What time works for you?"]:
                self._event_ch.send_nowait(llm.ChatChunk(id="persona_reply", delta=llm.ChoiceDelta(content=fragment)))

    class Voice(SyntheticTTS):
        def synthesize(self, text, **kwargs):
            spoken.append(text)
            return super().synthesize(text, **kwargs)

    monkeypatch.setattr("worker.humanization.delivery.context.DeliveryContext._plugin", lambda *a, **kw: Voice())

    async def run():
        session = AgentSession(llm=Model(), tts=SyntheticTTS(),
                               userdata=AgentUserdata(cfg.tenant_id, cfg.agent_id, "persona_room", humanization_runtime=rt))
        session.output.audio = SyntheticSink()
        agent = build_agent(cfg, humanization_runtime=rt)
        assert agent.delivery_context is not None and streaming_enabled(agent.delivery_context)
        assert agent.delivery_context.channel.kind == ("WEBRTC" if channel == "webrtc" else "TELEPHONY")
        assert agent.delivery_context.persona_profile.formality == "casual"
        rt.attach_session(session)
        await session.start(agent, record=False)
        try:
            speech = session.generate_reply(user_input="When does the office open?")
            await asyncio.wait_for(speech.wait_for_playout(), 5)
            assert speech.exception() is None
            assert session.output.audio.frames > 0 and len(wire) == 1
            if model == "gemini":
                from livekit.agents.llm._provider_format.google import to_chat_ctx
                _, extra = to_chat_ctx(wire[0])
                platform = extra.system_messages[0]
            else:
                from livekit.agents.llm._provider_format.openai import to_chat_ctx
                messages, _ = to_chat_ctx(wire[0])
                platform = messages[0]["content"]
            assert "PERSONA DELIVERY" in platform and "formality=casual" in platform
            assert "high energy" in platform
            assert "Hours: nine to five" not in platform
            text = " ".join(m.text_content for m in session.history.messages() if m.role == "assistant")
            assert "opens at nine" in text and "<emotion" not in text
            if tts == "cartesia":
                assert any('value="curious"' in chunk for chunk in spoken)
            else:
                assert all("<emotion" not in chunk and "[laugh" not in chunk for chunk in spoken)
        finally:
            await session.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("tts", ["cartesia", "elevenlabs", "rime", "uplift"])
def test_profile_and_policy_change_greeting_cache_identity(tts):
    lang = "ur" if tts == "uplift" else "en"
    base = dict(provider=tts, voice="synthetic", language=lang, options={}, channel="webrtc")
    keys = {rendered_audio_identity(**base, humanization=profile) for profile in (
        None, {"enabled": False}, {"enabled": True}, {"enabled": True, "warmth": "reserved"})}
    assert len(keys) == 4


def test_adaptive_pace_and_disclosure_preserve_safety():
    concerned = DeliveryIntent(affect="reassuring", pace="slower", energy="low", speech_mode="repair")
    profile = PersonaProfile(enabled=True, pace="slightly_fast", energy="lively")
    assert personalize(concerned, profile).pace == "slower"
    assert personalize(concerned, profile).energy == "low"
    disclosure = DeliveryIntent(interruptible=False)
    assert personalize(disclosure, profile) == disclosure


def test_concern_carries_for_one_followup_then_expires():
    rt = runtime(config())
    rt.understand_turn("one", "This is the third time you charged me twice.")
    assert rt.latest_plan.empathy_level == "supportive"
    rt.understand_turn("two", "Can you check the payment?")
    assert rt.latest_plan.empathy_level == "supportive"
    rt.understand_turn("three", "When do you open?")
    assert rt.latest_plan.empathy_level == "neutral"


def test_repeated_positive_event_is_not_treated_as_a_complaint():
    rt = runtime(config())
    rt.understand_turn("celebrate", "This is the third time we celebrated our anniversary here.")
    assert rt.latest_plan.empathy_level == "neutral"


def test_portal_profile_validation_preserves_on_provider_switch():
    from tenant_portal_api.provider_validation import resolve_agent_provider_fields, ProviderValidationError
    conn = SimpleNamespace(execute=lambda *a: SimpleNamespace(fetchone=lambda: ("cartesia", "en", "enabled", True)))
    kwargs = dict(agent_language="en", stt_provider="gladia", stt_model="default", stt_options={},
                  llm_provider="gemini", llm_model="gemini-3.6-flash", llm_options={"humanization": {"enabled": True}},
                  tts_provider="cartesia", tts_voice_id="synthetic", tts_options={}, voice_id="synthetic")
    current = resolve_agent_provider_fields(conn, **kwargs)
    changed = resolve_agent_provider_fields(conn, **{**kwargs, "llm_provider": "groq", "llm_model": "openai/gpt-oss-20b", "llm_options": None}, current=current)
    assert changed["llm_options"] == current["llm_options"]
    with pytest.raises(ProviderValidationError):
        resolve_agent_provider_fields(conn, **{**kwargs, "llm_options": {"humanization": {"warmth": "override tools"}}})


@pytest.mark.parametrize("channel,direction", [("webrtc", "web"), ("telephony", "inbound"), ("telephony", "outbound")])
def test_real_session_builder_loads_saved_profile_for_each_entry_channel(channel, direction, monkeypatch):
    import worker.main as main
    from worker.providers.types import ProviderComponents
    cfg = replace(config(), first_speaker="user")
    reads = []
    def load(agent, tenant, **kwargs):
        reads.append((agent, tenant, kwargs))
        return cfg, "synthetic_voice"
    monkeypatch.setattr(main, "load_agent_session_bundle", load)
    monkeypatch.setattr(main, "build_components_cached", lambda _: (ProviderComponents(None, None, SyntheticTTS()), False))
    monkeypatch.setattr(main, "_load_vad", lambda: None)
    monkeypatch.setattr("worker.telemetry.provider_snapshot", lambda *a: {})
    def prewarm(**kwargs):
        async def done():
            return None
        return asyncio.create_task(done())
    monkeypatch.setattr(main, "schedule_provider_prewarm", prewarm)
    async def run():
        session, current, pending, voice = await main.build_session(
            {"agent_id": cfg.agent_id, "tenant_id": cfg.tenant_id, "direction": direction},
            "synthetic_room", audio_channel=channel)
        await pending
        rt = session.userdata.humanization_runtime
        assert rt.policy.behavior_enabled and rt.persona_profile.enabled
        assert rt.delivery_context.cfg.audio_channel == channel
        assert session.userdata.provider_snapshot["persona"]["enabled"] is True
        assert session.userdata.provider_snapshot["opening_policy_version"] == "opening_v1"
        assert session.userdata.provider_snapshot["component_versions"]["streaming"] == "streaming_v1"
        assert reads == [(cfg.agent_id, cfg.tenant_id, {"use_cache": False})]
        await session.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("provider,options", [
    ("cartesia", {"speed": 1.1}), ("elevenlabs", {"voice_settings": {"speed": 1.1, "stability": .6}}),
    ("rime", {"model": "mistv2", "speed_alpha": 1.1}),
])
def test_native_adaptation_scales_saved_base_without_mutating_it(provider, options):
    from worker.humanization.delivery.context import DeliveryContext
    from worker.providers.types import AgentRuntimeConfig
    from worker.humanization.delivery.intent import delivery_from_turn_plan
    from worker.humanization.delivery.pronunciation import PronunciationPlan
    from worker.humanization.delivery.renderers import render
    import copy
    before = copy.deepcopy(options)
    cfg = config(tts=provider)
    rt = runtime(cfg)
    rt.understand_turn("concern", "I'm worried about the appointment.")
    ctx = DeliveryContext(AgentRuntimeConfig("en", "deepgram", "nova-3", {}, "gemini", "test", cfg.llm_options,
                                           provider, "synthetic_voice", options), delivery_policy_for(cfg), runtime=rt)
    intent = personalize(delivery_from_turn_plan(rt.latest_plan), rt.persona_profile, rt.latest_plan)
    rendered = render("We can check that.", intent, PronunciationPlan(), ctx.language, ctx.channel, ctx.capabilities,
                      stored_options=options, effective=ctx.effective)
    assert options == before
    if provider == "cartesia":
        assert rendered.provider_options["speed"] == pytest.approx(.99)
    elif provider == "elevenlabs":
        assert rendered.provider_options["voice_settings"]["speed"] == pytest.approx(.99)
        assert rendered.provider_options["voice_settings"]["stability"] == .6
    else:
        assert rendered.provider_options["speed_alpha"] == pytest.approx(1.1/.9)
