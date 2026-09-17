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
    # Longer than brief echo blips; still under ~0.7s so intentional barge-in feels snappy.
    assert 0.4 <= interruption["min_duration"] <= 0.7
    assert interruption["resume_false_interruption"] is False
    preemptive = TURN_HANDLING_OPTIONS["preemptive_generation"]
    assert preemptive["enabled"] is True
    assert preemptive["preemptive_tts"] is True
    assert preemptive["max_speech_duration"] >= 10.0


def test_telephony_turn_handling_disables_false_interruption_resume():
    from worker.latency import TELEPHONY_TURN_HANDLING_OPTIONS, turn_handling_for_channel

    tel = turn_handling_for_channel("telephony")
    interruption = tel["interruption"]
    assert interruption["enabled"] is True
    assert interruption["discard_audio_if_uninterruptible"] is False
    assert interruption["resume_false_interruption"] is False
    assert interruption["false_interruption_timeout"] <= 0.7
    # Telephony disables preemptive LLM so free-tier Groq TPM is not burned on cancels.
    assert tel["preemptive_generation"]["enabled"] is False
    assert TELEPHONY_TURN_HANDLING_OPTIONS["preemptive_generation"]["enabled"] is False
    web = turn_handling_for_channel("webrtc")
    assert web["preemptive_generation"]["enabled"] is True
    assert web["interruption"]["resume_false_interruption"] is False
    assert web["interruption"]["min_duration"] >= 0.4
    groq_web = turn_handling_for_channel("webrtc", llm_provider="groq")
    assert groq_web["preemptive_generation"]["enabled"] is False


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


def test_session_room_options_telephony_keeps_room():
    opts = session_room_options(audio_channel="telephony")
    assert opts.close_on_disconnect is True
    assert opts.delete_room_on_close is False


def test_wire_barge_in_flush_interrupts_when_user_speaks_over_agent(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("UVA_FORCE_BARGE_IN_FLUSH", "1")
    session = MagicMock()
    session.userdata = SimpleNamespace(opening_active=False)
    logger = MagicMock()
    handlers: dict[str, object] = {}

    def _on(event: str, handler):
        handlers[event] = handler

    session.on.side_effect = _on
    wire_barge_in_flush(session, logger, audio_channel="webrtc")

    handlers["agent_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )
    handlers["user_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )

    session.interrupt.assert_called_once_with(force=True)
    assert any(
        "interrupted in-flight agent speech" in str(c.args[0])
        for c in logger.info.call_args_list
    )


def test_wire_barge_in_flush_webrtc_default_skips_force_interrupt():
    session = MagicMock()
    session.userdata = SimpleNamespace(opening_active=False)
    logger = MagicMock()
    handlers: dict[str, object] = {}

    def _on(event: str, handler):
        handlers[event] = handler

    session.on.side_effect = _on
    wire_barge_in_flush(session, logger, audio_channel="webrtc")

    handlers["agent_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )
    handlers["user_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )

    session.interrupt.assert_not_called()
    assert any(
        "force flush off" in str(c.args[0]) for c in logger.info.call_args_list
    )


def test_wire_barge_in_flush_telephony_default_force_interrupts():
    session = MagicMock()
    session.userdata = SimpleNamespace(opening_active=False)
    logger = MagicMock()
    handlers: dict[str, object] = {}

    def _on(event: str, handler):
        handlers[event] = handler

    session.on.side_effect = _on
    wire_barge_in_flush(session, logger, audio_channel="telephony")

    handlers["agent_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )
    handlers["user_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )

    session.interrupt.assert_called_once_with(force=True)


def test_wire_barge_in_flush_skips_force_during_opening(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("UVA_FORCE_BARGE_IN_FLUSH", "1")
    session = MagicMock()
    session.userdata = SimpleNamespace(opening_active=True)
    logger = MagicMock()
    handlers: dict[str, object] = {}

    def _on(event: str, handler):
        handlers[event] = handler

    session.on.side_effect = _on
    wire_barge_in_flush(session, logger, audio_channel="webrtc")

    handlers["agent_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )
    handlers["user_state_changed"](
        SimpleNamespace(new_state="speaking", old_state="listening")
    )

    session.interrupt.assert_not_called()
    assert any("opening active" in str(c.args[0]) for c in logger.info.call_args_list)


def test_wire_barge_in_flush_skips_when_agent_not_speaking(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("UVA_FORCE_BARGE_IN_FLUSH", "1")
    session = MagicMock()
    session.userdata = SimpleNamespace(opening_active=False)
    logger = MagicMock()
    handlers: dict[str, object] = {}

    def _on(event: str, handler):
        handlers[event] = handler

    session.on.side_effect = _on
    wire_barge_in_flush(session, logger, audio_channel="webrtc")

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
