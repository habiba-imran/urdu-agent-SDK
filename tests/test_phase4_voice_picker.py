"""Phase 4 tests — Voice Picker catalogue endpoint and SDK resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from control_plane.app import app as cp_app


def test_list_voices_endpoint():
    """Verify GET /v1/voices returns a non-empty list of enabled Urdu voices."""
    client = TestClient(cp_app)

    response = client.get("/v1/voices")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    first = data[0]
    assert "id" in first
    assert "displayName" in first
    assert "gender" in first
    assert "enabled" in first
    assert first["enabled"] is True


def test_voices_catalogue_contains_expected_urdu_voices():
    """Verify voices list contains standard expected Urdu voices (or fallback defaults)."""
    client = TestClient(cp_app)
    response = client.get("/v1/voices")
    data = response.json()

    voice_ids = [v["id"] for v in data]
    # Check that at least one recognizable Urdu voice ID is present
    assert any(
        vid in voice_ids
        for vid in [
            "v_meklc281",
            "helpdesk-agent",
            "street-vendor",
            "prime-time-anchor",
            "nosey-aunty",
            "jinn",
            "punjabi-masi",
        ]
    )
