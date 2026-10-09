"""Internal capabilities tied to installed path/options; no public API promotion."""

from __future__ import annotations

import hashlib
import importlib
import inspect
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .policy import ACTIVE_PROVIDERS


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    model: str
    plugin_version: str
    path: str
    source_fingerprint: str
    options: tuple[str, ...]
    streaming: bool = False
    aligned_transcript: bool = False
    alignment_mode: str = "canonical"
    emotion: bool = False
    speed: bool = False
    pause: bool = False
    nonverbals: tuple[str, ...] = ()
    pronunciation: tuple[str, ...] = ("NORMAL", "ALIAS", "SPELL_PLAIN", "DIGIT_GROUP")
    continuation: str = "framework_owned"
    fast_cancellation: bool = False  # caller-side stop latency is not verified
    native_output_formats: tuple[str, ...] = ()
    live_verified: bool = False


def effective_options(provider: str, voice: str, language: str, options: dict, channel: str) -> dict:
    if provider == "cartesia":
        from worker.providers.tts.cartesia_options import resolve_cartesia_tts_kwargs
        return resolve_cartesia_tts_kwargs(voice, language, options, audio_channel=channel)
    if provider == "rime":
        from worker.providers.tts.rime_options import resolve_rime_tts_kwargs
        return resolve_rime_tts_kwargs(voice, "eng", options, audio_channel=channel)
    if provider == "elevenlabs":
        from dataclasses import asdict
        from worker.providers.tts.elevenlabs_options import resolve_elevenlabs_tts_kwargs
        result = resolve_elevenlabs_tts_kwargs(voice, language, options)
        result["voice_settings"] = asdict(result["voice_settings"])
        # Installed default verified in elevenlabs/tts.py; adapter deliberately omits it.
        from livekit.plugins.elevenlabs import tts as eleven_tts
        result["encoding"] = getattr(eleven_tts, "_DefaultEncoding", "unknown")
        result["sample_rate"] = int(result["encoding"].split("_")[1]) if "_" in result["encoding"] else "unknown"
        return result
    if provider == "uplift":
        import os
        from worker.providers.tts.uplift import resolve_uplift_phrase_config_id
        return {
            "model": "uplift", "voice_id": voice, "mode": os.getenv("UPLIFT_MODE", "fixture"),
            "output_format": "PCM_22050_16",
            "phrase_replacement_config_id": resolve_uplift_phrase_config_id(),
        }
    raise ValueError("unselectable TTS provider")


def resolve_capabilities(provider: str, effective: dict) -> ProviderCapabilities:
    if provider not in ACTIVE_PROVIDERS:
        raise ValueError("unselectable TTS provider")
    plugin = "upliftai" if provider == "uplift" else provider
    fixture = provider == "uplift" and effective.get("mode") == "fixture"
    model = str(effective.get("model", "unknown"))
    try:
        installed = version("livekit-plugins-" + plugin)
        module = importlib.import_module("livekit.plugins." + plugin + ".tts")
        source = Path(module.__file__).read_bytes()
        path = str(module.__file__)
        fingerprint = hashlib.sha256(source).hexdigest()[:16]
        parameters = tuple(sorted(inspect.signature(module.TTS).parameters))
    except (PackageNotFoundError, ImportError, OSError, AttributeError, TypeError):
        installed, path, fingerprint, parameters = "unavailable", "unavailable", "", ()
    # Audited 1.6.5 path only. Upgrades fail closed until deliberately re-audited.
    audited = installed == "1.6.5"
    sonic = audited and provider == "cartesia" and model.startswith("sonic-3")
    native_spell = audited and provider == "rime" and model in {"coda", "mistv2", "mistv3"}
    # Arcana speed direction/spell behavior lacks current account proof; use plain fallback.
    rime_speed = audited and provider == "rime" and model in {"coda", "mistv2", "mistv3"} and "speed_alpha" in parameters
    eleven_speed = audited and provider == "elevenlabs" and model in {
        "eleven_flash_v2_5", "eleven_flash_v2", "eleven_turbo_v2_5",
        "eleven_turbo_v2", "eleven_multilingual_v2",
    } and "voice_settings" in parameters
    pronunciation = ("NORMAL", "ALIAS", "SPELL_PLAIN", "DIGIT_GROUP")
    if sonic:
        pronunciation += ("SPELL_NATIVE",)
    if native_spell:
        pronunciation += ("SPELL_NATIVE",)
    if provider == "uplift" and not fixture and effective.get("phrase_replacement_config_id"):
        pronunciation += ("ACCOUNT_PHRASE_CONFIG",)
    return ProviderCapabilities(
        provider, model, installed, "fixture" if fixture else path, fingerprint,
        tuple(sorted(effective)), streaming=audited and not fixture and (
            provider != "rime" or effective.get("use_websocket", False)
        ),
        aligned_transcript=audited and (provider == "elevenlabs" or (
            provider == "rime" and effective.get("use_websocket", False)
        )),
        emotion=sonic and effective.get("language", "en").startswith("en"),
        speed=sonic or rime_speed or eleven_speed, pause=sonic,
        # Soft laughter is deliberately omitted until lane listening verifies it.
        pronunciation=pronunciation,
        native_output_formats=(
            (str(effective.get("output_format")),) if provider == "uplift"
            else (str(effective.get("encoding", "pcm")), str(effective.get("sample_rate", "plugin_default")))
        ),
    )
