"""Cartesia TTS adapter (Phase 6c, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py (provider level) AND
the specific voice row's own `rollout_state`/`enabled` in the `voices` table are both the real
gates, not this file. Constructor args verified against livekit-plugins-cartesia==1.6.5:
`model`, `voice`, `language`, `speed`, `emotion`, `volume` (see upstream tts.py).

Phase B humanization defaults (sonic-3.5, speed 0.95, emotion calm+content) and Phase C audio
profiles (webrtc pcm_s16le 16kHz / telephony pcm_mulaw 8kHz) live in cartesia_options.py.

Requires CARTESIA_API_KEY (env var, or api_key= kwarg) — the plugin itself raises a clear
ValueError if neither is set, checked eagerly at construction (same pattern as every other
provider adapter in this repo).
"""

from __future__ import annotations

from typing import Any

from .cartesia_options import resolve_cartesia_tts_kwargs


def build(voice_id: str, language: str, tts_options: dict | None = None, *, audio_channel: str = "webrtc") -> Any:
    from livekit.plugins import cartesia

    return cartesia.TTS(
        **resolve_cartesia_tts_kwargs(
            voice_id, language, tts_options, audio_channel=audio_channel
        )
    )
