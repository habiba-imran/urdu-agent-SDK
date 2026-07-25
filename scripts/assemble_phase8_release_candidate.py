#!/usr/bin/env python3
"""Assemble a Phase 8 release-candidate manifest.

Collects the concrete artifacts Habiba owns for Phase 8:
- SDK version candidate
- dashboard route inventory
- host-backend starter metadata
- optional staging URL / release tag annotations
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_head() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        return out or None
    except Exception:
        return None


def build_manifest() -> dict:
    sdk_pkg = _read_json(ROOT / "sdk" / "package.json")
    dashboard_pkg = _read_json(ROOT / "dashboard" / "package.json")
    host_pkg = _read_json(ROOT / "examples" / "host-backend-node" / "package.json")

    dashboard_routes = [
        "/",
        "/agents",
        "/credentials",
        "/sessions",
    ]

    tarballs = sorted(p.name for p in (ROOT / "sdk").glob("*.tgz"))

    return {
        "phase": 8,
        "track": "habiba",
        "git_commit": _git_head(),
        "sdk": {
            "package_name": sdk_pkg["name"],
            "version_candidate": sdk_pkg["version"],
            "tarballs": tarballs,
            "has_dist": (ROOT / "sdk" / "dist").exists(),
        },
        "dashboard": {
            "package_name": dashboard_pkg["name"],
            "local_url": "http://localhost:3000",
            "staging_url": os.environ.get("PHASE8_DASHBOARD_STAGING_URL"),
            "routes": dashboard_routes,
        },
        "host_backend_starter": {
            "package_name": host_pkg["name"],
            "version": host_pkg["version"],
            "tag_or_ref": os.environ.get("PHASE8_HOST_BACKEND_TAG"),
            "path": "examples/host-backend-node",
        },
        "notes": os.environ.get("PHASE8_NOTES"),
    }


def main() -> int:
    manifest = build_manifest()
    STATE.mkdir(exist_ok=True)
    out_path = STATE / "phase8_release_candidate.json"
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
