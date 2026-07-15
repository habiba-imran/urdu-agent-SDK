#!/usr/bin/env python3
"""Fixture manifest validator (ponytail-OFF baseline arm — P0-T07).

Verifies that the committed fixture cache is internally consistent, so that a
cache-miss in test mode is always a genuine gap and never a stale-manifest
artifact (docs/30-GUIDE-FREE-TIER.md §2).

Two fixture families are checked:

* TTS — ``tests/fixtures/tts/manifest.json`` maps a content hash to metadata;
        every hash must have a matching ``<hash>.wav`` on disk, and every
        ``<hash>.wav`` on disk must appear in the manifest.
* STT — every ``<name>.wav`` must be paired with a ``<name>.expected.txt`` gold
        transcript, and vice versa.

Exit status is 0 when both families are consistent and 1 otherwise, so the
script doubles as a CI gate.

This is the deliberately-verbose baseline arm of the P0-T07 ponytail
measurement; the terse counterpart lives in ``bench/ponytail/on/``. Both
implement identical behaviour — only the coding discipline differs. The
reproducible size delta between them is recorded in docs/40-ADR.md ADR-004.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


@dataclass
class ValidationResult:
    """Collects the problems found while validating one fixture family."""

    family: str
    missing_files: list[str] = field(default_factory=list)
    orphan_files: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when neither missing nor orphaned entries were found."""
        return not self.missing_files and not self.orphan_files

    def describe(self) -> str:
        """Return a human-readable one-line summary for this family."""
        if self.ok:
            return f"[OK]   {self.family}: manifest and disk agree"
        parts = []
        if self.missing_files:
            parts.append(f"{len(self.missing_files)} referenced-but-missing")
        if self.orphan_files:
            parts.append(f"{len(self.orphan_files)} on-disk-but-unlisted")
        return f"[FAIL] {self.family}: " + ", ".join(parts)


def validate_tts(tts_dir: Path) -> ValidationResult:
    """Validate the TTS manifest against the ``*.wav`` files in ``tts_dir``."""
    result = ValidationResult(family="tts")
    manifest_path = tts_dir / "manifest.json"
    if not manifest_path.exists():
        result.missing_files.append(str(manifest_path))
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        result.missing_files.append(f"{manifest_path} (invalid JSON: {exc})")
        return result
    listed_hashes = set(manifest.keys())
    disk_hashes = {p.stem for p in tts_dir.glob("*.wav")}
    for missing in sorted(listed_hashes - disk_hashes):
        result.missing_files.append(f"{missing}.wav")
    for orphan in sorted(disk_hashes - listed_hashes):
        result.orphan_files.append(f"{orphan}.wav")
    return result


def validate_stt(stt_dir: Path) -> ValidationResult:
    """Validate that every STT ``*.wav`` has a matching ``*.expected.txt``."""
    result = ValidationResult(family="stt")
    if not stt_dir.exists():
        return result
    wav_stems = {p.stem for p in stt_dir.glob("*.wav")}
    txt_stems = {
        p.name[: -len(".expected.txt")] for p in stt_dir.glob("*.expected.txt")
    }
    for missing in sorted(wav_stems - txt_stems):
        result.missing_files.append(f"{missing}.expected.txt")
    for orphan in sorted(txt_stems - wav_stems):
        result.orphan_files.append(f"{orphan}.wav")
    return result


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run both validators, and return a process exit code."""
    parser = argparse.ArgumentParser(description="Validate the fixture cache.")
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=DEFAULT_FIXTURES_ROOT,
        help="Path to the tests/fixtures directory.",
    )
    args = parser.parse_args(argv)

    results = [
        validate_tts(args.fixtures_root / "tts"),
        validate_stt(args.fixtures_root / "stt"),
    ]
    for result in results:
        print(result.describe())
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
