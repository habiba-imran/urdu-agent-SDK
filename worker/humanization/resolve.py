"""Resolve effective providers after telephony remaps (Phase 0).

Humanization must use the *effective* LLM/TTS providers, not the pre-remap DB config.
This module is the single wrap around ``force_cartesia_for_telephony`` /
``force_groq_for_telephony`` so later profile builders never forget remaps.
"""

from __future__ import annotations

from dataclasses import dataclass

from worker.config import AgentConfig
from worker.telephony_tts import (
    force_cartesia_for_telephony,
    force_groq_for_english_webrtc,
    force_groq_for_telephony,
)


@dataclass(frozen=True)
class EffectiveProviders:
    """Post-remap session identity for humanization + pipeline build."""

    cfg: AgentConfig
    provider_voice_id: str | None
    audio_channel: str
    cartesia_forced: bool = False
    groq_forced: bool = False

    @property
    def llm_provider(self) -> str:
        return (self.cfg.llm_provider or "").strip().lower()

    @property
    def tts_provider(self) -> str:
        return (self.cfg.tts_provider or "").strip().lower()

    @property
    def stt_provider(self) -> str:
        return (self.cfg.stt_provider or "").strip().lower()

    @property
    def agent_language(self) -> str:
        return (self.cfg.agent_language or "").strip().lower()


def resolve_effective_providers(
    cfg: AgentConfig,
    provider_voice_id: str | None,
    *,
    audio_channel: str,
) -> EffectiveProviders:
    """Apply telephony remaps; return effective cfg + voice for downstream build.

    Behavior is intentionally identical to calling the two force_* helpers in sequence
    (Cartesia TTS remap, then Groq LLM remap).
    """
    channel = (audio_channel or "webrtc").strip().lower()
    cfg, voice, cartesia_forced = force_cartesia_for_telephony(
        cfg, provider_voice_id, audio_channel=channel
    )
    cfg, groq_tel = force_groq_for_telephony(cfg, audio_channel=channel)
    cfg, groq_web = force_groq_for_english_webrtc(cfg, audio_channel=channel)
    return EffectiveProviders(
        cfg=cfg,
        provider_voice_id=voice,
        audio_channel=channel,
        cartesia_forced=cartesia_forced,
        groq_forced=groq_tel or groq_web,
    )
