"""Wave 2 — §3.1/§3.5/§5a narrative items: admin revocation, origin allowlist, webhook limit.

These three were named in the audit's prose rather than given an F-* id, and all three are
"the control exists but nothing can reach it": an admin token that outlived the account, an
origin allowlist nothing could set, and an unauthenticated endpoint with no rate limit.
"""

from __future__ import annotations

import datetime
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


# ------------------------------------------------------------ §3.5 admin token revocation


class _Row:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, row):
        self._row = row

    def execute(self, sql, params=None):
        return _Row(self._row)

    def rollback(self):
        pass


def _claims(issued_minutes_ago: int = 1) -> dict:
    issued = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        minutes=issued_minutes_ago
    )
    return {"sub": str(uuid.uuid4()), "iat": int(issued.timestamp())}


def test_active_admin_session_is_accepted():
    from admin.auth import assert_admin_session_valid

    assert_admin_session_valid(_Conn((None, None)), _claims())


def test_disabled_admin_token_is_refused():
    """§3.5: an 8-hour token kept working after the account should have been disabled."""
    from admin.auth import AdminAuthError, assert_admin_session_valid

    disabled = datetime.datetime.now(datetime.UTC)
    with pytest.raises(AdminAuthError) as excinfo:
        assert_admin_session_valid(_Conn((disabled, None)), _claims())
    assert excinfo.value.status == 401


def test_tokens_issued_before_revocation_are_refused():
    """Sign one admin out everywhere without rotating ADMIN_JWT_SECRET (which would sign
    out every admin)."""
    from admin.auth import AdminAuthError, assert_admin_session_valid

    revoked_at = datetime.datetime.now(datetime.UTC)
    with pytest.raises(AdminAuthError):
        assert_admin_session_valid(_Conn((None, revoked_at)), _claims(issued_minutes_ago=5))


def test_tokens_issued_after_revocation_still_work():
    from admin.auth import assert_admin_session_valid

    revoked_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=10)
    assert_admin_session_valid(_Conn((None, revoked_at)), _claims(issued_minutes_ago=1))


def test_missing_admin_row_is_refused():
    from admin.auth import AdminAuthError, assert_admin_session_valid

    with pytest.raises(AdminAuthError):
        assert_admin_session_valid(_Conn(None), _claims())


def test_revocation_fails_open_when_the_migration_is_not_applied():
    """0032 may not have landed yet; refusing every admin would be the worse failure."""
    import psycopg

    from admin.auth import assert_admin_session_valid

    class _OldSchemaConn(_Conn):
        def execute(self, sql, params=None):
            raise psycopg.errors.UndefinedColumn("column does not exist")

    assert_admin_session_valid(_OldSchemaConn(None), _claims())


# ------------------------------------------------------------- §3.1 origin allowlist setter


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://app.example.com", "https://app.example.com"),
        ("https://app.example.com/", "https://app.example.com"),
        ("  https://app.example.com  ", "https://app.example.com"),
        ("http://localhost:5173", "http://localhost:5173"),
    ],
)
def test_origins_are_normalized_to_header_shape(raw, expected):
    """The mint compares against the browser's Origin header, which is scheme://host[:port]
    with no path — a stored value of any other shape would silently never match."""
    from tenant_portal_api.app import _normalize_origin

    assert _normalize_origin(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "app.example.com",
        "https://app.example.com/path",
        "https://app.example.com?x=1",
        "ftp://app.example.com",
    ],
)
def test_malformed_origins_are_refused(bad):
    from fastapi import HTTPException

    from tenant_portal_api.app import _normalize_origin

    with pytest.raises(HTTPException):
        _normalize_origin(bad)


# --------------------------------------------------------------- §5a webhook rate limiting


def test_webhook_rate_limit_triggers_and_is_per_ip():
    from tenant_portal_api import telephony_webhooks as hooks

    hooks._webhook_hits.clear()
    ip = "203.0.113.7"
    for _ in range(hooks.WEBHOOK_RATE_LIMIT_PER_MIN):
        assert hooks._webhook_rate_limited(ip) is False
    assert hooks._webhook_rate_limited(ip) is True
    # A different sender is unaffected.
    assert hooks._webhook_rate_limited("198.51.100.4") is False
    hooks._webhook_hits.clear()


def test_webhook_rate_limit_memory_is_bounded(monkeypatch):
    from tenant_portal_api import telephony_webhooks as hooks

    hooks._webhook_hits.clear()
    monkeypatch.setattr(hooks, "_MAX_SEEN_ENTRIES", 100)
    for i in range(hooks._MAX_SEEN_ENTRIES + 250):
        hooks._webhook_rate_limited(f"10.0.0.{i}")
    assert len(hooks._webhook_hits) <= hooks._MAX_SEEN_ENTRIES
    hooks._webhook_hits.clear()
