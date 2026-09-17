"""Humanization profiles — composed after telephony remaps.

Call order (do not reorder):
  1. load AgentConfig from DB
  2. apply telephony remaps (``resolve_effective_providers``)
  3. build SpokenOutputProfile / TTSHumanizationProfile / TurnProfile from *effective* providers
  4. construct STT/LLM/TTS + AgentSession

Phase 0: resolver + dataclass stubs.
Phase 1: SpokenOutputProfile composition (universal + LLM overlay + TTS overlay).
Later phases fill TurnProfile and TTSHumanizationProfile beyond stubs.
"""

from __future__ import annotations

from .history import (
    apply_history_hygiene,
    plain_text_for_history,
    resolve_chat_history_max_items,
    system_instructions_static_prefix_ok,
)
from .resolve import EffectiveProviders, resolve_effective_providers
from .spoken import (
    GEMINI_LLM_OVERLAY,
    GROQ_LLM_OVERLAY,
    UNIVERSAL_SPOKEN_RULES,
    URDU_SPOKEN_OUTPUT_RULES,
    build_spoken_output_profile,
    compose_system_instructions,
    language_overlay_for,
    llm_overlay_for,
    tts_overlay_for,
)
from .turn import (
    TURN_AB_LISTEN_LOG_FIELDS,
    build_turn_profile,
    materialize_turn_detection,
    resolve_deepgram_endpointing_ms,
    resolve_deepgram_flux_eager_threshold,
    resolve_deepgram_stt_mode,
    resolve_turn_detector_version,
    turn_profile_to_livekit_options,
)
from .types import SpokenOutputProfile, TTSHumanizationProfile, TurnProfile

__all__ = [
    "EffectiveProviders",
    "GEMINI_LLM_OVERLAY",
    "GROQ_LLM_OVERLAY",
    "SpokenOutputProfile",
    "TTSHumanizationProfile",
    "TURN_AB_LISTEN_LOG_FIELDS",
    "TurnProfile",
    "UNIVERSAL_SPOKEN_RULES",
    "URDU_SPOKEN_OUTPUT_RULES",
    "apply_history_hygiene",
    "build_spoken_output_profile",
    "build_turn_profile",
    "compose_system_instructions",
    "language_overlay_for",
    "llm_overlay_for",
    "materialize_turn_detection",
    "plain_text_for_history",
    "resolve_chat_history_max_items",
    "resolve_deepgram_endpointing_ms",
    "resolve_deepgram_flux_eager_threshold",
    "resolve_deepgram_stt_mode",
    "resolve_effective_providers",
    "resolve_turn_detector_version",
    "system_instructions_static_prefix_ok",
    "tts_overlay_for",
    "turn_profile_to_livekit_options",
]
