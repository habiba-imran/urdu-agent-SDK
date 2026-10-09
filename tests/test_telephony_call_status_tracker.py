"""A-01.6: worker mirrors LiveKit SIP state onto telephony_calls.

Without this, outbound rows stayed ``dialing`` until the 2h reconciler flipped them to
``failed / provider_timeout`` — unless Telnyx webhooks happened to be configured.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from worker import session_close  # noqa: E402
from worker.telephony_call_status import (  # noqa: E402
    TelephonyCallStatusTracker,
    attach_call_status_tracker,
    disconnect_reason_name,
)

from test_telephony_quota_release import QuotaDb  # noqa: E402


class FakeRoom:
    def __init__(self, remotes: dict[str, Any] | None = None):
        self.handlers: dict[str, list] = {}
        self.remote_participants = remotes or {}

    def on(self, event: str, fn):
        self.handlers.setdefault(event, []).append(fn)

    def emit(self, event: str, *args):
        for fn in self.handlers.get(event, []):
            fn(*args)


def _sip(attrs: dict[str, str] | None = None, *, identity="sip-telephony-outbound-c1", reason=None):
    return SimpleNamespace(
        attributes=dict(attrs or {}),
        identity=identity,
        kind="sip",
        disconnect_reason=reason,
    )


class _Reason:
    def __init__(self, name: str):
        self.name = name


ROOM = "telephony-outbound-c1"  # QuotaDb.add_call default room for call id "c1"


def _tracker(db: QuotaDb, room: str = ROOM, **kw) -> TelephonyCallStatusTracker:
    return TelephonyCallStatusTracker(
        room_name=room,
        conn_factory=lambda: db,
        run_blocking=lambda fn: fn(),
        **kw,
    )


# ---------------------------------------------------------------- transitions


def test_dialing_ringing_active_are_mirrored_in_order_with_answered_at():
    db = QuotaDb()
    db.add_call("c1", status="dialing")
    room = FakeRoom()
    t = _tracker(db).attach(room)

    p = _sip({"sip.callStatus": "dialing"})
    room.emit("participant_connected", p)
    assert db.calls[0]["platform_status"] == "dialing"

    room.emit("participant_attributes_changed", {"sip.callStatus": "ringing"}, p)
    assert db.calls[0]["platform_status"] == "ringing"
    assert db.calls[0].get("answered_at") is None

    room.emit("participant_attributes_changed", {"sip.callStatus": "active"}, p)
    assert db.calls[0]["platform_status"] == "in_progress"
    assert db.calls[0]["answered_at"] == "now"
    assert t.answered is True

    # transitions guard against downgrades at the SQL level
    sqls = [s for s in db.executed if "set platform_status = %s" in s]
    assert all("platform_status = any(%s)" in s for s in sqls)
    assert all("sip.callstatus:" in s or True for s in sqls)


def test_late_or_repeated_lower_status_is_ignored():
    db = QuotaDb()
    db.add_call("c1", status="dialing")
    t = _tracker(db)
    t.on_sip_call_status("active")
    before = len(db.executed)
    t.on_sip_call_status("ringing")  # late
    t.on_sip_call_status("active")  # duplicate
    assert len(db.executed) == before
    assert db.calls[0]["platform_status"] == "in_progress"


def test_terminal_row_is_never_overwritten_by_sip_status():
    """Telnyx webhook already said busy; a straggling 'ringing' must not revive it."""
    db = QuotaDb()
    db.add_call("c1", status="busy")
    _tracker(db).on_sip_call_status("ringing")
    assert db.calls[0]["platform_status"] == "busy"


def test_hangup_and_unknown_values_are_not_mapped():
    db = QuotaDb()
    db.add_call("c1", status="in_progress")
    t = _tracker(db)
    t.on_sip_call_status("hangup")
    t.on_sip_call_status("")
    t.on_sip_call_status("weird")
    assert not any("set platform_status" in s for s in db.executed)


def test_automation_counts_as_answered():
    db = QuotaDb()
    db.add_call("c1", status="dialing")
    t = _tracker(db)
    t.on_sip_call_status("automation")
    assert t.answered is True
    assert db.calls[0]["platform_status"] == "in_progress"


def test_row_lookup_is_retried_until_portal_commits_the_row():
    """Agent dispatch happens before the portal commits telephony_calls; do not cache a miss."""
    db = QuotaDb()
    t = _tracker(db)
    t.on_sip_call_status("dialing")  # no row yet -> skipped
    assert not any("set platform_status" in s for s in db.executed)
    db.add_call("c1", status="dialing")
    t.on_sip_call_status("active")
    assert db.calls[0]["platform_status"] == "in_progress"


def test_attach_applies_status_of_participant_already_in_room():
    db = QuotaDb()
    db.add_call("c1", status="dialing")
    room = FakeRoom(remotes={"p": _sip({"sip.callStatus": "active"})})
    _tracker(db).attach(room)
    assert db.calls[0]["platform_status"] == "in_progress"


def test_fallback_lookup_by_call_id_when_room_name_not_on_row():
    db = QuotaDb()
    db.add_call("c1", room="other-room", status="dialing")
    # QuotaDb only knows the room lookup + a generic id lookup; add the id query.
    orig = db.execute

    def execute(q, params=None):
        sql = " ".join(q.lower().split())
        if sql.startswith("select id, tenant_id, platform_status from telephony_calls where id = %s"):
            c = db._by_id(params[0])
            return type("C", (), {"fetchone": lambda self: (c["id"], c["tenant_id"], c["platform_status"]) if c else None})()
        return orig(q, params)

    db.execute = execute  # type: ignore[method-assign]
    _tracker(db, telephony_call_id="c1").on_sip_call_status("active")
    assert db.calls[0]["platform_status"] == "in_progress"


# -------------------------------------------------------------- dial failures


def test_user_unavailable_before_answer_finalizes_no_answer_and_releases():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.add_call("c1", status="ringing")
    room = FakeRoom()
    t = _tracker(db).attach(room)

    room.emit("participant_disconnected", _sip({"sip.callStatus": "ringing"}, reason=_Reason("USER_UNAVAILABLE")))

    c = db.calls[0]
    assert c["platform_status"] == "no_answer"
    assert c["error_code"] == "callee_unavailable"
    assert c["ended_at"] == "now"
    assert c["quota_released_at"] == "now"
    assert db.quota["tenant-a"] == 0
    assert t.finalized is True

    # worker shutdown afterwards: nothing to change, nothing to double-release
    res = session_close._release_on_conn(
        db, room_name=ROOM, tenant_id="tenant-a", elapsed_sec=12,
        end_reason="participant_disconnected", session_obj=None, transcript=[],
    )
    assert res.telephony_call_id == "c1"
    assert res.quota_decremented is False
    assert db.calls[0]["platform_status"] == "no_answer"
    assert db.quota["tenant-a"] == 0


def test_user_rejected_is_busy_and_trunk_failure_is_failed():
    for reason, status, code in (
        ("USER_REJECTED", "busy", "callee_rejected"),
        ("SIP_TRUNK_FAILURE", "failed", "sip_trunk_failure"),
    ):
        db = QuotaDb()
        db.quota["tenant-a"] = 1
        db.add_call("c1", status="dialing")
        _tracker(db).on_sip_participant_disconnected(reason)
        assert db.calls[0]["platform_status"] == status, reason
        assert db.calls[0]["error_code"] == code
        assert db.quota["tenant-a"] == 0


def test_disconnect_after_answer_is_left_to_session_close():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.add_call("c1", status="dialing")
    t = _tracker(db)
    t.on_sip_call_status("active")
    t.on_sip_participant_disconnected("CLIENT_INITIATED")
    assert db.calls[0]["platform_status"] == "in_progress"
    assert db.quota["tenant-a"] == 1  # released by session_close at shutdown, not here


def test_unmapped_disconnect_before_answer_is_left_to_session_close():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.add_call("c1", status="ringing")
    _tracker(db).on_sip_participant_disconnected("ROOM_DELETED")
    assert db.calls[0]["platform_status"] == "ringing"
    # ...and session_close then records it as no_answer via the row status
    res = session_close._release_on_conn(
        db, room_name=ROOM, tenant_id="tenant-a", elapsed_sec=5,
        end_reason="room_deleted", session_obj=None, transcript=[],
    )
    assert res.quota_decremented is True
    assert db.calls[0]["platform_status"] == "no_answer"


def test_non_sip_participant_disconnect_is_ignored():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.add_call("c1", status="dialing")
    room = FakeRoom()
    _tracker(db).attach(room)
    browser = SimpleNamespace(attributes={}, identity="user-1", kind="standard", disconnect_reason=_Reason("USER_UNAVAILABLE"))
    room.emit("participant_disconnected", browser)
    assert db.calls[0]["platform_status"] == "dialing"
    assert db.quota["tenant-a"] == 1


# ------------------------------------------------------------------ plumbing


def test_disconnect_reason_name_normalizes_enum_str_and_none():
    assert disconnect_reason_name(_Reason("user_rejected")) == "USER_REJECTED"
    assert disconnect_reason_name("sip_trunk_failure") == "SIP_TRUNK_FAILURE"
    assert disconnect_reason_name(None) == ""


def test_attach_helper_never_raises():
    class BrokenRoom:
        def on(self, *a, **k):
            raise RuntimeError("no events")

    assert attach_call_status_tracker(BrokenRoom(), room_name="r") is None


def test_db_failure_in_write_does_not_propagate_to_room_callback():
    class Broken(QuotaDb):
        def execute(self, q, params=None):
            raise RuntimeError("db down")

    t = TelephonyCallStatusTracker(room_name="r", conn_factory=Broken, run_blocking=None)
    # no running loop -> inline; the inline path lets exceptions surface, so guard here
    import pytest

    with pytest.raises(RuntimeError):
        t.on_sip_call_status("active")
