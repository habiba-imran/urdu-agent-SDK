"""Phase 2 latency remediation — unit tests (UVA-3/6/7)."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from worker.latency import (
    TURN_HANDLING_OPTIONS,
    VAD_OPTIONS,
    TurnLatencyTracker,
    prewarm_llm,
    wire_turn_latency,
)
from worker.providers.llm import gemini as gemini_mod


def test_phase2_endpointing_tighter_than_phase1_defaults():
    assert TURN_HANDLING_OPTIONS["endpointing"]["min_delay"] == 0.15
    assert TURN_HANDLING_OPTIONS["endpointing"]["max_delay"] == 1.5
    assert TURN_HANDLING_OPTIONS["preemptive_generation"]["preemptive_tts"] is True


def test_vad_silence_gate_tuned_for_eou():
    assert VAD_OPTIONS["min_silence_duration"] <= 0.4
    assert VAD_OPTIONS["min_silence_duration"] >= 0.3


def test_gemini_voice_path_disables_thinking(monkeypatch):
    captured: dict = {}

    class FakeLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    def _thinking_config(**kwargs):
        return kwargs

    fake_types = SimpleNamespace(
        HttpOptions=lambda timeout: SimpleNamespace(timeout=timeout),
        ThinkingConfig=_thinking_config,
    )
    fake_google = SimpleNamespace(LLM=FakeLLM)
    monkeypatch.setitem(sys.modules, "livekit.plugins.google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
    monkeypatch.setitem(sys.modules, "google.genai", SimpleNamespace(types=fake_types))
    gemini_mod.build("gemini-2.5-flash")
    assert captured["thinking_config"] == {"thinking_level": "minimal"}


def test_deepgram_stt_voice_options(monkeypatch):
    import sys

    created: dict = {}

    class FakeSTT:
        def __init__(self, **kwargs):
            created.update(kwargs)

    import worker.providers.stt.deepgram as dg

    fake_deepgram = SimpleNamespace(STT=FakeSTT)
    monkeypatch.setitem(sys.modules, "livekit.plugins.deepgram", fake_deepgram)
    dg.build("en")
    assert created["model"] == "nova-3"
    assert created["no_delay"] is True
    assert created["endpointing_ms"] == 10


@pytest.mark.asyncio
async def test_prewarm_llm_tolerates_failure():
    llm = MagicMock()
    llm.chat.side_effect = RuntimeError("offline")
    await prewarm_llm(llm)


def test_turn_latency_tracker_emits_on_tts():
    room = MagicMock()
    room.name = "room-1"
    logger = MagicMock()
    tracker = TurnLatencyTracker(room, logger)

    tracker.mark_user_stopped_speaking()
    tracker.on_metrics(
        SimpleNamespace(
            metrics=SimpleNamespace(
                speech_id="sp1",
                end_of_utterance_delay=0.08,
                transcription_delay=0.18,
            )
        )
    )
    tracker.on_metrics(
        SimpleNamespace(metrics=SimpleNamespace(speech_id="sp1", ttft=0.36))
    )
    tracker.on_metrics(
        SimpleNamespace(
            metrics=SimpleNamespace(
                speech_id="sp1",
                duration=0.5,
                ttfb=0.075,
            )
        )
    )

    assert room.local_participant.publish_data.call_count == 2
    payload = json.loads(room.local_participant.publish_data.call_args_list[0].args[0])
    assert payload["type"] == "turn_latency"
    assert payload["sttMs"] == 180
    assert payload["turnMs"] == 80
    assert payload["llmMs"] == 360
    assert payload["ttsTtfbMs"] == 75
    assert "turn_latency_breakdown" in payload
    rolling = json.loads(room.local_participant.publish_data.call_args_list[1].args[0])
    assert rolling["type"] == "metrics_updated"


def test_turn_latency_tracker_skips_greeting_only_tts():
    room = MagicMock()
    logger = MagicMock()
    tracker = TurnLatencyTracker(room, logger)
    tracker.on_metrics(
        SimpleNamespace(
            metrics=SimpleNamespace(
                speech_id="greeting",
                duration=1.0,
                ttfb=0.08,
            )
        )
    )
    room.local_participant.publish_data.assert_not_called()


def test_wire_turn_latency_registers_handlers():
    session = MagicMock()
    wire_turn_latency(session, MagicMock(), MagicMock())
    assert session.on.call_count == 3
