"""P3-T02 / P3-T04 — TTS fixture cache + FixtureTTS wiring.

A cache miss is a hard LookupError with ZERO network.  A cache HIT replays committed
fixtures through the FixtureTTS adapter so the worker can call ``make_tts`` and get
synthesized audio without knowing whether the backend is a fixture or live Uplift.

Runs under the conftest offline guard, so if the cache read ever tried to reach Uplift
the guard would trip.  It does not: the cache read is pure stdlib, and the FixtureTTS
adapter delegates to it.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.tts_cache import get, key, require  # noqa: E402


def test_cache_miss_raises_lookuperror_no_network():
    miss_text = "utterance-with-no-committed-fixture-xyz"
    with pytest.raises(LookupError) as e:
        require("v_meklc281", miss_text)
    assert "FIXTURE MISS" in str(e.value)
    assert get("v_meklc281", miss_text) is None


def test_key_is_deterministic_and_distinct():
    assert key("v_meklc281", "hello") == key("v_meklc281", "hello")
    assert key("v_meklc281", "a") != key("v_meklc281", "b")
    assert key("v_other", "a") != key("v_meklc281", "a")


def test_fixture_tts_plays_cached_wav():
    """P3-T04 gate: FixtureTTS replays the committed reference greeting wav."""
    from worker.factories import make_tts  # noqa: E402

    tts = make_tts("v_meklc281")
    greeting = "السلام علیکم، TechZone Laptops میں خوش آمدید۔ میں مہ نور بات کر رہی ہوں، میں آپ کی کیا مدد کر سکتی ہوں؟"

    async def _play():
        stream = tts.synthesize(greeting)
        frames = []
        duration = 0.0
        async for ev in stream:
            frames.append(ev.frame)
            duration += ev.frame.duration
            assert ev.frame.sample_rate == 22050
            assert ev.frame.num_channels == 1
        assert len(frames) >= 1
        total_bytes = sum(len(bytes(f.data)) for f in frames)
        assert total_bytes > 10000
        assert 7.5 < duration < 12.0  # ~8.6s
        await stream.aclose()

    asyncio.run(_play())
