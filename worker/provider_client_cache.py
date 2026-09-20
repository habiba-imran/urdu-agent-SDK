"""Thread-local STT/LLM/TTS instance cache (cold-start / build_ms).

LiveKit on Windows defaults to THREAD job runners: multiple jobs can share one OS
process. A process-global plugin cache would let two concurrent jobs share one
Cartesia/Gladia client — unsafe. Thread-local storage matches the runner model:
each job thread reuses clients across *sequential* jobs on that runner only.

Key includes provider/model/voice/channel/options so demo provider flips never reuse
the wrong stack.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from typing import Any

from .providers.registry import build_components
from .providers.types import AgentRuntimeConfig, ProviderComponents

logger = logging.getLogger("worker.provider_client_cache")

_thread = threading.local()
_MAX_ENTRIES = 16


def _options_fingerprint(options: dict | None) -> str:
    raw = json.dumps(options or {}, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def make_provider_client_cache_key(cfg: AgentRuntimeConfig) -> tuple[str, ...]:
    return (
        (cfg.agent_language or "").strip().lower(),
        (cfg.stt_provider or "").strip().lower(),
        (cfg.stt_model or "").strip(),
        _options_fingerprint(cfg.stt_options),
        (cfg.llm_provider or "").strip().lower(),
        (cfg.llm_model or "").strip(),
        _options_fingerprint(cfg.llm_options),
        (cfg.tts_provider or "").strip().lower(),
        (cfg.tts_voice_id or "").strip(),
        _options_fingerprint(cfg.tts_options),
        (cfg.audio_channel or "webrtc").strip().lower(),
    )


def _cache_dict() -> dict[tuple[str, ...], ProviderComponents]:
    cache = getattr(_thread, "client_cache", None)
    if cache is None:
        cache = {}
        _thread.client_cache = cache
    return cache


def clear_provider_client_cache() -> None:
    """Drop this thread's client cache (tests)."""
    cache = getattr(_thread, "client_cache", None)
    if cache is not None:
        cache.clear()


def seed_default_provider_stack() -> bool:
    """Construct the demo default STT/LLM/TTS shells into this thread's client cache.

    Env (optional; all provider fields have defaults when seeding is enabled):
      UVA_PREWARM_PROVIDER_STACK=1          # must be truthy to enable
      UVA_PREWARM_AGENT_LANGUAGE=en
      UVA_PREWARM_STT_PROVIDER=deepgram
      UVA_PREWARM_STT_MODEL=nova-3
      UVA_PREWARM_LLM_PROVIDER=groq
      UVA_PREWARM_LLM_MODEL=openai/gpt-oss-20b
      UVA_PREWARM_TTS_PROVIDER=cartesia
      UVA_PREWARM_TTS_VOICE_ID=...          # required when stack seed enabled
      UVA_PREWARM_AUDIO_CHANNEL=webrtc

    Safe for LiveKit ``prewarm_fnc`` (runs on the job runner thread) so the thread-local
    cache is populated before the first job on that runner. Returns True on success.
    """
    raw = (os.getenv("UVA_PREWARM_PROVIDER_STACK") or "").strip().lower()
    if raw not in ("1", "true", "yes", "on"):
        return False
    voice = (os.getenv("UVA_PREWARM_TTS_VOICE_ID") or "").strip()
    if not voice:
        logger.warning(
            "UVA_PREWARM_PROVIDER_STACK set but UVA_PREWARM_TTS_VOICE_ID missing — skip"
        )
        return False

    cfg = AgentRuntimeConfig(
        agent_language=(os.getenv("UVA_PREWARM_AGENT_LANGUAGE") or "en").strip(),
        stt_provider=(os.getenv("UVA_PREWARM_STT_PROVIDER") or "deepgram").strip(),
        stt_model=(os.getenv("UVA_PREWARM_STT_MODEL") or "nova-3").strip(),
        stt_options={},
        llm_provider=(os.getenv("UVA_PREWARM_LLM_PROVIDER") or "groq").strip(),
        llm_model=(
            os.getenv("UVA_PREWARM_LLM_MODEL") or "openai/gpt-oss-20b"
        ).strip(),
        llm_options={},
        tts_provider=(os.getenv("UVA_PREWARM_TTS_PROVIDER") or "cartesia").strip(),
        tts_voice_id=voice,
        tts_options={},
        audio_channel=(os.getenv("UVA_PREWARM_AUDIO_CHANNEL") or "webrtc").strip(),
    )
    try:
        _components, hit = build_components_cached(cfg)
        del _components
        logger.info(
            "provider stack seeded lang=%s stt=%s llm=%s tts=%s voice=%s channel=%s "
            "already_cached=%s",
            cfg.agent_language,
            cfg.stt_provider,
            cfg.llm_provider,
            cfg.tts_provider,
            cfg.tts_voice_id,
            cfg.audio_channel,
            hit,
        )
        return True
    except Exception as exc:
        logger.warning("provider stack seed failed: %s", exc)
        return False


def build_components_cached(
    cfg: AgentRuntimeConfig,
    *,
    use_cache: bool = True,
) -> tuple[ProviderComponents, bool]:
    """Return ``(components, cache_hit)``.

    On hit, returns the same plugin instances previously built on this job thread.
    Instances are transport shells (streams are per-call); do not share across threads.
    """
    if not use_cache:
        return build_components(cfg), False

    key = make_provider_client_cache_key(cfg)
    cache = _cache_dict()
    hit = cache.get(key)
    if hit is not None:
        # Refresh LRU order
        cache.pop(key)
        cache[key] = hit
        return hit, True

    components = build_components(cfg)
    cache[key] = components
    while len(cache) > _MAX_ENTRIES:
        # dict preserves insertion order — drop oldest
        cache.pop(next(iter(cache)))
    return components, False
