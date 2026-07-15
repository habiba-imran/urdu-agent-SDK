"""Per-call session state shared between the bot, tools, and processors."""

import uuid
from dataclasses import dataclass, field


@dataclass
class SessionState:
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    turn_number: int = 0
    end_requested: bool = False  # set by end_conversation_summary tool
    summary_written: bool = False
    latencies_ms: list[int] = field(default_factory=list)
    tokens_per_turn: list[int] = field(default_factory=list)
    tool_turn_flags: list[bool] = field(
        default_factory=list
    )  # aligned with latencies_ms
    reasoning_tokens_seen: int = 0  # should stay 0 with v2 non-reasoning models
    llm_failovers: int = 0  # provider switches (429s / malformed tool calls)
