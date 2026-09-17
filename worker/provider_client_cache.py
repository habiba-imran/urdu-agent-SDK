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
