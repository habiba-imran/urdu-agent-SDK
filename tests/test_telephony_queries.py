"""Unit tests for telephony repository queries using mock database cursor.

Phase 6 verification suite.
"""

from unittest.mock import MagicMock
import pytest
from tenant_portal_api.telephony_queries import (
    assign_number_to_agent,
    disconnect_telnyx_connection,
    get_active_telnyx_connection,
    get_idempotency_key,
    list_managed_numbers,
    release_call_quota_once,
    reserve_call_quota,
    save_idempotency_key,
    upsert_telnyx_connection_verifying,
)


class FakeDbConn:
    def __init__(self):
        self.executed_queries = []
        self.rows_to_return = []

    def execute(self, query: str, params: tuple = ()):
        self.executed_queries.append((query.strip(), params))
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            self.rows_to_return.pop(0) if self.rows_to_return else None
        )
        mock_cursor.fetchall.return_value = self.rows_to_return
        return mock_cursor


def test_get_active_telnyx_connection_found():
    conn = FakeDbConn()
    conn.rows_to_return = [
        ("conn_123", "tenant_abc", "My Telnyx", "active", "active", "fingerprint_123", "act_999", None, None)
    ]
    res = get_active_telnyx_connection(conn, "tenant_abc")
    assert res is not None
    assert res["id"] == "conn_123"
    assert res["platform_status"] == "active"


def test_upsert_telnyx_connection_verifying():
    conn = FakeDbConn()
    conn.rows_to_return = [
        ("conn_new", "tenant_abc", "Label", "verifying", "fp_123", "2026-01-01T00:00:00Z")
    ]
    res = upsert_telnyx_connection_verifying(conn, "tenant_abc", "Label", "fp_123", "enc_ref")
    assert res["id"] == "conn_new"
    assert res["platform_status"] == "verifying"


def test_assign_number_to_agent_success():
    conn = FakeDbConn()
    # Agent check passes
    conn.rows_to_return = [("agent_123",)]
    res = assign_number_to_agent(conn, "tenant_abc", "num_456", "agent_123")
    assert res is True


def test_assign_number_to_agent_invalid_agent():
    conn = FakeDbConn()
    # Agent check fails (returns None)
    conn.rows_to_return = []
    res = assign_number_to_agent(conn, "tenant_abc", "num_456", "agent_invalid")
    assert res is False


def test_reserve_call_quota():
    conn = FakeDbConn()
    # Current concurrency = 2, max = 5
    conn.rows_to_return = [(2, 5)]
    res = reserve_call_quota(conn, "tenant_abc")
    assert res is True


def test_reserve_call_quota_exceeded():
    conn = FakeDbConn()
    # Current concurrency = 5, max = 5
    conn.rows_to_return = [(5, 5)]
    res = reserve_call_quota(conn, "tenant_abc")
    assert res is False
