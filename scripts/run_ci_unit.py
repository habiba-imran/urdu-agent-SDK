"""Run the offline CI unit suite listed in tests/ci_unit_manifest.txt (P4-H1)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "ci_unit_manifest.txt"


def main() -> int:
    # Force-empty DB URL so DB fixtures skip (not hang). control_plane.app allows
    # missing SUPABASE_DB_URL when CI_UNIT_FORCE_OFFLINE=1.
    os.environ["CI_UNIT_FORCE_OFFLINE"] = "1"
    os.environ["SUPABASE_DB_URL"] = ""
    if not (os.environ.get("TENANT_SECRET_ENCRYPTION_KEY") or "").strip():
        # Harmless test key — production must set a real one (M1-F01).
        os.environ["TENANT_SECRET_ENCRYPTION_KEY"] = "ci-unit-test-encryption-key"

    paths: list[str] = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path = ROOT / line
        if not path.exists():
            print(f"::warning::ci unit manifest path missing: {line}", file=sys.stderr)
            continue
        paths.append(str(path))

    if not paths:
        print("::error::ci unit manifest produced no paths", file=sys.stderr)
        return 2

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *paths,
        "-v",
        "--tb=short",
        "-m",
        "not live",
    ]
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
