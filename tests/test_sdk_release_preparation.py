"""Execute release/deploy checks locally with synthetic hooks; no deployment or publishing."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.safe_load(
        (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    )


def git_bash():
    if os.name != "nt":
        executable = shutil.which("bash")
    else:
        git = shutil.which("git")
        executable = str(Path(git).parents[1] / "bin/bash.exe") if git else None
    if not executable or not Path(executable).exists():
        pytest.skip("Git Bash/bash is needed to execute workflow shell contracts")
    return executable


def run_shell(script, cwd, **overrides):
    env = {**os.environ, **overrides}
    return subprocess.run(
        [git_bash(), "--noprofile", "--norc", "-c", script],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def deploy_steps():
    return workflow("deploy-staging.yml")["jobs"]["deploy-staging"]["steps"]


def fake_deploy_run(tmp_path, *, absent=None, failing=None):
    # Override curl in the shell itself: no subprocess or network connection can occur.
    stub = """set -e
curl() {
  printf '%s\n' "$*" >> calls.txt
  case "$*" in *fixture-failing*) return 22 ;; esac
}
"""
    scripts = [stub]
    hook_index = 0
    for step in deploy_steps():
        if "HOOK_URL" in step.get("env", {}):
            hook_index += 1
            secret = step["env"]["HOOK_URL"]
            hook = "" if secret == absent else f"fixture-{hook_index}"
            if secret == failing:
                hook = "fixture-failing"
            scripts.append(f"HOOK_URL='{hook}'\n" + step["run"])
        elif "local staging worker" in step["name"]:
            scripts.append(step["run"])
    result = run_shell("\n".join(scripts), tmp_path)
    calls = (
        (tmp_path / "calls.txt").read_text().splitlines()
        if (tmp_path / "calls.txt").exists()
        else []
    )
    return result, calls


def test_staging_deploy_reaches_all_three_hosted_services_without_worker_hook(tmp_path):
    result, calls = fake_deploy_run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert len(calls) == 3
    assert [call.rsplit(" ", 1)[1] for call in calls] == [
        "fixture-1",
        "fixture-2",
        "fixture-3",
    ]
    assert "worker remains local" in result.stdout.lower()
    assert not any(
        "WORKER_STAGING" in str(step.get("env", {})) for step in deploy_steps()
    )


@pytest.mark.parametrize("index", [0, 1, 2])
def test_missing_hosted_hook_still_fails_before_later_deploys(tmp_path, index):
    hooks = [
        step["env"]["HOOK_URL"]
        for step in deploy_steps()
        if "HOOK_URL" in step.get("env", {})
    ]
    result, calls = fake_deploy_run(tmp_path, absent=hooks[index])
    assert result.returncode != 0
    assert len(calls) == index
    assert "is not set" in result.stdout


def test_render_hook_error_still_fails_workflow(tmp_path):
    hooks = [
        step["env"]["HOOK_URL"]
        for step in deploy_steps()
        if "HOOK_URL" in step.get("env", {})
    ]
    result, calls = fake_deploy_run(tmp_path, failing=hooks[1])
    assert result.returncode == 22
    assert len(calls) == 2


@pytest.mark.parametrize("folder", ["sdk-server", "telephony"])
def test_release_target_matches_lockfile_and_changelog(
    folder,
):
    package = ROOT / folder
    manifest = json.loads((package / "package.json").read_text())
    lock = json.loads((package / "package-lock.json").read_text())
    assert (
        manifest["version"]
        == lock["version"]
        == lock["packages"][""]["version"]
        == "0.1.1"
    )
    assert "## [0.1.1]" in (package / "CHANGELOG.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "license_value,terms,expected",
    [
        (None, None, 1),
        ("SEE LICENSE IN LICENSE", None, 1),
        ("SEE LICENSE IN LICENSE", " \n", 1),
        (
            "SEE LICENSE IN LICENSE",
            "Synthetic test terms only; not a project license.",
            0,
        ),
    ],
)
def test_tag_release_license_check_blocks_missing_terms(
    tmp_path, license_value, terms, expected
):
    steps = workflow("release-sdk.yml")["jobs"]["release"]["steps"]
    guard = next(
        s for s in steps if s["name"] == "Check license metadata and packaged terms"
    )
    assert "publish == 'true'" in guard["if"]
    assert (
        "@awaazlabs-uva/agents" in guard["if"]
        and "@awaazlabs-uva/telephony" in guard["if"]
    )
    package = tmp_path / "package"
    package.mkdir()
    manifest = {"name": "fixture-package", "version": "0.1.1"}
    if license_value is not None:
        manifest["license"] = license_value
    (package / "package.json").write_text(json.dumps(manifest))
    if terms is not None:
        (package / "LICENSE").write_text(terms)
    result = run_shell(guard["run"], tmp_path, DIR="package")
    assert result.returncode == expected, result.stdout + result.stderr
    assert ("::error::" in result.stderr) == bool(expected)


def test_client_version_guard_still_rejects_wrong_install_pin(tmp_path, monkeypatch):
    from tests import test_sdk_docs_contract as docs

    guide = tmp_path / "CLIENT_QUICKSTART.md"
    guide.write_text("npm install @awaazlabs-uva/agents@9.9.9")
    for directory in ["sdk", "sdk-server", "telephony"]:
        destination = tmp_path / directory
        destination.mkdir()
        shutil.copyfile(ROOT / directory / "README.md", destination / "README.md")
    monkeypatch.setattr(docs, "ROOT", tmp_path)
    monkeypatch.setattr(docs, "DOC_GLOBS", [guide])
    with pytest.raises(AssertionError, match="version pin mismatches"):
        docs.test_package_json_versions_match_docs_pins()
