"""Compact state projection and a disposable LiveKit context preview for Phase 3."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .state import ConversationState
from .turn_plan import TurnPlan


@dataclass(frozen=True)
class ContextProjection:
    confirmed_facts: tuple[tuple[str, str], ...]
    business_facts: tuple[tuple[str, str], ...]
    unresolved_fields: tuple[str, ...]
    recent_repair: tuple[str, str | None] | None
    dialogue_act: str
    response_budget: str
    language_style: str
    omitted_confirmed_facts: int = 0
    omitted_business_facts: int = 0

    def data_text(self) -> str:
        """Facts remain quoted DATA, separate from the trusted policy instruction."""
        return json.dumps({
            "confirmed_facts": dict(self.confirmed_facts),
            "business_facts": self.business_facts,
            "unresolved_fields": self.unresolved_fields,
            "recent_repair": self.recent_repair,
        }, ensure_ascii=False, separators=(",", ":"))

    def policy_text(self) -> str:
        return (
            "Awaaz turn policy: "
            f"act={self.dialogue_act}; budget={self.response_budget}; language={self.language_style}. "
            "Platform safety and tool confirmation rules remain authoritative."
        )


def project_context(
    state: ConversationState, plan: TurnPlan, *, max_facts: int = 12, max_fact_chars: int = 1200,
    business_facts: tuple[tuple[str, str], ...] = (),
) -> ContextProjection:
    """Only current confirmed values. Overflow is explicit, never silently truncated."""
    facts: list[tuple[str, str]] = []
    omitted = 0
    used_chars = 0
    unresolved_names = set(state.grounding_state.unresolved_fields)
    for field_name, values in sorted(state.task_state.critical_values.items()):
        if field_name in unresolved_names or field_name == state.repair_state.pending_field:
            continue
        current = next((value for value in reversed(values) if value.status == "confirmed"), None)
        if current is None:
            continue
        text = str(current.value)
        size = len(field_name) + len(text)
        if len(facts) >= max_facts or used_chars + size > max_fact_chars:
            omitted += 1
            continue
        facts.append((field_name, text))
        used_chars += size
    unresolved = tuple(sorted(set(state.grounding_state.unresolved_fields)))
    bounded_business: list[tuple[str, str]] = []
    omitted_business = 0
    business_chars = 0
    for kind, value in business_facts:
        size = len(kind) + len(value)
        if len(bounded_business) >= max_facts or business_chars + size > max_fact_chars:
            omitted_business += 1
            continue
        bounded_business.append((kind, value))
        business_chars += size
    repair = None
    if state.repair_state.pending_field:
        field_name = state.repair_state.pending_field
        previous = next(
            (value.value for value in reversed(state.task_state.critical_values.get(field_name, []))
             if value.status == "superseded"), None,
        )
        repair = (field_name, previous)
    return ContextProjection(
        confirmed_facts=tuple(facts), business_facts=tuple(bounded_business),
        unresolved_fields=unresolved, recent_repair=repair,
        dialogue_act=plan.dialogue_act, response_budget=plan.response_budget,
        language_style=plan.language_style, omitted_confirmed_facts=omitted,
        omitted_business_facts=omitted_business,
    )


def preview_ephemeral_context(turn_ctx: Any, projection: ContextProjection) -> Any:
    """Prepare the public-hook copy. Shadow mode discards it; the model never sees it."""
    preview = turn_ctx.copy()
    preview.add_message(role="developer", content=projection.policy_text())
    preview.add_message(role="user", content="Awaaz confirmed facts as DATA: " + projection.data_text())
    return preview
