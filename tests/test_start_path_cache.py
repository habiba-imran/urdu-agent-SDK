"""Unit tests for phase-B start cuts: DB pool, provider client cache, stale skip."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from worker.provider_client_cache import (
    build_components_cached,
    clear_provider_client_cache,
    make_provider_client_cache_key,
)
from worker.providers.types import AgentRuntimeConfig, ProviderComponents
from worker.stale_jobs import abandon_stale_job_if_needed


def _runtime(**overrides) -> AgentRuntimeConfig:
    base = dict(
        agent_language="en",
        stt_provider="gladia",
        stt_model="default",
        stt_options={},
        llm_provider="groq",
        llm_model="openai/gpt-oss-20b",
        llm_options={},
        tts_provider="cartesia",
        tts_voice_id="voice-1",
        tts_options={},
        audio_channel="webrtc",
    )
    base.update(overrides)
    return AgentRuntimeConfig(**base)


def test_provider_client_cache_key_stable_and_sensitive():
    a = make_provider_client_cache_key(_runtime())
    b = make_provider_client_cache_key(_runtime())
    assert a == b
    different_voice = make_provider_client_cache_key(_runtime(tts_voice_id="voice-2"))
    assert different_voice != a
    different_channel = make_provider_client_cache_key(_runtime(audio_channel="telephony"))
    assert different_channel != a


def test_build_components_cached_reuses_instances_on_same_thread():
    clear_provider_client_cache()
    cfg = _runtime()
    fake = ProviderComponents(stt=object(), llm=object(), tts=object())
    calls: list[AgentRuntimeConfig] = []

    def _build(c: AgentRuntimeConfig) -> ProviderComponents:
        calls.append(c)
        return fake

    with patch("worker.provider_client_cache.build_components", side_effect=_build):
        first, hit1 = build_components_cached(cfg)
        second, hit2 = build_components_cached(cfg)
    assert hit1 is False
    assert hit2 is True
    assert first is fake
    assert second is fake
    assert len(calls) == 1


def test_build_components_cached_misses_on_provider_flip():
    clear_provider_client_cache()
    a = ProviderComponents(stt="a", llm="a", tts="a")
    b = ProviderComponents(stt="b", llm="b", tts="b")

    def _build(c: AgentRuntimeConfig) -> ProviderComponents:
        return a if c.tts_provider == "cartesia" else b

    with patch("worker.provider_client_cache.build_components", side_effect=_build):
        first, _ = build_components_cached(_runtime(tts_provider="cartesia"))
        second, hit = build_components_cached(_runtime(tts_provider="rime", tts_voice_id="v2"))
    assert first is a
    assert second is b
    assert hit is False


def test_seed_default_provider_stack_env_gated(monkeypatch):
    from worker.provider_client_cache import seed_default_provider_stack

    clear_provider_client_cache()
    monkeypatch.delenv("UVA_PREWARM_PROVIDER_STACK", raising=False)
    assert seed_default_provider_stack() is False

    monkeypatch.setenv("UVA_PREWARM_PROVIDER_STACK", "1")
    monkeypatch.delenv("UVA_PREWARM_TTS_VOICE_ID", raising=False)
    assert seed_default_provider_stack() is False

    monkeypatch.setenv("UVA_PREWARM_TTS_VOICE_ID", "voice-demo")
    fake = ProviderComponents(stt=object(), llm=object(), tts=object())
    with patch("worker.provider_client_cache.build_components", return_value=fake):
        assert seed_default_provider_stack() is True
        again, hit = build_components_cached(
            _runtime(
                stt_provider="deepgram",
                stt_model="nova-3",
                llm_provider="groq",
                llm_model="openai/gpt-oss-20b",
                tts_provider="cartesia",
                tts_voice_id="voice-demo",
            )
        )
    assert hit is True
    assert again is fake


@pytest.mark.asyncio
async def test_abandon_stale_skips_db_for_fresh_dispatch_metadata():
    ctx = MagicMock()
    ctx.room.name = "room-fresh"
    ctx.shutdown = MagicMock()

    with patch("worker.stale_jobs.evaluate_session_for_job") as evaluate:
        abandoned = await abandon_stale_job_if_needed(ctx, skip_db=True)

    assert abandoned is False
    evaluate.assert_not_called()
    ctx.shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_abandon_stale_still_runs_db_when_not_skipped():
    ctx = MagicMock()
    ctx.room.name = "room-check"
    ctx.shutdown = MagicMock()

    with (
        patch(
            "worker.stale_jobs.evaluate_session_for_job",
            return_value=(False, ""),
        ) as evaluate,
    ):
        abandoned = await abandon_stale_job_if_needed(ctx, skip_db=False)

    assert abandoned is False
    evaluate.assert_called_once_with("room-check")


def test_worker_db_pool_reuses_connection(monkeypatch):
    from worker import db_pool as dp

    dp.reset_worker_db_pool()
    created: list[object] = []

    class _FakeConn:
        closed = False

        def __init__(self) -> None:
            self.info = SimpleNamespace(transaction_status=0)

        def close(self) -> None:
            self.closed = True

        def rollback(self) -> None:
            return None

        def execute(self, *a, **k):
            return SimpleNamespace(fetchone=lambda: (1,))

    def _connect(**kwargs):
        conn = _FakeConn()
        created.append(conn)
        return conn

    monkeypatch.setattr(dp.psycopg, "connect", _connect)
    with dp.worker_db_connection(connect_timeout=2) as c1:
        assert c1 is created[0]
    with dp.worker_db_connection(connect_timeout=2) as c2:
        assert c2 is created[0]
    assert len(created) == 1
    dp.reset_worker_db_pool()
