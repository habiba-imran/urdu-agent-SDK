"""Phase 5 humanization: gated provider delivery experiments (defaults unchanged)."""

from __future__ import annotations

import pytest

from worker.config import AgentConfig
from worker.fish_spoken_sanitize import sanitize_spoken_text as fish_sanitize
from worker.humanization.spoken import compose_system_instructions, tts_overlay_for
from worker.providers.llm import gemini as gemini_llm
from worker.providers.tts.cartesia_options import (
    cartesia_experiment_label,
    resolve_cartesia_tts_kwargs,
)
from worker.providers.tts.elevenlabs_options import (
    ElevenLabsTtsOptionsError,
    elevenlabs_v3_streaming_available,
    validate_elevenlabs_tts_options,
)
from worker.providers.tts.fish_audio_options import (
    FISH_RESTRAINED_SPOKEN_OVERLAY,
    fish_restrained_spoken_enabled,
    resolve_fish_tts_kwargs,
    validate_fish_tts_options,
)
from worker.providers.tts.rime_options import resolve_rime_tts_kwargs, validate_rime_tts_options
from worker.spoken_sanitize import sanitizer_for_provider


def _cfg(**overrides) -> AgentConfig:
    base = dict(
        agent_id="a",
        tenant_id="t",
        name="n",
        prompt="persona",
        voice_id="v",
        llm_model="openai/gpt-oss-20b",
        agent_language="en",
        llm_provider="groq",
        tts_provider="cartesia",
    )
    base.update(overrides)
    return AgentConfig(**base)


# --- 5A Cartesia ---


def test_cartesia_sonic36_opt_in_via_tts_options():
    kwargs = resolve_cartesia_tts_kwargs("voice", "en", {"model": "sonic-3.6"})
    assert kwargs["model"] == "sonic-3.6"
    # Default path unchanged.
    assert resolve_cartesia_tts_kwargs("voice", "en", {})["model"] == "sonic-3.5"


def test_cartesia_demo_env_model_override(monkeypatch):
    monkeypatch.setenv("CARTESIA_TTS_MODEL", "sonic-3.6")
    assert resolve_cartesia_tts_kwargs("voice", "en", {})["model"] == "sonic-3.6"
    # Explicit agent option wins over env.
    assert (
        resolve_cartesia_tts_kwargs("voice", "en", {"model": "sonic-3.5"})["model"]
        == "sonic-3.5"
    )


def test_cartesia_experiment_label_includes_style():
    assert cartesia_experiment_label({}) == "sonic-3.5+light"
    assert (
        cartesia_experiment_label({"model": "sonic-3.6", "spoken_style": "light"})
        == "sonic-3.6+light"
    )


# --- 5B Rime ---


def test_rime_coda_and_mist_opt_in_without_arcana_speed_alpha():
    coda = resolve_rime_tts_kwargs("lyra", "eng", {"model": "coda"})
    assert coda["model"] == "coda"
    assert "speed_alpha" not in coda

    mist = resolve_rime_tts_kwargs("cove", "eng", {"model": "mistv3"})
    assert mist["model"] == "mistv3"
    assert "speed_alpha" not in mist

    mist_tuned = resolve_rime_tts_kwargs(
        "cove", "eng", {"model": "mistv3", "speed_alpha": 1.0}
    )
    assert mist_tuned["speed_alpha"] == 1.0

    arcana = resolve_rime_tts_kwargs("astra", "eng", {})
    assert arcana["model"] == "arcana"
    assert arcana["speed_alpha"] == 1.1


def test_rime_rejects_unknown_model():
    with pytest.raises(Exception) as exc:
        validate_rime_tts_options({"model": "not-a-rime-model"})
    assert "model" in str(exc.value).lower()


# --- 5C ElevenLabs ---


def test_elevenlabs_v3_refused_on_pinned_plugin():
    assert elevenlabs_v3_streaming_available() is False
    with pytest.raises(ElevenLabsTtsOptionsError) as exc:
        validate_elevenlabs_tts_options({"model": "eleven_v3_conversational"})
    assert "1.7.1" in str(exc.value) or "text-to-dialogue" in str(exc.value)

    with pytest.raises(ElevenLabsTtsOptionsError):
        validate_elevenlabs_tts_options({"spoken_style": "audio_tags"})

    # Baseline still ok.
    assert validate_elevenlabs_tts_options({"model": "eleven_flash_v2_5"}) == {
        "model": "eleven_flash_v2_5"
    }


# --- 5D Fish ---


def test_fish_restrained_overlay_and_sanitizer_allowlist():
    assert fish_restrained_spoken_enabled({}) is False
    assert fish_restrained_spoken_enabled({"spoken_style": "restrained"}) is True

    opts = {"spoken_style": "restrained"}
    overlay = tts_overlay_for(_cfg(tts_provider="fish_audio", tts_options=opts))
    assert overlay == FISH_RESTRAINED_SPOKEN_OVERLAY

    kept = fish_sanitize(
        "Hello [emphasis] there [gasp] [crying] friend [laugh]",
        tts_options=opts,
    )
    assert "[emphasis]" in kept
    assert "[laugh]" in kept
    assert "[gasp]" not in kept
    assert "[crying]" not in kept

    stripped = fish_sanitize("Hello [emphasis] there", tts_options={})
    assert "[emphasis]" not in stripped

    # spoken_style must not leak into TTS constructor kwargs.
    kwargs = resolve_fish_tts_kwargs("vid", opts)
    assert "spoken_style" not in kwargs
    assert kwargs["model"] == "s2.1-pro"


def test_fish_plain_compose_has_no_bracket_teaching():
    text = compose_system_instructions(_cfg(tts_provider="fish_audio"))
    assert "Fish Audio delivery" in text
    assert "[gasp]" not in text
    assert FISH_RESTRAINED_SPOKEN_OVERLAY not in text


def test_sanitizer_dispatcher_passes_fish_options():
    fn = sanitizer_for_provider(
        "fish_audio", tts_options={"spoken_style": "restrained"}
    )
    assert fn is not None
    out = fn("ok [calm] no [sobbing]")
    assert "[calm]" in out
    assert "[sobbing]" not in out


# --- 5E Gemini thinking level ---


def test_gemini_thinking_level_env(monkeypatch):
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", "low")
    assert gemini_llm._resolve_thinking_level() == "low"
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", "nope")
    assert gemini_llm._resolve_thinking_level() == "minimal"


def test_validate_fish_spoken_style():
    assert validate_fish_tts_options({"spoken_style": "restrained"}) == {
        "spoken_style": "restrained"
    }
    with pytest.raises(Exception):
        validate_fish_tts_options({"spoken_style": "theatrical"})
