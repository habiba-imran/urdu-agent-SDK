"""Phase 8 tests — production readiness, deep health probe, load testing, and failure-recovery drill."""

from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane.app import app as cp_app  # noqa: E402
from bench.load_test import run_load_test  # noqa: E402
from scripts.simulate_worker_crash import run_failure_recovery_drill  # noqa: E402


def test_deep_health_check_endpoint():
    """Verify GET /healthz/deep returns status and infrastructure connectivity metadata."""
    client = TestClient(cp_app)

    response = client.get("/healthz/deep")
    assert response.status_code in (200, 503)

    data = response.json()
    assert "service" in data
    assert data["service"] == "uva-control-plane"
    assert "database" in data
    assert "livekit" in data


def test_load_test_harness_dry_run():
    """Verify bench/load_test.py executes cleanly for concurrent load simulation."""
    client = TestClient(cp_app)

    # Fast local test with TestClient
    res_1 = client.get("/healthz")
    assert res_1.status_code == 200

    # Run load test helper function
    stats = asyncio.run(run_load_test("http://testserver", concurrency=2, bursts=1))
    assert isinstance(stats, dict)
    assert "total_requests" in stats
    assert stats["total_requests"] == 2


def test_failure_recovery_drill():
    """Verify worker crash drill repairs stale open sessions and resets concurrency to zero."""
    result = run_failure_recovery_drill()
    assert result["success"] is True
    assert result["final_concurrency"] == 0
    assert result["end_reason"] in ("reconciled_stale", "stale_reconciled")
