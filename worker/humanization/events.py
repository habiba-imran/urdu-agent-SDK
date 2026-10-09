"""Controlled, replayable state transitions for Phase 2."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from .state import ConversationState, GenerationState, GroundedValue, ToolCallState

EventKind = Literal[
    "user_turn_committed", "assistant_turn_completed", "ground_value", "ground_superseded",
    "repair_pending", "tool_started", "tool_finished", "generation_started",
    "generation_finished", "session_closed", "ground_unresolved", "tool_result",
]
_GROUND_RANK = {"unresolved": 0, "inferred": 1, "heard": 2, "confirmed": 3}
_TOOL_TERMINAL = {"completed", "error", "timeout", "outcome_unknown"}
_GEN_TERMINAL = {"completed", "cancelled", "error"}


@dataclass(frozen=True)
class StateEvent:
    event_id: str
    sequence: int
    kind: EventKind
    turn_id: str | None = None
    generation_id: str | None = None
    tool_call_id: str | None = None
    field_name: str | None = None
    observation_id: str | None = None
    value: str | None = None
    status: str | None = None
    outcome: str | None = None
    business_effect: str | None = None
    result_data: dict | None = None
    request_identity: int | None = None


def reduce_state(state: ConversationState, event: StateEvent) -> ConversationState:
    """Return a new state. Terminal IDs are tombstones for late starts/completions."""
    if event.sequence < 0 or event.event_id in state.seen_event_ids:
        return state
    new = deepcopy(state)
    new.seen_event_ids.append(event.event_id)
    kind = event.kind
    if kind == "user_turn_committed" and event.turn_id:
        if event.turn_id not in new.interaction_state.committed_turn_ids:
            new.interaction_state.committed_turn_ids.append(event.turn_id)
    elif kind == "assistant_turn_completed" and event.turn_id:
        if event.turn_id not in new.recent_behavior_state.assistant_turn_ids:
            new.recent_behavior_state.assistant_turn_ids.append(event.turn_id)
            new.recent_behavior_state.assistant_turn_ids = new.recent_behavior_state.assistant_turn_ids[-8:]
    elif kind == "ground_value" and event.field_name and event.observation_id and event.value is not None:
        if event.status not in _GROUND_RANK:
            raise ValueError("invalid grounding status")
        values = new.task_state.critical_values.setdefault(event.field_name, [])
        same = next((v for v in values if v.observation_id == event.observation_id), None)
        if same:
            if event.sequence >= same.sequence and same.status != "superseded" and _GROUND_RANK[event.status] > _GROUND_RANK[same.status]:
                same.status = event.status
                same.sequence = event.sequence
            return new
        current = next((v for v in reversed(values) if v.status not in {"superseded", "unresolved"}), None)
        if current and (event.sequence <= current.sequence or _GROUND_RANK[current.status] > _GROUND_RANK[event.status]):
            if current.value == event.value and event.status in {"heard", "confirmed"} and event.sequence > current.sequence:
                if event.field_name in new.grounding_state.unresolved_fields:
                    new.grounding_state.unresolved_fields.remove(event.field_name)
            return new
        if current:
            current.status = "superseded"
        values.append(GroundedValue(event.observation_id, event.value, event.status, event.turn_id, event.sequence))
        if event.field_name in new.grounding_state.unresolved_fields:
            new.grounding_state.unresolved_fields.remove(event.field_name)
    elif kind == "ground_superseded" and event.field_name and event.observation_id:
        for value in new.task_state.critical_values.get(event.field_name, []):
            if value.observation_id == event.observation_id and event.sequence >= value.sequence:
                value.status = "superseded"
                value.sequence = event.sequence
                if event.field_name not in new.grounding_state.unresolved_fields:
                    new.grounding_state.unresolved_fields.append(event.field_name)
                break
    elif kind == "ground_unresolved" and event.field_name:
        if event.field_name not in new.grounding_state.unresolved_fields:
            new.grounding_state.unresolved_fields.append(event.field_name)
        new.repair_state.pending_field = event.field_name
    elif kind == "tool_result" and event.tool_call_id:
        call = new.tool_state.calls.setdefault(event.tool_call_id, ToolCallState("running", event.sequence))
        call.status = {"SUCCESS": "completed", "NO_RESULT": "completed",
                       "OUTCOME_UNKNOWN": "outcome_unknown", "DEPENDENCY_TIMEOUT": "timeout"}.get(event.outcome, "error")
        call.sequence = event.sequence
        call.outcome = event.outcome
        call.business_effect = event.business_effect or "none"
        call.result_data = deepcopy(event.result_data)
        call.request_identity = event.request_identity
    elif kind == "repair_pending":
        new.repair_state.pending_field = event.field_name
    elif kind == "tool_started" and event.tool_call_id:
        old = new.tool_state.calls.get(event.tool_call_id)
        if old is None:
            new.tool_state.calls[event.tool_call_id] = ToolCallState("running", event.sequence)
    elif kind == "tool_finished" and event.tool_call_id:
        if event.status not in _TOOL_TERMINAL:
            raise ValueError("invalid tool outcome")
        old = new.tool_state.calls.get(event.tool_call_id)
        if old is None or (old.status == "running" and event.sequence >= old.sequence):
            if old is None:
                new.tool_state.calls[event.tool_call_id] = ToolCallState(event.status, event.sequence, event.status)
            else:
                old.status, old.sequence = event.status, event.sequence
                old.outcome = old.outcome or event.status
    elif kind == "generation_started" and event.generation_id:
        old = new.speech_state.generations.get(event.generation_id)
        if old is None:
            new.speech_state.generations[event.generation_id] = GenerationState("active", event.sequence)
            new.speech_state.active_generation_id = event.generation_id
    elif kind == "generation_finished" and event.generation_id:
        if event.status not in _GEN_TERMINAL:
            raise ValueError("invalid generation outcome")
        old = new.speech_state.generations.get(event.generation_id)
        if old is None or (old.status == "active" and event.sequence >= old.sequence):
            new.speech_state.generations[event.generation_id] = GenerationState(event.status, event.sequence)
            if new.speech_state.active_generation_id == event.generation_id:
                new.speech_state.active_generation_id = None
    elif kind == "session_closed":
        new.session_closed = True
        # A committed write/tool outcome may arrive after close; tool events remain accepted.
    return new
