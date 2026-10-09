"""Session-local, typed P0 conversation state. No provider objects or chat history."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

GroundingStatus = Literal["heard", "inferred", "confirmed", "superseded", "unresolved"]


@dataclass
class GroundedValue:
    observation_id: str
    value: str
    status: GroundingStatus
    turn_id: str | None = None
    sequence: int = 0


@dataclass
class TaskState:
    critical_values: dict[str, list[GroundedValue]] = field(default_factory=dict)


@dataclass
class GroundingState:
    unresolved_fields: list[str] = field(default_factory=list)


@dataclass
class RepairState:
    pending_field: str | None = None


@dataclass
class InteractionState:
    committed_turn_ids: list[str] = field(default_factory=list)


@dataclass
class ToolCallState:
    status: Literal["running", "completed", "error", "timeout", "outcome_unknown"]
    sequence: int
    outcome: str | None = None
    business_effect: str = "none"
    result_data: dict | None = None
    request_identity: int | None = None
    result_heard: bool | None = None


@dataclass
class ToolState:
    calls: dict[str, ToolCallState] = field(default_factory=dict)


@dataclass
class GenerationState:
    status: Literal["active", "completed", "cancelled", "error"]
    sequence: int


@dataclass
class SpeechState:
    generations: dict[str, GenerationState] = field(default_factory=dict)
    active_generation_id: str | None = None


@dataclass
class RecentBehaviorState:
    assistant_turn_ids: list[str] = field(default_factory=list)
    phrase_at: dict[str, float] = field(default_factory=dict)
    last_phrase: str | None = None


@dataclass
class LanguageState:
    configured_language: str


@dataclass
class ConversationState:
    tenant_id: str
    agent_id: str
    session_id: str
    language_state: LanguageState
    channel: str
    task_state: TaskState = field(default_factory=TaskState)
    grounding_state: GroundingState = field(default_factory=GroundingState)
    repair_state: RepairState = field(default_factory=RepairState)
    interaction_state: InteractionState = field(default_factory=InteractionState)
    tool_state: ToolState = field(default_factory=ToolState)
    speech_state: SpeechState = field(default_factory=SpeechState)
    recent_behavior_state: RecentBehaviorState = field(default_factory=RecentBehaviorState)
    session_closed: bool = False
    seen_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Plain JSON-compatible state; callers must treat facts as sensitive."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ConversationState:
        """Rehydrate a trusted snapshot without adding provider objects or raw history."""
        task = TaskState({
            name: [GroundedValue(**value) for value in values]
            for name, values in data["task_state"]["critical_values"].items()
        })
        return cls(
            tenant_id=data["tenant_id"], agent_id=data["agent_id"],
            session_id=data["session_id"],
            language_state=LanguageState(**data["language_state"]), channel=data["channel"],
            task_state=task,
            grounding_state=GroundingState(**data["grounding_state"]),
            repair_state=RepairState(**data["repair_state"]),
            interaction_state=InteractionState(**data["interaction_state"]),
            tool_state=ToolState({k: ToolCallState(**v) for k, v in data["tool_state"]["calls"].items()}),
            speech_state=SpeechState(
                generations={k: GenerationState(**v) for k, v in data["speech_state"]["generations"].items()},
                active_generation_id=data["speech_state"]["active_generation_id"],
            ),
            recent_behavior_state=RecentBehaviorState(**data["recent_behavior_state"]),
            session_closed=data["session_closed"], seen_event_ids=list(data["seen_event_ids"]),
        )
