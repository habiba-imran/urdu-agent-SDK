"""Telephony voice quality helpers — force Cartesia TTS + Groq LLM on PSTN."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worker.config import AgentConfig

# Cartesia plugin default / Katie — low-latency Sonic voice used by test-agent UX.
TELEPHONY_CARTESIA_VOICE_ID = "cartesia-katie-friendly-fixer"
TELEPHONY_CARTESIA_PROVIDER_VOICE_ID = "f786b574-daa5-4673-aa0c-cbe3e8534c02"

# Voice-proven Groq model (~0.5s content TTFT vs Gemini 3.6 Flash ~1.5–3s+ on PSTN).
TELEPHONY_GROQ_MODEL = os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-20b")


def force_cartesia_for_telephony(
    cfg: "AgentConfig",
    provider_voice_id: str | None,
    *,
    audio_channel: str,
) -> tuple["AgentConfig", str | None, bool]:
    """Remap Rime (or other) agents to Cartesia on the PSTN leg.

    Rime at telephony 8 kHz repeatedly under-runs realtime (`flush audio emitter due to
    slow audio generation`) and produces laggy/flickering speech. Browser test-agent UX
    already prefers Cartesia — telephony must match.
    """
    if audio_channel != "telephony":
        return cfg, provider_voice_id, False
    if (cfg.tts_provider or "").lower() == "cartesia":
        return cfg, provider_voice_id, False

    new_cfg = replace(
        cfg,
        tts_provider="cartesia",
        tts_voice_id=TELEPHONY_CARTESIA_VOICE_ID,
        # Drop Rime-only options so Cartesia gets platform defaults (sonic-3.5 + tokenizer).
        tts_options={},
        voice_id=TELEPHONY_CARTESIA_VOICE_ID,
    )
    return new_cfg, TELEPHONY_CARTESIA_PROVIDER_VOICE_ID, True


def force_groq_for_telephony(
    cfg: "AgentConfig",
    *,
    audio_channel: str,
) -> tuple["AgentConfig", bool]:
    """Remap Gemini → Groq on English PSTN so turn replies stay near the ≤800ms budget.

    Measured on this workspace (2026-09): Cartesia TTFB ~135–220ms is fine; Gemini 3.6 Flash
    TTFT is ~1.5–3s (sometimes much worse) even with thinking_level=minimal. Groq
    ``openai/gpt-oss-20b`` with ``reasoning_effort=low`` returns speakable content in ~0.5s.
    Urdu agents keep Gemini (Groq is not in ``ur`` capabilities).
    """
    if audio_channel != "telephony":
        return cfg, False
    lang = (cfg.agent_language or "ur").lower()
    if lang.startswith("ur"):
        return cfg, False
    if (cfg.llm_provider or "").lower() == "groq":
        return cfg, False
    if (cfg.llm_provider or "").lower() != "gemini":
        return cfg, False
    if not (os.getenv("GROQ_API_KEY") or "").strip():
        return cfg, False

    return (
        replace(
            cfg,
            llm_provider="groq",
            llm_model=TELEPHONY_GROQ_MODEL,
            llm_options={},
        ),
        True,
    )
