"""Unit tests for F-H18 Phase C reconcile_sessions (no network)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from reconcile_sessions import reconcile_sessions  # noqa: E402


class FakeCursor:
    def __init__(self, db: "FakeReconcileDb") -> None:
        self.db = db
        self.rowcount = 0
        self._result: list[tuple] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.db.executed.append((sql, params))
        low = " ".join(sql.lower().split())
        params = params or ()

        if "select id, tenant_id, room_name, started_at" in low:
            # Stale open sessions older than max-age (caller already filtered in SQL;
            # fake DB returns precomputed stale list).
            self._result = list(self.db.stale_sessions)
            return

        if "update sessions" in low and "reconciled_stale" in low:
            if self.db.dry_run_guard:
                raise AssertionError("UPDATE sessions must not run in dry-run")
            self.rowcount = len(self.db.stale_sessions)
            # Mark those sessions closed so open-count query sees them gone.
            closed_ids = {row[0] for row in self.db.stale_sessions}
            self.db.open_sessions = [
                s for s in self.db.open_sessions if s["id"] not in closed_ids
            ]
            self.db.stale_sessions = []
            self._result = []
            return

        if "true_open_count" in low or (
            "from tenants" in low and "open_count" in low
        ):
            # Build tenant rows: (tenant_id, true_open, concurrent_now)
            counts: dict[str, int] = {}
            for s in self.db.open_sessions:
                counts[s["tenant_id"]] = counts.get(s["tenant_id"], 0) + 1
            rows = []
            for t_id in self.db.tenants:
                true_open = counts.get(t_id, 0)
                current = self.db.quota.get(t_id)
                rows.append((t_id, true_open, current))
            self._result = rows
            return

        if "insert into quota_state" in low:
            if self.db.dry_run_guard:
                raise AssertionError("INSERT quota_state must not run in dry-run")
            t_id, true_open = params[0], params[1]
            self.db.quota[t_id] = true_open
            self.db.quota_writes += 1
            self._result = []
            return

        self._result = []

    def fetchall(self) -> list[tuple]:
        return list(self._result)


class FakeReconcileDb:
    """In-memory stand-in for the two queries reconcile_sessions issues."""

    def __init__(
        self,
        *,
        tenants: list[str],
        open_sessions: list[dict[str, Any]],
        stale_sessions: list[tuple],
        quota: dict[str, int | None],
    ) -> None:
        self.tenants = tenants
        self.open_sessions = list(open_sessions)
        self.stale_sessions = list(stale_sessions)
        self.quota = dict(quota)
        self.executed: list[tuple[str, tuple | None]] = []
        self.quota_writes = 0
        self.dry_run_guard = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def test_reconcile_closes_stale_and_fixes_concurrent_now() -> None:
    tenant = "t-1"
    stale = ("sess-old", tenant, "room-old", "2026-01-01")
    db = FakeReconcileDb(
        tenants=[tenant],
        open_sessions=[
            {"id": "sess-old", "tenant_id": tenant},
            # Young open session should remain after stale close
            {"id": "sess-live", "tenant_id": tenant},
        ],
        stale_sessions=[stale],
        quota={tenant: 5},  # drifted high after crash
    )

    stats = reconcile_sessions(max_age_minutes=30, dry_run=False, conn=db)

    assert stats["stale_sessions_closed"] == 1
    assert stats["tenants_reconciled"] == 1
    assert stats["total_open_sessions_remaining"] == 1  # only sess-live
    assert db.quota[tenant] == 1
    assert db.quota_writes == 1
    assert any("reconciled_stale" in sql.lower() for sql, _ in db.executed)


def test_reconcile_dry_run_does_not_write() -> None:
    tenant = "t-1"
    stale = ("sess-old", tenant, "room-old", "2026-01-01")
    db = FakeReconcileDb(
        tenants=[tenant],
        open_sessions=[{"id": "sess-old", "tenant_id": tenant}],
        stale_sessions=[stale],
        quota={tenant: 3},
    )
    db.dry_run_guard = True

    stats = reconcile_sessions(max_age_minutes=30, dry_run=True, conn=db)

    assert stats["stale_sessions_closed"] == 1
    assert stats["tenants_reconciled"] == 1  # would fix 3 → 1
    assert db.quota[tenant] == 3  # unchanged
    assert db.quota_writes == 0
    assert not any("update sessions" in sql.lower() for sql, _ in db.executed)
    assert not any("insert into quota_state" in sql.lower() for sql, _ in db.executed)


def test_reconcile_noop_when_already_aligned() -> None:
    tenant = "t-1"
    db = FakeReconcileDb(
        tenants=[tenant],
        open_sessions=[{"id": "sess-live", "tenant_id": tenant}],
        stale_sessions=[],
        quota={tenant: 1},
    )

    stats = reconcile_sessions(max_age_minutes=30, dry_run=False, conn=db)

    assert stats["stale_sessions_closed"] == 0
    assert stats["tenants_reconciled"] == 0
    assert stats["total_open_sessions_remaining"] == 1
    assert db.quota_writes == 0


def test_reconcile_fixes_quota_even_without_stale_sessions() -> None:
    """Crash closed the row elsewhere but left concurrent_now high — still realign."""
    tenant = "t-1"
    db = FakeReconcileDb(
        tenants=[tenant],
        open_sessions=[],
        stale_sessions=[],
        quota={tenant: 2},
    )

    stats = reconcile_sessions(max_age_minutes=30, dry_run=False, conn=db)

    assert stats["stale_sessions_closed"] == 0
    assert stats["tenants_reconciled"] == 1
    assert stats["total_open_sessions_remaining"] == 0
    assert db.quota[tenant] == 0
