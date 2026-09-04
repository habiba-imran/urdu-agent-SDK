"""Phase 1 latency remediation — unit tests (UVA-1/2/4/10/11)."""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import MagicMock

import pytest

from worker.latency import (
    TURN_HANDLING_OPTIONS,
    await_greeting_prewarm,
    load_session_identity,
    parse_dispatch_metadata,
    prewarm_tts,
    schedule_provider_prewarm,
)
from worker.session_opening import resolve_session_opening
from worker.config import (
    AgentConfig,
    clear_agent_config_cache,
    resolve_provider_voice_id_local,
)


def test_turn_handling_enables_preemptive_generation_and_faster_endpointing():
    preemptive = TURN_HANDLING_OPTIONS["preemptive_generation"]
    assert preemptive["enabled"] is True
    assert preemptive["preemptive_tts"] is True
    assert TURN_HANDLING_OPTIONS["turn_detection"] == "stt"
    assert TURN_HANDLING_OPTIONS["endpointing"]["min_delay"] <= 0.2
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


@pytest.mark.asyncio
async def test_schedule_provider_prewarm_returns_awaitable_tts_task():
    tts_calls: list[str] = []
    stt_calls: list[str] = []

    class _EmptyStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def aclose(self) -> None:
            return None

    class _Tts:
        def prewarm(self) -> None:
            tts_calls.append("tts")

    class _Stt:
        def prewarm(self) -> None:
            stt_calls.append("stt")

    llm = MagicMock()
    llm.chat = MagicMock(return_value=_EmptyStream())

    started = time.monotonic()
    task = schedule_provider_prewarm(
        tts=_Tts(),
        llm=llm,
        stt=_Stt(),
        room_name="room-test",
    )
    schedule_ms = int(round((time.monotonic() - started) * 1000))
    assert isinstance(task, asyncio.Task)
    assert schedule_ms < 100
    await asyncio.wait_for(task, timeout=1.0)
    assert tts_calls == ["tts"]
    assert stt_calls == ["stt"]


@pytest.mark.asyncio
async def test_await_greeting_prewarm_swallows_timeout():
    async def _hang() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(_hang())
    started = time.monotonic()
    await await_greeting_prewarm(task, timeout=0.05)
    assert (time.monotonic() - started) < 1.0
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_prewarm_tts_runs_sync_prewarm_on_event_loop():
    """Regression: LiveKit pool prewarm uses asyncio.create_task — not to_thread()."""
    loop = asyncio.get_running_loop()
    seen_on_loop = False

    def prewarm() -> None:
        nonlocal seen_on_loop
        seen_on_loop = asyncio.get_running_loop() is loop
        asyncio.create_task(asyncio.sleep(0))

    tts = MagicMock()
    tts.prewarm = prewarm
    await prewarm_tts(tts)
    assert seen_on_loop is True


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


def test_low_latency_cartesia_tokenizer_flushes_quickly():
    from worker.providers.tts.cartesia_options import low_latency_cartesia_tokenizer

    tok = low_latency_cartesia_tokenizer()
    cfg = tok._config
    assert cfg.min_sentence_len == 1
    assert cfg.stream_context_len == 1
    assert cfg.min_token_len == 1
    assert cfg.max_token_len == 100
    assert cfg.xml_aware is True
    parts = tok.tokenize("We provide mobile services.")
    assert parts
    assert "mobile" in parts[0] or "We" in parts[0]


def test_resolve_provider_voice_id_local_rime_prefixes():
    assert resolve_provider_voice_id_local("rime-arcana-andromeda") == "andromeda"
    assert resolve_provider_voice_id_local("rime-coda-luna") == "luna"
    assert resolve_provider_voice_id_local("cartesia-slug") is None
    assert resolve_provider_voice_id_local(None) is None


def test_clear_agent_config_cache_is_safe():
    clear_agent_config_cache()
    clear_agent_config_cache()


def test_load_session_identity_returns_none_on_db_error(monkeypatch):
    import psycopg

    monkeypatch.setattr(psycopg, "connect", MagicMock(side_effect=RuntimeError("no db")))
    assert load_session_identity("missing-room") is None
