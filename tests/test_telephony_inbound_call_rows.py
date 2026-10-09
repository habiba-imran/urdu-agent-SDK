"""A-01.4: inbound PSTN calls are persisted, reserved and released like outbound.

``resolve_inbound_sip_call`` used to reserve quota on a non-autocommit connection that
the worker closed without commit (rolled back) and never wrote a ``telephony_calls`` or
``sessions`` row, so inbound calls were absent from call history, unbilled, had no
recording link and no quota slot. These tests pin the committed transaction, the rows,
the idempotent re-resolution, failure handling, and the end-to-end worker close.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from worker import session_close  # noqa: E402
from worker.telephony_runtime import resolve_inbound_sip_call, resolve_session_metadata  # noqa: E402

from test_telephony_client_calling_simulation import ClientCallingSimulationDb, FakeCursor  # noqa: E402

ATTRS = {
    "sip.trunkPhoneNumber": "+18005550199",
    "sip.phoneNumber": "+14155550123",
    "sip.callID": "SCL_inbound_001",
    "sip.callIDFull": "SCL_inbound_001_full",
}


class TxDb(ClientCallingSimulationDb):
    """Simulation fake with commit/rollback semantics and the worker-close SQL surface."""

    def __init__(self):
        super().__init__()
        self.commits = 0
        self.rollbacks = 0
        self.fail_on: str | None = None
        self.sessions_quota_decrements = 0
        self.usage_events: list[tuple] = []
        self._snapshot()

    # --- transaction emulation -------------------------------------------------
    def _snapshot(self):
        self._saved = copy.deepcopy((self.calls, self.sessions, self.quota))

    def commit(self):
        self.commits += 1
        self._snapshot()

    def rollback(self):
        self.rollbacks += 1
        self.calls, self.sessions, self.quota = copy.deepcopy(self._saved)

    # --- SQL -------------------------------------------------------------------
    def execute(self, query: str, params: tuple[Any, ...] = ()):
        sql = " ".join(query.lower().split())
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError(f"injected failure on: {self.fail_on}")

        if "select id, session_id from telephony_calls" in sql and "direction = 'inbound'" in sql:
            c = next((x for x in self.calls if x.get("room_name") == params[0] and x.get("direction") == "inbound"), None)
            return FakeCursor((c["id"], c.get("session_id")) if c else None)

        # worker/session_close + telephony_queries.finalize_call surface
        if "update sessions set ended_at = now()" in sql and "returning id" in sql:
            s = next((s for s in self.sessions if s["room_name"] == params[-1] and s["ended_at"] is None), None)
            if not s:
                return FakeCursor(None)
            s["ended_at"] = "now"
            return FakeCursor((s["id"],))
        if "from telephony_calls" in sql and "where room_name = %s" in sql and "select id, tenant_id, platform_status" in sql:
            rows = [c for c in self.calls if c.get("room_name") == params[0]]
            c = rows[0] if rows else None
            return FakeCursor((c["id"], c["tenant_id"], c["platform_status"], c.get("quota_reserved_at"), c.get("quota_released_at")) if c else None)
        if "select platform_status from telephony_calls where id = %s" in sql:
            c = next((x for x in self.calls if x["id"] == params[0]), None)
            return FakeCursor((c["platform_status"],) if c else None)
        if "update quota_state set concurrent_now = greatest(concurrent_now - 1, 0)" in sql:
            self.sessions_quota_decrements += 1
            self.quota[params[0]] = max(0, self.quota.get(params[0], 0) - 1)
            return FakeCursor(None)
        if "insert into usage_events" in sql:
            self.usage_events.append(params)
            return FakeCursor(None)
        if "update telephony_calls set usage_recorded_at" in sql:
            for c in self.calls:
                if c["id"] == params[0]:
                    c["usage_recorded_at"] = "now"
            return FakeCursor(None)
        if "retention_until" in sql:
            return FakeCursor(None)
        if "update telephony_calls" in sql and "set platform_status = %s" in sql and "ended_at = coalesce(ended_at, now())" in sql:
            for c in self.calls:
                if c["id"] == params[-1]:
                    c["platform_status"] = params[0]
                    c["ended_at"] = "now"
            return FakeCursor(None)

        return super().execute(query, params)


def _resolve(db: TxDb, room: str | None = "sip-room-1", attrs: dict[str, str] | None = None):
    return resolve_inbound_sip_call(
        participant_attributes=attrs or ATTRS,
        db_conn=db,
        room_name=room,
    )


# ------------------------------------------------------------------ persistence


def test_inbound_resolution_persists_session_and_call_and_commits():
    db = TxDb()
    res = _resolve(db)

    assert res["tenant_id"] == "tenant_client_1"
    assert res["agent_id"] == "agent_voice_1"
    assert res["direction"] == "inbound"
    assert res["room_name"] == "sip-room-1"
    assert res["caller_phone_number"] == "+14155550123"
    assert res["telephony_call_id"] and res["session_id"]

    # The worker opens psycopg without autocommit; the reservation only survives if
    # resolution commits.
    assert db.commits == 1
    assert db.rollbacks == 0
    assert db.quota["tenant_client_1"] == 1

    assert db.sessions == [{
        "id": res["session_id"],
        "tenant_id": "tenant_client_1",
        "agent_id": "agent_voice_1",
        "room_name": "sip-room-1",
        "ended_at": None,
    }]
    call = db.calls[0]
    assert call["id"] == res["telephony_call_id"]
    assert call["session_id"] == res["session_id"]
    assert call["direction"] == "inbound"
    assert call["platform_status"] == "in_progress"
    assert call["room_name"] == "sip-room-1"
    assert call["from_number"] == "+14155550123"  # caller ANI
    assert call["to_number"] == "+18005550199"  # our number
    assert call["sip_trunk_phone_number"] == "+18005550199"
    assert call["phone_number_id"] == "num_client_1"
    assert call["livekit_sip_call_id"] == "SCL_inbound_001"
    assert call["livekit_sip_call_id_full"] == "SCL_inbound_001_full"
    assert call["quota_reserved_at"] is not None  # ledger entry for release paths


def test_inbound_insert_sql_shape():
    db = TxDb()
    seen: list[str] = []
    orig = db.execute

    def spy(q, p=()):
        seen.append(" ".join(q.lower().split()))
        return orig(q, p)

    db.execute = spy  # type: ignore[method-assign]
    _resolve(db)
    insert = next(s for s in seen if s.startswith("insert into telephony_calls"))
    assert "'inbound'" in insert
    assert "'in_progress'" in insert
    assert "quota_reserved_at" in insert and "answered_at" in insert and "started_at" in insert
    assert "case when %s then now() else null end" in insert
    # sessions row is written before the call row that references it
    assert seen.index(next(s for s in seen if s.startswith("insert into sessions"))) < seen.index(insert)


def test_inbound_re_resolution_for_same_room_reuses_row_without_second_reservation():
    db = TxDb()
    first = _resolve(db)
    second = _resolve(db)

    assert second["telephony_call_id"] == first["telephony_call_id"]
    assert second["session_id"] == first["session_id"]
    assert len(db.calls) == 1
    assert len(db.sessions) == 1
    assert db.quota["tenant_client_1"] == 1


def test_inbound_quota_exhausted_rejects_and_rolls_back():
    db = TxDb()
    db.quota["tenant_client_1"] = 2  # max_concurrent is 2
    db._snapshot()

    with pytest.raises(ValueError, match="concurrency limit reached"):
        _resolve(db)

    assert db.rollbacks == 1
    assert db.commits == 0
    assert db.calls == []
    assert db.sessions == []
    assert db.quota["tenant_client_1"] == 2


def test_inbound_persistence_failure_fails_open_and_rolls_back_reservation():
    db = TxDb()
    db.fail_on = "insert into telephony_calls"

    res = _resolve(db)

    # Caller is already connected: resolution still succeeds so the agent answers...
    assert res["tenant_id"] == "tenant_client_1"
    assert res["telephony_call_id"] is None
    assert res["session_id"] is None
    # ...but nothing half-written survives, and the reservation is not leaked.
    assert db.rollbacks == 1
    assert db.commits == 0
    assert db.calls == []
    assert db.sessions == []
    assert db.quota["tenant_client_1"] == 0


def test_inbound_without_room_name_keeps_legacy_reservation_only(caplog):
    import logging

    db = TxDb()
    with caplog.at_level(logging.WARNING, logger="worker.telephony_runtime"):
        res = _resolve(db, room=None)
    assert res["telephony_call_id"] is None
    assert db.calls == [] and db.sessions == []
    assert db.quota["tenant_client_1"] == 1
    assert db.commits == 1
    assert any("no room_name supplied" in r.message for r in caplog.records)


def test_inbound_unknown_number_writes_nothing():
    db = TxDb()
    with pytest.raises(ValueError, match="Unknown inbound phone number"):
        _resolve(db, attrs={**ATTRS, "sip.trunkPhoneNumber": "+10000000000"})
    assert db.calls == [] and db.sessions == []
    assert db.commits == 0


def test_resolve_session_metadata_threads_room_name_to_inbound():
    class P:
        metadata = "{}"
        attributes = dict(ATTRS)
        kind = "sip"
        identity = "sip_+14155550123"

    db = TxDb()
    resolved = resolve_session_metadata(participant=P(), db_conn=db, room_name="sip-room-9")
    assert resolved["tenant_id"] == "tenant_client_1"
    tele = resolved["telephony"]
    assert tele["direction"] == "inbound"
    assert tele["room_name"] == "sip-room-9"
    assert tele["telephony_call_id"] == db.calls[0]["id"]
    assert db.sessions[0]["room_name"] == "sip-room-9"


# ------------------------------------------------------- end-to-end worker close


def test_inbound_call_is_closed_billed_and_released_by_worker_shutdown():
    db = TxDb()
    res = _resolve(db)
    assert db.quota["tenant_client_1"] == 1

    out = session_close._release_on_conn(
        db,
        room_name="sip-room-1",
        tenant_id="tenant_client_1",
        elapsed_sec=95,
        end_reason="participant_disconnected",
        session_obj=None,
        transcript=[],
    )

    assert out.closed is True
    assert out.session_id == res["session_id"]
    assert out.telephony_call_id == res["telephony_call_id"]
    assert db.sessions[0]["ended_at"] == "now"

    call = db.calls[0]
    assert call["platform_status"] == "completed"
    assert call["ended_at"] == "now"
    assert call["quota_released_at"] is not None
    assert call["usage_recorded_at"] == "now"

    # released through the telephony ledger, not the sessions-style blind decrement
    assert out.quota_decremented is True
    assert db.quota["tenant_client_1"] == 0
    assert db.sessions_quota_decrements == 0

    # PSTN minutes billed against the linked session
    assert db.usage_events == [("tenant_client_1", res["session_id"], "agent_sec", 95.0)]
    assert out.usage_events == 1

    # second shutdown (or a late Telnyx hangup) cannot decrement again
    again = session_close._release_on_conn(
        db,
        room_name="sip-room-1",
        tenant_id="tenant_client_1",
        elapsed_sec=95,
        end_reason="participant_disconnected",
        session_obj=None,
        transcript=[],
    )
    assert again.closed is False
    assert again.quota_decremented is False
    assert db.quota["tenant_client_1"] == 0
    assert len(db.usage_events) == 1
