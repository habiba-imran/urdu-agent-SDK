"""Phase 4 latency remediation — infrastructure & reliability (UVA-9/13/14/15)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from control_plane.app import app as cp_app
from worker.latency import (
    TURN_HANDLING_OPTIONS,
    prewarm_stt,
    session_room_options,
    wire_barge_in_flush,
)
from worker.providers.stt import deepgram as dg_mod


def test_turn_handling_barge_in_and_preemptive_partial_feed():
    interruption = TURN_HANDLING_OPTIONS["interruption"]
    assert interruption["enabled"] is True
    assert interruption["discard_audio_if_uninterruptible"] is True
    assert interruption["min_duration"] <= 0.35
    preemptive = TURN_HANDLING_OPTIONS["preemptive_generation"]
    assert preemptive["enabled"] is True
    assert preemptive["preemptive_tts"] is True
    assert preemptive["max_speech_duration"] >= 10.0


def test_telephony_turn_handling_disables_false_interruption_resume():
    from worker.latency import TELEPHONY_TURN_HANDLING_OPTIONS, turn_handling_for_channel

    tel = turn_handling_for_channel("telephony")
    assert tel is TELEPHONY_TURN_HANDLING_OPTIONS
    interruption = tel["interruption"]
    assert interruption["enabled"] is True
    assert interruption["discard_audio_if_uninterruptible"] is False
    assert interruption["resume_false_interruption"] is False
    assert interruption["false_interruption_timeout"] <= 0.7
    assert turn_handling_for_channel("webrtc") is TURN_HANDLING_OPTIONS


def test_is_telephony_job_from_room_or_metadata():
    from worker.latency import is_telephony_job

    assert is_telephony_job(room_name="telephony-inbound-abc") is True
    assert is_telephony_job(room_name="browser-room") is False
    assert (
        is_telephony_job(job_metadata='{"direction":"inbound","tenant_id":"t","agent_id":"a"}')
        is True
    )
    assert is_telephony_job(job_metadata='{"tenant_id":"t","agent_id":"a"}') is False


def test_session_room_options_fast_teardown():
    opts = session_room_options()
    assert opts.close_on_disconnect is True
    assert opts.delete_room_on_close is True


def test_wire_barge_in_flush_interrupts_when_user_speaks_over_agent():
    session = MagicMock()
    logger = MagicMock()
    handlers: dict[str, object] = {}

    def _on(event: str, handler):
        handlers[event] = handler

    session.on.side_effect = _on
    wire_barge_in_flush(session, logger)

    handlers["agent_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )
    handlers["user_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )

    session.interrupt.assert_called_once_with(force=True)
    logger.info.assert_called_once()


def test_wire_barge_in_flush_skips_when_agent_not_speaking():
    session = MagicMock()
    logger = MagicMock()
    handlers: dict[str, object] = {}

    def _on(event: str, handler):
        handlers[event] = handler

    session.on.side_effect = _on
    wire_barge_in_flush(session, logger)

    handlers["user_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )
    session.interrupt.assert_not_called()


@pytest.mark.asyncio
async def test_prewarm_stt_calls_provider():
    stt = MagicMock()
    await prewarm_stt(stt)
    stt.prewarm.assert_called_once()


@pytest.mark.asyncio
async def test_prewarm_stt_noop_when_missing():
    await prewarm_stt(object())


def test_deepgram_interim_results_enabled_for_partial_llm_feed(monkeypatch):
    created: dict = {}

    class FakeSTT:
        def __init__(self, **kwargs):
            created.update(kwargs)

    fake_deepgram = SimpleNamespace(STT=FakeSTT)
    monkeypatch.setitem(__import__("sys").modules, "livekit.plugins.deepgram", fake_deepgram)
    dg_mod.build("en")
    assert created["interim_results"] is True
    assert created["no_delay"] is True


def test_warm_health_endpoint():
    client = TestClient(cp_app)
    response = client.get("/healthz/warm")
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["service"] == "uva-control-plane"
    assert "checks" in data
    assert "database" in data["checks"]
    assert "livekit_api" in data["checks"]
    assert "elapsedMs" in data
