"""Fast-track Batch A: real wrapper/gate tests and deterministic multilingual fixtures."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS

import httpx
import pytest
from livekit.agents import Agent, AgentSession, llm, stt
from livekit.agents.types import TimedString

from worker.humanization.agent import AwaazAgent
from worker.humanization.coordinator import TurnCoordinator
from worker.humanization.evidence import TranscriptEvidence, from_speech_event
from worker.humanization.orchestrator import ToolOrchestrator, execution_plan, failure
from worker.humanization.policy import resolve_humanization_policy
from worker.humanization.runtime import HumanizationRuntime
from worker.humanization.understanding import current_value, understand
from worker.tools import AgentUserdata, _gated_write_client_tool, _post_client_tool
from worker.write_tool_gate import note_user_turn, propose_or_confirm_write, set_verified_caller_phone


def runtime():
    return HumanizationRuntime(tenant_id="t", agent_id="a", session_id="r", language="en",
                              channel="webrtc", policy=resolve_humanization_policy(environ={}))


def userdata(*, with_runtime=True):
    ud = AgentUserdata("t", "a", "r", tools_base_url="https://tools.example", tools_auth_secret="test")
    set_verified_caller_phone(ud, "+923001234567")
    if with_runtime:
        ud.humanization_runtime = runtime()
    return ud


def args(slot="2026-10-12T10:00:00"):
    return dict(customer_name="Ali", customer_phone="+923001234567", slot_start_time=slot)


def gate(ud, details=None, confirmation=None):
    return propose_or_confirm_write(ud, tool_name="book_appointment", path="/book",
                                   raw_args=details or args(), confirmation_id=confirmation)


FIXTURES = json.loads((Path(__file__).parent / "fixtures/humanization/repair.batch-a.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("label,first,repair,field,expected", FIXTURES)
def test_repair_supersedes_prior_value(label, first, repair, field, expected):
    rt = runtime()
    rt.understand_turn("first", first)
    rt.understand_turn("repair", repair)
    assert current_value(rt.state, field) == expected
    assert rt.state.task_state.critical_values[field][0].status == "superseded"
    assert not rt.state.grounding_state.unresolved_fields


@pytest.mark.parametrize("text,field", [("Friday or Monday", "date"), ("kal", "date"), ("10 baje", "time"), ("10:30", "time"), ("Friday nahi", "date"), ("جمعہ نہیں", "date")])
def test_ambiguous_or_negated_critical_value_blocks_write(text, field):
    ud = userdata()
    rt = ud.humanization_runtime
    rt.understand_turn("details", "My name is Ali, 2026-10-12 at 10 am")
    rt.understand_turn("ambiguous", text)
    action, payload = gate(ud)
    assert action == "reject" and field in payload["needs_clarification"]
    assert rt.latest_plan.dialogue_act == "CLARIFY"


def test_missing_evidence_blocks_llm_guess_and_contextual_answer_resolves():
    ud = userdata()
    rt = ud.humanization_runtime
    rt.understand_turn("one", "2026-10-12 at 10 am")
    assert gate(ud)[0] == "reject"
    assert rt.latest_plan.clarification_target == "name"
    rt.understand_turn("two", "Ali")
    assert gate(ud)[0] == "propose"


def test_superseded_friday_cannot_be_consumed_as_iso_write():
    ud = userdata()
    rt = ud.humanization_runtime
    rt.understand_turn("one", "My name is Ali, Friday at 10 am")
    rt.offered_slots = {"2026-10-16T10:00:00"}
    assert gate(ud, args("2026-10-16T10:00:00"))[0] == "propose"
    rt.understand_turn("two", "No Monday")
    assert gate(ud, args("2026-10-16T10:00:00"))[0] == "reject"


def test_confirmed_survives_weaker_inference_but_explicit_correction_replaces():
    rt = runtime()
    rt.observe("ground_value", field_name="date", value="Friday", status="confirmed", observation_id="a")
    rt.observe("ground_value", field_name="date", value="Monday", status="inferred", observation_id="b")
    assert current_value(rt.state, "date") == "Friday"
    rt.understand_turn("fix", "Actually Monday")
    assert current_value(rt.state, "date") == "Monday"


def test_evidence_preserves_installed_fields_without_fabricating_scores():
    event = stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[
        stt.SpeechData(language="en", text="Monday", confidence=.87,
                       words=[TimedString("Monday", start_time=.2, end_time=.8)])])
    dg = from_speech_event(event, provider="deepgram", model="nova-3")
    assert (dg.text, dg.is_final, dg.start, dg.end, dg.confidence) == ("Monday", True, .2, .8, .87)
    assert dg.words[0].confidence is None
    assert from_speech_event(event, provider="gladia", model=None).confidence is None
    assert from_speech_event(event, provider="deepgram", model="flux-general-en").confidence is None
    event.alternatives[0].words = None
    assert from_speech_event(event, provider="gladia", model=None).start is None
    end = stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)
    assert from_speech_event(end, provider="gladia", model=None).provider_eot is True
    assert understand(TranscriptEvidence("Friday", False)).entities == ()


def test_turn_coordinator_tracks_baseline_only_framework_commits():
    tc = TurnCoordinator()
    tc.event("VOICE_START")
    assert tc.state == "USER_SPEAKING"
    tc.event("STT_FINAL", incomplete=True)
    assert tc.state == "TURN_CANDIDATE" and not tc.speculation_eligible
    tc.event("EOT_CANDIDATE")
    assert tc.state == "TURN_CANDIDATE"
    tc.event("TURN_RESUMED")
    assert tc.state == "USER_SPEAKING"
    tc.event("EOT_CONFIRMED", turn_id="turn")
    assert tc.state == "TURN_COMMITTED" and tc.reason == "framework_commit"
    tc.event("AGENT_START")
    tc.event("VOICE_START")
    assert tc.state == "INTERRUPTION_CANDIDATE"
    tc.event("AGENT_END")
    assert tc.state == "INTERRUPTION_CANDIDATE"


async def install_http(monkeypatch, post):
    async def client():
        return NS(post=post)
    monkeypatch.setattr("worker.tools._shared_http_client", client)
    monkeypatch.setattr("worker.ssrf_guard.prepare_tools_post_url", lambda url: (url, {}))


@pytest.mark.asyncio
async def test_unconfirmed_write_never_dispatches(monkeypatch):
    posts = []
    async def post(*a, **kw):
        posts.append(kw)
        return NS(raise_for_status=lambda: None, json=lambda: {"success": True})
    await install_http(monkeypatch, post)
    ud = userdata()
    ud.humanization_runtime.understand_turn("details", "My name is Ali, 2026-10-12 at 10 am")
    ctx = NS(userdata=ud)
    proposal = await _gated_write_client_tool(ctx, tool_name="book_appointment", path="/book", raw_args=args(), confirmation_id=None)
    rejected = await _gated_write_client_tool(ctx, tool_name="book_appointment", path="/book", raw_args=args(), confirmation_id=proposal["confirmation_id"])
    assert rejected["needs_confirmation"] and not posts


@pytest.mark.asyncio
async def test_post_dispatch_unknown_blocks_retry_and_new_proposal(monkeypatch):
    posts = []
    async def post(*a, **kw):
        posts.append(kw)
        raise httpx.ReadTimeout("secret raw error https://backend")
    await install_http(monkeypatch, post)
    ud = userdata()
    ud.humanization_runtime.understand_turn("details", "My name is Ali, 2026-10-12 at 10 am")
    _, proposal = gate(ud)
    note_user_turn(ud, "yes")
    ctx = NS(userdata=ud, function_call=NS(call_id="write1"))
    async def commit():
        return await _gated_write_client_tool(ctx, tool_name="book_appointment", path="/book", raw_args=args(), confirmation_id=proposal["confirmation_id"])
    result = await commit()
    replay = await commit()
    assert result["outcome"] == replay["outcome"] == "OUTCOME_UNKNOWN"
    assert gate(ud)[1]["outcome"] == "OUTCOME_UNKNOWN"
    assert len(posts) == 1 and "secret raw error" not in str(result)
    assert ud.humanization_runtime.state.tool_state.calls["write1"].business_effect == "unknown"


@pytest.mark.asyncio
async def test_concurrent_confirm_posts_once_and_completed_replay_survives_interrupted_speech(monkeypatch):
    started, finish = asyncio.Event(), asyncio.Event()
    posts = []
    async def post(*a, **kw):
        posts.append(kw)
        started.set()
        await finish.wait()
        return NS(raise_for_status=lambda: None, json=lambda: {"success": True, "confirmationCode": "ABC"})
    await install_http(monkeypatch, post)
    ud = userdata()
    rt = ud.humanization_runtime
    rt.understand_turn("details", "My name is Ali, 2026-10-12 at 10 am")
    _, proposal = gate(ud)
    note_user_turn(ud, "yes")
    ctx = NS(userdata=ud, function_call=NS(call_id="w"))
    async def commit():
        return await _gated_write_client_tool(ctx, tool_name="book_appointment", path="/book", raw_args=args(), confirmation_id=proposal["confirmation_id"])
    task = asyncio.create_task(commit())
    await started.wait()
    assert (await commit())["outcome"] == "OUTCOME_UNKNOWN"
    finish.set()
    result = await task
    rt.observe("generation_finished", generation_id="speech", status="cancelled")
    rt.observe("tool_finished", tool_call_id="w", status="completed")
    assert (await commit()) == result
    state = rt.state.tool_state.calls["w"]
    assert state.business_effect == "committed" and state.result_heard is None
    assert state.result_data["confirmationCode"] == "ABC" and len(posts) == 1
    assert ud.write_gate.write_tool_calls == 1


@pytest.mark.asyncio
async def test_stale_read_not_handed_to_llm_after_correction(monkeypatch):
    entered, finish = asyncio.Event(), asyncio.Event()
    async def post(*a, **kw):
        entered.set()
        await finish.wait()
        return NS(raise_for_status=lambda: None, json=lambda: {"available": True, "voiceSummary": "Friday is available", "slots": [{"startTime": "2026-10-16T10:00:00"}]})
    await install_http(monkeypatch, post)
    ud = userdata()
    rt = ud.humanization_runtime
    rt.understand_turn("one", "Friday")
    task = asyncio.create_task(_post_client_tool(NS(userdata=ud, function_call=NS(call_id="read")), path="/read", payload={"date": "2026-10-16"}, tool_name="check_availability"))
    await entered.wait()
    rt.understand_turn("two", "No Monday")
    finish.set()
    with pytest.raises(llm.StopResponse):
        await task
    assert rt.offered_slots == set()
    assert rt.state.tool_state.calls["read"].outcome == "SUCCESS"


@pytest.mark.asyncio
async def test_fast_read_skips_bridge_slow_read_starts_request_before_bridge():
    calls = []
    orchestrator = ToolOrchestrator(bridges_enabled=True, delay=.01)
    orchestrator.bridge_callback = lambda text: calls.append("bridge")
    async def fast():
        calls.append("fast_request")
        return {"found": True}
    plan = execution_plan("lookup_business_info", "fast", 0)
    await orchestrator.run(plan, fast)
    assert calls == ["fast_request"]
    async def slow():
        calls.append("slow_request")
        await asyncio.sleep(.03)
        return {"found": True}
    await orchestrator.run(execution_plan("lookup_business_info", "slow", 0), slow)
    assert calls == ["fast_request", "slow_request", "bridge"]
    assert not runtime().tools.bridges_enabled and not runtime().clarification_enabled


@pytest.mark.parametrize("status,outcome", [(404, "NO_RESULT"), (409, "CONFLICT"), (422, "VALIDATION_ERROR"), (429, "RATE_LIMITED"), (503, "DEPENDENCY_UNAVAILABLE")])
def test_http_errors_are_actionable_and_never_raw(status, outcome):
    request = httpx.Request("POST", "https://backend")
    exc = httpx.HTTPStatusError("secret HTTP error", request=request, response=httpx.Response(status, request=request))
    result = failure(exc, write=False, dispatched=True)
    assert result.outcome == outcome and "secret HTTP" not in str(result.payload())
    if status == 503:
        assert failure(exc, write=True, dispatched=True).outcome == "OUTCOME_UNKNOWN"


def test_pre_dispatch_timeout_does_not_claim_unknown_write():
    assert failure(httpx.ConnectTimeout("raw"), write=True, dispatched=False).outcome == "DEPENDENCY_TIMEOUT"


def test_affirmation_cannot_survive_later_correction():
    ud = userdata(with_runtime=False)
    _, proposal = gate(ud)
    note_user_turn(ud, "yes")
    note_user_turn(ud, "No, Monday")
    assert gate(ud, confirmation=proposal["confirmation_id"])[0] == "reject"


@pytest.mark.asyncio
async def test_escalation_only_records_followup(monkeypatch):
    from worker.tools import escalate_to_human
    monkeypatch.setattr("worker.tools._insert_escalation", lambda **kw: None)
    ud = userdata()
    result = await escalate_to_human(NS(userdata=ud, function_call=NS(call_id="e")), "help")
    assert result["businessEffect"] == "escalation_recorded" and not result["liveTransfer"]
    assert "No live transfer" in result["voiceSummary"]
    assert ud.humanization_runtime.tools.plans["e"].category == "ESCALATION_RECORD"


@pytest.mark.asyncio
async def test_public_stt_hook_yields_identical_events(monkeypatch):
    events = [stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[stt.SpeechData(language="ur", text="پیر")])]
    async def stream(*args):
        for event in events:
            yield event
    monkeypatch.setattr(Agent, "stt_node", lambda *args: stream())
    rt = runtime()
    rt.provider_snapshot = {"stt": {"provider": "gladia", "effective_model": None}}
    agent = AwaazAgent(instructions="plain", humanization_runtime=rt)
    assert [event async for event in agent.stt_node(None, None)] == events
    assert rt.last_evidence.text == "پیر" and rt.last_evidence.confidence is None
    assert rt.coordinator.state == "TURN_CANDIDATE"


@pytest.mark.asyncio
async def test_installed_session_suppresses_stale_tool_continuation(monkeypatch):
    from test_humanization_observability_framework import SyntheticSink, SyntheticTTS, SyntheticLLM
    from worker.tools import lookup_business_info
    ud = userdata()
    rt = ud.humanization_runtime
    async def post(*a, **kw):
        rt.understand_turn("correction", "No Monday")
        return NS(raise_for_status=lambda: None, json=lambda: {"success": True, "result": "Friday availability"})
    await install_http(monkeypatch, post)
    session = AgentSession(llm=SyntheticLLM(), tts=SyntheticTTS(), userdata=ud)
    sink = SyntheticSink()
    session.output.audio = sink
    rt.attach_session(session)
    agent = AwaazAgent(instructions="plain", tools=[lookup_business_info], humanization_runtime=rt)
    await session.start(agent, record=False)
    try:
        handle = session.generate_reply(user_input="Friday")
        await asyncio.wait_for(handle.wait_for_playout(), 5)
        assert handle.exception() is None
        assert sink.frames == 0
        assert not any(item.type == "function_call_output" for item in session.history.items)
        assert rt.tools.results["synthetic_call_1"].outcome == "SUCCESS"
    finally:
        await session.aclose()


def test_business_effect_is_projected_next_turn_without_changing_history(monkeypatch):
    from livekit.agents.llm import ChatContext
    observed = runtime()
    observed.observe("tool_result", tool_call_id="w", outcome="SUCCESS", business_effect="committed",
                     result_data={"confirmationCode": "ABC", "businessEffect": "committed"})
    observed.observe("generation_finished", generation_id="speech", status="cancelled")
    captured = []
    monkeypatch.setattr(Agent, "llm_node", lambda self, chat_ctx, *args: captured.append(chat_ctx))
    ctx = ChatContext.empty()
    agent = AwaazAgent(instructions="plain", humanization_runtime=observed)
    agent.llm_node(ctx, [], None)
    assert len(ctx.items) == 0
    assert "ABC" in captured[0].items[-1].text_content
    assert "interrupted" in captured[0].items[-2].text_content


@pytest.mark.asyncio
async def test_cancelled_dispatched_write_is_unknown_and_cannot_repeat(monkeypatch):
    entered = asyncio.Event()
    posts = []
    async def post(*a, **kw):
        posts.append(kw)
        entered.set()
        await asyncio.Future()
    await install_http(monkeypatch, post)
    ud = userdata()
    ud.humanization_runtime.understand_turn("details", "My name is Ali, 2026-10-12 at 10 am")
    _, proposal = gate(ud)
    note_user_turn(ud, "yes")
    ctx = NS(userdata=ud, function_call=NS(call_id="cancelled_write"))
    task = asyncio.create_task(_gated_write_client_tool(ctx, tool_name="book_appointment", path="/book", raw_args=args(), confirmation_id=proposal["confirmation_id"]))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gate(ud, confirmation=proposal["confirmation_id"])[1]["outcome"] == "OUTCOME_UNKNOWN"
    assert ud.humanization_runtime.state.tool_state.calls["cancelled_write"].business_effect == "unknown"
    assert len(posts) == 1


@pytest.mark.asyncio
async def test_stale_read_before_dispatch_and_cancelled_running_read():
    rt = runtime()
    orchestrator = rt.tools
    plan = execution_plan("check_availability", "before", rt.semantic_revision)
    rt.understand_turn("new", "Monday")
    async def forbidden():
        pytest.fail("Stale request dispatched")
    with pytest.raises(llm.StopResponse):
        await orchestrator.run(plan, forbidden)
    entered = asyncio.Event()
    async def running():
        entered.set()
        await asyncio.Future()
    plan = execution_plan("check_availability", "running", rt.semantic_revision)
    task = asyncio.create_task(orchestrator.run(plan, running))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert rt.state.tool_state.calls["running"].outcome == "CANCELLED"
    assert rt.state.tool_state.calls["running"].business_effect == "none"


def test_real_low_confidence_is_segment_scoped_and_requests_repair():
    rt = runtime()
    rt.provider_snapshot = {"stt": {"provider": "deepgram", "effective_model": "nova-3"}}
    rt.observe_transcript(stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT,
        alternatives=[stt.SpeechData(language="en", text="Friday", confidence=.4)]))
    rt.understand_turn("one", "Friday")
    assert rt.latest_plan.dialogue_act == "CLARIFY"
    assert "date" in rt.state.grounding_state.unresolved_fields
    rt.observe_transcript(stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT,
        alternatives=[stt.SpeechData(language="en", text="No Monday", confidence=.9)]))
    rt.understand_turn("two", "No Monday")
    assert current_value(rt.state, "date") == "Monday"
    assert not rt.state.grounding_state.unresolved_fields


def test_existing_and_new_reschedule_dates_have_distinct_roles():
    from worker.humanization.understanding import write_uncertainties
    rt = runtime()
    rt.understand_turn("one", "existing appointment 2026-10-12, new date 2026-10-13 at 11 am")
    assert current_value(rt.state, "existing_date") == "2026-10-12"
    assert current_value(rt.state, "date") == "2026-10-13"
    assert not write_uncertainties(rt, "reschedule_appointment", {
        "customer_phone": "+923001234567", "existing_date": "2026-10-12",
        "new_slot_start_time": "2026-10-13T11:00:00"}, "+923001234567")


def test_bare_contextual_name_correction_and_negative_proposal_invalidation():
    rt = runtime()
    rt.understand_turn("one", "My name is Ali")
    rt.understand_turn("two", "No, Ahmed")
    assert current_value(rt.state, "name") == "Ahmed"
    ud = userdata(with_runtime=False)
    _, proposal = gate(ud)
    note_user_turn(ud, "no")
    note_user_turn(ud, "yes")
    assert gate(ud, confirmation=proposal["confirmation_id"])[0] == "reject"


@pytest.mark.asyncio
async def test_write_no_result_does_not_become_committed(monkeypatch):
    async def post(*a, **kw):
        request = httpx.Request("POST", "https://tools.example/book")
        response = httpx.Response(404, request=request)
        response.raise_for_status()
    await install_http(monkeypatch, post)
    ud = userdata()
    ud.humanization_runtime.understand_turn("details", "My name is Ali, 2026-10-12 at 10 am")
    _, proposal = gate(ud)
    note_user_turn(ud, "yes")
    result = await _gated_write_client_tool(NS(userdata=ud, function_call=NS(call_id="missing")), tool_name="book_appointment", path="/book", raw_args=args(), confirmation_id=proposal["confirmation_id"])
    assert result["outcome"] == "NO_RESULT" and result["businessEffect"] == "none"
    assert ud.write_gate.write_tool_calls == 0 and not ud.write_gate.completed_writes


@pytest.mark.asyncio
async def test_installed_session_fresh_read_works_and_duration_counted_once(monkeypatch):
    from unittest.mock import MagicMock
    from test_humanization_observability_framework import SyntheticSink, SyntheticTTS, SyntheticLLM
    from worker.latency import wire_turn_latency
    from worker.tools import lookup_business_info
    async def post(*a, **kw):
        return NS(raise_for_status=lambda: None, json=lambda: {"success": True, "result": "nine to five"})
    await install_http(monkeypatch, post)
    ud = userdata()
    rt = ud.humanization_runtime
    session = AgentSession(llm=SyntheticLLM(), tts=SyntheticTTS(), userdata=ud)
    sink = SyntheticSink()
    session.output.audio = sink
    rt.attach_session(session)
    agent = AwaazAgent(instructions="plain", tools=[lookup_business_info], humanization_runtime=rt)
    tracker = wire_turn_latency(session, MagicMock(), MagicMock(), agent=agent)
    ud.latency_tracker = tracker
    await session.start(agent, record=False)
    try:
        handle = session.generate_reply(user_input="business hours")
        await asyncio.wait_for(handle.wait_for_playout(), 5)
        assert handle.exception() is None and sink.frames > 0
        assert len(tracker._tools) == 1
        assert tracker._tools["synthetic_call_1"]["duration_ms"] is not None
        assert rt.state.tool_state.calls["synthetic_call_1"].outcome == "SUCCESS"
        assert any(item.type == "function_call_output" for item in session.history.items)
    finally:
        await session.aclose()


@pytest.mark.asyncio
async def test_preemptive_and_final_input_ids_share_identity_until_user_changes():
    from livekit.agents.llm import ChatContext
    rt = runtime()
    ctx = ChatContext.empty()
    ctx.add_message(role="user", content="Friday")
    rt.bind_generation_input(ctx)
    plan = execution_plan("check_availability", "preemptive", rt.semantic_revision)
    rt.understand_turn("final_hook_other_id", "Friday")
    assert rt.tools.current(plan)
    result = await rt.tools.run(plan, lambda: asyncio.sleep(0, result={"available": True}))
    assert result["outcome"] == "SUCCESS"
    rt.turn_event("VOICE_START")
    rt.understand_turn("changed", "No Monday")
    assert not rt.tools.current(plan) and current_value(rt.state, "date") == "Monday"


def test_cancel_cannot_omit_an_ambiguous_date_to_bypass_safety():
    ud = userdata()
    ud.humanization_runtime.understand_turn("ambiguous", "Friday or Monday")
    action, payload = propose_or_confirm_write(ud, tool_name="cancel_appointment", path="/cancel",
                                              raw_args={"customer_phone": "+923001234567"}, confirmation_id=None)
    assert action == "reject" and "date" in payload["needs_clarification"]
