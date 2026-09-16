"""In-process PCM cache for static agent greetings (cold-start / time-to-first-audio).

Cache hits let ``session.say(..., audio=...)`` skip live TTS RTT on the critical path.
Keys include provider + voice + text + channel so demo provider flips never replay the
wrong voice.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from livekit import rtc

logger = logging.getLogger("worker.greeting_cache")

# (agent_id, tts_provider, provider_voice_id, greeting_hash, audio_channel)
GreetingCacheKey = tuple[str, str, str, str, str]

_DEFAULT_MAX_ENTRIES = 32


@dataclass(frozen=True)
class GreetingCacheEntry:
    frames: list[rtc.AudioFrame]
    created_at: float


def hash_greeting_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def make_greeting_cache_key(
    *,
    agent_id: str,
    tts_provider: str,
    provider_voice_id: str,
    greeting_text: str,
    audio_channel: str,
) -> GreetingCacheKey:
    return (
        agent_id,
        (tts_provider or "").strip().lower(),
        (provider_voice_id or "").strip(),
        hash_greeting_text(greeting_text),
        (audio_channel or "webrtc").strip().lower(),
    )


def clone_audio_frame(frame: rtc.AudioFrame) -> rtc.AudioFrame:
    """Copy PCM so cached frames survive after the synthesizer closes its buffers."""
    raw = bytes(memoryview(frame.data).cast("B"))
    return rtc.AudioFrame(
        data=raw,
        sample_rate=frame.sample_rate,
        num_channels=frame.num_channels,
        samples_per_channel=frame.samples_per_channel,
    )


async def synthesize_greeting_frames(tts: Any, text: str) -> list[rtc.AudioFrame]:
    """Run the session TTS instance once and collect cloned PCM frames."""
    frames: list[rtc.AudioFrame] = []
    stream = tts.synthesize(text)
    try:
        async with stream:
            async for event in stream:
                frame = getattr(event, "frame", event)
                frames.append(clone_audio_frame(frame))
    except TypeError:
        # Some fakes / older wrappers are not async context managers.
        async for event in stream:
            frame = getattr(event, "frame", event)
            frames.append(clone_audio_frame(frame))
        aclose = getattr(stream, "aclose", None)
        if callable(aclose):
            await aclose()
    if not frames:
        raise RuntimeError("TTS returned no audio frames for greeting")
    return frames


async def frames_to_async_iterable(
    frames: list[rtc.AudioFrame],
) -> AsyncIterator[rtc.AudioFrame]:
    """Replay cached frames for ``AgentSession.say(..., audio=)``."""
    for frame in frames:
        yield clone_audio_frame(frame)


class GreetingAudioCache:
    """Process-local LRU of pre-rendered greeting PCM."""

    def __init__(self, *, max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[GreetingCacheKey, GreetingCacheEntry] = OrderedDict()

    def has(self, key: GreetingCacheKey) -> bool:
        """True if PCM is cached — no clone (cheap gate for skip_tts prewarm)."""
        return key in self._entries

    def get(self, key: GreetingCacheKey) -> list[rtc.AudioFrame] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._entries.move_to_end(key)
        return [clone_audio_frame(f) for f in entry.frames]

    def put(self, key: GreetingCacheKey, frames: list[rtc.AudioFrame]) -> None:
        if not frames:
            return
        stored = [clone_audio_frame(f) for f in frames]
        self._entries[key] = GreetingCacheEntry(frames=stored, created_at=time.monotonic())
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def invalidate_agent(self, agent_id: str) -> int:
        doomed = [k for k in self._entries if k[0] == agent_id]
        for key in doomed:
            del self._entries[key]
        return len(doomed)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


_cache = GreetingAudioCache()


def get_greeting_cache() -> GreetingAudioCache:
    return _cache


def schedule_greeting_cache_fill(
    *,
    tts: Any,
    key: GreetingCacheKey,
    text: str,
    room_name: str | None = None,
    cache: GreetingAudioCache | None = None,
) -> asyncio.Task[None]:
    """Non-blocking cache fill; failures are logged and never raise into the entrypoint."""
    store = cache if cache is not None else _cache

    async def _fill() -> None:
        try:
            if store.get(key) is not None:
                return
            frames = await synthesize_greeting_frames(tts, text)
            store.put(key, frames)
            logger.info(
                "greeting cache filled agent=%s provider=%s voice=%s channel=%s frames=%s room=%s",
                key[0],
                key[1],
                key[2],
                key[4],
                len(frames),
                room_name or "?",
            )
        except Exception as exc:
            logger.warning(
                "greeting cache fill failed agent=%s room=%s: %s",
                key[0],
                room_name or "?",
                exc,
            )

    return asyncio.create_task(_fill(), name="greeting_cache_fill")
