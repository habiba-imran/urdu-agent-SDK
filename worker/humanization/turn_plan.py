"""Provider-neutral, deterministic TurnPlan. Phase 3 uses it in shadow only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .state import ConversationState

DialogueAct = Literal["ANSWER", "CLARIFY", "REPAIR_CONFIRM", "CONFIRM_WRITE", "TOOL_WAIT"]
ResponseBudget = Literal["MICRO", "SHORT", "STANDARD"]
ToolPolicy = Literal["none", "wait", "propose_only", "confirmation_required", "gate_only"]


@dataclass(frozen=True)
class TurnSignals:
    """Trusted semantic inputs; Phase 4 may populate speech-derived fields later."""

    user_correction: bool = False
    critical_uncertainty: bool = False
    complaint_or_frustration: bool = False
    simple_factual_answer: bool = False
    tool_wait: bool = False
    write_phase: Literal["none", "proposed", "caller_confirmed"] = "none"


@dataclass(frozen=True)
class TurnPlan:
    dialogue_act: DialogueAct
    response_budget: ResponseBudget
    language_style: str
    certainty: Literal["unknown", "uncertain", "confirmed"]
    clarification_target: str | None
    empathy_level: Literal["neutral", "acknowledge", "supportive"]
    humor_permission: Literal["forbidden", "reactive_only"]
    laughter_permission: Literal["forbidden", "reactive_only"]
    filler_permission: Literal["forbidden", "brief_allowed"]
    question_policy: Literal["none", "one_clarifying", "confirm_action", "optional_follow_up"]
    tool_policy: ToolPolicy
    interruption_context: Literal["neutral", "repair", "critical", "tool_wait"]
    reason_codes: tuple[str, ...]


def language_style_for(configured_language: str) -> str:
    language = (configured_language or "").strip().lower()
    from .delivery.renderers import LanguageProfile
    # Resolve the mixed dialect before the broad Urdu prefix.
    if LanguageProfile(language).locale == "ur_pk_mixed":
        return "mixed"
    if language.startswith("ur"):
        return "ur_pk"
    if language.startswith("en"):
        return "en"
    return "unspecified"


def derive_turn_plan(state: ConversationState, signals: TurnSignals | None = None) -> TurnPlan:
    """No text classifier, provider option, network call, or write authority."""
    signals = signals or TurnSignals()
    unresolved = sorted(set(state.grounding_state.unresolved_fields))
    uncertain = signals.critical_uncertainty or bool(unresolved)
    correction = signals.user_correction or bool(state.repair_state.pending_field)
    waiting = signals.tool_wait or any(call.status == "running" for call in state.tool_state.calls.values())
    confirmed = any(
        value.status == "confirmed"
        for values in state.task_state.critical_values.values()
        for value in values
    )
    certainty = "uncertain" if uncertain else "confirmed" if confirmed else "unknown"
    target = unresolved[0] if unresolved else state.repair_state.pending_field
    reasons: list[str] = []

    # Safety precedence: unresolved/corrected entities suspend any write suggestion.
    if uncertain:
        act, budget, question, tool, interruption = "CLARIFY", "MICRO", "one_clarifying", "none", "critical"
        reasons.append("critical_uncertainty")
    elif correction:
        act, budget, question, tool, interruption = "REPAIR_CONFIRM", "SHORT", "one_clarifying", "none", "repair"
        reasons.append("user_correction")
    elif signals.write_phase == "proposed":
        act, budget, question, tool, interruption = "CONFIRM_WRITE", "SHORT", "confirm_action", "confirmation_required", "critical"
        reasons.append("write_proposal_pending")
    elif signals.write_phase == "caller_confirmed":
        act, budget, question, tool, interruption = "CONFIRM_WRITE", "MICRO", "none", "gate_only", "critical"
        reasons.append("caller_confirmation_observed")
    elif waiting:
        act, budget, question, tool, interruption = "TOOL_WAIT", "MICRO", "none", "wait", "tool_wait"
        reasons.append("tool_running")
    elif signals.simple_factual_answer:
        act, budget, question, tool, interruption = "ANSWER", "MICRO", "optional_follow_up", "none", "neutral"
        reasons.append("simple_factual_answer")
    else:
        act, budget, question, tool, interruption = "ANSWER", "SHORT", "optional_follow_up", "none", "neutral"
        reasons.append("default_answer")

    complaint = signals.complaint_or_frustration
    if complaint:
        reasons.append("complaint_or_frustration")
    sensitive = complaint or uncertain or correction or signals.write_phase != "none"
    return TurnPlan(
        dialogue_act=act, response_budget=budget,
        language_style=language_style_for(state.language_state.configured_language),
        certainty=certainty, clarification_target=target if act in {"CLARIFY", "REPAIR_CONFIRM"} else None,
        empathy_level="supportive" if complaint else "acknowledge" if correction else "neutral",
        humor_permission="forbidden" if sensitive else "reactive_only",
        laughter_permission="forbidden" if sensitive else "reactive_only",
        filler_permission="forbidden" if sensitive or waiting else "brief_allowed",
        question_policy=question, tool_policy=tool, interruption_context=interruption,
        reason_codes=tuple(reasons),
    )


def signals_from_write_gate(write_gate: object | None) -> TurnSignals:
    """Read only the existing gate's pending/affirmative flags, never its arguments."""
    if write_gate is None or getattr(write_gate, "pending_write", None) is None:
        return TurnSignals()
    return TurnSignals(
        write_phase="caller_confirmed" if bool(getattr(write_gate, "heard_affirmative", False)) else "proposed"
    )
