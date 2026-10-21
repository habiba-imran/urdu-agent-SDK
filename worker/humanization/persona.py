"""Validated, provider-neutral persona settings stored in llm_options.humanization.

Only bounded enums become trusted guidance. Tenant prose remains descriptive DATA.
No provider credentials, model parameters or business authority live in this profile.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from worker.providers.humanization import validate_profile


@dataclass(frozen=True)
class PersonaProfile:
    enabled: bool = False
    warmth: str = "warm"
    formality: str = "balanced"
    energy: str = "balanced"
    pace: str = "normal"
    expressiveness: str = "subtle"
    adaptive_pace: bool = True

    def guidance(self) -> str:
        return (
            "PERSONA DELIVERY - persona_v1. Keep the tenant's descriptive character and role "
            "consistent across greetings, answers, tool acknowledgements and closing. "
            f"Warmth={self.warmth}; formality={self.formality}; energy={self.energy}; "
            f"pace={self.pace}; expressiveness={self.expressiveness}. "
            "Warm means friendly and attentive; reserved means courteous and restrained. "
            "Casual uses relaxed contractions; formal uses respectful complete phrasing without jargon. "
            "Calm energy is measured; lively energy is lightly animated, never loud or theatrical. "
            "Use natural sentence rhythm and meaningful punctuation. Let genuine questions sound "
            "inquisitive and explanations settle naturally. Subtle expression uses small changes; "
            "balanced expression allows a little more variety when the content warrants it. "
            "Acknowledge concern briefly and soften your tone; accept corrections without defensiveness. "
            "Maintain that considerate tone while the issue is being resolved. Do not rotate emotions "
            "or add fillers, laughter, sighs, stage directions or artificial hesitations to sound human. "
            "Never change literal facts, claim human identity, or override disclosure and tool rules. "
            "Use only plain spoken text; audio rendering owns provider controls."
        )

    def wire(self) -> dict:
        result = asdict(self)
        result["adaptivePace"] = result.pop("adaptive_pace")
        return result


def profile_from_options(options: dict | None) -> PersonaProfile | None:
    if not options or "humanization" not in options:
        return None
    value = validate_profile(options["humanization"])
    if "adaptivePace" in value:
        value["adaptive_pace"] = value.pop("adaptivePace")
    return PersonaProfile(**value)


def policy_for_agent(cfg):
    from .policy import resolve_humanization_policy
    profile = profile_from_options(getattr(cfg, "llm_options", None))
    requested = None if profile is None else "conversational_v1" if profile.enabled else "baseline"
    return resolve_humanization_policy(requested)


def personalize(intent, profile: PersonaProfile | None, plan=None):
    if profile is None or not profile.enabled:
        return intent
    if not intent.interruptible:  # recording disclosure retains neutral platform delivery
        return intent
    careful = intent.speech_mode in {"repair", "confirmation", "tool_wait"} or (
        plan is not None and (plan.empathy_level == "supportive" or "caller_confused" in plan.reason_codes)
    )
    affect = intent.affect
    if affect == "warm" and profile.warmth != "warm":
        affect = "neutral"
    pace = intent.pace if careful and profile.adaptive_pace else profile.pace
    return replace(intent, affect=affect, pace=pace,
                   energy=intent.energy if careful else {"calm": "low", "balanced": "medium", "lively": "high"}[profile.energy],
                   intensity="low" if careful or profile.expressiveness == "subtle" else "medium",
                   adaptive_pace=profile.adaptive_pace)


def clause_intent(intent, text: str, profile: PersonaProfile | None):
    """Vary only on actual linguistic evidence, never random chunk position."""
    if profile and profile.enabled and intent.affect in {"warm", "neutral", "upbeat"} and intent.speech_mode == "normal":
        if text.rstrip().endswith(("?", "\u061f")):
            return replace(intent, affect="curious")
    return intent
