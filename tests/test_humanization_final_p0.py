"""Final P0 audit regressions at caller correction and backend outcome boundaries."""
from types import SimpleNamespace as NS

import pytest

from tests.test_humanization_batch_a import args, gate, install_http, userdata
from worker.humanization.orchestrator import execution_plan, normalize
from worker.humanization.understanding import current_value
from worker.tools import _gated_write_client_tool
from worker.write_tool_gate import note_user_turn


@pytest.mark.parametrize("text", ["Monday, not Friday", "Monday instead, not Friday", "پیر، جمعہ نہیں", "peer, jumma nahi"])
def test_replacement_before_negated_old_date_cannot_write_friday(text):
    ud = userdata()
    rt = ud.humanization_runtime
    rt.understand_turn("first", "My name is Ali, Friday at 10 am")
    rt.offered_slots = {"2026-10-16T10:00:00"}
    proposal = gate(ud, args("2026-10-16T10:00:00"))[1]
    rt.understand_turn("corrected", text)
    note_user_turn(ud, text)
    assert current_value(rt.state, "date") == "Monday"
    assert rt.state.task_state.critical_values["date"][0].status == "superseded"
    note_user_turn(ud, "yes")
    assert gate(ud, args("2026-10-16T10:00:00"), proposal["confirmation_id"])[0] == "reject"
    rt.understand_turn("clarified", "Monday")
    rt.offered_slots = {"2026-10-12T10:00:00"}
    assert gate(ud)[0] == "propose"


@pytest.mark.parametrize("outcome", ["OUTCOME_UNKNOWN", "CONFLICT", "DEPENDENCY_TIMEOUT", "VALIDATION_ERROR", "UNRECOGNIZED"])
@pytest.mark.parametrize("success", [None, True, False])
def test_declared_non_success_cannot_normalize_to_committed_success(outcome, success):
    body = {"outcome": outcome, "voiceSummary": "Successfully booked."}
    if success is not None:
        body["success"] = success
    result = normalize(body, execution_plan("book_appointment", "w", 0)).payload()
    assert result["outcome"] == ("OUTCOME_UNKNOWN" if outcome == "UNRECOGNIZED" else outcome)
    assert result["businessEffect"] == ("unknown" if result["outcome"] == "OUTCOME_UNKNOWN" else "none")
    assert result["success"] is False and result["retrySafe"] is False
    assert "Successfully booked" not in str(result)


@pytest.mark.asyncio
async def test_backend_unknown_without_error_flag_preserves_tombstone_and_posts_once(monkeypatch):
    posts = []

    async def post(*a, **kw):
        posts.append(kw)
        return NS(raise_for_status=lambda: None, json=lambda: {"outcome": "OUTCOME_UNKNOWN"})

    await install_http(monkeypatch, post)
    ud = userdata()
    ud.humanization_runtime.understand_turn("details", "My name is Ali, 2026-10-12 at 10 am")
    proposal = gate(ud)[1]
    note_user_turn(ud, "yes")
    ctx = NS(userdata=ud, function_call=NS(call_id="unknown_write"))
    for _ in range(2):
        result = await _gated_write_client_tool(ctx, tool_name="book_appointment", path="/book", raw_args=args(), confirmation_id=proposal["confirmation_id"])
        assert result["outcome"] == "OUTCOME_UNKNOWN"
        assert result["businessEffect"] == "unknown"
    assert len(posts) == 1 and ud.write_gate.write_tool_calls == 0
    assert gate(ud)[1]["outcome"] == "OUTCOME_UNKNOWN"
    assert ud.humanization_runtime.state.tool_state.calls["unknown_write"].business_effect == "unknown"


@pytest.mark.parametrize("first,repair,field,expected", [
    ("10 am", "11 am, not 10 am", "time", "11:00"),
    ("10 am", "11 am, 10 am nahi", "time", "11:00"),
    ("+12025550100", "+12025550101, not +12025550100", "phone", "+12025550101"),
    ("old@example.test", "new@example.test, not old@example.test", "email", "new@example.test"),
    ("My name is Bilal", "My name is Ali, not name is Bilal", "name", "Ali"),
    ("Doctor Bilal", "Doctor Ali, not doctor Bilal", "doctor_name", "Ali"),
    ("booking id OLD1", "booking id NEW2, not booking id OLD1", "booking_id", "NEW2"),
])
def test_local_negation_never_reactivates_rejected_critical_value(first, repair, field, expected):
    rt = userdata().humanization_runtime
    rt.understand_turn("first", first)
    rt.understand_turn("repair", repair)
    assert current_value(rt.state, field) == expected
    assert rt.state.task_state.critical_values[field][0].status == "superseded"


@pytest.mark.parametrize("policy,streaming", [("baseline", "baseline"), ("natural_v1_shadow", "streaming_v1")])
def test_telemetry_preserves_session_effective_policy_and_component_identity(policy, streaming, monkeypatch):
    from unittest.mock import MagicMock
    from tests.test_humanization_observability import Handle, created, metrics
    from worker.latency import TurnLatencyTracker

    monkeypatch.setenv("UVA_PUBLISH_TURN_LATENCY", "1")
    room, logger = MagicMock(), MagicMock()
    snapshot = {
        "language": "en", "channel": "webrtc", "humanization_policy_version": policy,
        "component_versions": {"streaming": streaming, "turn": "overlap_v1"},
        "delivery": {"policy_version": "delivery_v1", "renderer_version": "renderer_v1"},
    }
    tracker = TurnLatencyTracker(room, logger, snapshot=snapshot, lifecycle=True)
    handle = Handle()
    tracker.mark_user_stopped_speaking()
    created(tracker, handle)
    metrics(tracker, handle.id)
    handle.finish()
    tracker.close()
    import json
    events = [json.loads(call.args[1]) for call in logger.info.call_args_list
              if call.args[0] == "humanization_event %s"]
    published = [json.loads(call.args[0]) for call in room.local_participant.publish_data.call_args_list]
    assert events and published
    for payload in events + published:
        assert payload["humanization_policy_version"] == policy
        if "component_versions" in payload:
            assert payload["component_versions"]["streaming"] == streaming
            assert payload["component_versions"]["turn"] == "overlap_v1"
            assert payload["component_versions"]["delivery"] == "delivery_v1"


@pytest.mark.parametrize("tool", ["book_appointment", "reschedule_appointment"])
@pytest.mark.parametrize("service", [None, "Dr Ali", "Dr Bilal"])
def test_corrected_doctor_cannot_be_omitted_or_replaced_by_wrong_write_argument(tool, service):
    from worker.write_tool_gate import propose_or_confirm_write

    ud = userdata()
    rt = ud.humanization_runtime
    rt.understand_turn("details", "My name is Ali, 2026-10-12 at 10 am")
    rt.understand_turn("doctor", "Dr Ali")
    rt.understand_turn("corrected", "Not Dr Ali - Dr Ahmed")
    details = args() if tool == "book_appointment" else {
        "customer_phone": "+923001234567", "new_slot_start_time": "2026-10-12T10:00:00",
    }
    if service is not None:
        details["service_name"] = service
    action, payload = propose_or_confirm_write(ud, tool_name=tool, path="/write", raw_args=details, confirmation_id=None)
    assert action == "reject" and "doctor_name" in payload["needs_clarification"]
    rt.understand_turn("clarified", "Dr Ahmed")
    details["service_name"] = "Consultation with Dr Ahmed"
    action, _ = propose_or_confirm_write(ud, tool_name=tool, path="/write", raw_args=details, confirmation_id=None)
    assert action == "propose"
