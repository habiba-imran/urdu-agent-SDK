"""Phase 0 tests — healthz endpoints, CORS configuration, and session reconciliation script."""

from __future__ import annotations

import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane.app import app as cp_app
from admin.app import app as admin_app
try:
    from scripts.reconcile_sessions import reconcile_sessions
except ImportError:
    from reconcile_sessions import reconcile_sessions  # type: ignore # noqa: E402



def test_control_plane_healthz():
    """Verify GET /healthz on control plane returns 200 with service name."""
    client = TestClient(cp_app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "uva-control-plane"}


def test_admin_healthz():
    """Verify GET /healthz on admin backend returns 200 with service name."""
    client = TestClient(admin_app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "uva-admin"}


def test_reconcile_sessions_dry_run():
    """Verify reconcile_sessions runs cleanly in dry-run mode."""
    stats = reconcile_sessions(max_age_minutes=30, dry_run=True)
    assert isinstance(stats, dict)
    assert "stale_sessions_closed" in stats
    assert "tenants_reconciled" in stats
