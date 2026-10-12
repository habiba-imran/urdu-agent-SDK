"""Verify scanner exceptions do not hide credentials in future commits."""
from pathlib import Path
import json
import os
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")


def test_exact_historical_exception_keeps_future_findings_gating(tmp_path):
    scanner = shutil.which("gitleaks")
    local = ROOT / "tmp/publish-unblock/tools/gitleaks.exe"
    if not scanner and os.name == "nt" and local.exists():
        scanner = str(local)
    if not scanner:
        pytest.skip("Standalone Gitleaks CLI not installed; CI runs the Docker scanner gate")
    assert run(["git", "init", "--quiet"], tmp_path).returncode == 0
    shutil.copyfile(ROOT / ".gitleaks.toml", tmp_path / ".gitleaks.toml")
    fixture = tmp_path / "tests" / "test_mint.py"
    fixture.parent.mkdir()
    def commit(value):
        fixture.write_text('api_key = "' + value + '"\n')
        assert run(["git", "add", "tests/test_mint.py"], tmp_path).returncode == 0
        assert run(["git", "-c", "user.name=Scanner Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "Synthetic scanner fixture"], tmp_path).returncode == 0
    def scan():
        result = run([scanner, "git", ".", "--redact", "--no-banner", "--report-format=json", "--report-path=report.json", '--log-opts=--all'], tmp_path)
        rows = json.loads((tmp_path / "report.json").read_text())
        return result.returncode, rows
    commit("7a593f94c981e4b28d653e5ac12f903b")
    exit_code, first = scan()
    assert exit_code == 1 and len(first) == 1
    (tmp_path / ".gitleaksignore").write_text(first[0]["Fingerprint"] + "\n")
    assert scan()[0] == 0
    commit("41cb98bd652a0f379cc91be6535dba82")
    exit_code, second = scan()
    assert exit_code == 1 and len(second) == 1
    assert second[0]["Fingerprint"] != first[0]["Fingerprint"]
    assert second[0]["Secret"] == "REDACTED"
