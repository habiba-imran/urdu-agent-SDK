"""Unit tests for telephony repository queries using mock database cursor.

Phase 6 verification suite.
"""

from unittest.mock import MagicMock
from tenant_portal_api.telephony_queries import (
    assign_number_to_agent,
    get_active_telnyx_connection,
    release_call_quota_unpersisted,
    reserve_call_quota,
    upsert_telnyx_connection_verifying,
)


class FakeDbConn:
    def __init__(self):
        self.executed_queries = []
        self.rows_to_return = []

    def execute(self, query: str, params: tuple = ()):
        self.executed_queries.append((query.strip(), params))
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = (
            lambda: self.rows_to_return.pop(0) if self.rows_to_return else None
        )
        mock_cursor.fetchall.return_value = self.rows_to_return
        return mock_cursor


def test_get_active_telnyx_connection_found():
    conn = FakeDbConn()
    conn.rows_to_return = [
        (
            "conn_123",
            "tenant_abc",
            "My Telnyx",
            "active",
            "active",
            "fingerprint_123",
            "act_999",
            None,
            None,
            "enc_ref_123",
        )
    ]
    res = get_active_telnyx_connection(conn, "tenant_abc")
    assert res is not None
    assert res["id"] == "conn_123"
    assert res["platform_status"] == "active"
    assert res["encrypted_api_key_ref"] == "enc_ref_123"


def test_upsert_telnyx_connection_verifying():
    conn = FakeDbConn()
    conn.rows_to_return = [
        (
            "conn_new",
            "tenant_abc",
            "Label",
            "verifying",
            "fp_123",
            "2026-01-01T00:00:00Z",
        )
    ]
    res = upsert_telnyx_connection_verifying(
        conn, "tenant_abc", "Label", "fp_123", "enc_ref"
    )
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
    conn.rows_to_return = [(5,), (2,)]
    res = reserve_call_quota(conn, "tenant_abc")
    assert res is True
    assert "from tenants where id = %s" in conn.executed_queries[0][0].lower()
    assert "for update" not in conn.executed_queries[0][0].lower()
    assert "from quota_state where tenant_id = %s for update" in conn.executed_queries[2][0].lower()


def test_reserve_call_quota_exceeded():
    conn = FakeDbConn()
    conn.rows_to_return = [(5,), (5,)]
    res = reserve_call_quota(conn, "tenant_abc")
    assert res is False


def test_release_call_quota_unpersisted_decrements_concurrency():
    conn = FakeDbConn()
    release_call_quota_unpersisted(conn, "tenant_abc")
    assert len(conn.executed_queries) == 1
    query, params = conn.executed_queries[0]
    assert "update quota_state set concurrent_now = greatest(0, concurrent_now - 1)" in query.lower()
    assert params == ("tenant_abc",)
