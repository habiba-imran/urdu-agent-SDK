"""Phase 0–1 humanization: effective providers + spoken instruction composition."""

from __future__ import annotations

from worker.config import AgentConfig
from worker.humanization import (
    GEMINI_LLM_OVERLAY,
    GROQ_LLM_OVERLAY,
    UNIVERSAL_SPOKEN_RULES,
    build_spoken_output_profile,
    compose_system_instructions,
    resolve_effective_providers,
)


def _cfg(**overrides) -> AgentConfig:
    base = dict(
        agent_id="a",
        tenant_id="t",
        name="n",
        prompt="persona",
        voice_id="v",
        llm_model="gemini-2.5-flash",
        agent_language="en",
        llm_provider="gemini",
        tts_provider="uplift",
    )
    base.update(overrides)
    return AgentConfig(**base)


def test_resolve_effective_providers_webrtc_english_keeps_gemini(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg = _cfg(tts_provider="rime", llm_provider="gemini")
    effective = resolve_effective_providers(cfg, "andromeda", audio_channel="webrtc")
    assert effective.cartesia_forced is False
    assert effective.groq_forced is False
    assert effective.tts_provider == "rime"
    assert effective.llm_provider == "gemini"
    assert effective.provider_voice_id == "andromeda"


def test_resolve_effective_providers_webrtc_explicit_groq_sticks(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg = _cfg(tts_provider="rime", llm_provider="groq", llm_model="openai/gpt-oss-20b")
    effective = resolve_effective_providers(cfg, "andromeda", audio_channel="webrtc")
    assert effective.groq_forced is False
    assert effective.llm_provider == "groq"


def test_resolve_effective_providers_telephony_keeps_configured(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg = _cfg(tts_provider="rime", llm_provider="gemini", tts_voice_id="rime-arcana-astra")
    effective = resolve_effective_providers(cfg, "astra", audio_channel="telephony")
    assert effective.cartesia_forced is False
    assert effective.groq_forced is False
    assert effective.tts_provider == "rime"
    assert effective.llm_provider == "gemini"
    assert effective.cfg.tts_voice_id == "rime-arcana-astra"
    assert effective.provider_voice_id == "astra"


def test_universal_rules_have_no_provider_markup():
    assert "<emotion" not in UNIVERSAL_SPOKEN_RULES
    assert "<break" not in UNIVERSAL_SPOKEN_RULES
    assert "[laugh" not in UNIVERSAL_SPOKEN_RULES
    assert "Write for the ear" in UNIVERSAL_SPOKEN_RULES


def test_compose_cartesia_has_universal_llm_and_tts_layers():
    text = compose_system_instructions(
        _cfg(tts_provider="cartesia", llm_provider="gemini", llm_model="gemini-3.6-flash")
    )
    assert UNIVERSAL_SPOKEN_RULES in text
    assert GEMINI_LLM_OVERLAY in text
    assert "EMOTION (required" in text
    assert "Do NOT emit <emotion>" not in text
    # Universal + TTS should not triple the same anti-markdown paragraph.
    assert text.count("Do not use markdown, headings, bullets, emoji") == 1


def test_compose_cartesia_groq_uses_tts_markup_aware_overlay():
    from worker.humanization import GROQ_LLM_OVERLAY_TTS_MARKUP

    text = compose_system_instructions(
        _cfg(tts_provider="cartesia", llm_provider="groq", llm_model="openai/gpt-oss-20b")
    )
    assert GROQ_LLM_OVERLAY_TTS_MARKUP in text
    assert "Do not invent fillers or emotion tags just to pad" not in text
    assert "EMOTION (required" in text


def test_compose_cartesia_light_groq_keeps_plain_overlay():
    text = compose_system_instructions(
        _cfg(
            tts_provider="cartesia",
            llm_provider="groq",
            llm_model="openai/gpt-oss-20b",
            tts_options={"spoken_style": "light"},
        )
    )
    assert GROQ_LLM_OVERLAY in text
    assert "Do NOT emit <emotion>" in text
    assert "EMOTION (required" not in text


def test_compose_rime_has_no_cartesia_ssml_examples():
    text = compose_system_instructions(
        _cfg(tts_provider="rime", llm_provider="groq", llm_model="openai/gpt-oss-20b")
    )
    assert UNIVERSAL_SPOKEN_RULES in text
    assert GROQ_LLM_OVERLAY in text
    assert "Rime accepts NO SSML" in text
    assert "spell(" in text
    assert '<break time=' not in text
    assert '<emotion value=' not in text


def test_compose_elevenlabs_gets_universal_and_llm_without_tts_overlay():
    text = compose_system_instructions(
        _cfg(tts_provider="elevenlabs", llm_provider="groq", llm_model="openai/gpt-oss-20b")
    )
    assert UNIVERSAL_SPOKEN_RULES in text
    assert GROQ_LLM_OVERLAY in text
    assert "EMOTION (required" not in text
    assert "Rime accepts NO SSML" not in text
    assert "<break" not in text


def test_compose_uplift_gets_universal_and_gemini_overlay():
    text = compose_system_instructions(_cfg(tts_provider="uplift", llm_provider="gemini"))
    assert UNIVERSAL_SPOKEN_RULES in text
    assert GEMINI_LLM_OVERLAY in text
    assert "<emotion" not in text


def test_groq_overlay_char_budget_is_small():
    from worker.humanization import GROQ_LLM_OVERLAY_TTS_MARKUP

    # Keep Groq overlay tiny relative to free-tier prompt pressure.
    assert len(GROQ_LLM_OVERLAY) < 400
    assert len(GROQ_LLM_OVERLAY_TTS_MARKUP) < 400
    assert len(GEMINI_LLM_OVERLAY) < 450
    profile = build_spoken_output_profile(
        _cfg(tts_provider="elevenlabs", llm_provider="groq")
    )
    rendered = profile.render()
    # Universal + groq + ElevenLabs delivery overlay (plain-text humanization).
    assert len(rendered) < len(UNIVERSAL_SPOKEN_RULES) + 900
    assert GROQ_LLM_OVERLAY in rendered
    assert "ElevenLabs delivery" in rendered


def test_cartesia_path_system_chars_do_not_explode_vs_overlay_alone():
    """Cartesia trim + universal should not balloon past a modest ceiling."""
    text = compose_system_instructions(
        _cfg(tts_provider="cartesia", llm_provider="groq", llm_model="openai/gpt-oss-20b")
    )
    # Base (~1.2k) + universal (~0.9k) + groq (~0.3k) + cartesia delivery (~1.2k) ≈ < 5k.
    assert len(text) < 5000
