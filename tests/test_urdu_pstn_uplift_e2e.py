"""End-to-end verification: Urdu PSTN keeps Uplift + coherent spoken instructions."""

from __future__ import annotations

from worker.config import AgentConfig
from worker.humanization.spoken import (
    URDU_SPOKEN_OUTPUT_RULES,
    compose_system_instructions,
    tts_overlay_for,
)
from worker.humanization.resolve import resolve_effective_providers
from worker.main import _language_directive, build_agent, SYSTEM_INSTRUCTIONS
from worker.spoken_sanitize import sanitizer_for_provider


def _urdu_uplift(**overrides) -> AgentConfig:
    base = dict(
        agent_id="ur-agent",
        tenant_id="t",
        name="Urdu Agent",
        prompt="آپ ایک مددگار ایجنٹ ہیں۔",
        voice_id="v_meklc281",
        llm_model="gemini-3.6-flash",
        agent_language="ur",
        llm_provider="gemini",
        tts_provider="uplift",
        tts_voice_id="v_meklc281",
        stt_provider="gladia",
    )
    base.update(overrides)
    return AgentConfig(**base)


def test_urdu_pstn_e2e_keeps_uplift_and_coherent_prompt(monkeypatch):
    """Full path: remaps → effective cfg → instructions → overlay → sanitizer.

    Before the fix, telephony forced Cartesia Katie and the Cartesia emotion overlay
    contradicted URDU_SPOKEN_OUTPUT_RULES.
    """
    monkeypatch.setenv("GROQ_API_KEY", "test-key")  # must not steal Urdu Gemini
    cfg = _urdu_uplift()
    effective = resolve_effective_providers(
        cfg, "v_meklc281", audio_channel="telephony"
    )

    assert effective.cartesia_forced is False
    assert effective.groq_forced is False
    assert effective.tts_provider == "uplift"
    assert effective.llm_provider == "gemini"
    assert effective.agent_language.startswith("ur")
    assert effective.provider_voice_id == "v_meklc281"
    assert effective.cfg.tts_voice_id == "v_meklc281"

    instructions = compose_system_instructions(effective.cfg) + _language_directive(
        effective.cfg.agent_language
    )
    assert URDU_SPOKEN_OUTPUT_RULES in instructions
    assert "Uplift delivery" in instructions
    assert "EMOTION (required" not in instructions
    assert "<emotion value=" not in instructions
    assert "Respond only in Pakistani Urdu" in instructions

    overlay = tts_overlay_for(effective.cfg)
    assert "Uplift" in overlay
    assert "<emotion" not in overlay

    san = sanitizer_for_provider(
        effective.tts_provider, tts_options=effective.cfg.tts_options
    )
    assert san is not None
    leaked = san('جی <emotion value="calm"/> [whisper] ٹھیک ہے')
    assert "<emotion" not in leaked
    assert "[whisper]" not in leaked


def test_urdu_pstn_build_agent_matches_uplift_path(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    effective = resolve_effective_providers(
        _urdu_uplift(), "v_meklc281", audio_channel="telephony"
    )
    agent = build_agent(effective.cfg)
    assert agent.instructions.startswith(SYSTEM_INSTRUCTIONS)
    assert "LANGUAGE — Pakistani Urdu" in agent.instructions
    assert "Uplift delivery" in agent.instructions
    assert "EMOTION (required" not in agent.instructions


def test_english_rime_pstn_still_remaps_to_cartesia(monkeypatch):
    """Regression: English Rime PSTN must still force Cartesia."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg = AgentConfig(
        agent_id="en",
        tenant_id="t",
        name="n",
        prompt="persona",
        voice_id="rime-arcana-astra",
        llm_model="gemini-3.6-flash",
        agent_language="en",
        llm_provider="gemini",
        tts_provider="rime",
        tts_voice_id="rime-arcana-astra",
    )
    effective = resolve_effective_providers(cfg, "astra", audio_channel="telephony")
    assert effective.cartesia_forced is True
    assert effective.tts_provider == "cartesia"
    assert effective.groq_forced is True
    assert effective.llm_provider == "groq"
    text = compose_system_instructions(effective.cfg)
    assert "EMOTION (required" in text
