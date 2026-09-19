"""F-L6 Phase F — gate room publish of turn latency (no network)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from worker.latency import (
    TurnLatencyTracker,
    publish_turn_latency_enabled,
)


@pytest.fixture(autouse=True)
def _clear_fl6_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UVA_PUBLISH_TURN_LATENCY", raising=False)


def _drive_one_turn(tracker: TurnLatencyTracker) -> None:
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


def test_publish_turn_latency_disabled_by_default() -> None:
    assert publish_turn_latency_enabled() is False


def test_publish_turn_latency_explicit_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_PUBLISH_TURN_LATENCY", "0")
    assert publish_turn_latency_enabled() is False
    monkeypatch.setenv("UVA_PUBLISH_TURN_LATENCY", "false")
    assert publish_turn_latency_enabled() is False


def test_publish_turn_latency_explicit_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_PUBLISH_TURN_LATENCY", "1")
    assert publish_turn_latency_enabled() is True
    monkeypatch.setenv("UVA_PUBLISH_TURN_LATENCY", "yes")
    assert publish_turn_latency_enabled() is True


def test_tracker_skips_publish_data_when_flag_off() -> None:
    room = MagicMock()
    room.name = "room-off"
    logger = MagicMock()
    tracker = TurnLatencyTracker(room, logger)
    _drive_one_turn(tracker)
    room.local_participant.publish_data.assert_not_called()
    # Server INFO still emitted for ops.
    assert logger.info.called
    info_msg = logger.info.call_args[0][0]
    assert "turn_latency" in info_msg


def test_tracker_publishes_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_PUBLISH_TURN_LATENCY", "1")
    room = MagicMock()
    room.name = "room-on"
    logger = MagicMock()
    tracker = TurnLatencyTracker(room, logger)
    _drive_one_turn(tracker)
    assert room.local_participant.publish_data.call_count == 2
    topics = [
        c.kwargs["topic"] for c in room.local_participant.publish_data.call_args_list
    ]
    assert topics == ["turn_latency", "metrics_updated"]
    assert logger.info.called