"""Unit tests for Cartesia tts_options validation and build-time defaults (Phase B)."""

from worker.providers.tts.cartesia_options import (
    CARTESIA_TTS_DEFAULTS,
    CartesiaTtsOptionsError,
    cartesia_expressive_enabled,
    resolve_cartesia_tts_kwargs,
    validate_cartesia_tts_options,
)


def test_empty_options_validate_and_apply_defaults():
    assert validate_cartesia_tts_options({}) == {}
    kwargs = resolve_cartesia_tts_kwargs("voice-uuid", "en", {})
    assert kwargs["model"] == CARTESIA_TTS_DEFAULTS["model"]
    assert kwargs["speed"] == CARTESIA_TTS_DEFAULTS["speed"]
    assert kwargs["emotion"] == CARTESIA_TTS_DEFAULTS["emotion"]
    assert kwargs["voice"] == "voice-uuid"
    assert kwargs["language"] == "en"
    assert kwargs["encoding"] == "pcm_s16le"
    assert kwargs["sample_rate"] == 16000
    assert "volume" not in kwargs


def test_telephony_channel_uses_mulaw_8k():
    kwargs = resolve_cartesia_tts_kwargs(
        "voice-uuid", "en", {}, audio_channel="telephony"
    )
    assert kwargs["encoding"] == "pcm_mulaw"
    assert kwargs["sample_rate"] == 8000


def test_overrides_merge_with_defaults():
    kwargs = resolve_cartesia_tts_kwargs(
        "voice-uuid",
        "en",
        {"speed": 1.1, "emotion": ["sympathetic"]},
    )
    assert kwargs["model"] == "sonic-3.5"
    assert kwargs["speed"] == 1.1
    assert kwargs["emotion"] == ["sympathetic"]


def test_validate_accepts_single_emotion_string():
    assert validate_cartesia_tts_options({"emotion": "calm"}) == {"emotion": ["calm"]}


def test_validate_rejects_unknown_keys():
    try:
        validate_cartesia_tts_options({"encoding": "pcm_mulaw"})
        raise AssertionError("expected CartesiaTtsOptionsError")
    except CartesiaTtsOptionsError as exc:
        assert "unsupported" in str(exc)


def test_validate_rejects_out_of_range_speed():
    try:
        validate_cartesia_tts_options({"speed": 2.5})
        raise AssertionError("expected CartesiaTtsOptionsError")
    except CartesiaTtsOptionsError as exc:
        assert "speed" in str(exc)


def test_expressive_defaults_off_and_unavailable_on_cartesia_plugin():
    assert CARTESIA_TTS_DEFAULTS["expressive"] is False
    assert validate_cartesia_tts_options({"expressive": True}) == {"expressive": True}
    assert validate_cartesia_tts_options({"expressive": False}) == {"expressive": False}
    # Empty options → manual SSML path (expressive off by default).
    assert cartesia_expressive_enabled({}) is False
    assert cartesia_expressive_enabled({"expressive": False}) is False
    # Requesting expressive still requires a LiveKit build that exposes it; on 1.6.5
    # AgentSession has no public expressive kwarg, so this stays False.
    assert cartesia_expressive_enabled({"expressive": True}) is False
    kwargs = resolve_cartesia_tts_kwargs("voice-uuid", "en", {"expressive": True})
    assert "expressive" not in kwargs
    assert kwargs["model"] == CARTESIA_TTS_DEFAULTS["model"]
