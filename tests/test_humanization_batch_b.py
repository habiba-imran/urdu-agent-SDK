"""Batch B: common contract, real installed framework, options and cache isolation."""

from __future__ import annotations

import asyncio
import json

import pytest

from worker.humanization.delivery.canonical import canonical_spoken_text
from worker.humanization.delivery.capabilities import resolve_capabilities
from worker.humanization.delivery.context import DeliveryContext
from worker.humanization.delivery.intent import (
    DeliveryIntent, PauseIntent, constrain_delivery, delivery_from_turn_plan,
)
from worker.humanization.delivery.policy import resolve_delivery_policy
from worker.humanization.delivery.pronunciation import PronunciationPlan, PronunciationSpan, plan_pronunciation
from worker.humanization.delivery.renderers import render
from worker.humanization.state import ConversationState, LanguageState
from worker.humanization.turn_plan import TurnSignals, derive_turn_plan
from worker.providers.types import AgentRuntimeConfig

PROVIDERS = ("cartesia", "rime", "elevenlabs", "uplift")


def runtime_config(provider, *, language=None, channel="webrtc", options=None):
    return AgentRuntimeConfig(
        language or ("ur" if provider == "uplift" else "en"), "", "", {}, "", "", {},
        provider, "synthetic-voice", options or {}, channel,
    )


def context(provider, **kwargs):
    return DeliveryContext(runtime_config(provider, **kwargs), resolve_delivery_policy(
        provider, environ={"UVA_TTS_RENDERER_" + provider.upper(): "delivery_v1"},
    ))


def compile_text(provider, text, intent=None, plan=None, **kwargs):
    ctx = context(provider, **kwargs)
    return render(
        text, intent or DeliveryIntent(affect="reassuring", pace="slower"),
        plan or plan_pronunciation(text, language=ctx.language.language),
        ctx.language, ctx.channel, ctx.capabilities,
        stored_options=ctx.cfg.tts_options, effective=ctx.effective,
    )


@pytest.mark.parametrize("provider", PROVIDERS)
def test_same_canonical_semantics_and_business_facts_for_every_provider(provider):
    text = "Dr. Sana at Awaaz Clinic: 09:30, price 1500, email sana_test@example.com, code AB_19."
    result = compile_text(provider, text)
    assert result.canonical_text == text
    for fact in ("Dr. Sana", "Awaaz Clinic", "09:30", "1500"):
        assert fact in result.provider_text
    assert result.alignment_mode == "canonical"
    assert "[laugh" not in result.provider_text
    if provider != "cartesia":
        assert "<" not in result.provider_text and ">" not in result.provider_text
    if provider == "cartesia":
        assert '<emotion value="calm"/>' in result.provider_text
        assert "<spell>AB_19</spell>" in result.provider_text
        assert result.provider_options["speed"] < .95
    elif provider == "elevenlabs":
        assert result.provider_options["voice_settings"]["speed"] == .9
    elif provider == "rime":
        assert "spell(" not in result.provider_text  # Arcana native spell unverified
        assert "A B underscore one nine" in result.provider_text
    else:
        assert "ACCOUNT_PHRASE_CONFIG" not in context(provider).capabilities.pronunciation


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("affect", ["neutral", "warm", "reassuring", "concerned", "upbeat", "amused"])
def test_all_supported_affects_receive_safe_best_approximation(provider, affect):
    text = "I can help you with that."
    result = compile_text(provider, text, DeliveryIntent(affect=affect, nonverbal="soft_laugh"))
    assert result.canonical_text == text
    assert "[laughs]" not in result.provider_text
    assert "[laughter]" not in result.provider_text
    assert "nonverbal" in result.degraded
    if provider != "cartesia":
        assert result.provider_text == text
        if affect != "neutral":
            assert "affect_from_canonical_wording" in result.degraded


@pytest.mark.parametrize("provider", PROVIDERS)
def test_pronunciation_modes_are_separate_and_do_not_mutate_source(provider):
    text = "Sana ZX9 012345."
    plan = PronunciationPlan((
        PronunciationSpan(0, 4, "Sana", "ALIAS", alias="Saa na"),
        PronunciationSpan(5, 8, "ZX9", "SPELL"),
        PronunciationSpan(9, 15, "012345", "DIGIT_GROUP", group_sizes=(3, 3)),
    ))
    result = compile_text(provider, text, plan=plan, language="en")
    assert result.canonical_text == text
    assert "Saa na" in result.provider_text
    assert "zero one two, three four five" in result.provider_text
    assert plan.spans[1].source == "ZX9"
    phoneme = PronunciationPlan((PronunciationSpan(0, 4, "Sana", "PHONEME", phoneme="sɑnɑ"),))
    fallback = compile_text(provider, text, plan=phoneme)
    assert "Sana" in fallback.provider_text and "phoneme" in fallback.degraded
    assert "sɑnɑ" not in fallback.provider_text


@pytest.mark.parametrize("provider", PROVIDERS)
def test_invalid_or_injected_pronunciation_fails_to_original_text(provider):
    text = "Call Sana."
    for plan in (
        PronunciationPlan((PronunciationSpan(5, 9, "Other", "ALIAS", alias="Someone"),)),
        PronunciationPlan((PronunciationSpan(5, 9, "Sana", "ALIAS", alias="[laughs]"),)),
        PronunciationPlan((PronunciationSpan(5, 9, "Sana"), PronunciationSpan(6, 9, "ana"))),
    ):
        result = compile_text(provider, text, plan=plan)
        assert "Call Sana." in result.provider_text
        assert "invalid_pronunciation_plan" in result.degraded


@pytest.mark.parametrize("provider", PROVIDERS)
def test_pause_intent_does_not_split_protected_names_codes_or_numbers(provider):
    text = "Sana Clinic has code ZX9."
    plan = PronunciationPlan((PronunciationSpan(0, 11, "Sana Clinic"),))
    intent = DeliveryIntent(pauses=(PauseIntent(4, 400), PauseIntent(11, 250)))
    result = compile_text(provider, text, intent, plan)
    assert "Sana Clinic" in result.provider_text
    assert "protected_pause" in result.degraded
    assert result.canonical_text == text
    assert ('<break time="250ms"/>' in result.provider_text) == (provider == "cartesia")


def test_turn_plan_overrides_social_requests_and_preserves_state():
    state = ConversationState("t", "a", "s", LanguageState("en"), "webrtc")
    state.grounding_state.unresolved_fields = ["phone"]
    original = state.to_dict()
    plan = derive_turn_plan(state)
    intent = delivery_from_turn_plan(plan, continuity_identity="generation-1")
    assert intent.speech_mode == "repair" and intent.pace == "slower"
    assert intent.continuity_identity == "generation-1"
    guarded = constrain_delivery(DeliveryIntent(affect="amused", nonverbal="soft_laugh"), plan)
    assert guarded.nonverbal == "none" and guarded.affect == "warm"
    assert state.to_dict() == original
    complaint = derive_turn_plan(state, TurnSignals(complaint_or_frustration=True))
    assert delivery_from_turn_plan(complaint).affect == "reassuring"


def test_pronunciation_protects_urdu_english_names_phone_email_and_codes():
    text = "ڈاکٹر Sana، Awaaz Clinic سے +923001234567 پر بات کریں، test_id@example.com، ZX9."
    plan = plan_pronunciation(text, language="ur")
    plan.validate(text)
    assert any(s.source == "Sana" and s.mode == "NORMAL" for s in plan.spans)
    assert any(s.source == "test_id@example.com" and s.mode == "SPELL" for s in plan.spans)
    assert any(s.source == "+923001234567" and s.mode == "DIGIT_GROUP" for s in plan.spans)
    result = compile_text("uplift", text, plan=plan)
    assert result.canonical_text == text
    assert "ڈاکٹر Sana" in result.provider_text and "<" not in result.provider_text


@pytest.mark.parametrize("provider", PROVIDERS)
def test_default_off_explicit_provider_rollout_and_rollback(provider):
    assert not resolve_delivery_policy(provider, environ={}).enabled
    candidate = resolve_delivery_policy(provider, environ={
        "UVA_HUMANIZATION_POLICY_VERSION": "natural_v1",
        "UVA_TTS_RENDERER_" + provider.upper(): "delivery_v1",
    })
    assert candidate.enabled
    assert not resolve_delivery_policy(provider, environ={"UVA_HUMANIZATION_POLICY_VERSION": "natural_v1"}).enabled
    assert not resolve_delivery_policy(provider, environ={
        "UVA_TTS_RENDERER_" + provider.upper(): "baseline",
    }).enabled
    with pytest.raises(ValueError):
        resolve_delivery_policy(provider, environ={"UVA_TTS_RENDERER_" + provider.upper(): "unknown"})


def test_unregistered_fish_never_gets_renderer_or_capability():
    with pytest.raises(ValueError):
        resolve_delivery_policy("fish_audio", environ={"UVA_TTS_RENDERER_FISH_AUDIO": "delivery_v1"})
    with pytest.raises(ValueError):
        resolve_capabilities("fish_audio", {"model": "s2-pro"})


@pytest.mark.parametrize("model", ["arcana", "coda", "mistv2", "mistv3"])
def test_rime_model_capabilities_and_speed_direction_respect_installed_path(model):
    ctx = context("rime", options={"model": model})
    result = compile_text("rime", "Code ZX9.", options={"model": model})
    assert result.provider_options["model"] == model
    if model == "arcana":
        assert not ctx.capabilities.speed and "spell(" not in result.provider_text
        assert "speed_alpha" not in result.provider_options
    else:
        assert "spell(ZX9)" in result.provider_text
        assert (result.provider_options["speed_alpha"] > 1) == (model == "mistv2")
    assert "time_scale_factor" not in result.provider_options


def test_unknown_cartesia_model_or_unaudited_plugin_fails_closed(monkeypatch):
    ctx = context("cartesia", options={"model": "future-model"})
    assert not ctx.capabilities.emotion and not ctx.capabilities.pause
    import worker.humanization.delivery.capabilities as capabilities
    monkeypatch.setattr(capabilities, "version", lambda name: "9.9.9")
    caps = capabilities.resolve_capabilities("cartesia", {"model": "sonic-3.5", "language": "en"})
    assert not caps.emotion and not caps.speed and "SPELL_NATIVE" not in caps.pronunciation


def test_explicit_tenant_speed_settings_remain_authoritative():
    result = compile_text("cartesia", "Hello.", options={"speed": 1.1})
    assert result.provider_options["speed"] == 1.1
    options = {"voice_settings": {"speed": 1.1, "stability": .6}, "auto_mode": True}
    result = compile_text("elevenlabs", "Hello.", options=options)
    assert result.provider_options["voice_settings"] == options["voice_settings"]
    assert options == {"voice_settings": {"speed": 1.1, "stability": .6}, "auto_mode": True}


@pytest.mark.parametrize("provider", PROVIDERS)
def test_prompt_and_static_greeting_switch_to_neutral_semantics_then_rollback(provider, monkeypatch):
    from worker.config import AgentConfig
    from worker.humanization.spoken import tts_overlay_for, llm_overlay_for
    from worker.cartesia_spoken_output import greeting_instructions
    from worker.session_opening import resolve_session_opening
    cfg = AgentConfig("a", "t", "n", "Business facts.", "v", "m",
                      agent_language="ur" if provider == "uplift" else "en",
                      llm_provider="groq", tts_provider=provider, greeting="Hi, Sana.")
    original = tts_overlay_for(cfg)
    monkeypatch.setenv("UVA_TTS_RENDERER_" + provider.upper(), "delivery_v1")
    neutral = tts_overlay_for(cfg)
    assert "provider markup" in neutral
    assert "<emotion" not in neutral and "spell(" not in neutral and "[laugh" not in neutral
    assert provider not in neutral.lower()
    assert "<break" not in greeting_instructions(cfg)
    assert "Follow TTS delivery rules" not in llm_overlay_for("groq", cfg)
    assert resolve_session_opening(cfg).text == "Hi, Sana."
    monkeypatch.setenv("UVA_TTS_RENDERER_" + provider.upper(), "baseline")
    assert tts_overlay_for(cfg) == original


def test_canonical_cleanup_preserves_facts_and_unwraps_legacy_syntax():
    from worker.humanization.history import plain_text_for_history
    text = '<emotion value="calm"/>Call <spell>AB_19</spell> or spell(ZX9). [laughs] test_id@example.com'
    plain = canonical_spoken_text(text)
    assert "<" not in plain and "[laughs]" not in plain and "spell(" not in plain
    assert "AB_19" in plain and "test_id@example.com" in plain and "ZX9" in plain
    history = plain_text_for_history(plain)
    assert "AB_19" in history and "test_id@example.com" in history


@pytest.mark.parametrize("provider", PROVIDERS)
def test_version_model_voice_language_channel_and_tenant_miss_rendered_cache(provider):
    from worker.greeting_cache import make_greeting_cache_key
    kwargs = dict(agent_id="a", tts_provider=provider, provider_voice_id="v", greeting_text="Hi.",
                  audio_channel="webrtc", language="ur" if provider == "uplift" else "en", tenant_id="t")
    baseline = make_greeting_cache_key(**kwargs)
    for update in (
        {"policy_version": "candidate"}, {"renderer_version": "v2"}, {"pronunciation_version": "v2"},
        {"provider_voice_id": "other"}, {"language": "mixed"}, {"audio_channel": "telephony"},
        {"tenant_id": "other"},
    ):
        assert make_greeting_cache_key(**(kwargs | update)) != baseline


def test_effective_environment_model_and_phrase_config_change_cache_identity(monkeypatch):
    from worker.humanization.delivery.cache import rendered_audio_identity
    a = rendered_audio_identity("cartesia", "v", "en", {}, "webrtc")
    monkeypatch.setenv("CARTESIA_TTS_MODEL", "sonic-3.6")
    assert rendered_audio_identity("cartesia", "v", "en", {}, "webrtc") != a
    monkeypatch.setenv("UPLIFT_PHRASE_CONFIG_ID", "synthetic-config-a")
    a = rendered_audio_identity("uplift", "v", "ur", {}, "webrtc")
    monkeypatch.setenv("UPLIFT_PHRASE_CONFIG_ID", "synthetic-config-b")
    assert rendered_audio_identity("uplift", "v", "ur", {}, "webrtc") != a


def test_fixture_candidate_rejects_old_pcm_other_voice_and_text_fallback(tmp_path, monkeypatch):
    import services.tts_cache as cache
    monkeypatch.setattr(cache, "FIX_DIR", tmp_path)
    monkeypatch.setattr(cache, "MAN_PATH", tmp_path / "manifest.json")
    old = cache.key("v", "Hello")
    (tmp_path / (old + ".wav")).write_bytes(b"old audio")
    (tmp_path / "manifest.json").write_text(json.dumps({old: {"text": "Hello"}}))
    assert cache.get("v", "Hello") == b"old audio"
    assert cache.get("v", "Hello", rendered_identity="candidate") is None
    new = cache.key("v", "Hello", rendered_identity="candidate")
    (tmp_path / (new + ".wav")).write_bytes(b"new audio")
    (tmp_path / "manifest.json").write_text(json.dumps({new: {"text": "Hello"}}))
    assert cache.require("v", "Hello", rendered_identity="candidate") == b"new audio"
    assert cache.get("other", "Hello", rendered_identity="candidate") is None
    assert cache.get("v", "Hello", rendered_identity="next-policy") is None


@pytest.mark.parametrize("provider", PROVIDERS)
def test_real_framework_canonical_history_audio_and_tool_chunks(provider, monkeypatch):
    from livekit.agents import AgentSession, llm
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
    from test_humanization_observability_framework import SyntheticSink, SyntheticTTS
    from worker.humanization.agent import AwaazAgent
    from worker.humanization.runtime import HumanizationRuntime
    from worker.humanization.policy import resolve_humanization_policy
    import worker.providers.registry as registry
    import worker.providers.tts.uplift as uplift

    received = []
    closed = []

    class RecordingTTS(SyntheticTTS):
        def synthesize(self, text, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):
            received.append(text)
            return super().synthesize(text, conn_options=conn_options)

        async def aclose(self):
            closed.append(True)
            await super().aclose()

    monkeypatch.setattr(registry, "_build_tts", lambda cfg: RecordingTTS())
    monkeypatch.setattr(uplift, "build", lambda voice, **kwargs: RecordingTTS())

    class Model(llm.LLM):
        def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
            return Stream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)

    class Stream(llm.LLMStream):
        async def _run(self):
            for content in ('<emo', 'tion value="calm"/> ', 'Sana can help. ', 'Code <spell>', 'ZX9</spell>.'):
                self._event_ch.send_nowait(llm.ChatChunk(id="reply", delta=llm.ChoiceDelta(content=content)))
            self._event_ch.send_nowait(llm.ChatChunk(id="reply", usage=llm.CompletionUsage(
                completion_tokens=8, prompt_tokens=10, total_tokens=18)))

    async def run():
        runtime = HumanizationRuntime(
            tenant_id="t", agent_id="a", session_id="s", language="en",
            channel="webrtc", policy=resolve_humanization_policy(environ={}),
        )
        ctx = context(provider, language="en")
        ctx.runtime = runtime
        session = AgentSession(llm=Model(), tts=SyntheticTTS(), use_tts_aligned_transcript=False,
                               tts_text_transforms=[])
        sink = SyntheticSink()
        session.output.audio = sink
        agent = AwaazAgent(instructions="Plain speech.", humanization_runtime=runtime, delivery_context=ctx)
        runtime.attach_session(session)
        await session.start(agent, record=False)
        try:
            handle = session.generate_reply(user_input="Question")
            await asyncio.wait_for(handle.wait_for_playout(), timeout=5)
            assert handle.exception() is None and sink.frames > 0
            assistants = [m.text_content for m in session.history.messages() if m.role == "assistant"]
            assert assistants == ["Sana can help. Code ZX9."]
            assert [m.text_content for m in agent.chat_ctx.messages() if m.role == "assistant"] == assistants
            static = session.say("Call Sana.", allow_interruptions=True)
            await asyncio.wait_for(static.wait_for_playout(), timeout=5)
            assert static.exception() is None
            assert received and "Sana" in received[0]
            if provider == "cartesia":
                assert "<emotion" in received[0] and "<spell>ZX9</spell>" in received[0]
            else:
                assert "<" not in received[0] and "[laugh" not in received[0]
            assert len(closed) == 2
        finally:
            await session.aclose()

    asyncio.run(run())


def test_uplift_actual_fixture_adapter_receives_strict_version_identity(monkeypatch):
    from worker.providers.tts.uplift import build
    import services.tts_cache as cache
    calls = []
    monkeypatch.setenv("UPLIFT_MODE", "fixture")

    def require(voice, text, **kwargs):
        calls.append((voice, text, kwargs))
        return cache.pcm_to_wav(bytes(4410))
    monkeypatch.setattr(cache, "require", require)

    async def run():
        plugin = build("v", rendered_identity="candidate-policy")
        try:
            async with plugin.synthesize("السلام علیکم") as stream:
                frames = [ev.frame async for ev in stream]
                assert frames and frames[0].sample_rate == 22050
        finally:
            await plugin.aclose()
    asyncio.run(run())
    assert calls == [("v", "السلام علیکم", {"rendered_identity": "candidate-policy"})]


def test_canonical_rejects_unknown_cues_but_preserves_literal_identifiers():
    assert canonical_spoken_text("[unsupported dance] Your code is [AB_19].") == "Your code is AB_19."
    assert canonical_spoken_text("test_id@example.com and AB_19") == "test_id@example.com and AB_19"


def test_llm_canonical_boundary_preserves_tool_ids_arguments_and_usage():
    from livekit.agents import llm
    from worker.humanization.agent import AwaazAgent

    async def source():
        yield llm.ChatChunk(id="r", delta=llm.ChoiceDelta(content="<emotion value='calm'/>Checking."))
        yield llm.ChatChunk(id="r", delta=llm.ChoiceDelta(tool_calls=[
            llm.FunctionToolCall(name="lookup_business_info", arguments='{"query":"AB_19"}', call_id="call1"),
        ]))
        yield llm.ChatChunk(id="r", usage=llm.CompletionUsage(
            prompt_tokens=10, completion_tokens=5, total_tokens=15))

    async def run():
        agent = AwaazAgent(instructions="plain")
        chunks = [c async for c in agent._canonical_llm_stream(source())]
        assert chunks[0].delta.content == "Checking."
        assert chunks[1].delta.tool_calls[0].call_id == "call1"
        assert chunks[1].delta.tool_calls[0].arguments == '{"query":"AB_19"}'
        assert chunks[2].usage.total_tokens == 15
        assert chunks[0].id == chunks[1].id == "r"
    asyncio.run(run())


@pytest.mark.parametrize("provider", PROVIDERS)
def test_isolated_synthesis_closes_and_forwards_one_metric(provider, monkeypatch):
    from test_humanization_observability_framework import SyntheticTTS
    import worker.providers.registry as registry
    import worker.providers.tts.uplift as uplift
    plugin_instances = []
    effective_cfgs = []

    def build(cfg):
        effective_cfgs.append(cfg)
        plugin = SyntheticTTS()
        plugin_instances.append(plugin)
        return plugin
    monkeypatch.setattr(registry, "_build_tts", build)
    monkeypatch.setattr(uplift, "build", lambda *a, **kw: build(runtime_config("uplift")))

    async def run():
        target = SyntheticTTS()
        metrics = []
        target.on("metrics_collected", metrics.append)
        ctx = context(provider)
        ctx.metrics_target = target
        for _ in range(2):
            frames = [f async for f in ctx.audio("Sana can help.")]
            assert frames
        assert len(metrics) == 2
        assert len(plugin_instances) == 2 and plugin_instances[0] is not plugin_instances[1]
        assert ctx.cfg.tts_options == {}
        if provider != "uplift":
            assert all(cfg.tts_options["model"] == ctx.capabilities.model for cfg in effective_cfgs)
        await target.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("provider", PROVIDERS)
def test_real_tool_truth_survives_candidate_renderer(provider, monkeypatch):
    from livekit.agents import AgentSession
    from test_humanization_observability_framework import SyntheticTTS, SyntheticSink, SyntheticLLM
    from worker.humanization.agent import AwaazAgent
    from worker.humanization.runtime import HumanizationRuntime
    from worker.humanization.policy import resolve_humanization_policy
    from worker.tools import AgentUserdata, lookup_business_info
    import worker.providers.registry as registry
    import worker.providers.tts.uplift as uplift
    import worker.tools as tools
    import worker.ssrf_guard as ssrf

    from types import SimpleNamespace
    async def post(*a, **kw):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"success": True, "result": "nine to five"})
    async def client():
        return SimpleNamespace(post=post)
    monkeypatch.setattr(tools, "_shared_http_client", client)
    monkeypatch.setattr(ssrf, "prepare_tools_post_url", lambda url: (url, {}))
    monkeypatch.setattr(registry, "_build_tts", lambda cfg: SyntheticTTS())
    monkeypatch.setattr(uplift, "build", lambda *a, **kw: SyntheticTTS())

    async def run():
        runtime = HumanizationRuntime(
            tenant_id="t", agent_id="a", session_id="s", language="en",
            channel="webrtc", policy=resolve_humanization_policy(environ={}),
        )
        ud = AgentUserdata("t", "a", "s", tools_base_url="https://synthetic.example",
                           tools_auth_secret="sentinel")
        ud.humanization_runtime = runtime
        ctx = context(provider, language="en")
        ctx.runtime = runtime
        session = AgentSession(llm=SyntheticLLM(), tts=SyntheticTTS(), userdata=ud,
                               tts_text_transforms=[], use_tts_aligned_transcript=False)
        session.output.audio = SyntheticSink()
        runtime.attach_session(session)
        agent = AwaazAgent(instructions="plain", tools=[lookup_business_info],
                           humanization_runtime=runtime, delivery_context=ctx)
        await session.start(agent, record=False)
        try:
            handle = session.generate_reply(user_input="What are the hours?")
            await asyncio.wait_for(handle.wait_for_playout(), 5)
            assert handle.exception() is None
            assert runtime.tools.results["synthetic_call_1"].outcome == "SUCCESS"
            assert any(item.type == "function_call_output" for item in session.history.items)
            assert [m.text_content for m in session.history.messages() if m.role == "assistant"] == [
                "Synthetic business hours are nine to five."
            ]
        finally:
            await session.aclose()
    asyncio.run(run())


def test_actual_provider_constructors_preserve_models_and_audio_formats(monkeypatch):
    from worker.providers.registry import _build_tts
    for key in ("CARTESIA_API_KEY", "RIME_API_KEY", "ELEVEN_API_KEY", "UPLIFTAI_API_KEY"):
        monkeypatch.setenv(key, "synthetic-constructor-only")
    monkeypatch.setenv("UPLIFT_MODE", "live")

    async def run():
        expected = {"cartesia": ("sonic-3.5", 16000), "rime": ("arcana", 16000),
                    "elevenlabs": ("eleven_flash_v2_5", 22050), "uplift": (None, 22050)}
        for provider in PROVIDERS:
            plugin = _build_tts(runtime_config(provider))
            try:
                model, sample_rate = expected[provider]
                if model is not None:
                    assert plugin.model == model
                assert plugin.sample_rate == sample_rate
                assert plugin.num_channels == 1
            finally:
                await plugin.aclose()
    asyncio.run(run())


def test_uplift_phrase_config_live_constructor_preserves_pcm(monkeypatch):
    from livekit.plugins import upliftai
    from worker.providers.tts.uplift import build
    kwargs = []
    monkeypatch.setenv("UPLIFT_MODE", "live")
    monkeypatch.setenv("UPLIFT_PHRASE_CONFIG_ID", "synthetic-config")
    monkeypatch.delenv("UPLIFT_DISABLE_PHRASE_CONFIG", raising=False)
    monkeypatch.setattr(upliftai, "TTS", lambda **kw: kwargs.append(kw))
    build("v")
    assert kwargs == [{"voice_id": "v", "output_format": "PCM_22050_16",
                       "phrase_replacement_config_id": "synthetic-config"}]


def test_greeting_pcm_is_not_reused_after_policy_change():
    from livekit import rtc
    from worker.greeting_cache import GreetingAudioCache, make_greeting_cache_key
    kwargs = dict(agent_id="a", tts_provider="cartesia", provider_voice_id="v",
                  greeting_text="Hello.", audio_channel="webrtc", language="en", tenant_id="t")
    old_key = make_greeting_cache_key(**kwargs)
    new_key = make_greeting_cache_key(**kwargs, policy_version="next-policy")
    cache = GreetingAudioCache()
    cache.put(old_key, [rtc.AudioFrame(data=bytes(320), sample_rate=16000,
                                     num_channels=1, samples_per_channel=160)])
    assert cache.get(old_key) is not None
    assert cache.get(new_key) is None


@pytest.mark.parametrize("tail", ["<emo", "<stage direction", "[laugh", "[unsupported cue"])
def test_canonical_drops_incomplete_delivery_syntax(tail):
    assert canonical_spoken_text("Your code is AB_19. " + tail) == "Your code is AB_19."
    assert canonical_spoken_text("3 < 5, and test_id@example.com") == "3 < 5, and test_id@example.com"
