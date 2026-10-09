"""Phase 3 deterministic planning and projection contracts."""

from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace

from livekit.agents.llm import ChatContext

from worker.humanization.context_projection import preview_ephemeral_context, project_context
from worker.humanization.state import ConversationState, GroundedValue, LanguageState, ToolCallState
from worker.humanization.turn_plan import TurnSignals, derive_turn_plan, signals_from_write_gate


def state(language="en"):
    return ConversationState("tenant_secret", "agent_secret", "session_secret", LanguageState(language), "webrtc")


def test_fixed_state_replays_provider_neutral_plan_in_english_urdu_and_mixed():
    for language, expected in (("en", "en"), ("ur-PK", "ur_pk"), ("mixed", "mixed")):
        current = state(language)
        current.repair_state.pending_field = "appointment_date"
        a = derive_turn_plan(current)
        b = derive_turn_plan(current)
        assert a == b
        assert a.dialogue_act == "REPAIR_CONFIRM"
        assert a.language_style == expected
        assert not any("groq" in str(value) or "cartesia" in str(value) for value in asdict(a).values())


def test_rule_precedence_uncertainty_repair_write_wait_and_simple_answer():
    current = state()
    current.grounding_state.unresolved_fields.append("phone")
    plan = derive_turn_plan(current, TurnSignals(user_correction=True, write_phase="caller_confirmed"))
    assert (plan.dialogue_act, plan.clarification_target, plan.tool_policy) == ("CLARIFY", "phone", "none")
    current.grounding_state.unresolved_fields.clear()
    plan = derive_turn_plan(current, TurnSignals(user_correction=True, write_phase="proposed"))
    assert (plan.dialogue_act, plan.tool_policy) == ("REPAIR_CONFIRM", "none")
    proposed = derive_turn_plan(current, TurnSignals(write_phase="proposed"))
    confirmed = derive_turn_plan(current, TurnSignals(write_phase="caller_confirmed"))
    assert (proposed.dialogue_act, proposed.question_policy, proposed.tool_policy) == (
        "CONFIRM_WRITE", "confirm_action", "confirmation_required",
    )
    assert (confirmed.dialogue_act, confirmed.tool_policy) == ("CONFIRM_WRITE", "gate_only")
    current.tool_state.calls["internal_id"] = ToolCallState("running", 1)
    assert derive_turn_plan(current).tool_policy == "wait"
    current.tool_state.calls.clear()
    assert derive_turn_plan(current, TurnSignals(simple_factual_answer=True)).response_budget in {"MICRO", "SHORT"}


def test_complaint_forbids_humor_laughter_and_write_gate_is_read_only():
    current = state()
    gate = SimpleNamespace(pending_write=object(), heard_affirmative=False)
    signals = signals_from_write_gate(gate)
    plan = derive_turn_plan(current, TurnSignals(
        write_phase=signals.write_phase, complaint_or_frustration=True,
    ))
    assert (plan.humor_permission, plan.laughter_permission) == ("forbidden", "forbidden")
    assert gate.heard_affirmative is False
    assert signals_from_write_gate(SimpleNamespace(pending_write=None, heard_affirmative=True)).write_phase == "none"


def test_projection_keeps_only_current_confirmed_facts_and_explicit_overflow():
    current = state("ur")
    current.task_state.critical_values["date"] = [
        GroundedValue("old_id", "Monday", "superseded"),
        GroundedValue("new_id", "Tuesday", "confirmed"),
    ]
    current.task_state.critical_values["phone"] = [GroundedValue("raw_id", "123", "heard")]
    current.grounding_state.unresolved_fields.append("phone")
    plan = derive_turn_plan(current)
    projection = project_context(current, plan)
    body = projection.data_text()
    assert projection.confirmed_facts == (("date", "Tuesday"),)
    for forbidden in ("Monday", "old_id", "new_id", "raw_id", "tenant_secret", "session_secret", "gladia"):
        assert forbidden not in body + projection.policy_text()
    assert projection.unresolved_fields == ("phone",)
    assert project_context(current, plan, max_facts=0).omitted_confirmed_facts == 1
    current.repair_state.pending_field = "date"
    assert project_context(current, derive_turn_plan(current)).recent_repair == ("date", "Monday")


def test_ephemeral_public_hook_preview_does_not_mutate_original_context():
    current = state()
    current.task_state.critical_values["service"] = [GroundedValue("id", "Dental cleaning", "confirmed")]
    projection = project_context(current, derive_turn_plan(current))
    ctx = ChatContext.empty()
    ctx.add_message(role="user", content="What do you offer?")
    before = [(item.role, item.text_content) for item in ctx.messages()]
    preview = preview_ephemeral_context(ctx, projection)
    after = [(item.role, item.text_content) for item in ctx.messages()]
    assert before == after
    assert len(preview.messages()) == len(before) + 2
    assert "Dental cleaning" in preview.messages()[-1].text_content
    assert "Dental cleaning" not in str(before)


def test_business_fact_projection_is_separate_bounded_data():
    current = state()
    business = (("business name", "Willow Clinic"), ("hours", "Monday to Friday"))
    projection = project_context(
        current, derive_turn_plan(current), business_facts=business, max_facts=1,
    )
    assert projection.business_facts == business[:1]
    assert projection.omitted_business_facts == 1
    assert "Willow Clinic" in projection.data_text()
    assert "Willow Clinic" not in projection.policy_text()
