"""Provider-neutral TurnPlan; bounded conversational activation and mandatory identity/exit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .state import ConversationState

DialogueAct = Literal["ANSWER", "CLARIFY", "REPAIR_CONFIRM", "CONFIRM_WRITE", "TOOL_WAIT", "CLOSE", "IDENTIFY_AI", "ACKNOWLEDGE", "STOP"]
ResponseBudget = Literal["MICRO", "SHORT", "STANDARD"]
ToolPolicy = Literal["none", "wait", "propose_only", "confirmation_required", "gate_only"]


@dataclass(frozen=True)
class TurnSignals:
    """Trusted semantic inputs; Phase 4 may populate speech-derived fields later."""

    closing_intent: bool = False
    ai_identity_question: bool = False
    user_correction: bool = False
    critical_uncertainty: bool = False
    complaint_or_frustration: bool = False
    simple_factual_answer: bool = False
    tool_wait: bool = False
    conversational: bool = False
    acknowledgement: bool = False
    stop_intent: bool = False
    confusion: bool = False
    excitement: bool = False
    hesitation: bool = False
    critical_capture: bool = False
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

    # Closing/identity never authorize a business write, even with pending values.
    if signals.closing_intent:
        act, budget, question, tool, interruption = "CLOSE", "MICRO", "none", "none", "neutral"
        reasons.append("explicit_farewell")
    elif signals.ai_identity_question:
        act, budget, question, tool, interruption = "IDENTIFY_AI", "MICRO", "none", "none", "neutral"
        reasons.append("direct_ai_identity_question")
    elif signals.stop_intent:
        act, budget, question, tool, interruption = "STOP", "MICRO", "none", "none", "neutral"
        reasons.append("explicit_stop")
    elif uncertain:
        act, budget, question, tool, interruption = "CLARIFY", "MICRO", "one_clarifying", "none", "critical"
        reasons.append("critical_uncertainty")
    elif correction:
        act, budget, question, tool, interruption = "REPAIR_CONFIRM", "SHORT", "one_clarifying", "none", "repair"
        if signals.conversational and target is None and not signals.critical_capture:
            question = "none"
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
    elif signals.acknowledgement:
        act, budget, question, tool, interruption = "ACKNOWLEDGE", "MICRO", "none", "none", "neutral"
        reasons.append("short_acknowledgement")
    elif signals.simple_factual_answer:
        act, budget, question, tool, interruption = "ANSWER", "MICRO", "optional_follow_up", "none", "neutral"
        reasons.append("simple_factual_answer")
    else:
        act, budget, question, tool, interruption = "ANSWER", "SHORT", "optional_follow_up", "none", "neutral"
        reasons.append("default_answer")

    if signals.conversational and act == "ANSWER":
        question = "none"
    for present, reason in ((signals.confusion, "caller_confused"),
                            (signals.excitement, "caller_excited"),
                            (signals.hesitation, "caller_hesitating"),
                            (signals.critical_capture, "critical_capture")):
        if present:
            reasons.append(reason)
    complaint = signals.complaint_or_frustration
    if complaint:
        reasons.append("complaint_or_frustration")
    sensitive = complaint or uncertain or correction or signals.write_phase != "none" or signals.closing_intent or signals.ai_identity_question
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


def conversational_signals(text: str) -> TurnSignals:
    """Conservative whole-utterance exits; a mentioned farewell is not an exit."""
    import re
    import unicodedata
    value = unicodedata.normalize("NFKC", text).casefold().replace("’", "'")
    value = re.sub(r"[.!?,،؟؛۔。\s]+", " ", value).strip()
    farewell = (
        r"(?:(?:no|okay|ok|thanks|thank you|that's all|that is all|all right) )*"
        r"(?:bye|bye bye|goodbye|good bye|see you|take care)"
        r"(?: (?:thanks|thank you|take care|have a good day))*"
    )
    urdu = (
        r"(?:(?:نہیں|جی|شکریہ|بس|بس یہی|بس اتنا ہی|بس یہی تھا|ٹھیک ہے|آپ کا شکریہ) )*"
        r"(?:خدا حافظ|خداحافظ|اللہ حافظ|اللہحافظ|بائے|پھر ملیں گے)"
        r"(?: (?:شکریہ|آپ کا شکریہ))*"
    )
    roman = (
        r"(?:(?:nahi|nahin|jee|ji|shukriya|bas|bas itna hi|theek hai) )*"
        r"(?:allah hafiz|khuda hafiz|allah hafez|khuda hafez)"
        r"(?: shukriya)?"
    )
    closing = any(re.fullmatch(pattern, value) for pattern in (farewell, urdu, roman))
    identity = bool(re.search(
        r"\b(?:are you (?:an? )?(?:ai|robot|bot|human|real person)|"
        r"are you (?:an? )?(?:ai|virtual|automated) (?:assistant|agent)|"
        r"is this (?:an? )?(?:ai|bot)|are you (?:a )?human or (?:an? )?ai)\b"
        r"|(?:کیا آپ|آپ کیا|آپ) (?:ایک )?(?:اے آئی|اے آئی|AI|انسان|روبوٹ|بوٹ)"
        r"|\b(?:kya (?:aap|ap|tum) (?:ek )?(?:ai|insaan|robot|bot))\b",
        value, re.I,
    ))
    # Explicit lexical cues only; no inference from a bare "no" or question mark.
    concern = bool(re.search(
        r"\b(?:i(?:'m| am) (?:worried|concerned|frustrated|upset)|this is frustrating|"
        r"i(?:'ve| have) (?:already|been) (?:called|calling)|still not working)\b"
        r"|\u0645\u062c\u06be\u06d2 (?:\u0641\u06a9\u0631|\u067e\u0631\u06cc\u0634\u0627\u0646\u06cc)"
        r"|\b(?:mujhe fikr|main pareshan|mein pareshan)\b", value))
    confusion = bool(re.search(
        r"\b(?:i (?:don't|do not) understand|i(?:'m| am) confused|what do you mean|not sure)\b"
        r"|\u0633\u0645\u062c\u06be \u0646\u06c1\u06cc\u06ba|\b(?:samajh nahi|samajh nahin)\b", value))
    acknowledgement = bool(re.fullmatch(
        r"(?:okay|ok|got it|understood|thanks|thank you|\u062c\u06cc|\u0634\u06a9\u0631\u06cc\u06c1|"
        r"\u0679\u06be\u06cc\u06a9 \u06c1\u06d2|shukriya|theek hai)", value))
    stop = bool(re.fullmatch(
        r"(?:wait|stop|wait stop|hold on|please stop|stop please|\u0631\u06a9 \u062c\u0627\u0626\u06cc\u06ba|"
        r"\u0627\u06cc\u06a9 \u0644\u0645\u062d\u06c1|ruk jaiye|ruko|ek lamha)", value))
    excited = bool(re.search(r"\b(?:that's great|that is great|i(?:'m| am) excited|wonderful news)\b|\u0628\u06c1\u062a \u0627\u0686\u06be\u0627", value))
    hesitation = bool(re.search(r"\b(?:um|uh|let me think)\b|\u0627\u06cc\u06a9 \u0645\u0646\u0679", value))
    return TurnSignals(closing_intent=closing, ai_identity_question=identity,
                       conversational=True, complaint_or_frustration=concern,
                       user_correction=bool(re.search(r"^(?:actually|sorry|no)\b.*\b(?:meant|instead)|\bi meant\b", value)),
                       confusion=confusion, acknowledgement=acknowledgement,
                       stop_intent=stop, excitement=excited, hesitation=hesitation)


def conversational_response(act: str, language: str) -> str:
    urdu = language_style_for(language) in {"ur_pk", "mixed"}
    if act == "STOP":
        return "\u062c\u06cc\u06d4" if urdu else "Okay."
    if act == "CLOSE":
        return "شکریہ، خدا حافظ۔" if urdu else "Thank you for calling. Goodbye!"
    return "میں ایک اے آئی اسسٹنٹ ہوں۔" if urdu else "I'm an AI assistant."
