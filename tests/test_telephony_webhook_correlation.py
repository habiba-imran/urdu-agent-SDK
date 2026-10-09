"""A-01.1: Telnyx call.* webhooks must correlate to telephony_calls by provider ids.

Before this fix the handler compared Telnyx ``call_control_id`` against LiveKit's
``livekit_sip_call_id`` — different id spaces — so no call event ever updated a row.
Offline: fake connection, no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from tenant_portal_api import telephony_call_correlation as corr
from tenant_portal_api.telephony_webhooks import _apply_webhook_side_effects

NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


class _Cur:
    def __init__(self, rows: list[tuple] | None):
        self._rows = rows or []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    """Minimal telephony_calls / telnyx_sip_connections / quota_state model."""

    def __init__(self, *, columns_present: bool = True):
        self.calls: list[dict[str, Any]] = []
        self.sip_connections: list[dict[str, Any]] = []
        self.quota: dict[str, int] = {}
        self.columns_present = columns_present
        self.sql_log: list[str] = []

    @staticmethod
    def _digits(s: Any) -> str:
        return "".join(ch for ch in str(s or "") if ch.isdigit())

    def execute(self, query: str, params: tuple = ()):
        sql = " ".join(query.lower().split())
        self.sql_log.append(sql)

        if "from information_schema.columns" in sql:
            return _Cur([(1,)] if self.columns_present else [])

        if "from telnyx_sip_connections" in sql:
            c = next(
                (x for x in self.sip_connections if x["provider_sip_connection_id"] == params[0]),
                None,
            )
            return _Cur([(c["tenant_id"],)] if c else [])

        if "select id, tenant_id from telephony_calls" in sql and "provider_call_control_id = %s" in sql:
            assert self.columns_present, "queried provider column without migration"
            c = next((x for x in self.calls if x.get("provider_call_control_id") == params[0]), None)
            return _Cur([(c["id"], c["tenant_id"])] if c else [])

        if "select id, tenant_id from telephony_calls" in sql and "provider_call_session_id = %s" in sql:
            assert self.columns_present
            c = next((x for x in self.calls if x.get("provider_call_session_id") == params[0]), None)
            return _Cur([(c["id"], c["tenant_id"])] if c else [])

        if "select id, tenant_id from telephony_calls" in sql and "livekit_sip_call_id = %s" in sql:
            c = next(
                (
                    x
                    for x in self.calls
                    if x.get("livekit_sip_call_id") == params[0]
                    or x.get("livekit_sip_call_id_full") == params[1]
                ),
                None,
            )
            return _Cur([(c["id"], c["tenant_id"])] if c else [])

        if "select id, tenant_id, created_at" in sql and "provider_call_control_id is null" in sql:
            assert self.columns_present
            window_min, from_d, to_d = params[0], params[1], params[2]
            rest = list(params[3:])
            direction = rest.pop(0) if "and direction = %s" in sql else None
            tenant = rest.pop(0) if "and tenant_id = %s" in sql else None
            out = []
            for c in self.calls:
                if c.get("provider_call_control_id") is not None:
                    continue
                if c.get("platform_status") not in corr.ACTIVE_STATUSES:
                    continue
                if NOW - c["created_at"] > timedelta(minutes=window_min):
                    continue
                if self._digits(c.get("from_number")) != from_d or self._digits(c.get("to_number")) != to_d:
                    continue
                if direction and c.get("direction") != direction:
                    continue
                if tenant and c.get("tenant_id") != tenant:
                    continue
                out.append(c)
            out.sort(key=lambda c: c["created_at"], reverse=True)
            return _Cur([(c["id"], c["tenant_id"], c["created_at"]) for c in out[:5]])

        if "update telephony_calls" in sql and "set provider_call_control_id = %s" in sql:
            for c in self.calls:
                if c["id"] == params[-1] and c.get("provider_call_control_id") is None:
                    c["provider_call_control_id"] = params[0]
                    c["provider_call_session_id"] = params[1]
                    c["provider_call_leg_id"] = params[2]
                    return _Cur([(c["id"],)])
            return _Cur([])

        if "update telephony_calls set quota_released_at" in sql:
            for c in self.calls:
                if c["id"] == params[0] and c.get("quota_released_at") is None:
                    c["quota_released_at"] = NOW
                    return _Cur([(c["id"],)])
            return _Cur([])

        if "update quota_state set concurrent_now = greatest(0, concurrent_now - 1)" in sql:
            self.quota[params[0]] = max(0, self.quota.get(params[0], 0) - 1)
            return _Cur([])

        if "update telephony_calls" in sql and "set platform_status" in sql:
            mapped, target = params[0], params[-1]
            terminal = {"completed", "busy", "no_answer", "failed", "cancelled"}
            for c in self.calls:
                if c["id"] == target:
                    if c.get("platform_status") in terminal and mapped not in terminal:
                        pass
                    else:
                        c["platform_status"] = mapped
            return _Cur([])

        raise AssertionError(f"unexpected sql: {sql}")


def _call(
    call_id: str,
    *,
    tenant: str = "tenant-a",
    direction: str = "outbound",
    from_number: str = "+18005550199",
    to_number: str = "+14155550777",
    status: str = "dialing",
    created_at: datetime = NOW - timedelta(seconds=20),
    provider_cc: str | None = None,
) -> dict[str, Any]:
    return {
        "id": call_id,
        "tenant_id": tenant,
        "direction": direction,
        "from_number": from_number,
        "to_number": to_number,
        "platform_status": status,
        "created_at": created_at,
        "livekit_sip_call_id": f"SCL_{call_id}",
        "livekit_sip_call_id_full": f"SCL_{call_id}_full",
        "provider_call_control_id": provider_cc,
        "quota_released_at": None,
    }


def _telnyx(event_type: str, **payload: Any) -> dict[str, Any]:
    return {"data": {"event_type": event_type, "id": "evt-1", "payload": payload}}


@pytest.fixture(autouse=True)
def _reset_probe():
    corr.reset_column_probe()
    yield
    corr.reset_column_probe()


# --- identity extraction -------------------------------------------------------------------


def test_extract_identity_from_telnyx_body():
    ident = corr.extract_call_identity(
        _telnyx(
            "call.answered",
            call_control_id="v3:cc",
            call_session_id="sess",
            call_leg_id="leg",
            connection_id="conn-1",
            direction="outgoing",
            **{"from": "+1 (800) 555-0199", "to": "sip:+14155550777@sip.telnyx.com"},
            start_time="2026-10-07T12:00:00Z",
        )
    )
    assert ident.call_control_id == "v3:cc"
    assert ident.call_session_id == "sess"
    assert ident.call_leg_id == "leg"
    assert ident.connection_id == "conn-1"
    assert ident.direction == "outbound"
    assert ident.from_digits == "18005550199"
    assert ident.to_digits == "14155550777"
    assert ident.started_at == NOW


def test_extract_identity_tolerates_missing_fields():
    ident = corr.extract_call_identity({"data": {"payload": {}}})
    assert not ident.has_provider_id
    assert ident.direction is None
    assert ident.from_digits == "" and ident.to_digits == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+14155550777", "14155550777"),
        ("sip:+14155550777@sip.telnyx.com", "14155550777"),
        ("tel:+1-415-555-0777;ext=1", "14155550777"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_phone_digits(raw, expected):
    assert corr.normalize_phone_digits(raw) == expected


def test_map_provider_direction():
    assert corr.map_provider_direction("outgoing") == "outbound"
    assert corr.map_provider_direction("incoming") == "inbound"
    assert corr.map_provider_direction("sideways") is None


# --- resolution ------------------------------------------------------------------------------


def test_livekit_id_is_not_treated_as_telnyx_id():
    """The original bug: feeding call_control_id against livekit_sip_call_id."""
    conn = FakeConn()
    conn.calls.append(_call("c1"))
    ident = corr.extract_call_identity(_telnyx("call.hangup", call_control_id="v3:unknown"))
    assert corr.resolve_call_for_event(conn, ident) is None
    assert conn.calls[0]["platform_status"] == "dialing"


def test_first_event_binds_by_direction_and_numbers():
    conn = FakeConn()
    conn.calls.append(_call("c1"))
    ident = corr.extract_call_identity(
        _telnyx(
            "call.initiated",
            call_control_id="v3:cc1",
            call_session_id="s1",
            call_leg_id="l1",
            direction="outgoing",
            **{"from": "+18005550199", "to": "+14155550777"},
        )
    )
    assert corr.resolve_call_for_event(conn, ident) == ("c1", "tenant-a")
    assert conn.calls[0]["provider_call_control_id"] == "v3:cc1"
    assert conn.calls[0]["provider_call_session_id"] == "s1"
    assert conn.calls[0]["provider_call_leg_id"] == "l1"


def test_later_events_match_bound_provider_id_without_numbers():
    conn = FakeConn()
    conn.calls.append(_call("c1", provider_cc="v3:cc1"))
    ident = corr.extract_call_identity(_telnyx("call.hangup", call_control_id="v3:cc1"))
    assert corr.resolve_call_for_event(conn, ident) == ("c1", "tenant-a")
    # no bind attempted
    assert not any("set provider_call_control_id" in s for s in conn.sql_log)


def test_session_id_matches_when_control_id_differs():
    conn = FakeConn()
    row = _call("c1", provider_cc="v3:leg-a")
    row["provider_call_session_id"] = "sess-1"
    conn.calls.append(row)
    ident = corr.extract_call_identity(
        _telnyx("call.hangup", call_control_id="v3:leg-b", call_session_id="sess-1")
    )
    assert corr.resolve_call_for_event(conn, ident) == ("c1", "tenant-a")


def test_direction_mismatch_does_not_bind():
    conn = FakeConn()
    conn.calls.append(_call("c1", direction="outbound"))
    ident = corr.extract_call_identity(
        _telnyx(
            "call.initiated",
            call_control_id="v3:cc1",
            direction="incoming",
            **{"from": "+18005550199", "to": "+14155550777"},
        )
    )
    assert corr.resolve_call_for_event(conn, ident) is None
    assert conn.calls[0]["provider_call_control_id"] is None


def test_number_mismatch_does_not_bind():
    conn = FakeConn()
    conn.calls.append(_call("c1"))
    ident = corr.extract_call_identity(
        _telnyx(
            "call.initiated",
            call_control_id="v3:cc1",
            direction="outgoing",
            **{"from": "+18005550199", "to": "+14155559999"},
        )
    )
    assert corr.resolve_call_for_event(conn, ident) is None


def test_stale_calls_outside_window_do_not_bind():
    conn = FakeConn()
    conn.calls.append(_call("old", created_at=NOW - timedelta(minutes=corr.BIND_WINDOW_MINUTES + 1)))
    ident = corr.extract_call_identity(
        _telnyx(
            "call.initiated",
            call_control_id="v3:cc1",
            direction="outgoing",
            **{"from": "+18005550199", "to": "+14155550777"},
        )
    )
    assert corr.resolve_call_for_event(conn, ident) is None


def test_terminal_calls_do_not_bind():
    conn = FakeConn()
    conn.calls.append(_call("done", status="completed"))
    ident = corr.extract_call_identity(
        _telnyx(
            "call.initiated",
            call_control_id="v3:cc1",
            direction="outgoing",
            **{"from": "+18005550199", "to": "+14155550777"},
        )
    )
    assert corr.resolve_call_for_event(conn, ident) is None


def test_connection_id_scopes_bind_to_tenant():
    conn = FakeConn()
    conn.sip_connections.append({"provider_sip_connection_id": "conn-b", "tenant_id": "tenant-b"})
    conn.calls.append(_call("a1", tenant="tenant-a"))
    conn.calls.append(_call("b1", tenant="tenant-b", created_at=NOW - timedelta(seconds=40)))
    ident = corr.extract_call_identity(
        _telnyx(
            "call.initiated",
            call_control_id="v3:cc-b",
            connection_id="conn-b",
            direction="outgoing",
            **{"from": "+18005550199", "to": "+14155550777"},
        )
    )
    assert corr.resolve_call_for_event(conn, ident) == ("b1", "tenant-b")
    assert conn.calls[0]["provider_call_control_id"] is None
    assert conn.calls[1]["provider_call_control_id"] == "v3:cc-b"


def test_ambiguous_candidates_without_timestamp_refuse_to_bind():
    conn = FakeConn()
    conn.calls.append(_call("c1", created_at=NOW - timedelta(seconds=10)))
    conn.calls.append(_call("c2", created_at=NOW - timedelta(seconds=50)))
    ident = corr.extract_call_identity(
        _telnyx(
            "call.initiated",
            call_control_id="v3:cc1",
            direction="outgoing",
            **{"from": "+18005550199", "to": "+14155550777"},
        )
    )
    assert corr.resolve_call_for_event(conn, ident) is None
    assert all(c["provider_call_control_id"] is None for c in conn.calls)


def test_ambiguous_candidates_pick_nearest_to_start_time():
    conn = FakeConn()
    conn.calls.append(_call("recent", created_at=NOW - timedelta(seconds=5)))
    conn.calls.append(_call("older", created_at=NOW - timedelta(seconds=60)))
    ident = corr.extract_call_identity(
        _telnyx(
            "call.initiated",
            call_control_id="v3:cc1",
            direction="outgoing",
            start_time=(NOW - timedelta(seconds=58)).isoformat(),
            **{"from": "+18005550199", "to": "+14155550777"},
        )
    )
    assert corr.resolve_call_for_event(conn, ident) == ("older", "tenant-a")


def test_bind_race_falls_back_to_exact_lookup():
    """Two events for the same call race: the loser must still resolve the row."""
    conn = FakeConn()
    conn.calls.append(_call("c1"))
    ident = corr.extract_call_identity(
        _telnyx(
            "call.initiated",
            call_control_id="v3:cc1",
            direction="outgoing",
            **{"from": "+18005550199", "to": "+14155550777"},
        )
    )
    orig_bind = corr.bind_provider_ids

    def _racing_bind(c, call_id, i):
        # Simulate another process binding first.
        orig_bind(c, call_id, i)
        return False

    corr_bind = corr.bind_provider_ids
    try:
        corr.bind_provider_ids = _racing_bind  # type: ignore[assignment]
        assert corr.resolve_call_for_event(conn, ident) == ("c1", "tenant-a")
    finally:
        corr.bind_provider_ids = corr_bind  # type: ignore[assignment]


def test_legacy_livekit_match_still_works():
    """Mock LiveKit ids may coincide with what a test feeds as call_control_id."""
    conn = FakeConn()
    conn.calls.append(_call("c1"))
    ident = corr.extract_call_identity(_telnyx("call.hangup", call_control_id="SCL_c1"))
    assert corr.resolve_call_for_event(conn, ident) == ("c1", "tenant-a")


def test_pre_migration_database_degrades_to_legacy_only():
    conn = FakeConn(columns_present=False)
    conn.calls.append(_call("c1"))
    ident = corr.extract_call_identity(
        _telnyx(
            "call.initiated",
            call_control_id="v3:cc1",
            direction="outgoing",
            **{"from": "+18005550199", "to": "+14155550777"},
        )
    )
    # No provider-column query may be issued (FakeConn asserts), and nothing binds.
    assert corr.resolve_call_for_event(conn, ident) is None
    assert corr.extract_call_identity(_telnyx("call.hangup", call_control_id="SCL_c1"))
    assert corr.resolve_call_for_event(
        conn, corr.extract_call_identity(_telnyx("call.hangup", call_control_id="SCL_c1"))
    ) == ("c1", "tenant-a")


def test_event_without_any_identity_is_ignored():
    conn = FakeConn()
    conn.calls.append(_call("c1"))
    ident = corr.extract_call_identity(_telnyx("call.hangup"))
    assert corr.resolve_call_for_event(conn, ident) is None
    assert conn.sql_log == []


# --- side effects through the webhook module -------------------------------------------------


def test_side_effects_full_lifecycle_releases_quota_once():
    conn = FakeConn()
    conn.quota["tenant-a"] = 1
    conn.calls.append(_call("c1"))

    _apply_webhook_side_effects(
        conn,
        "call.answered",
        _telnyx(
            "call.answered",
            call_control_id="v3:cc1",
            direction="outgoing",
            **{"from": "+18005550199", "to": "+14155550777"},
        ),
    )
    assert conn.calls[0]["platform_status"] == "in_progress"
    assert conn.calls[0]["provider_call_control_id"] == "v3:cc1"
    assert conn.quota["tenant-a"] == 1

    _apply_webhook_side_effects(
        conn, "call.hangup", _telnyx("call.hangup", call_control_id="v3:cc1", hangup_cause="normal_clearing")
    )
    assert conn.calls[0]["platform_status"] == "completed"
    assert conn.calls[0]["quota_released_at"] is not None
    assert conn.quota["tenant-a"] == 0

    # Duplicate / retried terminal event: no second decrement.
    _apply_webhook_side_effects(conn, "call.hangup", _telnyx("call.hangup", call_control_id="v3:cc1"))
    assert conn.quota["tenant-a"] == 0


def test_side_effects_prefer_caller_supplied_match():
    conn = FakeConn()
    conn.calls.append(_call("c1"))
    _apply_webhook_side_effects(
        conn,
        "call.answered",
        _telnyx("call.answered", call_control_id="v3:anything"),
        matched_call=("c1", "tenant-a"),
    )
    assert conn.calls[0]["platform_status"] == "in_progress"
    assert not any("from information_schema" in s for s in conn.sql_log)


def test_side_effects_unmatched_event_touches_nothing():
    conn = FakeConn()
    conn.quota["tenant-a"] = 1
    conn.calls.append(_call("c1"))
    _apply_webhook_side_effects(conn, "call.hangup", _telnyx("call.hangup", call_control_id="v3:ghost"))
    assert conn.calls[0]["platform_status"] == "dialing"
    assert conn.quota["tenant-a"] == 1
    assert not any("set platform_status" in s for s in conn.sql_log)


def test_side_effects_ringing_maps_to_ringing():
    conn = FakeConn()
    conn.calls.append(_call("c1", provider_cc="v3:cc1"))
    _apply_webhook_side_effects(conn, "call.ringing", _telnyx("call.ringing", call_control_id="v3:cc1"))
    assert conn.calls[0]["platform_status"] == "ringing"


def test_side_effects_real_shaped_normal_hangup_is_completed():
    """Telnyx sends state/hangup_cause/sip_hangup_cause, not status — must still map cleanly."""
    conn = FakeConn()
    conn.quota["tenant-a"] = 1
    conn.calls.append(_call("c1", provider_cc="v3:cc1"))
    _apply_webhook_side_effects(
        conn,
        "call.hangup",
        _telnyx(
            "call.hangup",
            call_control_id="v3:cc1",
            state="hangup",
            hangup_cause="normal_clearing",
            hangup_source="callee",
            sip_hangup_cause="200",
        ),
    )
    assert conn.calls[0]["platform_status"] == "completed"
    assert conn.quota["tenant-a"] == 0


def test_side_effects_failed_hangup_releases_quota():
    conn = FakeConn()
    conn.quota["tenant-a"] = 1
    conn.calls.append(_call("c1", provider_cc="v3:cc1"))
    _apply_webhook_side_effects(
        conn,
        "call.hangup",
        _telnyx("call.hangup", call_control_id="v3:cc1", hangup_cause="user_busy", sip_response_code="486"),
    )
    assert conn.calls[0]["platform_status"] == "busy"
    assert conn.quota["tenant-a"] == 0
