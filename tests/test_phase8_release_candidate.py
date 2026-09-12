from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_phase8_soak_doc_exists():
    doc = ROOT / "docs" / "PHASE8_SOAK_AND_RC.md"
    assert doc.exists()
    content = doc.read_text(encoding="utf-8")
    assert "Multiple Tenant Agents" in content
    assert "Concurrent Dashboard Usage" in content
    assert "Long-Running Browser Session" in content
    assert "Release Candidate Assembly" in content


def test_release_candidate_script_writes_manifest():
    out = subprocess.run(
        [sys.executable, "scripts/assemble_phase8_release_candidate.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "phase8_release_candidate.json" in out.stdout

    manifest_path = ROOT / "state" / "phase8_release_candidate.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["phase"] == 8
    assert manifest["track"] == "habiba"
    assert manifest["sdk"]["package_name"] == "@awaazlabs-uva/voice"
    assert manifest["sdk"]["version_candidate"] == "0.1.0"
    assert "/" in manifest["dashboard"]["routes"]
    assert "/agents" in manifest["dashboard"]["routes"]
    assert manifest["host_backend_starter"]["package_name"] == "host-backend-node"


def test_dashboard_phase8_routes_exist():
    for rel in (
        "dashboard/src/app/page.tsx",
        "dashboard/src/app/agents/page.tsx",
        "dashboard/src/app/credentials/page.tsx",
        "dashboard/src/app/sessions/page.tsx",
    ):
        assert (ROOT / rel).exists(), f"missing dashboard route file: {rel}"
