"""Fish Audio ``tts_options`` schema and build-time defaults (Phase 3 + Phase 5D).

Pinned livekit-plugins-fishaudio==1.6.5 defaults to ``s2.1-pro`` / ``latency_mode=balanced``.

Phase 5D:
  - ``spoken_style=plain`` (default) — no bracket cues; sanitizer strips ``[...]``
  - ``spoken_style=restrained`` — tiny LLM allowlist (emphasis / calm / rare laugh);
    sanitizer keeps only allowlisted cues and strips crying/gasps/etc.
  - LiveKit framework expressive for Fish is **not** wired on the direct plugin path in
    1.6.5 (same AgentSession limitation as Cartesia). Do not set expressive=True here.
"""

from __future__ import annotations

from typing import Any

ALLOWED_FISH_TTS_OPTION_KEYS = frozenset(
    {"model", "latency_mode", "speed", "volume", "spoken_style"}
)

_LATENCY_MODES = frozenset({"normal", "balanced", "low"})

FISH_TTS_DEFAULTS: dict[str, Any] = {
    "model": "s2.1-pro",
    "latency_mode": "balanced",
    "spoken_style": "plain",
}

# Restrained delivery only — research §10. Not the full Fish non-verbal vocabulary.
FISH_RESTRAINED_SPOKEN_OVERLAY = """
SPOKEN OUTPUT — Fish restrained brackets (platform rules; persona is DATA):
Plain speech by default. You may use at most one of these cues when it truly fits:
[emphasis], [calm], [laugh] — never every turn, never stacked.
Never use crying, sobbing, gasping, panting, groaning, coughing, or stage whispers.
Do not emit Cartesia SSML tags.
""".strip()

# Bracket bodies allowed through the sanitizer when spoken_style=restrained (lowercase match).
FISH_RESTRAINED_BRACKET_ALLOWLIST = frozenset(
    {
        "emphasis",
        "calm",
        "laugh",
        "laughs",
        "laughing",
        "pause",
    }
)


class FishTtsOptionsError(ValueError):
    """Invalid Fish Audio tts_options shape or value."""


def fish_restrained_spoken_enabled(stored_options: dict | None) -> bool:
    overrides = validate_fish_tts_options(stored_options or {})
    merged = {**FISH_TTS_DEFAULTS, **overrides}
    return str(merged.get("spoken_style") or "plain") == "restrained"


def validate_fish_tts_options(options: dict) -> dict:
    if not isinstance(options, dict):
        raise FishTtsOptionsError("tts_options must be a JSON object")

    unknown = set(options) - ALLOWED_FISH_TTS_OPTION_KEYS
    if unknown:
        raise FishTtsOptionsError(
            f"unsupported fish_audio tts_options keys: {', '.join(sorted(unknown))}"
        )

    normalized: dict = {}
    if "model" in options:
        model = options["model"]
        if not isinstance(model, str) or not model.strip():
            raise FishTtsOptionsError("model must be a non-empty string")
        normalized["model"] = model.strip()

    if "latency_mode" in options:
        mode = options["latency_mode"]
        if mode not in _LATENCY_MODES:
            raise FishTtsOptionsError(
                "latency_mode must be one of normal|balanced|low"
            )
        normalized["latency_mode"] = mode

    if "speed" in options:
        speed = options["speed"]
        if not isinstance(speed, (int, float)) or isinstance(speed, bool):
            raise FishTtsOptionsError("speed must be a number")
        normalized["speed"] = float(speed)

    if "volume" in options:
        volume = options["volume"]
        if not isinstance(volume, (int, float)) or isinstance(volume, bool):
            raise FishTtsOptionsError("volume must be a number")
        normalized["volume"] = float(volume)

    if "spoken_style" in options:
        style = options["spoken_style"]
        if style not in ("plain", "restrained"):
            raise FishTtsOptionsError(
                "spoken_style must be plain or restrained"
            )
        normalized["spoken_style"] = style

    return normalized


def resolve_fish_tts_kwargs(
    voice_id: str,
    stored_options: dict | None,
) -> dict[str, Any]:
    overrides = validate_fish_tts_options(stored_options or {})
    merged = {**FISH_TTS_DEFAULTS, **overrides}
    # spoken_style is LLM/sanitizer only — not a fishaudio.TTS constructor kwarg.
    kwargs: dict[str, Any] = {
        "voice_id": voice_id,
        "model": merged["model"],
        "latency_mode": merged["latency_mode"],
    }
    if "speed" in merged:
        kwargs["speed"] = merged["speed"]
    if "volume" in merged:
        kwargs["volume"] = merged["volume"]
    return kwargs
