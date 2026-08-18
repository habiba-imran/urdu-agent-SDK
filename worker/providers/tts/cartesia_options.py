"""Cartesia ``tts_options`` schema, validation, and build-time defaults (Phase B humanization).

Stored ``agents.tts_options`` holds tenant overrides only (may be ``{}``). The adapter merges
with ``CARTESIA_TTS_DEFAULTS`` at construction time so existing agents pick up sonic-3.5 +
baseline emotion/speed without a DB migration.
"""

from __future__ import annotations

from typing import Literal

ALLOWED_CARTESIA_TTS_OPTION_KEYS = frozenset(
    {"model", "speed", "volume", "emotion", "expressive"}
)

AudioChannel = Literal["webrtc", "telephony"]

CARTESIA_TTS_DEFAULTS: dict = {
    "model": "sonic-3.5",
    "speed": 0.95,
    "emotion": ["calm", "content"],
}

# Phase C — match Cartesia output to the downstream audio leg (docs/cartesia_humanization.md Layer 6).
CARTESIA_AUDIO_PROFILES: dict[str, dict[str, str | int]] = {
    "webrtc": {"encoding": "pcm_s16le", "sample_rate": 16000},
    "telephony": {"encoding": "pcm_mulaw", "sample_rate": 8000},
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

    return normalized


def cartesia_expressive_enabled(stored_options: dict | None) -> bool:
    """Session-level A/B flag — never passed to cartesia.TTS()."""
    return bool((stored_options or {}).get("expressive") is True)


def resolve_cartesia_tts_kwargs(
    voice_id: str,
    language: str,
    stored_options: dict | None,
    *,
    audio_channel: str = "webrtc",
) -> dict:
    """Merge stored overrides with platform defaults; return kwargs for cartesia.TTS()."""
    overrides = validate_cartesia_tts_options(stored_options or {})
    tts_overrides = {k: v for k, v in overrides.items() if k != "expressive"}
    merged = {**CARTESIA_TTS_DEFAULTS, **tts_overrides}
    profile = CARTESIA_AUDIO_PROFILES.get(
        audio_channel, CARTESIA_AUDIO_PROFILES["webrtc"]
    )

    kwargs: dict = {
        "voice": voice_id,
        "language": language,
        "model": merged["model"],
        "speed": merged["speed"],
        "emotion": merged["emotion"],
        "encoding": profile["encoding"],
        "sample_rate": profile["sample_rate"],
    }
    if "volume" in merged:
        kwargs["volume"] = merged["volume"]
    return kwargs
