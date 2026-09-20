"""In-process PCM cache for static agent greetings (cold-start / time-to-first-audio).

Cache hits let ``session.say(..., audio=...)`` skip live TTS RTT on the critical path.
Keys include provider + voice + text + channel so demo provider flips never replay the
wrong voice.

Cache-miss path uses **single-flight** synthesis: one TTS request is shared by the
background fill and the opening turn (no double synthesis).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from livekit import rtc

logger = logging.getLogger("worker.greeting_cache")

# (agent_id, tts_provider, provider_voice_id, greeting_hash, audio_channel, options_fp)
GreetingCacheKey = tuple[str, str, str, str, str, str]

_DEFAULT_MAX_ENTRIES = 32


@dataclass(frozen=True)
class GreetingCacheEntry:
    frames: list[rtc.AudioFrame]
    created_at: float


def hash_greeting_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _tts_options_fingerprint(tts_options: dict | None) -> str:
    """Include delivery knobs so model/emotion/speed flips never replay stale PCM."""
    import json

    raw = json.dumps(tts_options or {}, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def make_greeting_cache_key(
    *,
    agent_id: str,
    tts_provider: str,
    provider_voice_id: str,
    greeting_text: str,
    audio_channel: str,
    tts_options: dict | None = None,
) -> GreetingCacheKey:
    return (
        agent_id,
        (tts_provider or "").strip().lower(),
        (provider_voice_id or "").strip(),
        hash_greeting_text(greeting_text),
        (audio_channel or "webrtc").strip().lower(),
        _tts_options_fingerprint(tts_options),
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
# Single-flight in-progress synthesis tasks (one TTS request per key).
_inflight: dict[GreetingCacheKey, asyncio.Task[list[rtc.AudioFrame]]] = {}


def get_greeting_cache() -> GreetingAudioCache:
    return _cache


def clear_greeting_inflight() -> None:
    """Drop in-flight task map (tests). Does not cancel running tasks."""
    _inflight.clear()


def start_greeting_synthesis(
    *,
    tts: Any,
    key: GreetingCacheKey,
    text: str,
    room_name: str | None = None,
    cache: GreetingAudioCache | None = None,
) -> asyncio.Task[list[rtc.AudioFrame]]:
    """Start or join single-flight greeting TTS. Never starts a second synth for ``key``."""
    store = cache if cache is not None else _cache
    hit = store.get(key)
    if hit is not None:

        async def _cached() -> list[rtc.AudioFrame]:
            return hit

        return asyncio.create_task(_cached(), name="greeting_synth_cached")

    existing = _inflight.get(key)
    if existing is not None and not existing.done():
        return existing

    async def _synth() -> list[rtc.AudioFrame]:
        try:
            frames = await synthesize_greeting_frames(tts, text)
            store.put(key, frames)
            logger.info(
                "greeting cache filled agent=%s provider=%s voice=%s channel=%s "
                "frames=%s room=%s",
                key[0],
                key[1],
                key[2],
                key[4],
                len(frames),
                room_name or "?",
            )
            return store.get(key) or frames
        except Exception as exc:
            logger.warning(
                "greeting synthesis failed agent=%s room=%s: %s",
                key[0],
                room_name or "?",
                exc,
            )
            raise
        finally:
            current = _inflight.get(key)
            if current is not None and current.done():
                _inflight.pop(key, None)

    task: asyncio.Task[list[rtc.AudioFrame]] = asyncio.create_task(
        _synth(), name="greeting_synth"
    )
    _inflight[key] = task
    return task


def schedule_greeting_cache_fill(
    *,
    tts: Any,
    key: GreetingCacheKey,
    text: str,
    room_name: str | None = None,
    cache: GreetingAudioCache | None = None,
) -> asyncio.Task[list[rtc.AudioFrame]]:
    """Backward-compatible alias: single-flight synthesis (same as ``start_greeting_synthesis``)."""
    return start_greeting_synthesis(
        tts=tts,
        key=key,
        text=text,
        room_name=room_name,
        cache=cache,
    )


async def await_greeting_frames(
    key: GreetingCacheKey,
    *,
    timeout: float,
    cache: GreetingAudioCache | None = None,
) -> list[rtc.AudioFrame] | None:
    """Return cached/in-flight greeting PCM within ``timeout``, or ``None`` on miss/fail."""
    store = cache if cache is not None else _cache
    hit = store.get(key)
    if hit is not None:
        return hit

    task = _inflight.get(key)
    if task is None:
        return None
    try:
        frames = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return frames
    except Exception:
        # Timeout or synth failure — opening may fall back to live session.say().
        hit = store.get(key)
        return hit


def seed_greeting_pcm_from_env() -> bool:
    """Optionally pre-synthesize demo greeting PCM at process start (sync wrapper).

    Env (all required when seeding):
      UVA_PREWARM_GREETING_TEXT
      UVA_PREWARM_AGENT_ID
      UVA_PREWARM_TTS_PROVIDER   (default cartesia)
      UVA_PREWARM_TTS_VOICE_ID   (provider voice id)
      UVA_PREWARM_AUDIO_CHANNEL  (default webrtc)

    Returns True if frames were stored. Failures are logged and never raised.
    """
    text = (os.getenv("UVA_PREWARM_GREETING_TEXT") or "").strip()
    agent_id = (os.getenv("UVA_PREWARM_AGENT_ID") or "").strip()
    voice_id = (os.getenv("UVA_PREWARM_TTS_VOICE_ID") or "").strip()
    if not text or not agent_id or not voice_id:
        return False
    provider = (os.getenv("UVA_PREWARM_TTS_PROVIDER") or "cartesia").strip().lower()
    channel = (os.getenv("UVA_PREWARM_AUDIO_CHANNEL") or "webrtc").strip().lower()
    language = (os.getenv("UVA_PREWARM_TTS_LANGUAGE") or "en").strip().lower()

    # Match runtime opening: sanitize so cache key equals plan_greeting_prewarm's key.
    try:
        from worker.spoken_sanitize import sanitizer_for_provider

        sanitize = sanitizer_for_provider(provider)
        if sanitize is not None:
            text = sanitize(text).strip()
            if not text:
                return False
    except Exception as exc:
        logger.warning(
            "stage=greeting_sanitize failed provider=%s err=%s (seeding unsanitized)",
            provider,
            exc,
        )

    key = make_greeting_cache_key(
        agent_id=agent_id,
        tts_provider=provider,
        provider_voice_id=voice_id,
        greeting_text=text,
        audio_channel=channel,
        tts_options={},
    )
    if _cache.has(key):
        return True

    try:
        if provider == "cartesia":
            from worker.providers.tts.cartesia import build as build_tts
        else:
            logger.info(
                "greeting PCM seed skipped — unsupported UVA_PREWARM_TTS_PROVIDER=%s",
                provider,
            )
            return False

        tts = build_tts(voice_id, language, None, audio_channel=channel)

        async def _run() -> list[rtc.AudioFrame]:
            return await synthesize_greeting_frames(tts, text)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            frames = asyncio.run(_run())
        else:
            # prewarm_fnc may run inside an existing loop (job process). asyncio.run
            # would fail — synthesize on a dedicated thread with its own loop.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                frames = pool.submit(lambda: asyncio.run(_run())).result(timeout=45)

        _cache.put(key, frames)
        logger.info(
            "greeting PCM seeded agent=%s provider=%s voice=%s channel=%s frames=%s",
            agent_id,
            provider,
            voice_id,
            channel,
            len(frames),
        )
        return True
    except Exception as exc:
        logger.warning("greeting PCM seed failed: %s", exc)
        return False
