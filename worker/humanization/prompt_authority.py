"""Phase 3 prompt-stack contract audit; no change to active instructions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

AUTHORITY_ORDER = (
    "platform_safety_and_business_invariants",
    "current_turn_plan",
    "language_profile",
    "tenant_persona_data",
    "provider_renderer",
)
TTS_LLM_DELIVERY_DEFERRED_TO_PHASE6 = (
    "cartesia_manual_ssml", "elevenlabs_audio_tags", "rime_delivery",
    "fish_delivery", "uplift_delivery",
)


@dataclass(frozen=True)
class PromptAudit:
    authority_order: tuple[str, ...]
    active_layer_order: tuple[str, ...]
    response_length_conflict: bool
    turn_plan_in_active_prompt: bool
    persona_same_role_as_platform: bool
    tts_delivery_deferred_to_phase6: tuple[str, ...]


def audit_prompt_stack(
    cfg: Any, system_instructions: str, persona_message: str, *,
    platform_role: str = "system", persona_role: str = "system",
) -> PromptAudit:
    """Describe the assembled prompt, including known blockers to activation."""
    from worker.cartesia_spoken_output import SYSTEM_INSTRUCTIONS_BASE, CLIENT_TOOLS_DISCIPLINE
    from worker.humanization.spoken import (
        UNIVERSAL_SPOKEN_RULES, language_overlay_for, llm_overlay_for, tts_overlay_for,
    )
    from worker.main import _PERSONA_FRAME, _language_directive
    from worker.tools import resolve_tools_base_url

    layers = [("platform_base", SYSTEM_INSTRUCTIONS_BASE)]
    if resolve_tools_base_url(cfg.tools_base_url):
        layers.append(("client_tools", CLIENT_TOOLS_DISCIPLINE))
    layers.extend((
        ("universal_spoken", UNIVERSAL_SPOKEN_RULES),
        ("llm_overlay", llm_overlay_for(cfg.llm_provider, cfg)),
        ("language_overlay", language_overlay_for(cfg.agent_language)),
        ("tts_overlay", tts_overlay_for(cfg)),
        ("language_directive", _language_directive(cfg.agent_language)),
    ))
    positions = [(name, system_instructions.find(part)) for name, part in layers if part]
    if any(index < 0 for _, index in positions) or [index for _, index in positions] != sorted(index for _, index in positions):
        raise ValueError("active prompt layers do not match expected order")
    if not persona_message.startswith(_PERSONA_FRAME):
        raise ValueError("tenant persona is not framed as DATA")
    return PromptAudit(
        AUTHORITY_ORDER,
        tuple(name for name, _ in positions) + ("tenant_persona_data",),
        "two or three short sentences" in SYSTEM_INSTRUCTIONS_BASE
        and "One or two short spoken sentences" in UNIVERSAL_SPOKEN_RULES,
        "Awaaz turn policy:" in system_instructions,
        persona_role == platform_role,
        TTS_LLM_DELIVERY_DEFERRED_TO_PHASE6,
    )
