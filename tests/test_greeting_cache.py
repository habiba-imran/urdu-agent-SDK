"""Unit tests for greeting PCM cache (cold-start path)."""

from __future__ import annotations

import asyncio

from livekit import rtc

from worker.greeting_cache import (
    GreetingAudioCache,
    frames_to_async_iterable,
    hash_greeting_text,
    make_greeting_cache_key,
    synthesize_greeting_frames,
)
from worker.session_opening import plan_greeting_prewarm
from worker.config import AgentConfig


def _cfg(**overrides) -> AgentConfig:
    base = dict(
        agent_id="agent-1",
        tenant_id="tenant-1",
        name="n",
        prompt="persona",
        voice_id="v",
        llm_model="gemini-2.5-flash",
        tts_provider="cartesia",
        greeting="Hello there.",
    )
    base.update(overrides)
    return AgentConfig(**base)


def _frame(payload: bytes = b"\x01\x00\x02\x00") -> rtc.AudioFrame:
    samples = len(payload) // 2
    return rtc.AudioFrame(
        data=payload,
        sample_rate=24000,
        num_channels=1,
        samples_per_channel=samples,
    )


def test_cache_key_includes_provider_voice_channel_and_text():
    a = make_greeting_cache_key(
        agent_id="a1",
        tts_provider="Cartesia",
        provider_voice_id="voice-a",
        greeting_text="Hi",
        audio_channel="webrtc",
    )
    b = make_greeting_cache_key(
        agent_id="a1",
        tts_provider="cartesia",
        provider_voice_id="voice-a",
        greeting_text="Hi",
        audio_channel="webrtc",
    )
    assert a == b
    assert a[3] == hash_greeting_text("Hi")

    different_voice = make_greeting_cache_key(
        agent_id="a1",
        tts_provider="cartesia",
        provider_voice_id="voice-b",
        greeting_text="Hi",
        audio_channel="webrtc",
    )
    assert different_voice != a

    different_channel = make_greeting_cache_key(
        agent_id="a1",
        tts_provider="cartesia",
        provider_voice_id="voice-a",
        greeting_text="Hi",
        audio_channel="telephony",
    )
    assert different_channel != a


def test_lru_evicts_oldest_and_invalidate_agent():
    cache = GreetingAudioCache(max_entries=2)
    k1 = make_greeting_cache_key(
        agent_id="a1",
        tts_provider="cartesia",
        provider_voice_id="v1",
        greeting_text="one",
        audio_channel="webrtc",
    )
    k2 = make_greeting_cache_key(
        agent_id="a1",
        tts_provider="cartesia",
        provider_voice_id="v2",
        greeting_text="two",
        audio_channel="webrtc",
    )
    k3 = make_greeting_cache_key(
        agent_id="a2",
        tts_provider="uplift",
        provider_voice_id="v3",
        greeting_text="three",
        audio_channel="webrtc",
    )
    cache.put(k1, [_frame(b"\x01\x00")])
    cache.put(k2, [_frame(b"\x02\x00")])
    assert cache.get(k1) is not None  # refresh LRU order
    cache.put(k3, [_frame(b"\x03\x00")])
    assert cache.get(k2) is None  # evicted
    assert cache.get(k1) is not None
    assert cache.get(k3) is not None
    assert cache.invalidate_agent("a1") == 1
    assert cache.get(k1) is None
    assert cache.get(k3) is not None


def test_frames_to_async_iterable_replays_cloned_pcm():
    original = _frame(b"\x10\x00\x20\x00")
    frames = [original]

    async def _collect():
        out = []
        async for frame in frames_to_async_iterable(frames):
            out.append(frame)
        return out

    replayed = asyncio.run(_collect())
    assert len(replayed) == 1
    assert bytes(memoryview(replayed[0].data).cast("B")) == b"\x10\x00\x20\x00"
    assert replayed[0] is not original


def test_synthesize_greeting_frames_collects_from_tts():
    class _Event:
        def __init__(self, frame):
            self.frame = frame

    class _Stream:
        def __init__(self, frames):
            self._frames = frames

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._frames:
                raise StopAsyncIteration
            return _Event(self._frames.pop(0))

    class _TTS:
        def synthesize(self, text: str):
            assert text == "Hello"
            return _Stream([_frame(b"\xaa\x00"), _frame(b"\xbb\x00")])

    frames = asyncio.run(synthesize_greeting_frames(_TTS(), "Hello"))
    assert len(frames) == 2
    assert bytes(memoryview(frames[0].data).cast("B")) == b"\xaa\x00"


def test_plan_greeting_prewarm_skips_wait_on_cache_hit():
    cache = GreetingAudioCache()
    from worker import greeting_cache as gc
    from worker import session_opening as so

    key = make_greeting_cache_key(
        agent_id="agent-1",
        tts_provider="cartesia",
        provider_voice_id="voice-x",
        greeting_text="Hello there.",
        audio_channel="webrtc",
    )
    cache.put(key, [_frame()])
    assert cache.has(key) is True
    assert cache.has(
        make_greeting_cache_key(
            agent_id="agent-1",
            tts_provider="rime",
            provider_voice_id="voice-x",
            greeting_text="Hello there.",
            audio_channel="webrtc",
        )
    ) is False
    # Point the module singleton used by plan_greeting_prewarm at our test cache.
    old = gc._cache
    gc._cache = cache
    try:
        plan = so.plan_greeting_prewarm(
            _cfg(),
            provider_voice_id="voice-x",
            audio_channel="webrtc",
        )
        assert plan.mode == "say"
        assert plan.cache_hit is True
        assert plan.await_prewarm is False
        assert plan.prewarm_timeout == 0.0
        assert plan.greeting_frames is not None
    finally:
        gc._cache = old


def test_plan_greeting_prewarm_cache_miss_and_generate_reply():
    from worker.greeting_cache import get_greeting_cache

    get_greeting_cache().clear()
    miss = plan_greeting_prewarm(
        _cfg(),
        provider_voice_id="voice-x",
        audio_channel="webrtc",
    )
    assert miss.mode == "say"
    assert miss.cache_hit is False
    assert miss.await_prewarm is False
    assert miss.await_synthesis is True
    assert miss.prewarm_timeout == 5.0

    gen = plan_greeting_prewarm(
        _cfg(greeting=""),
        provider_voice_id="voice-x",
        audio_channel="webrtc",
    )
    assert gen.mode == "generate_reply"
    assert gen.await_prewarm is True
    assert gen.await_synthesis is False
    assert gen.prewarm_timeout == 2.0


def test_single_flight_greeting_synthesis_shares_one_tts_call():
    from worker.greeting_cache import (
        clear_greeting_inflight,
        get_greeting_cache,
        start_greeting_synthesis,
        await_greeting_frames,
    )

    get_greeting_cache().clear()
    clear_greeting_inflight()
    key = make_greeting_cache_key(
        agent_id="agent-1",
        tts_provider="cartesia",
        provider_voice_id="voice-x",
        greeting_text="Hello there.",
        audio_channel="webrtc",
    )

    class _Event:
        def __init__(self, frame):
            self.frame = frame

    class _Stream:
        def __init__(self, frames, gate: asyncio.Event):
            self._frames = frames
            self._gate = gate

        async def __aenter__(self):
            await self._gate.wait()
            return self

        async def __aexit__(self, *args):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._frames:
                raise StopAsyncIteration
            return _Event(self._frames.pop(0))

    class _TTS:
        def __init__(self):
            self.calls = 0
            self.gate = asyncio.Event()

        def synthesize(self, text: str):
            self.calls += 1
            return _Stream([_frame(b"\x11\x00")], self.gate)

    async def _run():
        tts = _TTS()
        t1 = start_greeting_synthesis(tts=tts, key=key, text="Hello there.")
        t2 = start_greeting_synthesis(tts=tts, key=key, text="Hello there.")
        assert t1 is t2
        # Let the single-flight task start (synthesize is sync before the stream gate).
        await asyncio.sleep(0)
        assert tts.calls == 1
        tts.gate.set()
        frames = await await_greeting_frames(key, timeout=2.0)
        assert frames is not None
        assert len(frames) == 1
        assert tts.calls == 1
        # Second start after complete should hit cache (no new TTS).
        t3 = start_greeting_synthesis(tts=tts, key=key, text="Hello there.")
        await t3
        assert tts.calls == 1

    asyncio.run(_run())


def test_schedule_provider_prewarm_skip_stt_and_tts():
    from worker.latency import schedule_provider_prewarm

    class _Never:
        def prewarm(self):
            raise AssertionError("should not prewarm")

    async def _run():
        task = schedule_provider_prewarm(
            tts=_Never(),
            llm=_Never(),
            stt=_Never(),
            skip_tts=True,
            skip_stt=True,
        )
        await asyncio.wait_for(asyncio.shield(task), timeout=1.0)

    asyncio.run(_run())
