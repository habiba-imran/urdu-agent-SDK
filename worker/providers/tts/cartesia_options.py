"""Cartesia ``tts_options`` schema, validation, and build-time defaults (Phase B + Phase 5).

Stored ``agents.tts_options`` holds tenant overrides only (may be ``{}``). The adapter merges
with ``CARTESIA_TTS_DEFAULTS`` at construction time so existing agents pick up sonic-3.5 +
baseline emotion/speed without a DB migration.

Phase 5 A/B (defaults unchanged until listening promotes a winner):
  - ``tts_options.model=sonic-3.6`` (or snapshot id) — opt-in; plugin accepts ``str``
  - env ``CARTESIA_TTS_MODEL`` — demo-only default override when stored options omit ``model``
  - ``spoken_style=manual_ssml|light`` — already Phase 3
  - ``expressive=true`` — only effective when ``cartesia_expressive_available()``
"""

from __future__ import annotations

import os
from typing import Any, Literal

ALLOWED_CARTESIA_TTS_OPTION_KEYS = frozenset(
    {"model", "speed", "volume", "emotion", "expressive", "spoken_style"}
)

AudioChannel = Literal["webrtc", "telephony"]

# Documented experiment labels (research §30). Not a hard allowlist — Cartesia IDs move fast;
# the plugin types ``model`` as ``TTSModels | str`` and treats ``sonic-3*`` as Sonic 3 family.
CARTESIA_PHASE5_MODEL_IDS = frozenset(
    {
        "sonic-3.5",
        "sonic-3.6",
        "sonic-3.6-2026-08-27",
    }
)

CARTESIA_TTS_DEFAULTS: dict = {
    "model": "sonic-3.5",
    "speed": 0.95,
    # Used only for spoken_style=light (no per-turn tags). Manual SSML omits constructor
    # emotion so contextual <emotion> tags actually shift tone (audit medium fix).
    "emotion": ["calm", "content"],
    # Manual SSML is the working humanization path with ``livekit.plugins.cartesia.TTS``.
    # LiveKit's expressive pipeline is framework-internal, hardcoded off on AgentSession, and
    # only resolves for ``inference.TTS`` — not the Cartesia plugin. Defaulting expressive=True
    # previously selected the "don't emit <emotion>/<break>" prompt while nothing injected
    # tags → flat calm TTS with no tone shifts. Opt in with ``tts_options.expressive=true``
    # only when a future livekit-agents build exposes a public AgentSession expressive kwarg
    # (and you are on inference TTS).
    "expressive": False,
    # Phase 3: ``light`` = plain-text rules + constructor emotion (lower LLM token tax than
    # mandatory per-turn <emotion> tags). Opt into manual_ssml via tts_options when A/B needs it.
    "spoken_style": "light",
}

# Phase C — match Cartesia output to the LiveKit agent audio path.
# The installed livekit-plugins-cartesia AudioEmitter is hardcoded to mime_type="audio/pcm"
# (linear). Requesting pcm_mulaw makes LiveKit interpret µ-law bytes as s16le → garbled /
# unintelligible PSTN audio. LiveKit SIP resamples pcm_s16le → PCMU for Telnyx.
CARTESIA_AUDIO_PROFILES: dict[str, dict[str, str | int]] = {
    "webrtc": {"encoding": "pcm_s16le", "sample_rate": 16000},
    "telephony": {"encoding": "pcm_s16le", "sample_rate": 16000},
}

_MIN_SPEED = 0.6
_MAX_SPEED = 1.5
_MIN_VOLUME = 0.5
_MAX_VOLUME = 2.0


class CartesiaTtsOptionsError(ValueError):
    """Invalid Cartesia tts_options shape or value."""


def validate_cartesia_tts_options(options: dict) -> dict:
    """Validate and return normalized options to persist (overrides only, may be empty)."""
    if not isinstance(options, dict):
        raise CartesiaTtsOptionsError("tts_options must be a JSON object")

    unknown = set(options) - ALLOWED_CARTESIA_TTS_OPTION_KEYS
    if unknown:
        raise CartesiaTtsOptionsError(
            f"unsupported cartesia tts_options keys: {', '.join(sorted(unknown))}"
        )

    normalized: dict = {}
    if "model" in options:
        model = options["model"]
        if not isinstance(model, str) or not model.strip():
            raise CartesiaTtsOptionsError("model must be a non-empty string")
        normalized["model"] = model.strip()

    if "speed" in options:
        speed = options["speed"]
        if not isinstance(speed, (int, float)) or isinstance(speed, bool):
            raise CartesiaTtsOptionsError("speed must be a number")
        speed = float(speed)
        if not _MIN_SPEED <= speed <= _MAX_SPEED:
            raise CartesiaTtsOptionsError(
                f"speed must be between {_MIN_SPEED} and {_MAX_SPEED}"
            )
        normalized["speed"] = speed

    if "volume" in options:
        volume = options["volume"]
        if not isinstance(volume, (int, float)) or isinstance(volume, bool):
            raise CartesiaTtsOptionsError("volume must be a number")
        volume = float(volume)
        if not _MIN_VOLUME <= volume <= _MAX_VOLUME:
            raise CartesiaTtsOptionsError(
                f"volume must be between {_MIN_VOLUME} and {_MAX_VOLUME}"
            )
        normalized["volume"] = volume

    if "emotion" in options:
        emotion = options["emotion"]
        if isinstance(emotion, str):
            emotions = [emotion]
        elif isinstance(emotion, list):
            emotions = emotion
        else:
            raise CartesiaTtsOptionsError("emotion must be a string or list of strings")
        if not emotions or not all(isinstance(e, str) and e.strip() for e in emotions):
            raise CartesiaTtsOptionsError("emotion must be non-empty string(s)")
        normalized["emotion"] = [e.strip() for e in emotions]

    if "expressive" in options:
        expressive = options["expressive"]
        if not isinstance(expressive, bool):
            raise CartesiaTtsOptionsError("expressive must be a boolean")
        normalized["expressive"] = expressive

    if "spoken_style" in options:
        style = options["spoken_style"]
        if style not in ("manual_ssml", "light"):
            raise CartesiaTtsOptionsError(
                "spoken_style must be manual_ssml or light"
            )
        normalized["spoken_style"] = style

    return normalized


def cartesia_expressive_available() -> bool:
    """True only if this livekit-agents build exposes public AgentSession expressive.

    In 1.6.5 the session hardcodes ``_expressive=False`` and
    ``_resolve_expressive_options`` only activates for ``inference.TTS`` — so the
    Cartesia plugin never receives injected markup even if we wished it on.
    """
    import inspect

    try:
        from livekit.agents import AgentSession
    except Exception:
        return False
    return "expressive" in inspect.signature(AgentSession.__init__).parameters


def cartesia_expressive_enabled(stored_options: dict | None) -> bool:
    """Whether to use the expressive (no-manual-SSML) prompt profile.

    Requires both an explicit/merged ``expressive=True`` option *and* a LiveKit
    build that can actually run the expressive pipeline. Otherwise we fall back
    to manual ``<emotion>`` / ``<break>`` instructions so voice stays humanized.
    """
    overrides = validate_cartesia_tts_options(stored_options or {})
    merged = {**CARTESIA_TTS_DEFAULTS, **overrides}
    want = bool(merged.get("expressive", False))
    if not want:
        return False
    return cartesia_expressive_available()


def cartesia_light_spoken_enabled(stored_options: dict | None) -> bool:
    """True when ``spoken_style=light`` — plain-text Cartesia rules without LiveKit expressive.

    Constructor emotion defaults still apply; listening A/B should check whether they
    fight contextual prosody (Phase 5).
    """
    overrides = validate_cartesia_tts_options(stored_options or {})
    merged = {**CARTESIA_TTS_DEFAULTS, **overrides}
    return str(merged.get("spoken_style") or "manual_ssml") == "light"


def _demo_cartesia_model_override() -> str | None:
    """Optional worker env default when agent ``tts_options`` omit ``model`` (Phase 5A).

    Does not change the code default (``sonic-3.5``) unless the env is set. Prefer
    per-agent ``tts_options.model`` for durable experiments.
    """
    raw = (os.getenv("CARTESIA_TTS_MODEL") or "").strip()
    return raw or None


def cartesia_experiment_label(stored_options: dict | None) -> str:
    """Stable label for logs / listening notes (e.g. ``sonic-3.6+light``)."""
    overrides = validate_cartesia_tts_options(stored_options or {})
    demo = _demo_cartesia_model_override()
    model = overrides.get("model") or demo or CARTESIA_TTS_DEFAULTS["model"]
    style = overrides.get("spoken_style", CARTESIA_TTS_DEFAULTS["spoken_style"])
    expressive = bool(overrides.get("expressive", False))
    parts = [str(model), str(style)]
    if expressive:
        parts.append("expressive_requested")
    return "+".join(parts)


def resolve_cartesia_tts_kwargs(
    voice_id: str,
    language: str,
    stored_options: dict | None,
    *,
    audio_channel: str = "webrtc",
) -> dict:
    """Merge stored overrides with platform defaults; return kwargs for cartesia.TTS()."""
    overrides = validate_cartesia_tts_options(stored_options or {})
    tts_overrides = {
        k: v for k, v in overrides.items() if k not in ("expressive", "spoken_style")
    }
    merged = {**CARTESIA_TTS_DEFAULTS, **tts_overrides}
    # Demo env only fills model when the agent did not set one.
    if "model" not in overrides:
        demo_model = _demo_cartesia_model_override()
        if demo_model:
            merged["model"] = demo_model
    profile = CARTESIA_AUDIO_PROFILES.get(
        audio_channel, CARTESIA_AUDIO_PROFILES["webrtc"]
    )
    style = str(
        overrides.get("spoken_style")
        or CARTESIA_TTS_DEFAULTS.get("spoken_style")
        or "manual_ssml"
    )

    kwargs: dict = {
        "voice": voice_id,
        "language": language,
        "model": merged["model"],
        "speed": merged["speed"],
        "encoding": profile["encoding"],
        "sample_rate": profile["sample_rate"],
    }
    # Manual SSML: omit constructor emotion so per-turn <emotion> tags drive tone.
    # Light / explicit emotion override: keep baseline or tenant emotion list.
    if "emotion" in overrides:
        kwargs["emotion"] = overrides["emotion"]
    elif style == "light":
        kwargs["emotion"] = list(CARTESIA_TTS_DEFAULTS["emotion"])
    if "volume" in merged:
        kwargs["volume"] = merged["volume"]
    return kwargs


def low_latency_cartesia_tokenizer() -> Any:
    """Cartesia stream tokenizer tuned for voice latency (UVA-4).

    LiveKit's default blingfire ``SentenceTokenizer`` waits for sentence boundaries and
    ``stream_context_len=10`` before pushing text to the Cartesia websocket. That batches
    LLM tokens into multi-second silence before the first audio chunk.
    """
    from livekit.agents import tokenize

    return tokenize.blingfire.SentenceTokenizer(
        min_sentence_len=1,
        stream_context_len=1,
        min_token_len=1,
        max_token_len=100,
        retain_format=True,
        xml_aware=True,
    )
