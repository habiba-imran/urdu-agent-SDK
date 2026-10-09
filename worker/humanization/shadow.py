"""Phase 3 shadow observer: deterministic plan, no model-context mutation."""

from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Any

from .context_projection import ContextProjection, project_context
from .state import ConversationState
from .turn_plan import TurnPlan, TurnSignals, derive_turn_plan, signals_from_write_gate

_LOG = logging.getLogger(__name__)
_WORD_RE = re.compile(r"\S+")


@dataclass(frozen=True)
class ShadowTrace:
    plan: TurnPlan
    projection: ContextProjection
    signal_sources: tuple[str, ...]
    actual_word_count: int | None = None
    actual_has_question: bool | None = None
    budget_match: bool | None = None

    def log_fields(self) -> dict[str, object]:
        # Never log values, caller text, IDs, or the projected context body.
        return {
            "act": self.plan.dialogue_act,
            "budget": self.plan.response_budget,
            "certainty": self.plan.certainty,
            "language": self.plan.language_style,
            "tool_policy": self.plan.tool_policy,
            "question_policy": self.plan.question_policy,
            "reasons": self.plan.reason_codes,
            "confirmed_fact_count": len(self.projection.confirmed_facts),
            "business_fact_count": len(self.projection.business_facts),
            "unresolved_count": len(self.projection.unresolved_fields),
            "omitted_fact_count": self.projection.omitted_confirmed_facts,
            "omitted_business_fact_count": self.projection.omitted_business_facts,
            "signal_sources": self.signal_sources,
            "actual_word_count": self.actual_word_count,
            "actual_has_question": self.actual_has_question,
            "budget_match": self.budget_match,
        }


class ShadowObserver:
    """Bounded session-local traces; no authority over tools or output."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.traces: deque[ShadowTrace] = deque(maxlen=32)
        self._pending_index: int | None = None
        self.business_facts: tuple[tuple[str, str], ...] = ()

    def observe_turn(
        self, state: ConversationState, *, write_gate: object | None = None,
        signals: TurnSignals | None = None,
    ) -> ShadowTrace:
        if signals is None:
            signals = signals_from_write_gate(write_gate)
            sources = ("write_gate",) if signals.write_phase != "none" else ("state_only",)
        else:
            sources = ("explicit_trusted_signals",)
        plan = derive_turn_plan(state, signals)
        projection = project_context(state, plan, business_facts=self.business_facts)
        trace = ShadowTrace(plan, projection, sources)
        with self._lock:
            self.traces.append(trace)
            self._pending_index = len(self.traces) - 1
        _LOG.info("humanization_shadow_plan %s", trace.log_fields())
        return trace

    def observe_assistant(self, item: Any) -> ShadowTrace | None:
        """Compare committed output structurally; never store or log its text."""
        content = getattr(item, "text_content", None)
        if not isinstance(content, str):
            return None
        with self._lock:
            index = self._pending_index
            self._pending_index = None
            if index is None or index >= len(self.traces):
                return None
            original = self.traces[index]
            words = len(_WORD_RE.findall(content))
            limits = {"MICRO": 18, "SHORT": 40, "STANDARD": 80}
            trace = ShadowTrace(
                original.plan, original.projection, original.signal_sources,
                words, "?" in content or "؟" in content,
                words <= limits[original.plan.response_budget],
            )
            self.traces[index] = trace
        _LOG.info("humanization_shadow_actual %s", trace.log_fields())
        return trace
