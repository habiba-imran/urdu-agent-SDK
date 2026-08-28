"""Phase 1 latency remediation — unit tests (UVA-1/2/4/10/11)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from worker.latency import (
    TURN_HANDLING_OPTIONS,
    load_session_identity,
    parse_dispatch_metadata,
    prewarm_tts,
)
from worker.session_opening import resolve_session_opening
from worker.config import AgentConfig


def test_turn_handling_enables_preemptive_generation_and_faster_endpointing():
    assert TURN_HANDLING_OPTIONS["preemptive_generation"]["enabled"] is True
    assert TURN_HANDLING_OPTIONS["endpointing"]["min_delay"] <= 0.3
    assert TURN_HANDLING_OPTIONS["endpointing"]["max_delay"] <= 2.0


def test_parse_dispatch_metadata_round_trip():
    raw = json.dumps({"tenant_id": "t1", "agent_id": "a1"})
    assert parse_dispatch_metadata(raw) == {
        "tenant_id": "t1",
        "agent_id": "a1",
    }
    assert parse_dispatch_metadata(None) is None
    assert parse_dispatch_metadata("{bad") is None


@pytest.mark.asyncio
async def test_prewarm_tts_calls_provider():
    tts = MagicMock()
    await prewarm_tts(tts)
    tts.prewarm.assert_called_once()


@pytest.mark.asyncio
async def test_prewarm_tts_noop_when_missing():
    await prewarm_tts(object())


def test_static_greeting_skips_llm():
    cfg = AgentConfig(
        agent_id="a",
        tenant_id="t",
        name="n",
        prompt="persona",
        voice_id="v",
        llm_model="gemini-2.5-flash",
        greeting="Hi, thanks for calling.",
    )
    opening = resolve_session_opening(cfg)
    assert opening.mode == "say"
    assert opening.text == "Hi, thanks for calling."


def test_load_session_identity_returns_none_on_db_error(monkeypatch):
    import psycopg

    monkeypatch.setattr(psycopg, "connect", MagicMock(side_effect=RuntimeError("no db")))
    assert load_session_identity("missing-room") is None
