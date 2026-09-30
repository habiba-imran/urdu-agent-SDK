"""Telephony helpers — historically remapped TTS/LLM on PSTN.

Configured providers now always stick: session runtime uses the agent row as-is.
These helpers remain as no-ops so call sites / EffectiveProviders flags stay stable.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worker.config import AgentConfig

# Kept for tests / telephony defaults documentation (no longer forced at runtime).
TELEPHONY_CARTESIA_VOICE_ID = "cartesia-katie-friendly-fixer"
TELEPHONY_CARTESIA_PROVIDER_VOICE_ID = "f786b574-daa5-4673-aa0c-cbe3e8534c02"

TELEPHONY_GROQ_MODEL = os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-20b")
if TELEPHONY_GROQ_MODEL in (
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "qwen/qwen3.6-27b",
    "qwen/qwen3-32b",
    "qwen/qwen3.8-27b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "moonshotai/kimi-k2-instruct-0905",
):
    TELEPHONY_GROQ_MODEL = "openai/gpt-oss-20b"


def force_cartesia_for_telephony(
    cfg: "AgentConfig",
    provider_voice_id: str | None,
    *,
    audio_channel: str,
) -> tuple["AgentConfig", str | None, bool]:
    """No-op: configured TTS provider always sticks (including Rime on PSTN)."""
    del audio_channel  # retained for call-site compatibility
    return cfg, provider_voice_id, False


def force_groq_for_telephony(
    cfg: "AgentConfig",
    *,
    audio_channel: str,
) -> tuple["AgentConfig", bool]:
    """No-op: configured LLM provider always sticks on PSTN."""
    del audio_channel
    return cfg, False


def force_groq_for_english_webrtc(
    cfg: "AgentConfig",
    *,
    audio_channel: str,
) -> tuple["AgentConfig", bool]:
    """No-op: configured LLM provider always sticks on English WebRTC.

    ``UVA_FORCE_GROQ_ENGLISH`` is ignored (deprecated); provision ``llm_provider=groq``
    explicitly when Groq is desired.
    """
    del audio_channel
    return cfg, False
