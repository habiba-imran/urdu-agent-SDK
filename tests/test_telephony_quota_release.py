"""A-01.2: every telephony quota reservation has a release path.

Covers the query-layer primitives (``finalize_call``, ``release_call_quota_once``,
``release_leaked_call_quota``), the outbound dial failure path, the worker-side close
(``worker/session_close``) for telephony rooms, the telephony reconciler and the
sessions reconciler's realignment query.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from tenant_portal_api import telephony_queries as queries  # noqa: E402
from tenant_portal_api.telephony_reconcile import reconcile_telephony_state  # noqa: E402
from tenant_portal_api.telephony_service import TelephonyService  # noqa: E402
from tenant_portal_api.livekit_sip import LiveKitSipClient  # noqa: E402
from worker import session_close  # noqa: E402

from test_telephony_client_calling_simulation import ClientCallingSimulationDb  # noqa: E402


# --------------------------------------------------------------------------- fakes


class _Cur:
    def __init__(self, rows: list[tuple] | None = None, rowcount: int = 0):
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class QuotaDb:
    """Minimal telephony_calls + quota_state fake keyed on the SQL fragments the
    release path emits. Records every executed statement for ordering assertions."""

    ACTIVE = ("queued", "dialing", "ringing", "in_progress")
    TERMINAL = ("completed", "busy", "no_answer", "failed", "cancelled")

    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self.quota: dict[str, int] = {}
        self.sessions: list[dict[str, Any]] = []
        self.executed: list[str] = []
        self.sessions_quota_decrements = 0
        self.usage_events: list[tuple] = []
        self.minutes: dict[str, float] = {}
        self.transcripts: dict[str, Any] = {}
        self.retention_updates = 0

    def add_call(
        self,
        call_id: str,
        tenant: str = "tenant-a",
        *,
        status: str = "dialing",
        room: str | None = None,
        reserved: bool = True,
        released: bool = False,
        stale: bool = False,
    ) -> dict[str, Any]:
        c = {
            "id": call_id,
            "tenant_id": tenant,
            "platform_status": status,
            "room_name": room or f"telephony-outbound-{call_id}",
            "quota_reserved_at": "T0" if reserved else None,
            "quota_released_at": "T1" if released else None,
            "ended_at": None,
            "duration_sec": None,
            "error_code": None,
            "error_message": None,
            "raw_livekit_sip_participant_status": None,
            "stale": stale,
        }
        self.calls.append(c)
        return c

    def _by_id(self, call_id: str) -> dict[str, Any] | None:
        return next((c for c in self.calls if c["id"] == call_id), None)

    def execute(self, query: str, params: tuple | list | None = None):
        sql = " ".join(query.lower().split())
        params = tuple(params or ())
        self.executed.append(sql)

        # --- sessions (worker close) ---
        if "update sessions set ended_at = now()" in sql and "returning id" in sql:
            room = params[-1]
            s = next((s for s in self.sessions if s["room_name"] == room and s["ended_at"] is None), None)
            if not s:
                return _Cur([])
            s["ended_at"] = "now"
            return _Cur([(s["id"],)])
        if "update sessions set transcript" in sql:
            self.transcripts[params[-1]] = params[0]
            return _Cur([])
        if "update quota_state set concurrent_now = greatest(concurrent_now - 1, 0)" in sql:
            self.sessions_quota_decrements += 1
            self.quota[params[0]] = max(0, self.quota.get(params[0], 0) - 1)
            return _Cur([])

        # --- best-effort extras (usage / minutes / retention) ---
        if "insert into usage_events" in sql:
            self.usage_events.append(params)
            return _Cur([])
        if "insert into quota_state" in sql and "minutes_this_month" in sql:
            self.minutes[params[0]] = self.minutes.get(params[0], 0.0) + params[1]
            return _Cur([])
        if "update telephony_calls set usage_recorded_at = now()" in sql:
            c = self._by_id(params[0])
            if c and c.get("usage_recorded_at") is None:
                c["usage_recorded_at"] = "now"
            return _Cur([])
        if "retention_until" in sql and "update" in sql:
            self.retention_updates += 1
            return _Cur([])
        if "from information_schema.columns" in sql:
            return _Cur([])

        # --- telephony_calls ---
        if "from telephony_calls" in sql and "where room_name = %s" in sql:
            rows = [c for c in self.calls if c["room_name"] == params[0]]
            return _Cur([(c["id"], c["tenant_id"], c["platform_status"], c["quota_reserved_at"], c["quota_released_at"]) for c in rows[:1]])

        if "select platform_status from telephony_calls where id = %s" in sql:
            c = self._by_id(params[0])
            return _Cur([(c["platform_status"],)] if c else [])

        if "update telephony_calls set quota_released_at = now()" in sql:
            c = self._by_id(params[0])
            if c and c["quota_released_at"] is None:
                c["quota_released_at"] = "now"
                return _Cur([(c["id"],)])
            return _Cur([])

        if "update quota_state set concurrent_now = greatest(0, concurrent_now - 1)" in sql:
            self.quota[params[0]] = max(0, self.quota.get(params[0], 0) - 1)
            return _Cur([])

        if "update telephony_calls" in sql and "set platform_status = %s" in sql:
            c = self._by_id(params[-1])
            if c and "platform_status = any(%s)" in sql and c["platform_status"] not in params[-2]:
                return _Cur([], rowcount=0)
            if c:
                c["platform_status"] = params[0]
                if "answered_at = coalesce(answered_at, now())" in sql:
                    c["answered_at"] = c.get("answered_at") or "now"
                c["raw_livekit_sip_participant_status"] = params[1] or c["raw_livekit_sip_participant_status"]
                c["error_code"] = params[2] or c["error_code"]
                c["error_message"] = params[3] or c["error_message"]
                if "ended_at = coalesce(ended_at, now())" in sql:
                    c["ended_at"] = c["ended_at"] or "now"
                    c["duration_sec"] = c["duration_sec"] if c["duration_sec"] is not None else 42
            return _Cur([])

        # reconciler: stale active calls
        if "select id, tenant_id from telephony_calls" in sql and "interval '2 hours'" in sql:
            rows = [c for c in self.calls if c["platform_status"] in self.ACTIVE and c["stale"]]
            return _Cur([(c["id"], c["tenant_id"]) for c in rows[: params[0]]])

        # reconciler / sweep: terminal but unreleased
        if "select id, tenant_id from telephony_calls" in sql and "quota_released_at is null" in sql:
            rows = [
                c for c in self.calls
                if c["platform_status"] in self.TERMINAL
                and c["quota_reserved_at"] is not None
                and c["quota_released_at"] is None
            ]
            return _Cur([(c["id"], c["tenant_id"]) for c in rows[: params[0]]])

        # reconciler: pending purchases
        if "from telephony_phone_numbers" in sql:
            return _Cur([])

        raise AssertionError(f"unexpected sql: {sql}")

    def commit(self):
        pass


# ------------------------------------------------------------ query primitives


def test_release_call_quota_once_is_atomic_and_idempotent():
    db = QuotaDb()
    db.quota["tenant-a"] = 2
    db.add_call("c1")

    assert queries.release_call_quota_once(db, "c1", "tenant-a") is True
    assert db.quota["tenant-a"] == 1
    assert queries.release_call_quota_once(db, "c1", "tenant-a") is False
    assert db.quota["tenant-a"] == 1
    # Guard and stamp are a single conditional UPDATE (safe on autocommit connections).
    stamping = [s for s in db.executed if "set quota_released_at = now()" in s]
    assert all("quota_released_at is null returning id" in s for s in stamping)
    assert not any(s.startswith("select quota_released_at") for s in db.executed)


def test_release_call_quota_once_unknown_call_is_noop():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    assert queries.release_call_quota_once(db, "missing", "tenant-a") is False
    assert db.quota["tenant-a"] == 1


def test_transition_call_status_ended_stamps_ended_at_and_duration():
    db = QuotaDb()
    db.add_call("c1", status="in_progress")
    queries.transition_call_status(db, "c1", "completed", ended=True)
    c = db.calls[0]
    assert c["platform_status"] == "completed"
    assert c["ended_at"] == "now"
    assert c["duration_sec"] == 42
    sql = db.executed[-1]
    assert "ended_at = coalesce(ended_at, now())" in sql
    # duration is talk time: 0 for a call that was never answered
    assert "case when answered_at is not null" in sql
    assert "now() - answered_at" in sql


def test_transition_call_status_without_ended_leaves_timestamps():
    db = QuotaDb()
    db.add_call("c1")
    queries.transition_call_status(db, "c1", "ringing")
    assert db.calls[0]["platform_status"] == "ringing"
    assert db.calls[0]["ended_at"] is None
    sql = db.executed[-1]
    assert "ended_at" not in sql
    assert "answered_at" not in sql
    assert "started_at = coalesce(started_at, now())" in sql


def test_transition_call_status_answered_and_only_from_guard():
    db = QuotaDb()
    db.add_call("c1", status="ringing")
    queries.transition_call_status(
        db, "c1", "in_progress", answered=True, only_from=("queued", "dialing", "ringing")
    )
    sql = db.executed[-1]
    assert "answered_at = coalesce(answered_at, now())" in sql
    assert "platform_status = any(%s) and id = %s" in sql
    assert db.calls[0]["platform_status"] == "in_progress"


def test_finalize_call_transitions_and_releases_once():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.add_call("c1", status="in_progress")

    out = queries.finalize_call(db, "c1", "tenant-a", "completed")
    assert out == {"found": True, "status_changed": True, "quota_released": True}
    assert db.calls[0]["platform_status"] == "completed"
    assert db.calls[0]["ended_at"] == "now"
    assert db.quota["tenant-a"] == 0

    # Second finalize (e.g. webhook after worker close) is a no-op on both axes.
    out2 = queries.finalize_call(db, "c1", "tenant-a", "failed", error_code="late")
    assert out2 == {"found": True, "status_changed": False, "quota_released": False}
    assert db.calls[0]["platform_status"] == "completed"
    assert db.quota["tenant-a"] == 0


def test_finalize_call_repairs_release_on_already_terminal_row():
    """Status already terminal (webhook wrote it) but the release was skipped: release only."""
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.add_call("c1", status="busy")

    out = queries.finalize_call(db, "c1", "tenant-a", "failed")
    assert out["status_changed"] is False
    assert out["quota_released"] is True
    assert db.calls[0]["platform_status"] == "busy"  # never downgraded / rewritten
    assert db.quota["tenant-a"] == 0


def test_finalize_call_missing_row_and_bad_status():
    db = QuotaDb()
    assert queries.finalize_call(db, "nope", "tenant-a", "failed") == {
        "found": False,
        "status_changed": False,
        "quota_released": False,
    }
    with pytest.raises(ValueError):
        queries.finalize_call(db, "nope", "tenant-a", "ringing")


def test_release_leaked_call_quota_only_touches_reserved_unreleased_terminal_rows():
    db = QuotaDb()
    db.quota["tenant-a"] = 3
    db.add_call("leak1", status="completed")                 # eligible
    db.add_call("leak2", status="failed")                    # eligible
    db.add_call("done", status="completed", released=True)   # already released
    db.add_call("never", status="completed", reserved=False)  # never reserved -> must not decrement
    db.add_call("live", status="in_progress")                # still active -> not a leak

    released = queries.release_leaked_call_quota(db, batch_size=100)
    assert released == 2
    assert db.quota["tenant-a"] == 1
    assert db._by_id("never")["quota_released_at"] is None
    assert db._by_id("live")["quota_released_at"] is None


def test_find_open_call_by_room():
    db = QuotaDb()
    db.add_call("c1", room="room-x", status="dialing")
    found = queries.find_open_call_by_room(db, "room-x")
    assert found == {
        "id": "c1",
        "tenant_id": "tenant-a",
        "platform_status": "dialing",
        "quota_reserved_at": "T0",
        "quota_released_at": None,
    }
    assert queries.find_open_call_by_room(db, "unknown") is None
    assert queries.find_open_call_by_room(db, "  ") is None


# ------------------------------------------------------- outbound dial failures


class _DispatchFailsClient(LiveKitSipClient):
    def create_agent_dispatch(self, *a, **k):
        raise RuntimeError("livekit unavailable")


def test_outbound_dispatch_failure_releases_reservation():
    db = ClientCallingSimulationDb()
    service = TelephonyService(
        db_conn=db,
        livekit_client_factory=lambda mock_mode: _DispatchFailsClient(mock_mode=True),
    )
    with pytest.raises(RuntimeError, match="livekit unavailable"):
        service.create_outbound_call(
            tenant_id="tenant_client_1",
            agent_id="agent_voice_1",
            from_number_id="num_client_1",
            to_number="+14155550999",
            idempotency_key="dispatch-fails-1",
        )
    assert db.quota["tenant_client_1"] == 0
    assert db.calls == []


def test_outbound_insert_stamps_quota_reserved_at():
    db = ClientCallingSimulationDb()
    seen: list[str] = []
    orig = db.execute

    def spy(query, params=()):
        seen.append(" ".join(query.lower().split()))
        return orig(query, params)

    db.execute = spy  # type: ignore[method-assign]
    service = TelephonyService(
        db_conn=db,
        livekit_client_factory=lambda mock_mode: LiveKitSipClient(mock_mode=True),
    )
    service.create_outbound_call(
        tenant_id="tenant_client_1",
        agent_id="agent_voice_1",
        from_number_id="num_client_1",
        to_number="+14155550999",
        idempotency_key="stamp-1",
    )
    insert = next(s for s in seen if s.startswith("insert into telephony_calls"))
    assert "quota_reserved_at" in insert
    assert "now(), %s)" in insert  # quota_reserved_at = now(), then session_id
    assert db.quota["tenant_client_1"] == 1


# ----------------------------------------------------- worker-side close (session_close)


def _close(db: QuotaDb, room: str, tenant: str = "tenant-a", reason: str = "normal", elapsed: int = 61):
    return session_close._release_on_conn(
        db,
        room_name=room,
        tenant_id=tenant,
        elapsed_sec=elapsed,
        end_reason=reason,
        session_obj=None,
        transcript=[],
    )


def test_session_close_releases_telephony_reservation_when_no_sessions_row():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.add_call("c1", room="telephony-outbound-abc", status="in_progress")

    res = _close(db, "telephony-outbound-abc")

    assert res.closed is False
    assert res.session_id is None
    assert res.telephony_call_id == "c1"
    assert res.quota_decremented is True
    assert db.quota["tenant-a"] == 0
    c = db.calls[0]
    assert c["platform_status"] == "completed"
    assert c["ended_at"] == "now"
    assert c["quota_released_at"] == "now"
    assert c["raw_livekit_sip_participant_status"] == "worker_shutdown:normal"
    # Release went through the ledgered path, not the sessions-style blind decrement.
    assert db.sessions_quota_decrements == 0


def test_session_close_telephony_release_is_idempotent_against_webhook():
    db = QuotaDb()
    db.quota["tenant-a"] = 0  # webhook already released and set terminal status
    db.add_call("c1", room="r1", status="completed", released=True)

    res = _close(db, "r1")
    assert res.telephony_call_id == "c1"
    assert res.quota_decremented is False
    assert db.quota["tenant-a"] == 0
    assert db.calls[0]["platform_status"] == "completed"


def test_session_close_unanswered_stale_close_marks_failed():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.add_call("c1", room="r1", status="dialing")

    res = _close(db, "r1", reason="stale_orphan_dispatch")
    assert res.quota_decremented is True
    c = db.calls[0]
    assert c["platform_status"] == "failed"
    assert c["error_code"] == "worker_shutdown"
    assert db.quota["tenant-a"] == 0


def test_session_close_no_sessions_row_still_applies_retention_to_call():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.add_call("c1", room="r1", status="in_progress")
    _close(db, "r1")
    assert db.retention_updates >= 1
    assert db.usage_events == []  # no session to attribute usage to


# ------------------------------------------- A-01.3: outbound call with a sessions row


def _linked_call(db: QuotaDb, call_id: str = "c1", room: str = "telephony-outbound-abc", status: str = "in_progress"):
    db.sessions.append({"id": f"sess-{call_id}", "room_name": room, "ended_at": None})
    return db.add_call(call_id, room=room, status=status)


def test_session_close_linked_call_bills_transcribes_and_releases_via_ledger():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    _linked_call(db)

    res = session_close._release_on_conn(
        db,
        room_name="telephony-outbound-abc",
        tenant_id="tenant-a",
        elapsed_sec=125,
        end_reason="normal",
        session_obj=None,
        transcript=[{"role": "user", "text": "hello", "at": 1}],
    )

    # sessions row closed and transcript attached, exactly like a browser session
    assert res.closed is True
    assert res.session_id == "sess-c1"
    assert db.sessions[0]["ended_at"] == "now"
    assert res.transcript_attached is True
    assert "telephony-outbound-abc" in db.transcripts

    # quota released through the telephony ledger, never the blind sessions decrement
    assert res.telephony_call_id == "c1"
    assert res.quota_decremented is True
    assert db.quota["tenant-a"] == 0
    assert db.sessions_quota_decrements == 0
    c = db.calls[0]
    assert c["platform_status"] == "completed"
    assert c["ended_at"] == "now"
    assert c["quota_released_at"] == "now"

    # PSTN minutes are now billed: usage_events row + monthly minutes + call stamped
    assert res.usage_events == 1
    assert db.usage_events == [("tenant-a", "sess-c1", "agent_sec", 125.0)]
    assert db.minutes["tenant-a"] == pytest.approx(125 / 60.0)
    assert c["usage_recorded_at"] == "now"
    assert db.retention_updates >= 1


def test_session_close_linked_call_webhook_already_released_no_double_decrement():
    """Telnyx hangup released first; worker close must still bill but not decrement again."""
    db = QuotaDb()
    db.quota["tenant-a"] = 0
    _linked_call(db, status="completed")
    db.calls[0]["quota_released_at"] = "T1"

    res = session_close._release_on_conn(
        db,
        room_name="telephony-outbound-abc",
        tenant_id="tenant-a",
        elapsed_sec=30,
        end_reason="normal",
        session_obj=None,
        transcript=[],
    )
    assert res.closed is True
    assert res.quota_decremented is False
    assert db.quota["tenant-a"] == 0
    assert db.sessions_quota_decrements == 0
    assert db.calls[0]["platform_status"] == "completed"
    assert res.usage_events == 1
    assert db.minutes["tenant-a"] == pytest.approx(0.5)


def test_session_close_linked_call_adopts_row_tenant_for_billing():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    _linked_call(db)

    res = session_close._release_on_conn(
        db,
        room_name="telephony-outbound-abc",
        tenant_id="",
        elapsed_sec=60,
        end_reason="normal",
        session_obj=None,
        transcript=[],
    )
    assert res.quota_decremented is True
    assert db.quota["tenant-a"] == 0
    assert db.usage_events == [("tenant-a", "sess-c1", "agent_sec", 60.0)]
    assert db.minutes["tenant-a"] == pytest.approx(1.0)


def test_session_close_linked_call_second_close_is_noop_for_quota_and_usage():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    _linked_call(db)
    kwargs = dict(room_name="telephony-outbound-abc", tenant_id="tenant-a", elapsed_sec=10, end_reason="normal", session_obj=None, transcript=[])

    r1 = session_close._release_on_conn(db, **kwargs)
    r2 = session_close._release_on_conn(db, **kwargs)
    assert r1.closed and r1.quota_decremented
    assert not r2.closed and not r2.quota_decremented
    assert r2.telephony_call_id == "c1"
    assert db.quota["tenant-a"] == 0
    assert len(db.usage_events) == 1


def test_session_close_never_answered_call_is_no_answer_not_completed():
    """A-01.6: a call still dialing/ringing at shutdown was never answered."""
    for status in ("queued", "dialing", "ringing"):
        db = QuotaDb()
        db.quota["tenant-a"] = 1
        db.add_call("c1", room="r1", status=status)
        res = _close(db, "r1", reason="participant_disconnected")
        assert res.quota_decremented is True
        assert db.calls[0]["platform_status"] == "no_answer", status
        assert db.calls[0]["error_code"] is None
        assert db.quota["tenant-a"] == 0


def test_session_close_unknown_room_is_still_a_noop():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    res = _close(db, "browser-room-with-no-rows")
    assert res.closed is False
    assert res.telephony_call_id is None
    assert res.quota_decremented is False
    assert db.quota["tenant-a"] == 1


def test_session_close_browser_session_path_unchanged():
    """A browser room (sessions row, no telephony_calls row) still uses the plain decrement."""
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.sessions.append({"id": "s1", "room_name": "web-1", "ended_at": None})

    res = _close(db, "web-1")
    assert res.closed is True
    assert res.session_id == "s1"
    assert res.quota_decremented is True
    assert res.telephony_call_id is None
    assert db.sessions_quota_decrements == 1
    assert db.quota["tenant-a"] == 0
    assert db.usage_events == [("tenant-a", "s1", "agent_sec", 61.0)]
    # the only telephony_calls touch is the room lookup (and retention), never a release
    assert not any("quota_released_at = now()" in s for s in db.executed)


def test_session_close_uses_row_tenant_when_metadata_tenant_missing():
    db = QuotaDb()
    db.quota["tenant-a"] = 1
    db.add_call("c1", room="r1", status="in_progress")
    res = _close(db, "r1", tenant="")
    assert res.quota_decremented is True
    assert db.quota["tenant-a"] == 0


def test_session_close_telephony_lookup_failure_does_not_raise():
    class Broken(QuotaDb):
        def execute(self, query, params=None):
            sql = " ".join(query.lower().split())
            if "from telephony_calls" in sql:
                raise RuntimeError("db down")
            return super().execute(query, params)

    db = Broken()
    res = _close(db, "r1")
    assert res.telephony_call_id is None
    assert res.quota_decremented is False


# ------------------------------------------------------------ telephony reconciler


def test_reconciler_stale_call_releases_quota_and_counts_repair():
    db = QuotaDb()
    db.quota["tenant-a"] = 2
    db.add_call("stale1", status="dialing", stale=True)
    db.add_call("fresh", status="dialing")

    repairs = reconcile_telephony_state(db_conn=db, dry_run=False, batch_size=50)

    assert repairs["status"] == "completed"
    assert repairs["stale_calls_cleaned"] == 1
    assert repairs["quota_leaks_repaired"] == 1
    stale = db._by_id("stale1")
    assert stale["platform_status"] == "failed"
    assert stale["error_code"] == "provider_timeout"
    assert stale["ended_at"] == "now"
    assert stale["quota_released_at"] == "now"
    assert db._by_id("fresh")["platform_status"] == "dialing"
    assert db.quota["tenant-a"] == 1


def test_reconciler_sweeps_terminal_unreleased_rows():
    db = QuotaDb()
    db.quota["tenant-a"] = 2
    db.add_call("leak", status="completed")
    db.add_call("ok", status="completed", released=True)

    repairs = reconcile_telephony_state(db_conn=db, dry_run=False, batch_size=50)
    assert repairs["quota_leaks_found"] == 1
    assert repairs["quota_leaks_repaired"] == 1
    assert db._by_id("leak")["quota_released_at"] == "now"
    assert db.quota["tenant-a"] == 1


def test_reconciler_dry_run_reports_without_mutating():
    db = QuotaDb()
    db.quota["tenant-a"] = 2
    db.add_call("stale1", status="dialing", stale=True)
    db.add_call("leak", status="completed")

    repairs = reconcile_telephony_state(db_conn=db, dry_run=True, batch_size=50)
    assert repairs["dry_run"] is True
    assert repairs["stale_calls_cleaned"] == 1
    assert repairs["quota_leaks_found"] == 1
    assert repairs["quota_leaks_repaired"] == 0
    assert db.quota["tenant-a"] == 2
    assert db._by_id("stale1")["platform_status"] == "dialing"
    assert db._by_id("leak")["quota_released_at"] is None
    assert not any(s.startswith("update") for s in db.executed)


def test_reconciler_stale_call_already_released_is_not_double_counted():
    db = QuotaDb()
    db.quota["tenant-a"] = 0
    db.add_call("stale1", status="dialing", stale=True, released=True)

    repairs = reconcile_telephony_state(db_conn=db, dry_run=False, batch_size=50)
    assert repairs["stale_calls_cleaned"] == 1
    assert repairs["quota_leaks_repaired"] == 0
    assert db._by_id("stale1")["platform_status"] == "failed"
    assert db.quota["tenant-a"] == 0


# ------------------------------------------------- sessions reconciler realignment


def test_reconcile_sessions_counts_outstanding_telephony_reservations():
    from reconcile_sessions import reconcile_sessions

    class Cur:
        def __init__(self, db):
            self.db = db
            self.rowcount = 0
            self._rows: list[tuple] = []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def execute(self, sql, params=None):
            low = " ".join(sql.lower().split())
            self.db.executed.append(low)
            if "select id, tenant_id, room_name, started_at" in low:
                self.db.stale_select_sql = low
                # one stale browser session so the UPDATE path is exercised
                self._rows = [("sess-old", "tenant-a", "room-old", "2026-01-01")]
                return
            if "update sessions" in low and "reconciled_stale" in low:
                self.db.stale_update_sql = low
                self.rowcount = 1
                self._rows = []
                return
            if "from usage_events" in low:
                self._rows = [(1,)]  # already billed -> skip backfill
                return
            if "true_open_count" in low:
                self.db.realign_sql = low
                # Mirror the real query: sessions + outstanding telephony reservations.
                self._rows = [("tenant-a", 1 + 2, 0)]
                return
            if "insert into quota_state" in low:
                self.db.writes.append(params)
                return
            self._rows = []

        def fetchall(self):
            return list(self._rows)

        def fetchone(self):
            return self._rows[0] if self._rows else None

    class Db:
        def __init__(self):
            self.executed: list[str] = []
            self.writes: list[tuple] = []
            self.realign_sql = ""
            self.stale_select_sql = ""
            self.stale_update_sql = ""

        def cursor(self):
            return Cur(self)

        def commit(self):
            pass

        def rollback(self):
            pass

    db = Db()
    reconcile_sessions(max_age_minutes=30, dry_run=False, conn=db)

    assert "from telephony_calls" in db.realign_sql
    assert "quota_reserved_at is not null" in db.realign_sql
    assert "quota_released_at is null" in db.realign_sql
    assert "coalesce(s.open_count, 0) + coalesce(c.open_count, 0)" in db.realign_sql
    # A-01.3: a call's own sessions row must not be counted on top of its reservation.
    assert "not exists" in db.realign_sql
    assert "tc.session_id = s.id" in db.realign_sql
    assert db.writes == [("tenant-a", 3)]

    # A-01.5: the 30-minute stale close must not touch the sessions row of a live call;
    # both the SELECT (report) and the UPDATE (apply) carry the same exclusion.
    for sql in (db.stale_select_sql, db.stale_update_sql):
        assert sql, "stale query not issued"
        assert "not exists" in sql
        assert "tc.session_id = s.id" in sql
        assert "tc.quota_reserved_at is not null" in sql
        assert "tc.quota_released_at is null" in sql
        assert "tc.platform_status in ('queued', 'dialing', 'ringing', 'in_progress')" in sql
    assert "reconciled_stale" in db.stale_update_sql
