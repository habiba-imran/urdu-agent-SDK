"""Wave 2 — control-plane hardening: F-H4, F-H5, F-H7, F-M11.

These assert the behaviour the fixes introduced and, where it matters, that the old hole is
closed: junk requests can no longer lock a tenant out of minting, the limiter's memory is
bounded, and a refresh can no longer keep a suspended tenant's call alive forever.

No database: the refresh gates take their connection from `mint_db_connection`, which is
monkeypatched with a fake whose query results each test controls.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture
def cp(monkeypatch):
    for var, value in {
        "LIVEKIT_URL": "wss://test.livekit.cloud",
        "LIVEKIT_API_KEY": "test-key",
        "LIVEKIT_API_SECRET": "test-secret",
        "SUPABASE_DB_URL": "postgresql://test:test@127.0.0.1:5432/test",
        "CP_TENANT_SECRETS": "{}",
        "CP_ALLOWED_ORIGINS": "https://app.example.com",
        "UVA_ENV": "development",
    }.items():
        monkeypatch.setenv(var, value)
    import importlib

    module = importlib.import_module("control_plane.app")
    module._hits.clear()
    yield module
    module._hits.clear()


# ------------------------------------------------------------------ F-H4 / rate limiting


def test_unauthenticated_requests_do_not_fill_the_tenant_bucket(cp, monkeypatch):
    """F-H4: _rate_limited(x_tenant_id) used to record a hit before any signature was
    checked, so 120 junk requests a minute locked the real tenant out of minting."""
    from fastapi.testclient import TestClient

    from control_plane.mint import MintError

    def always_unauthenticated(**kwargs):
        raise MintError(401, "bad signature")

    monkeypatch.setattr(cp, "mint_session", always_unauthenticated)
    monkeypatch.setattr(
        cp, "mint_db_connection", lambda **kw: contextlib.nullcontext(object())
    )
    # The rejection audit opens its own database connection per call; this test is about
    # the limiter, so keep it off the network.
    monkeypatch.setattr(cp, "record_mint_rejection", lambda *a, **k: None)
    client = TestClient(cp.app)
    tenant = "victim-tenant"

    for _ in range(cp.RATE_LIMIT_PER_MIN + 5):
        response = client.post(
            "/v1/session",
            json={"agent_id": "a"},
            headers={
                "X-Tenant-Id": tenant,
                "X-Timestamp": "1",
                "X-Nonce": "n",
                "X-Signature": "forged",
            },
        )
        # Never a 429 for the tenant: the attacker's own IP bucket is what fills up.
        assert response.status_code in (401, 429)

    # The victim's bucket must still be empty, because nothing authenticated.
    assert cp._rate_limit_exceeded(tenant, cp.RATE_LIMIT_PER_MIN) is False


def test_successful_mints_do_count_against_the_tenant(cp):
    tenant = "busy-tenant"
    for _ in range(cp.RATE_LIMIT_PER_MIN):
        cp._rate_limit_record(tenant)
    assert cp._rate_limit_exceeded(tenant, cp.RATE_LIMIT_PER_MIN) is True


def test_flooding_one_ip_stops_that_ip(cp):
    ip = "ip:203.0.113.9"
    for _ in range(cp.RATE_LIMIT_IP_PER_MIN):
        cp._rate_limit_record(ip)
    assert cp._rate_limit_exceeded(ip, cp.RATE_LIMIT_IP_PER_MIN) is True
    # A different caller is unaffected.
    assert cp._rate_limit_exceeded("ip:198.51.100.2", cp.RATE_LIMIT_IP_PER_MIN) is False


# --------------------------------------------------------------- F-H5 / bounded limiter


def test_limiter_memory_is_bounded(cp, monkeypatch):
    """F-H5: _hits was an unbounded defaultdict — one entry per distinct key, forever."""
    monkeypatch.setattr(cp, "_MAX_TRACKED_KEYS", 200)
    for i in range(cp._MAX_TRACKED_KEYS + 500):
        cp._rate_limit_record(f"key-{i}")
    assert len(cp._hits) <= cp._MAX_TRACKED_KEYS
    # The most recent callers are the ones kept.
    assert f"key-{cp._MAX_TRACKED_KEYS + 499}" in cp._hits


def test_expired_windows_are_dropped(cp, monkeypatch):
    import time as _time

    cp._rate_limit_record("old-key")
    assert "old-key" in cp._hits
    # Jump past the 60s window; the next record prunes stale buckets.
    real_time = _time.time
    monkeypatch.setattr(cp.time, "time", lambda: real_time() + 120)
    cp._rate_limit_record("new-key")
    assert "old-key" not in cp._hits


# ------------------------------------------------------------------- F-H7 / refresh gates


class _FakeConn:
    """Returns a queued result per execute() call, in query order."""

    def __init__(self, tenant_row, session_row, quota_row):
        self._rows = [tenant_row, session_row, quota_row]
        self.queries: list[str] = []

    def execute(self, sql, params=None):
        self.queries.append(sql)
        row = self._rows.pop(0) if self._rows else None

        class _Result:
            def fetchone(self_inner):
                return row

        return _Result()


def _patch_conn(cp, monkeypatch, conn):
    monkeypatch.setattr(
        cp, "mint_db_connection", lambda **kwargs: contextlib.nullcontext(conn)
    )


def test_refresh_allows_an_active_tenant_with_a_live_session(cp, monkeypatch):
    _patch_conn(cp, monkeypatch, _FakeConn(("active", 1000), (None,), (10,)))
    cp._enforce_refresh_gates(tenant_id="t", room="r")  # must not raise


def test_refresh_is_refused_for_a_suspended_tenant(cp, monkeypatch):
    """F-H7: 'the admin suspend control is not a stop control'."""
    from fastapi import HTTPException

    _patch_conn(cp, monkeypatch, _FakeConn(("suspended", 1000), (None,), (10,)))
    with pytest.raises(HTTPException) as excinfo:
        cp._enforce_refresh_gates(tenant_id="t", room="r")
    assert excinfo.value.status_code == 403


def test_refresh_is_refused_after_the_session_closed(cp, monkeypatch):
    import datetime

    from fastapi import HTTPException

    ended = datetime.datetime.now(datetime.UTC)
    _patch_conn(cp, monkeypatch, _FakeConn(("active", 1000), (ended,), (10,)))
    with pytest.raises(HTTPException) as excinfo:
        cp._enforce_refresh_gates(tenant_id="t", room="r")
    assert excinfo.value.status_code == 409


def test_refresh_is_refused_past_the_monthly_cap(cp, monkeypatch):
    from fastapi import HTTPException

    _patch_conn(cp, monkeypatch, _FakeConn(("active", 100), (None,), (100,)))
    with pytest.raises(HTTPException) as excinfo:
        cp._enforce_refresh_gates(tenant_id="t", room="r")
    assert excinfo.value.status_code == 429


def test_refresh_is_refused_for_an_unknown_tenant(cp, monkeypatch):
    from fastapi import HTTPException

    _patch_conn(cp, monkeypatch, _FakeConn(None, None, None))
    with pytest.raises(HTTPException) as excinfo:
        cp._enforce_refresh_gates(tenant_id="t", room="r")
    assert excinfo.value.status_code == 401


def test_refresh_fails_open_when_the_database_is_unreachable(cp, monkeypatch):
    """A database blip must not drop every live call at once."""

    def boom(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(cp, "mint_db_connection", boom)
    cp._enforce_refresh_gates(tenant_id="t", room="r")  # must not raise


def test_refresh_count_is_capped(cp):
    from fastapi import HTTPException

    assert cp._next_refresh_count({}) == 1
    assert cp._next_refresh_count({"refresh_count": 5}) == 6
    # Garbage in the metadata restarts the count rather than crashing the call.
    assert cp._next_refresh_count({"refresh_count": "nonsense"}) == 1
    with pytest.raises(HTTPException) as excinfo:
        cp._next_refresh_count({"refresh_count": cp.MAX_REFRESHES})
    assert excinfo.value.status_code == 403


# ------------------------------------------------------------------------ F-M11 / nonces


def test_nonce_purge_refuses_a_window_that_could_delete_a_live_nonce():
    """The mint's replay window is 60s; deleting inside it would re-open replay."""
    import subprocess

    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "purge_used_nonces.py"), "--older-than-minutes", "1"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode != 0
    assert "at least 5" in (out.stderr + out.stdout)
