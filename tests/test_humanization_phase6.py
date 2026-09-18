"""Phase 6 humanization: gated Deepgram Flux + LiveKit TurnDetector (defaults unchanged)."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from worker.humanization.turn import (
    build_turn_profile,
    materialize_turn_detection,
    resolve_deepgram_flux_eager_threshold,
    resolve_deepgram_stt_mode,
    resolve_turn_detector_version,
    turn_profile_to_livekit_options,
)


def test_deepgram_stt_mode_default_nova(monkeypatch):
    monkeypatch.delenv("UVA_DEEPGRAM_STT_MODE", raising=False)
    assert resolve_deepgram_stt_mode(None) == "nova"
    assert resolve_deepgram_stt_mode({}) == "nova"


def test_deepgram_stt_mode_flux_env_and_options(monkeypatch):
    monkeypatch.setenv("UVA_DEEPGRAM_STT_MODE", "flux")
    assert resolve_deepgram_stt_mode(None) == "flux"
    monkeypatch.delenv("UVA_DEEPGRAM_STT_MODE", raising=False)
    assert resolve_deepgram_stt_mode({"stt_mode": "flux"}) == "flux"


def test_flux_eager_disabled_by_default_and_blocked_for_groq(monkeypatch):
    monkeypatch.delenv("UVA_DEEPGRAM_FLUX_EAGER_EOT", raising=False)
    assert resolve_deepgram_flux_eager_threshold(None, llm_provider="gemini") is None

    monkeypatch.setenv("UVA_DEEPGRAM_FLUX_EAGER_EOT", "1")
    assert resolve_deepgram_flux_eager_threshold(None, llm_provider="groq") is None
    th = resolve_deepgram_flux_eager_threshold(None, llm_provider="gemini")
    assert th == 0.5


def test_deepgram_flux_build_uses_sttv2(monkeypatch):
    created: dict = {}

    class FakeSTT:
        def __init__(self, **kwargs):
            created["stt"] = kwargs

    class FakeSTTv2:
        def __init__(self, **kwargs):
            created["sttv2"] = kwargs

    monkeypatch.setenv("UVA_DEEPGRAM_STT_MODE", "flux")
    monkeypatch.setitem(
        sys.modules,
        "livekit.plugins.deepgram",
        SimpleNamespace(STT=FakeSTT, STTv2=FakeSTTv2),
    )
    import worker.providers.stt.deepgram as dg

    dg.build("en", {"stt_mode": "flux", "flux_eager_eot": False})
    assert "sttv2" in created
    assert created["sttv2"]["model"] == "flux-general-en"
    assert "eager_eot_threshold" not in created["sttv2"]


def test_deepgram_flux_eager_passed_when_folded(monkeypatch):
    created: dict = {}

    class FakeSTTv2:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "livekit.plugins.deepgram",
        SimpleNamespace(STT=object, STTv2=FakeSTTv2),
    )
    import worker.providers.stt.deepgram as dg

    dg.build(
        "en",
        {
            "stt_mode": "flux",
            "flux_eager_eot": True,
            "eager_eot_threshold": 0.4,
        },
    )
    assert created["eager_eot_threshold"] == 0.4


def test_turn_detector_default_off(monkeypatch):
    monkeypatch.delenv("UVA_TURN_DETECTOR", raising=False)
    assert resolve_turn_detector_version("en") is None
    profile = build_turn_profile(
        audio_channel="webrtc", llm_provider="gemini", agent_language="en"
    )
    assert profile.detector == "stt"
    assert turn_profile_to_livekit_options(profile)["turn_detection"] == "stt"


def test_turn_detector_v1_mini_english_only(monkeypatch):
    monkeypatch.setenv("UVA_TURN_DETECTOR", "v1-mini")
    assert resolve_turn_detector_version("en") == "v1-mini"
    assert resolve_turn_detector_version("ur") is None

    profile = build_turn_profile(
        audio_channel="webrtc", llm_provider="gemini", agent_language="en"
    )
    assert profile.detector == "turn_detector_v1_mini"
    td = materialize_turn_detection(profile)
    from livekit.agents.inference import TurnDetector

    assert isinstance(td, TurnDetector)
    assert "mini" in td.model


def test_flux_falls_back_to_nova_for_non_english(monkeypatch):
    created: dict = {}

    class FakeSTT:
        def __init__(self, **kwargs):
            created["stt"] = kwargs

    class FakeSTTv2:
        def __init__(self, **kwargs):
            created["sttv2"] = kwargs

    monkeypatch.setitem(
        sys.modules,
        "livekit.plugins.deepgram",
        SimpleNamespace(STT=FakeSTT, STTv2=FakeSTTv2),
    )
    import worker.providers.stt.deepgram as dg

    dg.build("ur", {"stt_mode": "flux"})
    assert "stt" in created
    assert "sttv2" not in created
