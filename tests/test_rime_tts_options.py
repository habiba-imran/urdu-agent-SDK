"""Unit tests for Rime tts_options validation, Coda defaults, and audio profiles."""

from worker.providers.tts.rime_options import (
    RIME_TTS_DEFAULTS,
    RimeTtsOptionsError,
    resolve_rime_tts_kwargs,
    validate_rime_tts_options,
)


def test_empty_options_apply_coda_websocket_defaults():
    assert validate_rime_tts_options({}) == {}
    kwargs = resolve_rime_tts_kwargs("astra", "eng", {})
    assert kwargs["model"] == RIME_TTS_DEFAULTS["model"] == "coda"
    assert kwargs["speed_alpha"] == 1.1
    assert kwargs["use_websocket"] is True
    assert kwargs["segment"] == "bySentence"
    assert kwargs["speaker"] == "astra"
    assert kwargs["lang"] == "eng"
    assert kwargs["sample_rate"] == 16000
    assert "time_scale_factor" not in kwargs


def test_telephony_channel_uses_8k():
    kwargs = resolve_rime_tts_kwargs("astra", "eng", {}, audio_channel="telephony")
    assert kwargs["sample_rate"] == 8000
    assert kwargs["model"] == "coda"


def test_unknown_channel_falls_back_to_webrtc_16k():
    kwargs = resolve_rime_tts_kwargs("astra", "eng", {}, audio_channel="unknown")
    assert kwargs["sample_rate"] == 16000


def test_speed_alpha_override_keeps_coda():
    kwargs = resolve_rime_tts_kwargs("celeste", "eng", {"speed_alpha": 1.05})
    assert kwargs["model"] == "coda"
    assert kwargs["speed_alpha"] == 1.05


def test_validate_rejects_unknown_keys():
    try:
        validate_rime_tts_options({"emotion": ["calm"]})
        raise AssertionError("expected RimeTtsOptionsError")
    except RimeTtsOptionsError as exc:
        assert "unsupported" in str(exc)


def test_validate_rejects_out_of_range_speed_alpha():
    try:
        validate_rime_tts_options({"speed_alpha": 9.0})
        raise AssertionError("expected RimeTtsOptionsError")
    except RimeTtsOptionsError as exc:
        assert "speed_alpha" in str(exc)
