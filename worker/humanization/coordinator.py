"""Semantic lifecycle observer. LiveKit still decides every media endpoint."""
from __future__ import annotations

from dataclasses import dataclass
import re
import time


def overlap_enabled() -> bool:
    import os
    return os.getenv("UVA_OVERLAP_POLICY", "baseline") == "overlap_v1"


@dataclass
class TurnCoordinator:
    state: str = "LISTENING"
    candidate_id: int = 0
    committed_turn_id: str | None = None
    reason: str | None = None
    policy_class: str = "free_form"
    speculation_eligible: bool = False

    overlap_active: bool = False
    voice_started_at: float | None = None
    overlap_decision: str = "CONTINUE"
    recovery_strategy: str | None = None

    def decide_overlap(self, text: str, *, agent_speaking: bool, duration: float | None = None,
                       language: str = "en", awaiting_answer: bool = False) -> str:
        # Short listener feedback is tolerated only during an existing, free-form
        # agent turn. Unknown duration is insufficient evidence to suppress a turn.
        normalized = re.sub(r"[^\w\s]", "", text.casefold()).strip()
        english = {"wait", "stop", "no", "hold on"}
        urdu = {"nahi", "nahin", "نہیں", "ruko", "rukain", "رکو", "رکیں", "بس"}
        takeovers = english | (urdu if language.startswith("ur") else set())
        if normalized in takeovers or any(normalized.startswith(t + " ") for t in takeovers):
            decision = "YIELD"
        elif (agent_speaking or self.overlap_active) and not awaiting_answer and self.policy_class == "free_form" and self.state in {
            "AGENT_SPEAKING", "INTERRUPTION_CANDIDATE", "TURN_CANDIDATE", "USER_SPEAKING"
        } and duration is not None and 0 <= duration <= .6 and normalized in {
            "mhm", "yeah", "right", "okay", "hmm",
            *( {"ji", "haan", "acha", "جی", "ہاں", "اچھا"} if language.startswith("ur") else set() )
        }:
            decision = "CONTINUE"
        else:
            decision = "YIELD" if normalized else "CONTINUE"
        self.overlap_decision = decision
        return decision

    def recover_false(self, *, resumed: bool, canonical: str = "", heard_prefix: str = "") -> tuple[str, str | None]:
        self.overlap_decision = "RECOVER_FALSE"
        self.overlap_active = False
        self.state = "AGENT_SPEAKING" if resumed else "LISTENING"
        if resumed:
            self.recovery_strategy = "resume"
            return "resume", None
        # A cancelled generation cannot be revived. Replay only a short unplayed
        # clause, otherwise replan from the known prefix and recorded tool effects.
        boundary = 0
        if canonical.startswith(heard_prefix):
            # Restart the containing short clause, never a cut-off word suffix.
            boundary = max((m.end() for m in re.finditer(r"[.!?۔؟]\s+", canonical)
                            if m.end() <= len(heard_prefix)), default=0)
        remainder = canonical[boundary:] if canonical.startswith(heard_prefix) else ""
        clause = re.split(r"(?<=[.!?۔؟])\s+", remainder.strip())[0]
        if clause and len(clause.split()) <= 12:
            self.recovery_strategy = "restart_short_clause"
            return "restart_short_clause", clause
        self.recovery_strategy = "replan"
        return "replan", None

    def event(self, kind: str, *, turn_id: str | None = None, incomplete: bool = False) -> None:
        if kind == "VOICE_START":
            self.candidate_id += 1
            self.voice_started_at = time.monotonic()
            self.overlap_active = self.state == "AGENT_SPEAKING"
            self.state = "INTERRUPTION_CANDIDATE" if self.state == "AGENT_SPEAKING" else "USER_SPEAKING"
        elif kind in {"STT_INTERIM", "TURN_RESUMED"}:
            self.state = "USER_SPEAKING"
        elif kind in {"VOICE_END", "STT_FINAL", "EOT_CANDIDATE"}:
            if self.state != "TURN_COMMITTED":
                self.state = "TURN_CANDIDATE"
        elif kind == "EOT_CONFIRMED":
            self.committed_turn_id = turn_id
            self.state = "TURN_COMMITTED"
            self.reason = "framework_commit"
            self.overlap_active = False
        elif kind == "AGENT_START":
            self.state = "AGENT_SPEAKING"
        elif kind == "AGENT_END":
            if self.state == "AGENT_SPEAKING":
                self.state = "LISTENING"
        self.speculation_eligible = self.state == "TURN_CANDIDATE" and not incomplete
