"""Small trusted semantic delivery vocabulary, independent of vendor syntax."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..turn_plan import TurnPlan


@dataclass(frozen=True)
class PauseIntent:
    offset: int
    milliseconds: int = 250


@dataclass(frozen=True)
class DeliveryIntent:
    affect: Literal["neutral", "warm", "reassuring", "concerned", "upbeat", "amused"] = "neutral"
    intensity: Literal["low", "medium", "high"] = "low"
    pace: Literal["slower", "normal", "slightly_fast"] = "normal"
    energy: Literal["low", "medium", "high"] = "medium"
    emphasis: tuple[tuple[int, int], ...] = ()
    pauses: tuple[PauseIntent, ...] = ()
    nonverbal: Literal["none", "soft_laugh"] = "none"
    continuity_identity: str | None = None
    speech_mode: Literal["normal", "greeting", "repair", "confirmation", "tool_wait"] = "normal"
    interruptible: bool = True


def delivery_from_turn_plan(plan: TurnPlan | None, *, continuity_identity: str | None = None) -> DeliveryIntent:
    """TurnPlan controls safety/social policy; never infer laughter from model text."""
    if plan is None:
        return DeliveryIntent(affect="warm", continuity_identity=continuity_identity)
    mode = {
        "CLARIFY": "repair", "REPAIR_CONFIRM": "repair",
        "CONFIRM_WRITE": "confirmation", "TOOL_WAIT": "tool_wait",
    }.get(plan.dialogue_act, "normal")
    if "critical_capture" in plan.reason_codes and mode == "normal":
        mode = "confirmation"
    careful = mode in {"repair", "confirmation"}
    supportive = plan.empathy_level == "supportive"
    confused = "caller_confused" in plan.reason_codes
    precise = plan.interruption_context == "critical"
    return DeliveryIntent(
        affect="reassuring" if supportive else "neutral" if mode == "confirmation" else "concerned" if careful else
               "upbeat" if "caller_excited" in plan.reason_codes else "warm",
        pace="slower" if careful or supportive or confused or precise else "normal",
        energy="low" if supportive else "medium",
        speech_mode=mode, continuity_identity=continuity_identity,
    )


def constrain_delivery(intent: DeliveryIntent, plan: TurnPlan | None) -> DeliveryIntent:
    """Optional caller-supplied intent cannot bypass trusted TurnPlan."""
    from dataclasses import replace
    sensitive = intent.speech_mode in {"repair", "confirmation", "tool_wait"}
    forbid = sensitive or plan is None or plan.laughter_permission == "forbidden"
    humor_forbidden = sensitive or plan is None or plan.humor_permission == "forbidden"
    return replace(
        intent,
        affect="warm" if intent.affect == "amused" and humor_forbidden else intent.affect,
        nonverbal="none" if forbid else intent.nonverbal,
    )
