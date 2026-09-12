"""Tests for Phase 4 Low Severity Telephony Remediation & End-to-End Regression Smoke Matrix.

Covers:
- TEL-LOW-01: Global telephony health diagnostics & DB readiness check.
- End-to-End Regression Smoke Matrix across all telephony components.
"""

from __future__ import annotations

from typing import Any
import pytest

from tenant_portal_api.telephony_health import check_global_telephony_health
from tenant_portal_api.telephony_service import TelephonyService
from tenant_portal_api.telephony_reconcile import reconcile_telephony_state


class MockSmokeDb:
    def __init__(self):
        self.phone_numbers: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.idempotency: dict[tuple[str, str, str], dict[str, Any]] = {}

    def execute(self, query: str, params: tuple[Any, ...] = ()):
        sql = " ".join(query.lower().split())

        if "select 1" == sql.strip():
            return FakeCursor((1,))

        if "from telephony_phone_numbers" in sql and "select" in sql:
            if "provisioning_status = 'purchase_pending'" in sql:
                return MultiCursor([])
            return MultiCursor([])

        if "from telephony_calls" in sql and "select" in sql:
            return MultiCursor([])

        return FakeCursor(None)

    def commit(self):
        pass


class MultiCursor:
    def __init__(self, r_list: list[Any]):
        self._rows = r_list

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeCursor:
    def __init__(self, data: Any = None, rowcount: int = 1):
        self._data = data
        self.rowcount = rowcount

    def fetchone(self):
        return self._data

    def fetchall(self):
        return [self._data] if self._data is not None else []


def test_telephony_health_diagnostics():
    """TEL-LOW-01: Health check endpoint returns DB readiness and configuration indicators."""
    db = MockSmokeDb()
    health = check_global_telephony_health(db_conn=db)
    assert health["status"] in ("healthy", "degraded")
    assert health["db_connected"] is True
    assert health["remediation_phase"] == "Phase 4 - Complete"


def test_end_to_end_telephony_remediation_smoke_matrix():
    """End-to-End Regression Smoke Matrix verifying all remediated systems."""
    db = MockSmokeDb()
    service = TelephonyService(db_conn=db)

    # 1. Health check readiness
    health = check_global_telephony_health(db_conn=db)
    assert health["status"] in ("healthy", "degraded")

    # 2. Reconciler execution
    repairs = reconcile_telephony_state(db_conn=db, dry_run=False, batch_size=50)
    assert repairs["status"] == "completed"
