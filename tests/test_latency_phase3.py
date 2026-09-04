"""Phase 3 latency remediation — observability + tool path (UVA-5/UVA-8)."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from worker.cartesia_spoken_output import SYSTEM_INSTRUCTIONS_BASE
from worker.latency import (
    RollingLatencyStats,
    TurnLatencyTracker,
    build_turn_latency_payload,
    wire_turn_latency,
)
from worker.tools import FIXED_TOOLS, session_tools


def test_turn_latency_payload_includes_breakdown_and_aliases():
    parts = SimpleNamespace(
        stt_ms=180,
        turn_ms=80,
        llm_ms=360,
        tts_ms=500,
        tts_ttfb_ms=75,
        tool_ms=120,
        tool_name="lookup_business_info",
    )
    payload = build_turn_latency_payload("sp1", parts, e2e_ms=815)
    assert payload["type"] == "turn_latency"
    assert payload["llmTtftMs"] == 360
    assert payload["roundTripMs"] == 815
    assert payload["turn_latency_breakdown"]["toolMs"] == 120
    assert payload["turn_latency_breakdown"]["toolName"] == "lookup_business_info"


def test_rolling_latency_stats_publish_metrics_updated_shape():
    rolling = RollingLatencyStats()
    payload = rolling.record_turn(stt_ms=200, llm_ms=350, tts_ttfb_ms=80, e2e_ms=700)
    assert payload["type"] == "metrics_updated"
    assert payload["sttP50Ms"] == 200
    assert payload["llmTtftMs"] == 350
    assert payload["roundTripMs"] == 700
    payload2 = rolling.record_turn(stt_ms=100, llm_ms=500, tts_ttfb_ms=60, e2e_ms=900)
    assert payload2["sttP50Ms"] == 150
    assert payload2["turnCount"] == 2


def test_tool_execution_timing_attached_to_turn(monkeypatch):
    room = MagicMock()
    logger = MagicMock()
    tracker = TurnLatencyTracker(room, logger)

    times = iter([100.0, 100.05, 100.5, 100.58])
    monkeypatch.setattr("worker.latency.time.monotonic", lambda: next(times))

    tracker.on_tool_execution(
        SimpleNamespace(
            update=SimpleNamespace(
                type="tool_call_started",
                function_call=SimpleNamespace(call_id="c1", name="lookup_business_info"),
            )
        )
    )
    tracker.on_tool_execution(
        SimpleNamespace(
            update=SimpleNamespace(type="tool_call_ended", call_id="c1", status="done")
        )
    )
    tracker.on_metrics(
        SimpleNamespace(metrics=SimpleNamespace(speech_id="sp1", ttft=0.4))
    )
    tracker.on_metrics(
        SimpleNamespace(
            metrics=SimpleNamespace(
                speech_id="sp1",
                duration=0.5,
                ttfb=0.08,
            )
        )
    )

    assert room.local_participant.publish_data.call_count >= 1
    turn_payload = json.loads(room.local_participant.publish_data.call_args_list[0].args[0])
    assert turn_payload["toolMs"] > 0
    assert turn_payload["toolName"] == "lookup_business_info"


def test_session_tools_excludes_rag_without_base_url(monkeypatch):
    monkeypatch.delenv("UVA_TOOLS_BASE_URL", raising=False)
    tools = session_tools()
    assert tools == FIXED_TOOLS


def test_session_tools_includes_rag_when_configured(monkeypatch):
    monkeypatch.setenv("UVA_TOOLS_BASE_URL", "https://self-serve.example.com")
    tools = session_tools()
    names = [getattr(t, "__name__", str(t)) for t in tools]
    assert "lookup_business_info" in names
    assert len(tools) == len(FIXED_TOOLS) + 1


def test_system_instructions_include_tool_discipline():
    assert "Never call any tool for greetings" in SYSTEM_INSTRUCTIONS_BASE
    assert "lookup_business_info" in SYSTEM_INSTRUCTIONS_BASE
    assert "Begin speaking the first short clause" in SYSTEM_INSTRUCTIONS_BASE


def test_wire_turn_latency_registers_tool_handler():
    session = MagicMock()
    wire_turn_latency(session, MagicMock(), MagicMock())
    assert session.on.call_count == 3


@pytest.mark.asyncio
async def test_lookup_business_info_posts_to_configured_backend(monkeypatch):
    import worker.tools as tools_mod

    monkeypatch.setenv("UVA_TOOLS_BASE_URL", "https://self-serve.example.com")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"answer": "We open at 9am."}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            assert url == "https://self-serve.example.com/api/tools/lookup_business_info"
            assert json["query"] == "hours?"
            return FakeResponse()

    monkeypatch.setattr(tools_mod.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    tracker = MagicMock()
    ud = tools_mod.AgentUserdata(
        tenant_id="t1", agent_id="a1", room_name="r1", latency_tracker=tracker
    )
    ctx = SimpleNamespace(userdata=ud)
    result = await tools_mod.lookup_business_info(ctx, "hours?")
    assert result["answer"] == "We open at 9am."
    tracker.record_tool_duration.assert_called_once()
