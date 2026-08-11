"""Shared types for the provider registry (docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md
Phase 2, ADR-036).

No livekit import here — this module must stay import-safe without any provider plugin installed,
matching the lazy-import discipline worker/factories.py already established.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRuntimeConfig:
    """The resolved, per-session config the registry dispatches on. `tts_voice_id` is expected to
    already be resolved (tts_voice_id or voice_id fallback — see worker/main.py::build_session,
    and 0016's own comment on why a fresh row can have tts_voice_id NULL) by the time this is
    constructed; the registry and adapters trust it's populated.
    """

    agent_language: str
    stt_provider: str
    stt_model: str
    stt_options: dict
    llm_provider: str
    llm_model: str
    llm_options: dict
    tts_provider: str
    tts_voice_id: str
    tts_options: dict


@dataclass(frozen=True)
class ProviderComponents:
    """STT/LLM/TTS instances ready to pass into AgentSession(...). Left as `Any` (not the real
    livekit types) so importing this module never requires livekit.agents to be installed."""

    stt: Any
    llm: Any
    tts: Any
