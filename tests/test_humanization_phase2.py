"""Phase 2 humanization: TurnProfile + Deepgram endpointing A/B."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from worker.humanization.turn import (
    build_turn_profile,
    resolve_deepgram_endpointing_ms,
    turn_profile_to_livekit_options,
)
from worker.latency import turn_handling_for_channel
from worker.providers.stt import gladia as gladia_mod


def test_turn_profile_webrtc_defaults_match_legacy():
    profile = build_turn_profile(audio_channel="webrtc", llm_provider="gemini")
    opts = turn_profile_to_livekit_options(profile)
    legacy = turn_handling_for_channel("webrtc", llm_provider="gemini")
    assert opts == legacy
    assert opts["preemptive_generation"]["enabled"] is True
    assert opts["turn_detection"] == "stt"
    assert opts["endpointing"]["min_delay"] == 0.15


def test_turn_profile_telephony_and_groq_disable_preemptive(monkeypatch):
    monkeypatch.setenv("UVA_INTERRUPTION_MODE", "vad")
    tel = turn_profile_to_livekit_options(
        build_turn_profile(audio_channel="telephony", llm_provider="gemini")
    )
    assert tel["preemptive_generation"]["enabled"] is False
    assert tel["interruption"]["resume_false_interruption"] is False

    groq_web = turn_profile_to_livekit_options(
        build_turn_profile(audio_channel="webrtc", llm_provider="groq")
    )
    assert groq_web["preemptive_generation"]["enabled"] is False
    assert groq_web["preemptive_generation"]["preemptive_tts"] is False


def test_turn_profile_urdu_does_not_change_options():
    en = turn_profile_to_livekit_options(
        build_turn_profile(
            audio_channel="webrtc",
            stt_provider="gladia",
            llm_provider="gemini",
            agent_language="en",
        )
    )
    ur = turn_profile_to_livekit_options(
        build_turn_profile(
            audio_channel="webrtc",
            stt_provider="gladia",
            llm_provider="gemini",
            agent_language="ur",
        )
    )
    assert en == ur


def test_deepgram_endpointing_default_200(monkeypatch):
    monkeypatch.delenv("UVA_DEEPGRAM_ENDPOINTING_MS", raising=False)
    assert resolve_deepgram_endpointing_ms(None) == 200
    assert resolve_deepgram_endpointing_ms({}) == 200


def test_deepgram_endpointing_env_override(monkeypatch):
    monkeypatch.setenv("UVA_DEEPGRAM_ENDPOINTING_MS", "300")
    assert resolve_deepgram_endpointing_ms(None) == 300


def test_deepgram_endpointing_stt_options_beats_env(monkeypatch):
    monkeypatch.setenv("UVA_DEEPGRAM_ENDPOINTING_MS", "300")
    assert resolve_deepgram_endpointing_ms({"endpointing_ms": 200}) == 200


def test_deepgram_build_uses_resolved_endpointing(monkeypatch):
    created: dict = {}

    class FakeSTT:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setenv("UVA_DEEPGRAM_ENDPOINTING_MS", "200")
    monkeypatch.setitem(sys.modules, "livekit.plugins.deepgram", SimpleNamespace(STT=FakeSTT))
    import worker.providers.stt.deepgram as dg

    dg.build("en")
    assert created["endpointing_ms"] == 200
    assert created["model"] == "nova-3"


def test_gladia_still_disables_code_switching(monkeypatch):
    created: dict = {}

    class FakeSTT:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setitem(sys.modules, "livekit.plugins.gladia", SimpleNamespace(STT=FakeSTT))
    gladia_mod.build("ur")
    assert created["languages"] == ["ur"]
    assert created["code_switching"] is False
