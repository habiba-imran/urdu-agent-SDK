"""Keep in-console /docs and CLIENT_QUICKSTART pins aligned with package.json versions.

Clients install from the npm registry — docs must not advertise versions that are not
what these packages declare (and release-sdk.yml publishes).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PACKAGES = {
    "@awaazlabs-uva/voice": ROOT / "sdk" / "package.json",
    "@awaazlabs-uva/agents": ROOT / "sdk-server" / "package.json",
    "@awaazlabs-uva/telephony": ROOT / "telephony" / "package.json",
}

DOC_GLOBS = [
    ROOT / "dashboard" / "src" / "content" / "docs" / "pages",
    ROOT / "docs",
]

PINNED = re.compile(
    r"@(awaazlabs-uva/(?:voice|agents|telephony))@(\d+\.\d+\.\d+)"
)


def _declared_versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for name, path in PACKAGES.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["name"] == name, f"{path} name mismatch"
        out[name] = data["version"]
    return out


def test_package_json_versions_match_docs_pins():
    declared = _declared_versions()
    mismatches: list[str] = []
    scanned = 0

    files: list[Path] = []
    for base in DOC_GLOBS:
        if base.is_dir():
            files.extend(base.rglob("*.ts"))
            files.extend(base.rglob("*.md"))
        elif base.is_file():
            files.append(base)

    # Also package READMEs published to npm
    files.extend(
        [
            ROOT / "sdk" / "README.md",
            ROOT / "sdk-server" / "README.md",
            ROOT / "telephony" / "README.md",
        ]
    )

    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in PINNED.finditer(text):
            scanned += 1
            pkg = f"@{match.group(1)}"
            ver = match.group(2)
            expected = declared[pkg]
            if ver != expected:
                mismatches.append(
                    f"{path.relative_to(ROOT)}: {pkg}@{ver} (package.json is {expected})"
                )

    assert scanned > 0, "expected at least one @awaazlabs-uva/*@x.y.z pin in docs/READMEs"
    assert not mismatches, "version pin mismatches:\n" + "\n".join(mismatches)


def test_changelogs_have_section_for_package_version():
    declared = _declared_versions()
    for name, pkg_path in PACKAGES.items():
        version = declared[name]
        changelog = pkg_path.parent / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        assert f"## [{version}]" in text, f"{changelog} missing ## [{version}] (required by release-sdk.yml)"


def test_telephony_has_prepublish_guard():
    data = json.loads((ROOT / "telephony" / "package.json").read_text(encoding="utf-8"))
    assert "prepublishOnly" in data.get("scripts", {}), (
        "telephony must run build+lint before npm publish (parity with voice/agents)"
    )


def test_npm_readmes_do_not_advertise_demo_app_or_tarball():
    banned = [
        (ROOT / "sdk" / "README.md", ("demo-app", "examples/web-client", "examples/host-backend")),
        (ROOT / "telephony" / "README.md", (".tgz", "handoff tarball", "sdk/@awaazlabs-uva/telephony")),
    ]
    for path, needles in banned:
        text = path.read_text(encoding="utf-8").lower()
        for needle in needles:
            assert needle.lower() not in text, f"{path.name} still mentions '{needle}'"
