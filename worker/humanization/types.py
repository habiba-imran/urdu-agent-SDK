"""Humanization profile dataclasses (Phase 0–2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpokenOutputProfile:
    """LLM-facing spoken policy layers (Phase 1 + Phase 4 language).

    Render order: universal → llm_overlay → language_overlay → tts_overlay
    (empty strings omitted). Provider markup belongs only in ``tts_overlay``.
    """

    universal: str
    llm_overlay: str = ""
    language_overlay: str = ""
    tts_overlay: str = ""

    def render(self) -> str:
        parts = [
            p.strip()
            for p in (
                self.universal,
                self.llm_overlay,
                self.language_overlay,
                self.tts_overlay,
            )
            if p and p.strip()
        ]
        return "\n\n".join(parts)


@dataclass(frozen=True)
class TTSHumanizationProfile:
    """TTS delivery profile — filled in Phase 3+ (options, sanitizer, tokenizer)."""

    provider: str
    model: str | None = None
    expressive_mode: bool = False


@dataclass(frozen=True)
class TurnProfile:
    """STT / EOU / interruption profile (Phase 2).

    ``as_livekit_options`` / ``turn_profile_to_livekit_options`` produce the dict passed to
    ``AgentSession(turn_handling=...)``. Deepgram ``endpointing_ms`` is separate (STT adapter).
    """

    channel: str
    stt_provider: str
    llm_provider: str = ""
    detector: str = "stt"
    endpointing_min_delay: float = 0.15
    endpointing_max_delay: float = 1.5
    preemptive_generation_enabled: bool = True
    preemptive_tts: bool = True
    interruption_enabled: bool = True
    interruption_mode: str = "vad"
    resume_false_interruption: bool = True
    false_interruption_timeout: float = 1.5
    discard_audio_if_uninterruptible: bool = True
    interruption_min_duration: float = 0.3
    preemptive_max_speech_duration: float = 12.0
    preemptive_max_retries: int = 3
