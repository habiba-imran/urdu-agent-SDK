"""Non-audible, session-local observability. No dialogue or policy authority."""

from __future__ import annotations

import math
import re
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from uuid import uuid4

POLICY_VERSION = "baseline"
COMPONENT_VERSIONS = dict.fromkeys(
    ("turn", "delivery", "streaming", "language", "channel", "renderer"), "baseline"
)
OUTCOMES = frozenset({
    "completed", "interrupted", "cancelled", "cancelled_speculation", "provider_error",
    "tool_error", "tool_timeout", "tool_outcome_unknown", "false_interruption", "stale",
})
STAGES = (
    "user_speech_started", "user_speech_stopped", "turn_committed", "llm_request_start",
    "first_useful_llm_text", "first_speakable_chunk_ready", "tts_request_start",
    "tts_first_audio", "speech_complete", "speech_interrupted",
)
TOOL_NAMES = frozenset({
    "lookup_business_info", "check_availability", "book_appointment",
    "reschedule_appointment", "cancel_appointment", "end_conversation_summary",
    "escalate_to_human",
})


def new_id(kind: str) -> str:
    return f"{kind}_{uuid4().hex}"


def identifier(value: Any) -> str | None:
    """Only identifiers, never arbitrary provider payloads, URLs or error messages."""
    if isinstance(value, str) and "://" not in value and re.fullmatch(r"[\w./:+-]{1,160}", value, flags=re.ASCII):
        return value
    return None


def measurement(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(value) and value >= 0:
            return float(value)
    return None


def percentile_report(values: Any, *, validated: bool = False) -> dict[str, Any]:
    samples = sorted(values) if validated else sorted(v for value in values if (v := measurement(value)) is not None)
    count = len(samples)
    # Nearest rank for tails; preserve legacy median for p50. A hundred samples
    # is the minimum even to display p99, not a confidence/production claim.
    def tail(p: float, minimum: int) -> float | None:
        return samples[math.ceil(p * count) - 1] if count >= minimum else None

    median = None
    if count:
        median = (samples[(count - 1) // 2] + samples[count // 2]) / 2
    return {"sampleCount": count, "p50Ms": median, "p95Ms": tail(.95, 20),
            "p99Ms": tail(.99, 100), "window": "rolling", "confidence": "descriptive"}


class LatencyDistributions:
    """Bounded outcome/provider/model/language/channel buckets, with explicit counts."""

    def __init__(self, *, window: int = 256, max_buckets: int = 32) -> None:
        self.window = window
        self.max_buckets = max_buckets
        self.buckets: OrderedDict[tuple, dict[str, deque]] = OrderedDict()

    def record(self, *, outcome: str, lane: tuple, values: dict[str, Any]) -> dict:
        if outcome not in OUTCOMES:
            raise ValueError("unsupported telemetry outcome")
        key = (outcome, *lane)
        bucket = self.buckets.setdefault(key, {})
        self.buckets.move_to_end(key)
        while len(self.buckets) > self.max_buckets:
            self.buckets.popitem(last=False)
        for name, value in values.items():
            if (sample := measurement(value)) is not None:
                bucket.setdefault(name, deque(maxlen=self.window)).append(sample)
        return {"outcome": outcome, "lane": list(lane),
                "laneDimensions": ["stt_provider", "stt_model", "llm_provider", "llm_model",
                                   "tts_provider", "tts_model", "language", "channel", "operation"],
                "metrics": {name: percentile_report(bucket.get(name, ()), validated=True) for name in values}}


@lru_cache(maxsize=32)
def plugin_version(provider: str) -> str | None:
    provider = {"gemini": "google", "uplift": "upliftai"}.get(provider, provider)
    try:
        return version(f"livekit-plugins-{provider}")
    except PackageNotFoundError:
        return None


def provider_snapshot(cfg: Any, runtime_cfg: Any, components: Any) -> dict[str, Any]:
    """Mirror the installed adapters' effective constructor options, by allowlist.

    Caller text, arbitrary stored dictionaries, endpoints, credentials, phrase
    dictionaries and account-scoped pronunciation IDs are never copied.
    """
    import os
    from worker.providers.llm.gemini import resolve_gemini_model, _resolve_thinking_level
    from worker.providers.llm.groq import resolve_groq_model, _MAX_COMPLETION_TOKENS

    language, channel = runtime_cfg.agent_language, runtime_cfg.audio_channel
    stt = runtime_cfg.stt_provider
    def known_model(value: Any) -> str | None:
        return identifier(value) if value not in (None, "unknown", "default") else None

    stt_model = known_model(getattr(components.stt, "model", None))
    if stt == "deepgram":
        options = runtime_cfg.stt_options
        flux = options.get("stt_mode") == "flux" and language.startswith("en")
        stt_model = stt_model or ("flux-general-en" if flux else runtime_cfg.stt_model)
        stt_options = {"sample_rate": 16000, "stt_mode": "flux" if flux else "nova"}
        if flux:
            eager = None if options.get("flux_eager_eot") is False else measurement(options.get("eager_eot_threshold"))
            stt_options.update(eager_eot_threshold=eager,
                               eot_threshold=min(.9, eager + .1) if eager and eager > .7 else .7)
        else:
            stt_options.update(language="en-US" if language.startswith("en") else language,
                               no_delay=True, interim_results=True, smart_format=False,
                               endpointing_ms=measurement(options.get("endpointing_ms")))
    else:
        stt_options = {"languages": [language], "code_switching": False}
        # The adapter does not select a vendor model. Do not equate stored
        # "default" with a verified vendor deployment model.
        stt_model = stt_model or None

    llm = runtime_cfg.llm_provider
    if llm == "groq":
        llm_model = resolve_groq_model(runtime_cfg.llm_model)[0]
        llm_options = {"max_completion_tokens": _MAX_COMPLETION_TOKENS,
                       "timeout_seconds": 30, "max_retries": 0}
        if llm_model.startswith("openai/gpt-oss"):
            llm_options["reasoning_effort"] = "low"
        elif llm_model.startswith("qwen/"):
            llm_options["reasoning_effort"] = "none"
    else:
        llm_model = resolve_gemini_model(runtime_cfg.llm_model)[0]
        llm_options = {"temperature": .35, "max_output_tokens": 180, "timeout_seconds": 30}
        llm_options.update({"thinking_level": _resolve_thinking_level()} if "gemini-3" in llm_model.lower()
                           else {"thinking_budget": 0})
    llm_model = known_model(getattr(components.llm, "model", None)) or llm_model

    tts = runtime_cfg.tts_provider
    if tts == "cartesia":
        from worker.providers.tts.cartesia_options import resolve_cartesia_tts_kwargs
        tts_options = resolve_cartesia_tts_kwargs(runtime_cfg.tts_voice_id, language,
                                                 runtime_cfg.tts_options, audio_channel=channel)
        tts_options.pop("voice", None)
        tts_options["word_timestamps"] = False
        if "emotion" in tts_options:
            from typing import get_args
            from livekit.plugins.cartesia.models import TTSVoiceEmotion
            emotions = {value.lower() for value in get_args(TTSVoiceEmotion)}
            # The existing adapter accepts arbitrary strings. General telemetry
            # exposes only installed categorical labels, never arbitrary text.
            tts_options["emotion"] = [e if e.lower() in emotions else None
                                      for e in tts_options["emotion"][:16]]
    elif tts == "rime":
        import inspect
        from livekit.plugins import rime
        from worker.providers.tts.rime_options import resolve_rime_tts_kwargs
        tts_options = resolve_rime_tts_kwargs(runtime_cfg.tts_voice_id, "eng",
                                              runtime_cfg.tts_options, audio_channel=channel)
        allowed = set(inspect.signature(rime.TTS).parameters)
        tts_options = {k: v for k, v in tts_options.items() if k in allowed and k != "speaker"}
    elif tts == "elevenlabs":
        import inspect
        from livekit.plugins import elevenlabs
        from worker.providers.tts.elevenlabs_options import resolve_elevenlabs_tts_kwargs
        tts_options = resolve_elevenlabs_tts_kwargs(runtime_cfg.tts_voice_id, language,
                                                   runtime_cfg.tts_options)
        allowed = set(inspect.signature(elevenlabs.TTS).parameters)
        tts_options = {k: v for k, v in tts_options.items() if k in allowed and k != "voice_id"}
        settings = tts_options.get("voice_settings")
        if settings is not None:
            tts_options["voice_settings"] = {k: getattr(settings, k) for k in
                ("stability", "similarity_boost", "style", "speed", "use_speaker_boost")}
    else:
        from worker.providers.tts.uplift import resolve_uplift_phrase_config_id
        mode = os.getenv("UPLIFT_MODE", "fixture")
        tts_options = {"mode": mode, "output_format": "PCM_22050_16",
                       "phrase_replacements_enabled": bool(resolve_uplift_phrase_config_id())}
    tts_model = known_model(getattr(components.tts, "model", None)) or tts_options.get("model")
    # Cached clients may outlive an environment override. Read only these exact
    # installed 1.6.5 option fields; never serialize _opts wholesale (it can hold
    # keys, headers, endpoints and account data). Unknown fields remain resolved
    # constructor configuration, with an explicit source label.
    def actual_options(client: Any, resolved: dict) -> dict:
        opts = getattr(client, "_opts", None)
        out = dict(resolved)
        for key in resolved:
            value = getattr(opts, key, None)
            if isinstance(value, (bool, int, float)) and (isinstance(value, bool) or measurement(value) is not None):
                out[key] = value
            elif isinstance(value, str) and identifier(value):
                out[key] = value
        return out

    stt_options = actual_options(components.stt, stt_options)
    llm_options = actual_options(components.llm, llm_options)
    tts_options = actual_options(components.tts, tts_options)
    def entry(provider: str, requested: Any, effective: Any, options: dict) -> dict:
        def scalar(value: Any) -> Any:
            if value is None or isinstance(value, bool):
                return value
            return identifier(value) if isinstance(value, str) else measurement(value)
        safe_options = {key: [scalar(v) for v in value[:16]] if isinstance(value, list)
                        else {k: scalar(v) for k, v in value.items()} if key == "voice_settings" and isinstance(value, dict)
                        else scalar(value) for key, value in options.items()}
        return {"provider": provider, "requested_model": identifier(requested),
                "effective_model": identifier(effective), "effective_options": safe_options,
                "plugin_version": plugin_version(provider),
                "options_source": "adapter_resolution_with_allowlisted_installed_options"}

    return {"language": language, "channel": channel,
            "source": "local_constructor_configuration", "deployed_verified": False,
            "stt": entry(stt, cfg.stt_model, stt_model, stt_options),
            "llm": entry(llm, cfg.llm_model, llm_model, llm_options),
            "tts": {**entry(tts, (cfg.tts_options or {}).get("model"), tts_model, tts_options),
                    "voice": identifier(runtime_cfg.tts_voice_id)}}


@dataclass
class GenerationTrace:
    session_id: str
    user_turn_id: str | None
    assistant_turn_id: str
    generation_id: str = field(default_factory=lambda: new_id("generation"))
    stages: dict[str, float | None] = field(default_factory=lambda: dict.fromkeys(STAGES))
    outcome: str | None = None
    usage: dict[str, float] = field(default_factory=dict)
    usage_reported: bool = False

    def identity(self) -> dict:
        return {name: getattr(self, name) for name in
                ("session_id", "user_turn_id", "assistant_turn_id", "generation_id")}
