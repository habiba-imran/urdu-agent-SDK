"""Phase 3 humanization: sanitizers + ElevenLabs/Fish options + Cartesia spoken_style."""

from __future__ import annotations

from worker.config import AgentConfig
from worker.humanization.spoken import compose_system_instructions, tts_overlay_for
from worker.providers.tts.cartesia_options import (
    cartesia_light_spoken_enabled,
    validate_cartesia_tts_options,
)
from worker.providers.tts.elevenlabs_options import (
    ELEVENLABS_TTS_DEFAULTS,
    ElevenLabsTtsOptionsError,
    resolve_elevenlabs_tts_kwargs,
    validate_elevenlabs_tts_options,
)
from worker.providers.tts.fish_audio_options import (
    FISH_TTS_DEFAULTS,
    FishTtsOptionsError,
    resolve_fish_tts_kwargs,
    validate_fish_tts_options,
)
from worker.spoken_sanitize import sanitizer_for_provider


def _cfg(**overrides) -> AgentConfig:
    base = dict(
        agent_id="a",
        tenant_id="t",
        name="n",
        prompt="persona",
        voice_id="v",
        llm_model="m",
        agent_language="en",
        llm_provider="groq",
        tts_provider="elevenlabs",
    )
    base.update(overrides)
    return AgentConfig(**base)


def test_sanitizers_strip_cartesia_and_fish_markup():
    sample = 'Hi <emotion value="calm"/> <break time="200ms"/> [whisper] **there**'
    for provider in ("rime", "elevenlabs", "fish_audio", "uplift"):
        fn = sanitizer_for_provider(provider)
        assert fn is not None
        out = fn(sample)
        assert "<emotion" not in out
        assert "<break" not in out
        assert "[whisper]" not in out
        assert "**" not in out
        assert "Hi" in out
        assert "there" in out


def test_cartesia_sanitizer_keeps_ssml():
    fn = sanitizer_for_provider("cartesia")
    assert fn is not None
    out = fn('Hi <break time="200ms"/> there')
    assert '<break time="200ms"/>' in out


def test_elevenlabs_defaults_and_validation():
    assert validate_elevenlabs_tts_options({}) == {}
    kwargs = resolve_elevenlabs_tts_kwargs("voice-1", "en", {})
    assert kwargs["model"] == ELEVENLABS_TTS_DEFAULTS["model"]
    assert kwargs["auto_mode"] is True
    assert kwargs["voice_settings"].stability == 0.5
    try:
        validate_elevenlabs_tts_options({"unknown": 1})
        raise AssertionError("expected error")
    except ElevenLabsTtsOptionsError:
        pass


def test_fish_defaults_and_validation():
    assert validate_fish_tts_options({}) == {}
    kwargs = resolve_fish_tts_kwargs("voice-1", {})
    assert kwargs["model"] == FISH_TTS_DEFAULTS["model"]
    assert kwargs["latency_mode"] == "balanced"
    try:
        validate_fish_tts_options({"latency_mode": "turbo"})
        raise AssertionError("expected error")
    except FishTtsOptionsError:
        pass


def test_elevenlabs_resolve_kwargs_include_defaults():
    kwargs = resolve_elevenlabs_tts_kwargs("vid", "en", {})
    assert kwargs["voice_id"] == "vid"
    assert kwargs["language"] == "en"
    assert kwargs["model"] == "eleven_flash_v2_5"
    assert kwargs["auto_mode"] is True
    assert kwargs["apply_text_normalization"] == "off"
    assert kwargs["enable_ssml_parsing"] is False
    assert kwargs["voice_settings"].stability == 0.5


def test_fish_resolve_kwargs_include_defaults_and_overrides():
    kwargs = resolve_fish_tts_kwargs("vid", {"latency_mode": "low", "speed": 1.05})
    assert kwargs["voice_id"] == "vid"
    assert kwargs["model"] == "s2.1-pro"
    assert kwargs["latency_mode"] == "low"
    assert kwargs["speed"] == 1.05


def test_cartesia_spoken_style_light_uses_plain_overlay():
    assert validate_cartesia_tts_options({"spoken_style": "light"}) == {
        "spoken_style": "light"
    }
    assert cartesia_light_spoken_enabled({"spoken_style": "light"}) is True
    # Platform default is manual_ssml — empty options are not light.
    assert cartesia_light_spoken_enabled({}) is False
    overlay = tts_overlay_for(_cfg(tts_provider="cartesia", tts_options={"spoken_style": "light"}))
    assert "Do NOT emit <emotion>" in overlay
    manual = tts_overlay_for(
        _cfg(tts_provider="cartesia", tts_options={"spoken_style": "manual_ssml"})
    )
    assert "EMOTION (required" in manual
    default_manual = tts_overlay_for(_cfg(tts_provider="cartesia"))
    assert "EMOTION (required" in default_manual


def test_elevenlabs_compose_includes_plain_delivery_overlay():
    text = compose_system_instructions(_cfg(tts_provider="elevenlabs", llm_provider="groq"))
    assert "ElevenLabs delivery" in text
    assert "Write for the ear" in text
