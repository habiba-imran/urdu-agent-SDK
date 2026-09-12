"""Rime ``tts_options`` schema and build-time defaults (Phase B humanization).

Stored ``agents.tts_options`` holds tenant overrides only (may be ``{}``). The adapter merges
with ``RIME_TTS_DEFAULTS`` so existing Rime agents pick up Arcana + WebSocket without a DB
migration.

The seeded voice catalog uses Arcana speakers (``rime-arcana-*`` -> ``astra``, ``celeste``,
...). Default ``model`` is ``arcana`` to match the plugin and catalog. Coda remains opt-in
via ``tts_options.model = \"coda\"`` with a Coda voice such as ``lyra``.

``speed_alpha`` is the speed control that works over WebSocket (docs/rime-labs-humanization.md).
Values slightly above 1.0 are the documented "a bit slower / more deliberate" starting point.
"""

from __future__ import annotations

ALLOWED_RIME_TTS_OPTION_KEYS = frozenset({"model", "speed_alpha", "time_scale_factor"})

# Matches livekit.plugins.rime.models.ArcanaVoices — every seeded ``voices.provider_voice_id``.
_ARCANA_SPEAKERS = frozenset(
    {"luna", "celeste", "orion", "ursa", "astra", "esther", "estelle", "andromeda"}
)

RIME_TTS_DEFAULTS: dict = {
    "model": "arcana",
    "speed_alpha": 1.1,
    "use_websocket": True,
    "segment": "immediate",
}

# Phase C — match Rime output to the downstream audio leg (docs/rime-labs-humanization.md Layer 10).
# The LiveKit plugin WebSocket path uses PCM (not native µ-law); we still match sample rate
# so LiveKit/SIP does not resample from the plugin default 22050 Hz.
RIME_AUDIO_PROFILES: dict[str, dict[str, int]] = {
    "webrtc": {"sample_rate": 16000},
    "telephony": {"sample_rate": 8000},
}

_MIN_SPEED_ALPHA = 0.5
_MAX_SPEED_ALPHA = 2.0
_MIN_TIME_SCALE = 0.5
_MAX_TIME_SCALE = 2.0


class RimeTtsOptionsError(ValueError):
    """Invalid Rime tts_options shape or value."""


def validate_rime_tts_options(options: dict) -> dict:
    """Validate and return normalized options to persist (overrides only, may be empty)."""
    if not isinstance(options, dict):
        raise RimeTtsOptionsError("tts_options must be a JSON object")

    unknown = set(options) - ALLOWED_RIME_TTS_OPTION_KEYS
    if unknown:
        raise RimeTtsOptionsError(
            f"unsupported rime tts_options keys: {', '.join(sorted(unknown))}"
        )

    normalized: dict = {}
    if "model" in options:
        model = options["model"]
        if not isinstance(model, str) or not model.strip():
            raise RimeTtsOptionsError("model must be a non-empty string")
        normalized["model"] = model.strip()

    if "speed_alpha" in options:
        speed = options["speed_alpha"]
        if not isinstance(speed, (int, float)) or isinstance(speed, bool):
            raise RimeTtsOptionsError("speed_alpha must be a number")
        speed = float(speed)
        if not _MIN_SPEED_ALPHA <= speed <= _MAX_SPEED_ALPHA:
            raise RimeTtsOptionsError(
                f"speed_alpha must be between {_MIN_SPEED_ALPHA} and {_MAX_SPEED_ALPHA}"
            )
        normalized["speed_alpha"] = speed

    if "time_scale_factor" in options:
        scale = options["time_scale_factor"]
        if not isinstance(scale, (int, float)) or isinstance(scale, bool):
            raise RimeTtsOptionsError("time_scale_factor must be a number")
        scale = float(scale)
        if not _MIN_TIME_SCALE <= scale <= _MAX_TIME_SCALE:
            raise RimeTtsOptionsError(
                f"time_scale_factor must be between {_MIN_TIME_SCALE} and {_MAX_TIME_SCALE}"
            )
        normalized["time_scale_factor"] = scale

    return normalized


def resolve_rime_tts_kwargs(
    speaker: str,
    lang: str,
    stored_options: dict | None,
    *,
    audio_channel: str = "webrtc",
) -> dict:
    """Merge stored overrides with platform defaults; return kwargs for rime.TTS()."""
    overrides = validate_rime_tts_options(stored_options or {})
    merged = {**RIME_TTS_DEFAULTS, **overrides}
    model = merged["model"]
    # Legacy default was coda while the catalog only seeds Arcana speakers — coerce so
    # ``rime-arcana-astra`` et al. always hit a valid model/speaker pair unless the tenant
    # explicitly chose a non-Arcana model in stored tts_options.
    if speaker in _ARCANA_SPEAKERS and model == "coda" and "model" not in overrides:
        model = "arcana"
    profile = RIME_AUDIO_PROFILES.get(audio_channel, RIME_AUDIO_PROFILES["webrtc"])

    kwargs: dict = {
        "speaker": speaker,
        "lang": lang,
        "model": model,
        "speed_alpha": merged["speed_alpha"],
        "use_websocket": merged["use_websocket"],
        "segment": merged["segment"],
        "sample_rate": profile["sample_rate"],
    }
    if "time_scale_factor" in merged and not merged["use_websocket"]:
        kwargs["time_scale_factor"] = merged["time_scale_factor"]
    return kwargs
