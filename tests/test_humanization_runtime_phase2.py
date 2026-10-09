"""Phase 2 state, ordering, isolation and installed-framework hook contracts."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from types import SimpleNamespace as NS

from livekit.agents import Agent
from livekit.agents.llm import ChatContext

from worker.humanization.agent import AwaazAgent
from worker.humanization.events import StateEvent, reduce_state
from worker.humanization.history import AuditTranscript, apply_history_hygiene
from worker.humanization.policy import resolve_humanization_policy
from worker.humanization.runtime import HumanizationRuntime
from worker.humanization.state import ConversationState
from worker.session_close import build_transcript


def runtime(tenant="tenant_a", agent="agent_a", session="session_a"):
    return HumanizationRuntime(
        tenant_id=tenant, agent_id=agent, session_id=session, language="ur", channel="webrtc",
        policy=resolve_humanization_policy(environ={}),
        provider_snapshot={"stt": "gladia", "deployed_verified": False},
    )


def test_policy_resolution_is_baseline_and_legacy_overrides_still_visible():
    default = resolve_humanization_policy(environ={})
    assert (default.requested_version, default.effective_version, default.behavior_enabled) == ("baseline", "baseline", False)
    candidate = resolve_humanization_policy(
        "natural_v1", environ={"UVA_INTERRUPTION_MODE": "adaptive", "UVA_CHAT_HISTORY_MAX_ITEMS": "8", "UVA_PROVIDER_MAX_RETRY": "2"},
    )
    assert candidate.effective_version == "natural_v1_shadow"
    assert dict(candidate.legacy_overrides) == {"UVA_INTERRUPTION_MODE": "adaptive", "UVA_CHAT_HISTORY_MAX_ITEMS": "8", "UVA_PROVIDER_MAX_RETRY": "2"}


def test_reducer_replay_serialization_and_grounding_authority():
    original = runtime().state
    events = [
        StateEvent("u1", 1, "user_turn_committed", turn_id="u1"),
        StateEvent("g1", 2, "ground_value", turn_id="u1", field_name="appointment_date", observation_id="v1", value="Monday", status="heard"),
        StateEvent("g2", 3, "ground_value", turn_id="u1", field_name="appointment_date", observation_id="v1", value="Monday", status="confirmed"),
        StateEvent("g3", 4, "ground_value", turn_id="u1", field_name="appointment_date", observation_id="v2", value="Tuesday", status="inferred"),
        StateEvent("u2", 5, "user_turn_committed", turn_id="u2"),
        StateEvent("g4", 6, "ground_value", turn_id="u2", field_name="appointment_date", observation_id="v3", value="Wednesday", status="confirmed"),
        StateEvent("a1", 7, "assistant_turn_completed", turn_id="a1"),
    ]
    replay_a = original
    replay_b = original
    for event in events:
        replay_a = reduce_state(replay_a, event)
    for event in events:
        replay_b = reduce_state(replay_b, event)
    assert replay_a == replay_b
    values = replay_a.task_state.critical_values["appointment_date"]
    assert [(v.value, v.status) for v in values] == [("Monday", "superseded"), ("Wednesday", "confirmed")]
    assert json.loads(json.dumps(replay_a.to_dict())) == replay_a.to_dict()
    assert ConversationState.from_dict(json.loads(json.dumps(replay_a.to_dict()))) == replay_a
    assert replay_a.interaction_state.committed_turn_ids == ["u1", "u2"]


def test_out_of_order_terminals_and_tool_after_close_cannot_resurrect_generation():
    state = runtime().state
    events = [
        StateEvent("gend", 12, "generation_finished", generation_id="gen1", status="cancelled"),
        StateEvent("gstart", 10, "generation_started", generation_id="gen1"),
        StateEvent("close", 13, "session_closed"),
        StateEvent("tend", 15, "tool_finished", tool_call_id="call1", status="completed"),
        StateEvent("tstart", 11, "tool_started", tool_call_id="call1"),
        StateEvent("gend2", 16, "generation_finished", generation_id="gen1", status="completed"),
    ]
    for event in events:
        state = reduce_state(state, event)
    assert state.speech_state.generations["gen1"].status == "cancelled"
    assert state.speech_state.active_generation_id is None
    assert state.tool_state.calls["call1"].status == "completed"
    assert state.session_closed


def test_concurrent_session_facts_and_recent_behavior_are_isolated():
    first, second = runtime(), runtime("tenant_b", "agent_b", "session_b")
    first.observe("ground_value", field_name="phone", observation_id="f1", value="SENSITIVE_FACT", status="confirmed")
    first.observe("assistant_turn_completed", turn_id="a1")
    assert second.state.task_state.critical_values == {}
    assert second.state.recent_behavior_state.assistant_turn_ids == []
    assert "SENSITIVE_FACT" not in json.dumps(second.state.to_dict())
    assert first.provider_snapshot is not second.provider_snapshot


def test_session_events_snapshots_and_independent_tool_speech_state():
    callbacks = {}
    class FakeSession:
        def on(self, name, callback):
            callbacks[name] = callback

    observed = runtime()
    observed.attach_session(FakeSession())
    callbacks["conversation_item_added"](NS(item=NS(role="user", id="user1")))
    callbacks["tool_execution_updated"](NS(update=NS(type="tool_call_started", function_call=NS(call_id="call1"))))
    handle_callbacks = []
    handle = NS(id="speech1", add_done_callback=handle_callbacks.append)
    callbacks["speech_created"](NS(speech_handle=handle))
    callbacks["close"](NS())
    callbacks["tool_execution_updated"](NS(update=NS(type="tool_call_ended", call_id="call1", status="done")))
    handle_callbacks[0](NS(interrupted=True, exception=lambda: None))
    assert observed.state.tool_state.calls["call1"].status == "completed"
    assert observed.state.speech_state.generations["speech1"].status == "cancelled"
    assert [s.boundary for s in observed.snapshots] == [
        "before_user_turn", "after_user_turn_commit", "session_close", "after_tool_result",
    ]
    assert json.loads(json.dumps(asdict(observed.snapshots[0]))) == asdict(observed.snapshots[0])


def test_audit_transcript_survives_legacy_session_history_window(monkeypatch):
    monkeypatch.setenv("UVA_CHAT_HISTORY_MAX_ITEMS", "8")
    history = ChatContext.empty()
    audit = AuditTranscript()
    session = NS(history=history, userdata=NS(audit_transcript=audit))
    for i in range(20):
        item = history.add_message(role="user" if i % 2 == 0 else "assistant", content=f"turn {i}")
        apply_history_hygiene(session, item=item)
        audit.record(item)
    assert len(history.items) <= 9
    transcript = build_transcript(session)
    assert len(transcript) == 20
    assert transcript[0]["text"] == "turn 0"
    assert transcript[-1]["text"] == "turn 19"


def test_awaaz_hook_boundary_delegates_provider_nodes_and_canonicalizes_transcript(monkeypatch):
    sentinels = [object() for _ in range(4)]
    monkeypatch.setattr(Agent, "stt_node", lambda self, *a: sentinels[0])
    monkeypatch.setattr(Agent, "llm_node", lambda self, *a: sentinels[1])
    monkeypatch.setattr(Agent, "tts_node", lambda self, *a: sentinels[2])
    monkeypatch.setattr(Agent, "transcription_node", lambda self, *a: sentinels[3])
    async def completed(self, *args):
        return None
    monkeypatch.setattr(Agent, "on_user_turn_completed", completed)
    agent = AwaazAgent(instructions="baseline", humanization_runtime=runtime())
    assert agent.id == "default_agent"
    assert agent.stt_node(None, None) is sentinels[0]
    assert agent.llm_node(None, [], None) is sentinels[1]
    assert agent.tts_node(None, None) is sentinels[2]
    async def transcript():
        async def marked():
            yield '<emotion'
            yield ' value="calm"/>Hello.'
        assert ''.join([piece async for piece in agent.transcription_node(marked(), None)]) == 'Hello.'
    asyncio.run(transcript())
    asyncio.run(agent.on_user_turn_completed(None, None))
def test_cancelled_handle_exception_cannot_escape_or_resurrect_generation():
    callbacks = {}

    class FakeSession:
        def on(self, name, callback):
            callbacks[name] = callback

    observed = runtime()
    observed.attach_session(FakeSession())
    done_callbacks = []
    callbacks["speech_created"](NS(speech_handle=NS(id="cancelled_speech", add_done_callback=done_callbacks.append)))

    def cancelled_exception():
        raise asyncio.CancelledError()

    done_callbacks[0](NS(interrupted=False, exception=cancelled_exception))
    assert observed.state.speech_state.generations["cancelled_speech"].status == "cancelled"
    assert observed.state.speech_state.active_generation_id is None
