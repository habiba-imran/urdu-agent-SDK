"""Session-local input, semantic turns and business outcome authority."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any
from uuid import uuid4

from .events import StateEvent, reduce_state
from .policy import HumanizationPolicy
from .state import ConversationState, LanguageState


@dataclass(frozen=True)
class StateSnapshot:
    boundary: str
    sequence: int
    state: dict


class HumanizationRuntime:
    """The per-session lock protects short, deterministic state operations only."""

    def __init__(
        self, *, tenant_id: str, agent_id: str, session_id: str,
        language: str, channel: str, policy: HumanizationPolicy,
        provider_snapshot: dict[str, Any] | None = None,
    ) -> None:
        self.policy = policy
        # The existing allowlisted diagnostic snapshot excludes credentials/URLs.
        self.provider_snapshot = deepcopy(provider_snapshot or {})
        self._state = ConversationState(
            tenant_id=tenant_id, agent_id=agent_id, session_id=session_id,
            language_state=LanguageState(language), channel=channel,
        )
        self._lock = RLock()
        self._sequence = 0
        from collections import deque

        self.snapshots: deque[StateSnapshot] = deque(maxlen=128)
        self.shadow = None
        if policy.effective_version == "natural_v1_shadow":
            from .shadow import ShadowObserver
            self.shadow = ShadowObserver()
        self.persona_fact_audit = None
        self.prompt_authority_audit = None
        from .coordinator import TurnCoordinator
        from .orchestrator import ToolOrchestrator
        self.coordinator = TurnCoordinator()
        from .coordinator import overlap_enabled
        from .delivery.renderers import LanguageProfile, ChannelProfile
        self.overlap_enabled = overlap_enabled()
        self.language_profile = LanguageProfile(language)
        self.channel_profile = ChannelProfile(channel)
        self.provider_snapshot["interaction"] = {
            "overlap_policy": "overlap_v1" if self.overlap_enabled else "baseline",
            "language_profile": self.language_profile.locale,
            "language_version": self.language_profile.version,
            "channel_profile": self.channel_profile.kind,
            "channel_version": self.channel_profile.version,
            "audible_activation_verified": False,
        }
        self.last_overlap_decision = None
        self.failure_outcome = None
        self.last_speech_handle = None
        self.playback_evidence = {}
        self.heard_items = {}
        self.tools = ToolOrchestrator(self)  # spoken bridges OFF until listening gate
        self.semantic_revision = 0
        self.offered_slots: set[str] = set()
        self._understood_turns: set[str] = set()
        self.latest_plan = None
        self.latest_signals = None
        self.clarification_enabled = False
        self.last_evidence = None
        self.tool_request_revisions: dict[str, int] = {}
        self._request_turn_ids: set[str] = set()
        self._request_input_text: str | None = None
        self._request_input_revision = -1
        self.pending_evidence = deque(maxlen=32)

    def functional_phrase(self, function: str, *, now: float | None = None, cooldown: float = 12.0) -> str | None:
        import time
        now = time.monotonic() if now is None else now
        with self._lock:
            recent = self._state.recent_behavior_state
            last = recent.phrase_at.get(function)
            # Also suppress back-to-back different functions realizing the same text.
            text = self.language_profile.phrase(function)
            latest = max(recent.phrase_at.values(), default=float("-inf"))
            if (last is not None and now-last < cooldown) or (recent.last_phrase == text and now-latest < cooldown):
                return None
            recent.phrase_at[function] = now
            recent.last_phrase = text
            return text

    def overlap(self, text: str, *, duration: float | None = None) -> str:
        with self._lock:
            pending = self._state.repair_state.pending_field is not None or (
                self.latest_plan is not None and self.latest_plan.dialogue_act in {"CLARIFY", "REPAIR_CONFIRM", "CONFIRM_WRITE"}
            )
            return self.coordinator.decide_overlap(
                text, agent_speaking=self.coordinator.state == "AGENT_SPEAKING",
                duration=duration, language=self.language_profile.locale, awaiting_answer=pending,
            )

    def bind_generation_input(self, chat_ctx: Any) -> None:
        # generate_reply(user_input=...) can invoke LLM before the public history event.
        # Bind request identity here without calling it an acoustic/framework commit.
        with self._lock:
            user = next((item for item in reversed(chat_ctx.items) if getattr(item, "role", None) == "user" and item.id != "awaaz_persona_data"), None)
            if user is not None:
                self._bind_input(user.id, user.text_content or "")

    def _bind_input(self, turn_id: str, text: str) -> None:
        if turn_id in self._request_turn_ids:
            return
        self._request_turn_ids.add(turn_id)
        # LiveKit's preemptive transcript and final hook can have different message
        # IDs for the same unchanged input. Alias them only within the same epoch.
        if text != self._request_input_text or self._request_input_revision != self.semantic_revision:
            self.semantic_revision += 1
        self._request_input_text = text
        self._request_input_revision = self.semantic_revision

    def turn_event(self, kind: str, **fields: Any) -> None:
        with self._lock:
            if kind == "VOICE_START":
                self.semantic_revision += 1
            self.coordinator.event(kind, **fields)

    def observe_transcript(self, event: Any) -> None:
        from .evidence import from_speech_event
        source = self.provider_snapshot.get("stt", {})
        evidence = from_speech_event(event, provider=source.get("provider"), model=source.get("effective_model"))
        if evidence is None:
            return
        self.last_evidence = evidence
        if evidence.is_final:
            self.pending_evidence.append(evidence)
        self.turn_event("EOT_CANDIDATE" if evidence.provider_eot else "STT_FINAL" if evidence.is_final else "STT_INTERIM")

    def understand_turn(self, turn_id: str, text: str) -> None:
        from .evidence import TranscriptEvidence
        from .understanding import apply_understanding
        from .turn_plan import conversational_signals, derive_turn_plan
        with self._lock:
            if turn_id in self._understood_turns:
                return
            self._understood_turns.add(turn_id)
            self._bind_input(turn_id, text)
            # The committed aggregate may include several provider finals; use its text,
            # not an arbitrary last fragment/confidence for the whole turn.
            parsed = apply_understanding(self, TranscriptEvidence(text, True), turn_id)
            # Segment confidence is kept segment-scoped; never pretend it describes
            # the aggregate transcript. Last real field evidence wins for this turn.
            from .understanding import understand, current_value
            scores = {}
            for evidence in self.pending_evidence:
                for name, value in understand(evidence).entities:
                    scores[name] = (value, evidence.confidence)
            self.pending_evidence.clear()
            for name, (value, confidence) in scores.items():
                if confidence is not None and confidence < 0.65 and current_value(self.state, name) == value:
                    self.observe("ground_unresolved", field_name=name)
            if parsed.correction or parsed.unresolved:
                self.offered_slots.clear()
            self.turn_event("EOT_CONFIRMED", turn_id=turn_id)
            from dataclasses import replace
            signals = conversational_signals(text)
            self.latest_signals = replace(
                signals,
                user_correction=bool(parsed.correction and (parsed.entities or parsed.unresolved)) or signals.user_correction,
                critical_capture=any(name in {"phone", "date", "time", "email", "booking_id", "reference_code"}
                                     for name, _ in parsed.entities),
            )
            self.latest_plan = derive_turn_plan(self.state, self.latest_signals)
            self.coordinator.policy_class = "structured_capture" if self.state.grounding_state.unresolved_fields else "free_form"

    def observe_response(self, text: str) -> None:
        import re
        from .delivery.canonical import canonical_spoken_text
        plain = canonical_spoken_text(text).casefold().strip()
        opener = re.match(r"^(sure thing|absolutely|of course|sure|got it|okay|certainly)\b", plain)
        with self._lock:
            recent = self._state.recent_behavior_state
            recent.opening_phrases.append(opener.group(1) if opener else "direct")
            del recent.opening_phrases[:-4]
            recent.question_streak = recent.question_streak + 1 if plain.endswith(("?", "\u061f")) else 0

    def require_clarification(self, fields: tuple[str, ...]) -> None:
        from .turn_plan import derive_turn_plan
        for name in fields:
            self.observe("ground_unresolved", field_name=name)
        if fields:
            self.observe("repair_pending", field_name=fields[0])
        self.latest_plan = derive_turn_plan(self.state)
        self.coordinator.policy_class = "structured_capture"

    @property
    def state(self) -> ConversationState:
        with self._lock:
            return deepcopy(self._state)

    def apply(self, event: StateEvent) -> ConversationState:
        with self._lock:
            self._sequence = max(self._sequence, event.sequence)
            self._state = reduce_state(self._state, event)
            return deepcopy(self._state)

    def observe(self, kind: str, *, event_id: str | None = None, **fields: Any) -> ConversationState:
        with self._lock:
            self._sequence += 1
            event = StateEvent(event_id or uuid4().hex, self._sequence, kind, **fields)
            self._state = reduce_state(self._state, event)
            return deepcopy(self._state)

    def snapshot(self, boundary: str) -> StateSnapshot:
        if boundary not in {
            "before_user_turn", "after_user_turn_commit", "after_tool_result",
            "after_assistant_turn", "session_close",
        }:
            raise ValueError("unknown state boundary")
        with self._lock:
            snap = StateSnapshot(boundary, self._sequence, self._state.to_dict())
            self.snapshots.append(snap)
            return snap

    def attach_session(self, session: Any) -> None:
        """Public AgentSession events; no raw transcript is copied into state."""
        def on_item(ev: Any) -> None:
            item = getattr(ev, "item", None)
            role = getattr(item, "role", None)
            item_id = getattr(item, "id", None)
            if not item_id:
                return
            if role == "user":
                self.snapshot("before_user_turn")
                self.understand_turn(item_id, getattr(item, "text_content", None) or "")
                self.observe("user_turn_committed", event_id=f"user:{item_id}", turn_id=item_id)
                self.snapshot("after_user_turn_commit")
            elif role == "assistant":
                self.observe("assistant_turn_completed", event_id=f"assistant:{item_id}", turn_id=item_id)
                if self.policy.behavior_enabled and not getattr(item, "interrupted", False):
                    self.observe_response(getattr(item, "text_content", None) or "")
                self.snapshot("after_assistant_turn")
                if self.shadow is not None:
                    try:
                        self.shadow.observe_assistant(item)
                    except Exception:
                        from livekit.agents.log import logger
                        logger.exception("humanization shadow assistant comparison failed")

        def on_tool(ev: Any) -> None:
            update = getattr(ev, "update", None)
            update_type = getattr(update, "type", None)
            call = getattr(update, "function_call", None)
            call_id = getattr(call, "call_id", None) or getattr(update, "call_id", None)
            if not call_id:
                return
            if update_type == "tool_call_started":
                self.observe("tool_started", event_id=f"tool-start:{call_id}", tool_call_id=call_id)
            elif update_type == "tool_call_ended":
                raw = getattr(update, "status", None)
                status = {"done": "completed", "error": "error", "cancelled": "outcome_unknown"}.get(raw)
                if status is None:
                    return
                self.observe("tool_finished", event_id=f"tool-end:{call_id}", tool_call_id=call_id, status=status)
                self.snapshot("after_tool_result")

        def on_speech(ev: Any) -> None:
            handle = getattr(ev, "speech_handle", None)
            generation_id = getattr(handle, "id", None)
            if not generation_id:
                return
            self.last_speech_handle = handle
            self.observe("generation_started", event_id=f"generation-start:{generation_id}", generation_id=generation_id)

            def on_done(done: Any) -> None:
                error = None
                if callable(getattr(done, "exception", None)):
                    try:
                        error = done.exception()
                    except BaseException as exc:
                        error = exc
                interrupted = bool(getattr(done, "interrupted", False))
                status = (
                    "cancelled" if interrupted or isinstance(error, asyncio.CancelledError)
                    else "error" if error else "completed"
                )
                self.observe("generation_finished", event_id=f"generation-end:{generation_id}", generation_id=generation_id, status=status)
                evidence = self.playback_evidence.pop(generation_id, None)
                if evidence is not None and evidence.synchronized_transcript is not None:
                    for item in getattr(done, "chat_items", ()):
                        canonical = getattr(item, "text_content", None) or ""
                        prefix = evidence.synchronized_transcript
                        if getattr(item, "role", None) == "assistant" and canonical.startswith(prefix):
                            self.heard_items[item.id] = prefix
                while len(self.heard_items) > 64:
                    self.heard_items.pop(next(iter(self.heard_items)))

            handle.add_done_callback(on_done)

        def on_close(_ev: Any) -> None:
            self.observe("session_closed", event_id="session-close")
            self.snapshot("session_close")

        def on_user_state(ev: Any) -> None:
            self.turn_event("VOICE_START" if ev.new_state == "speaking" else "VOICE_END")

        def on_agent_state(ev: Any) -> None:
            if ev.new_state == "speaking":
                self.turn_event("AGENT_START")
            elif ev.old_state == "speaking":
                self.turn_event("AGENT_END")

        self.tools.bridge_callback = (
            (lambda text: session.say(text, allow_interruptions=True))
            if self.state.language_state.configured_language.startswith("en") or self.overlap_enabled else None
        )
        session.on("user_state_changed", on_user_state)
        session.on("agent_state_changed", on_agent_state)
        session.on("conversation_item_added", on_item)
        session.on("tool_execution_updated", on_tool)
        session.on("speech_created", on_speech)
        session.on("close", on_close)
