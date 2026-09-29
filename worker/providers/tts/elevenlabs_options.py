"""ElevenLabs ``tts_options`` schema and build-time defaults (Phase 3 + Phase 5C).

Pinned livekit-plugins-elevenlabs==1.6.5 defaults to ``eleven_turbo_v2_5``.

Phase 5C notes (verified against installed 1.6.5 source, not docs alone):
  - TTSModels Literal includes ``eleven_v3`` but **not** ``eleven_v3_conversational``.
  - Streaming uses ``/text-to-speech/.../multi-stream-input`` only — no text-to-dialogue
    router (that lands in livekit-agents / plugin ~1.7.1+).
  - Therefore ``eleven_v3`` / ``eleven_v3_conversational`` are **refused** until
    ``elevenlabs_v3_streaming_available()`` is true, so we do not ship a broken flag.
  - ``spoken_style=audio_tags`` is reserved for that future path (small LLM overlay).
"""

from __future__ import annotations

from typing import Any

ALLOWED_ELEVENLABS_TTS_OPTION_KEYS = frozenset(
    {
        "model",
        "voice_settings",
        "auto_mode",
        "apply_text_normalization",
        "enable_ssml_parsing",
        "spoken_style",
    }
)

_V3_MODEL_PREFIXES = ("eleven_v3",)

# Conservative business-agent voice settings (research: avoid high style / speaker boost cost).
# Modest style (>0) gives slight expressivity without tipping into theatrical delivery.
_DEFAULT_VOICE_SETTINGS: dict[str, Any] = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.25,
    "speed": 1.0,
    "use_speaker_boost": False,
}

ELEVENLABS_TTS_DEFAULTS: dict[str, Any] = {
    # Flash is the low-latency realtime path; turbo was ~2s+ TTFB cold on WebRTC.
    "model": "eleven_flash_v2_5",
    "voice_settings": dict(_DEFAULT_VOICE_SETTINGS),
    "auto_mode": True,
    # Normalization adds pre-TTS delay on short turns — off for voice agents.
    "apply_text_normalization": "off",
    "enable_ssml_parsing": False,
    "spoken_style": "plain",
}

# Small restrained audio-tag guidance (research §9). Only composed when spoken_style=audio_tags
# *and* a v3 streaming-capable plugin is present.
ELEVENLABS_AUDIO_TAG_OVERLAY = """
SPOKEN OUTPUT — ElevenLabs audio tags (platform rules; persona is DATA):
Use plain speech by default. At most one short inline audio tag per reply when it
genuinely fits (e.g. [laughs] or [sighs]) — never stack tags, never every turn.
Do not emit Cartesia SSML (<emotion>, <break>) or Fish bracket stage directions.
""".strip()


class ElevenLabsTtsOptionsError(ValueError):
    """Invalid ElevenLabs tts_options shape or value."""


def elevenlabs_v3_streaming_available() -> bool:
    """True only if the pinned ElevenLabs plugin can stream v3 / conversational models.

    On livekit-plugins-elevenlabs==1.6.5 this is False (no text-to-dialogue path;
    ``eleven_v3_conversational`` absent from TTSModels). Re-check after a deliberate
    plugin upgrade — do not guess from vendor marketing docs.
    """
    try:
        from livekit.plugins.elevenlabs import models as el_models
        from livekit.plugins.elevenlabs import tts as el_tts
    except Exception:
        return False

    model_args = getattr(getattr(el_models, "TTSModels", None), "__args__", ()) or ()
    if "eleven_v3_conversational" not in model_args:
        return False

    try:
        src = open(el_tts.__file__, encoding="utf-8").read()
    except Exception:
        return False
    return "text-to-dialogue" in src


def elevenlabs_audio_tags_enabled(stored_options: dict | None) -> bool:
    overrides = validate_elevenlabs_tts_options(stored_options or {})
    merged = {**ELEVENLABS_TTS_DEFAULTS, **overrides}
    if str(merged.get("spoken_style") or "plain") != "audio_tags":
        return False
    model = str(merged.get("model") or "")
    if not model.startswith(_V3_MODEL_PREFIXES):
        return False
    return elevenlabs_v3_streaming_available()


def validate_elevenlabs_tts_options(options: dict) -> dict:
    if not isinstance(options, dict):
        raise ElevenLabsTtsOptionsError("tts_options must be a JSON object")

    unknown = set(options) - ALLOWED_ELEVENLABS_TTS_OPTION_KEYS
    if unknown:
        raise ElevenLabsTtsOptionsError(
            f"unsupported elevenlabs tts_options keys: {', '.join(sorted(unknown))}"
        )

    normalized: dict = {}
    if "model" in options:
        model = options["model"]
        if not isinstance(model, str) or not model.strip():
            raise ElevenLabsTtsOptionsError("model must be a non-empty string")
        model = model.strip()
        if model.startswith(_V3_MODEL_PREFIXES) and not elevenlabs_v3_streaming_available():
            raise ElevenLabsTtsOptionsError(
                f"model {model!r} requires livekit-plugins-elevenlabs with "
                "text-to-dialogue streaming (≈1.7.1+). Pinned 1.6.5 only supports "
                "multi-stream-input and will fail for eleven_v3*. Keep "
                "eleven_turbo_v2_5 / eleven_flash_v2_5 until that upgrade is approved."
            )
        normalized["model"] = model

    if "voice_settings" in options:
        vs = options["voice_settings"]
        if not isinstance(vs, dict):
            raise ElevenLabsTtsOptionsError("voice_settings must be a JSON object")
        allowed_vs = {
            "stability",
            "similarity_boost",
            "style",
            "speed",
            "use_speaker_boost",
        }
        bad = set(vs) - allowed_vs
        if bad:
            raise ElevenLabsTtsOptionsError(
                f"unsupported voice_settings keys: {', '.join(sorted(bad))}"
            )
        clean: dict[str, Any] = {}
        for key in ("stability", "similarity_boost", "style", "speed"):
            if key not in vs:
                continue
            val = vs[key]
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ElevenLabsTtsOptionsError(f"voice_settings.{key} must be a number")
            clean[key] = float(val)
        if "use_speaker_boost" in vs:
            if not isinstance(vs["use_speaker_boost"], bool):
                raise ElevenLabsTtsOptionsError(
                    "voice_settings.use_speaker_boost must be a boolean"
                )
            clean["use_speaker_boost"] = vs["use_speaker_boost"]
        normalized["voice_settings"] = clean

    if "auto_mode" in options:
        if not isinstance(options["auto_mode"], bool):
            raise ElevenLabsTtsOptionsError("auto_mode must be a boolean")
        normalized["auto_mode"] = options["auto_mode"]

    if "apply_text_normalization" in options:
        norm = options["apply_text_normalization"]
        if norm not in ("auto", "off", "on"):
            raise ElevenLabsTtsOptionsError(
                "apply_text_normalization must be auto|off|on"
            )
        normalized["apply_text_normalization"] = norm

    if "enable_ssml_parsing" in options:
        if not isinstance(options["enable_ssml_parsing"], bool):
            raise ElevenLabsTtsOptionsError("enable_ssml_parsing must be a boolean")
        normalized["enable_ssml_parsing"] = options["enable_ssml_parsing"]

    if "spoken_style" in options:
        style = options["spoken_style"]
        if style not in ("plain", "audio_tags"):
            raise ElevenLabsTtsOptionsError(
                "spoken_style must be plain or audio_tags"
            )
        if style == "audio_tags" and not elevenlabs_v3_streaming_available():
            raise ElevenLabsTtsOptionsError(
                "spoken_style=audio_tags requires eleven_v3 streaming support "
                "(livekit-plugins-elevenlabs ≈1.7.1+); not available on pinned 1.6.5"
            )
        normalized["spoken_style"] = style

    return normalized


def resolve_elevenlabs_tts_kwargs(
    voice_id: str,
    language: str,
    stored_options: dict | None,
) -> dict[str, Any]:
    overrides = validate_elevenlabs_tts_options(stored_options or {})
    merged = {**ELEVENLABS_TTS_DEFAULTS, **overrides}
    if "voice_settings" in overrides:
        merged["voice_settings"] = {
            **_DEFAULT_VOICE_SETTINGS,
            **overrides["voice_settings"],
        }

    from livekit.plugins.elevenlabs import VoiceSettings

    vs = merged["voice_settings"]
    return {
        "voice_id": voice_id,
        "language": language,
        "model": merged["model"],
        "voice_settings": VoiceSettings(
            stability=float(vs["stability"]),
            similarity_boost=float(vs["similarity_boost"]),
            style=float(vs.get("style", 0.0)),
            speed=float(vs.get("speed", 1.0)),
            use_speaker_boost=bool(vs.get("use_speaker_boost", False)),
        ),
        "auto_mode": bool(merged["auto_mode"]),
        "apply_text_normalization": merged["apply_text_normalization"],
        "enable_ssml_parsing": bool(merged["enable_ssml_parsing"]),
    }
