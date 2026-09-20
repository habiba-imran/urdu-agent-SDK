"""F-C7 Phase E: write-tool gate + caller identity unit tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from worker.caller_identity import (
    remote_party_from_telephony_call,
    resolve_verified_caller_phone,
)
from worker.telephony_runtime import extract_sip_participant_attributes
from worker.tools import AgentUserdata
from worker.write_tool_gate import (
    check_ownership,
    make_idempotency_key,
    mark_write_success,
    max_write_tool_calls,
    note_user_turn,
    phones_match,
    propose_or_confirm_write,
    set_verified_caller_phone,
    validate_write_args,
)


def _ud(**kwargs) -> AgentUserdata:
    base = dict(
        tenant_id="t1",
        agent_id="a1",
        room_name="room-1",
    )
    base.update(kwargs)
    return AgentUserdata(**base)


def test_first_book_call_proposes_no_pending_http_fields():
    ud = _ud()
    action, payload = propose_or_confirm_write(
        ud,
        tool_name="book_appointment",
        path="/api/tools/book_slot",
        raw_args={
            "customer_name": "Ali",
            "customer_phone": "+923001234567",
            "slot_start_time": "2026-09-18T10:00:00",
        },
        confirmation_id=None,
    )
    assert action == "propose"
    assert payload["needs_confirmation"] is True
    assert payload["confirmation_id"]
    assert payload.get("success") is False


def test_confirm_bad_id_rejects():
    ud = _ud()
    propose_or_confirm_write(
        ud,
        tool_name="book_appointment",
        path="/api/tools/book_slot",
        raw_args={
            "customer_name": "Ali",
            "customer_phone": "03001234567",
            "slot_start_time": "2026-09-18T10:00:00",
        },
        confirmation_id=None,
    )
    note_user_turn(ud)
    action, payload = propose_or_confirm_write(
        ud,
        tool_name="book_appointment",
        path="/api/tools/book_slot",
        raw_args={
            "customer_name": "Ali",
            "customer_phone": "03001234567",
            "slot_start_time": "2026-09-18T10:00:00",
        },
        confirmation_id="not-the-real-id",
    )
    assert action == "reject"
    assert "confirmation_id" in payload["error"]


def test_confirm_same_turn_rejects():
    ud = _ud()
    action, propose = propose_or_confirm_write(
        ud,
        tool_name="book_appointment",
        path="/api/tools/book_slot",
        raw_args={
            "customer_name": "Ali",
            "customer_phone": "+923001234567",
            "slot_start_time": "2026-09-18T10:00:00",
        },
        confirmation_id=None,
    )
    assert action == "propose"
    action2, payload = propose_or_confirm_write(
        ud,
        tool_name="book_appointment",
        path="/api/tools/book_slot",
        raw_args={
            "customer_name": "Ali",
            "customer_phone": "+923001234567",
            "slot_start_time": "2026-09-18T10:00:00",
        },
        confirmation_id=propose["confirmation_id"],
    )
    assert action2 == "reject"
    assert "has not confirmed" in payload["error"]


def test_confirm_after_user_turn_allows_post():
    ud = _ud()
    _, propose = propose_or_confirm_write(
        ud,
        tool_name="book_appointment",
        path="/api/tools/book_slot",
        raw_args={
            "customer_name": "Ali",
            "customer_phone": "+923001234567",
            "slot_start_time": "2026-09-18T10:00:00",
        },
        confirmation_id=None,
    )
    note_user_turn(ud)
    action, payload = propose_or_confirm_write(
        ud,
        tool_name="book_appointment",
        path="/api/tools/book_slot",
        raw_args={
            "customer_name": "Ali",
            "customer_phone": "+923001234567",
            "slot_start_time": "2026-09-18T10:00:00",
        },
        confirmation_id=propose["confirmation_id"],
    )
    assert action == "confirm"
    assert payload["idempotency_key"]
    assert payload["normalized_args"]["customer_name"] == "Ali"


def test_cancel_without_verified_phone_rejects():
    ud = _ud()
    action, payload = propose_or_confirm_write(
        ud,
        tool_name="cancel_appointment",
        path="/api/tools/cancel_appointment",
        raw_args={"customer_phone": "+923001234567"},
        confirmation_id=None,
    )
    assert action == "reject"
    assert "verified_caller_phone" in payload["error"]


def test_cancel_mismatched_phone_rejects():
    ud = _ud()
    set_verified_caller_phone(ud, "+923001111111")
    action, payload = propose_or_confirm_write(
        ud,
        tool_name="cancel_appointment",
        path="/api/tools/cancel_appointment",
        raw_args={"customer_phone": "+923001234567"},
        confirmation_id=None,
    )
    assert action == "reject"
    assert "does not match" in payload["error"]


def test_cancel_matching_phone_proposes_then_confirms():
    ud = _ud()
    set_verified_caller_phone(ud, "+923001234567")
    action, propose = propose_or_confirm_write(
        ud,
        tool_name="cancel_appointment",
        path="/api/tools/cancel_appointment",
        raw_args={"customer_phone": "03001234567"},
        confirmation_id=None,
    )
    assert action == "propose"
    note_user_turn(ud)
    action2, payload = propose_or_confirm_write(
        ud,
        tool_name="cancel_appointment",
        path="/api/tools/cancel_appointment",
        raw_args={"customer_phone": "03001234567"},
        confirmation_id=propose["confirmation_id"],
    )
    assert action2 == "confirm"


def test_trunk_e164_must_not_satisfy_ownership_when_ani_differs():
    """Job trunk e164 must never be treated as verified caller."""
    # Resolve ignores e164_number on dispatch — only verified_caller_phone / ANI / remote party.
    phone = resolve_verified_caller_phone(
        dispatch_or_md={
            "e164_number": "+15551234567",  # trunk
            "from_number": "+15551234567",
        },
        participant=None,
        room_name=None,
        db_conn=None,
    )
    assert phone is None

    ud = _ud()
    # Even if someone wrongly set trunk as verified, cancel for a different ANI fails.
    set_verified_caller_phone(ud, "+15551234567")
    err = check_ownership(
        "cancel_appointment",
        {"customer_phone": "+923001234567"},
        ud.verified_caller_phone,
    )
    assert err is not None


def test_sip_ani_resolves_as_verified_not_trunk():
    participant = SimpleNamespace(
        metadata=None,
        attributes={
            "sip.trunkPhoneNumber": "+15551234567",
            "sip.phoneNumber": "+923009998887",
        },
    )
    phone = resolve_verified_caller_phone(
        dispatch_or_md={"e164_number": "+15551234567"},
        participant=participant,
        room_name=None,
        db_conn=None,
    )
    assert phone == "+923009998887"


def test_extract_sip_includes_caller_phone_number():
    attrs = extract_sip_participant_attributes(
        None,
        {"sip.phoneNumber": "+15105550100", "sip.trunkPhoneNumber": "+15551234567"},
    )
    assert attrs["caller_phone_number"] == "+15105550100"
    assert attrs["trunk_phone_number"] == "+15551234567"


def test_telephony_remote_party_inbound_outbound():
    assert (
        remote_party_from_telephony_call(
            direction="inbound",
            from_number="+923001111111",
            to_number="+15551234567",
        )
        == "+923001111111"
    )
    assert (
        remote_party_from_telephony_call(
            direction="outbound",
            from_number="+15551234567",
            to_number="+923002222222",
        )
        == "+923002222222"
    )


def test_invalid_schema_rejects():
    ud = _ud()
    action, payload = propose_or_confirm_write(
        ud,
        tool_name="book_appointment",
        path="/api/tools/book_slot",
        raw_args={
            "customer_name": "Ali",
            "customer_phone": "+923001234567",
            "slot_start_time": "not-iso",
            "extra_evil": "x",
        },
        confirmation_id=None,
    )
    assert action == "reject"
    assert "unexpected" in payload["error"] or "ISO" in payload["error"]


def test_budget_exceeded_rejects(monkeypatch):
    monkeypatch.setenv("UVA_MAX_WRITE_TOOL_CALLS", "1")
    assert max_write_tool_calls() == 1
    ud = _ud()
    set_verified_caller_phone(ud, "+923001234567")
    _, propose = propose_or_confirm_write(
        ud,
        tool_name="cancel_appointment",
        path="/api/tools/cancel_appointment",
        raw_args={"customer_phone": "+923001234567"},
        confirmation_id=None,
    )
    note_user_turn(ud)
    action, payload = propose_or_confirm_write(
        ud,
        tool_name="cancel_appointment",
        path="/api/tools/cancel_appointment",
        raw_args={"customer_phone": "+923001234567"},
        confirmation_id=propose["confirmation_id"],
    )
    assert action == "confirm"
    mark_write_success(
        ud,
        confirmation_id=propose["confirmation_id"],
        idempotency_key=payload["idempotency_key"],
        result={"success": True},
        tool_name="cancel_appointment",
        args_hash="x",
    )
    action2, payload2 = propose_or_confirm_write(
        ud,
        tool_name="cancel_appointment",
        path="/api/tools/cancel_appointment",
        raw_args={"customer_phone": "+923001234567"},
        confirmation_id=None,
    )
    assert action2 == "reject"
    assert "budget" in payload2["error"]


def test_idempotent_second_confirm_replays_without_new_key_change():
    ud = _ud()
    set_verified_caller_phone(ud, "+923001234567")
    _, propose = propose_or_confirm_write(
        ud,
        tool_name="cancel_appointment",
        path="/api/tools/cancel_appointment",
        raw_args={"customer_phone": "+923001234567"},
        confirmation_id=None,
    )
    note_user_turn(ud)
    _, conf = propose_or_confirm_write(
        ud,
        tool_name="cancel_appointment",
        path="/api/tools/cancel_appointment",
        raw_args={"customer_phone": "+923001234567"},
        confirmation_id=propose["confirmation_id"],
    )
    key = conf["idempotency_key"]
    from worker.write_tool_gate import args_hash as _ah

    digest = _ah("cancel_appointment", {"customer_phone": "+923001234567"})
    mark_write_success(
        ud,
        confirmation_id=propose["confirmation_id"],
        idempotency_key=key,
        result={"success": True, "voiceSummary": "cancelled"},
        tool_name="cancel_appointment",
        args_hash=digest,
    )
    action, replay = propose_or_confirm_write(
        ud,
        tool_name="cancel_appointment",
        path="/api/tools/cancel_appointment",
        raw_args={"customer_phone": "+923001234567"},
        confirmation_id=propose["confirmation_id"],
    )
    assert action == "replay"
    assert replay["success"] is True
    # Cross-tool reuse of same confirmation_id must not replay success.
    action_x, payload_x = propose_or_confirm_write(
        ud,
        tool_name="book_appointment",
        path="/api/tools/book_slot",
        raw_args={
            "customer_name": "Ali",
            "customer_phone": "+923001234567",
            "slot_start_time": "2026-09-18T10:00:00",
        },
        confirmation_id=propose["confirmation_id"],
    )
    assert action_x == "reject"
    assert "different action" in payload_x["error"]
    assert make_idempotency_key(
        tenant_id="t1",
        agent_id="a1",
        room_name="room-1",
        tool_name="cancel_appointment",
        normalized_args={"customer_phone": "+923001234567"},
        confirmation_id=propose["confirmation_id"],
    ) == key


def test_phones_match_variants():
    assert phones_match("+923001234567", "03001234567")
    assert phones_match("923001234567", "+923001234567")
    assert not phones_match("+923001234567", "+923009999999")


def test_validate_book_ok():
    args, err = validate_write_args(
        "book_appointment",
        {
            "customer_name": "Ali",
            "customer_phone": "+92-300-1234567",
            "slot_start_time": "2026-09-18T10:00:00+05:00",
        },
    )
    assert err is None
    assert args["customer_phone"] == "+923001234567"


@pytest.mark.asyncio
async def test_gated_write_posts_once(monkeypatch):
    """Integration: propose → user turn → confirm hits _post_client_tool once."""
    from worker import tools as tools_mod

    posts: list[dict] = []

    async def fake_post(ctx, *, path, payload, tool_name, idempotency_key=None):
        posts.append(
            {
                "path": path,
                "payload": payload,
                "tool_name": tool_name,
                "idempotency_key": idempotency_key,
            }
        )
        return {"success": True, "voiceSummary": "booked"}

    monkeypatch.setattr(tools_mod, "_post_client_tool", fake_post)

    ud = _ud(tools_base_url="http://example.test")
    ctx = SimpleNamespace(userdata=ud)

    r1 = await tools_mod.book_appointment.__wrapped__(
        ctx,
        customer_name="Ali",
        customer_phone="+923001234567",
        slot_start_time="2026-09-18T10:00:00",
    )
    assert r1.get("needs_confirmation") is True
    assert posts == []

    note_user_turn(ud)
    r2 = await tools_mod.book_appointment.__wrapped__(
        ctx,
        customer_name="Ali",
        customer_phone="+923001234567",
        slot_start_time="2026-09-18T10:00:00",
        confirmation_id=r1["confirmation_id"],
    )
    assert r2.get("success") is True
    assert len(posts) == 1
    assert posts[0]["idempotency_key"]

    # Replay — no second POST
    r3 = await tools_mod.book_appointment.__wrapped__(
        ctx,
        customer_name="Ali",
        customer_phone="+923001234567",
        slot_start_time="2026-09-18T10:00:00",
        confirmation_id=r1["confirmation_id"],
    )
    assert r3.get("success") is True
    assert len(posts) == 1


def test_parse_dispatch_preserves_verified_caller_phone():
    from worker.latency import parse_dispatch_metadata

    md = parse_dispatch_metadata(
        '{"tenant_id":"t","agent_id":"a","verified_caller_phone":"+923001234567","e164_number":"+1555"}'
    )
    assert md is not None
    assert md["verified_caller_phone"] == "+923001234567"
    assert "e164_number" not in md
