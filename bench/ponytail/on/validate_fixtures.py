#!/usr/bin/env python3
"""Fixture manifest validator (ponytail-default arm — P0-T07).

Same behaviour as bench/ponytail/off/validate_fixtures.py: checks that the TTS
manifest and the STT .wav/.expected.txt pairs agree with what is on disk, and
exits non-zero on any mismatch. See docs/40-ADR.md ADR-004 for the size delta.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def check() -> int:
    tts = ROOT / "tts"
    listed = set(
        json.loads((tts / "manifest.json").read_text(encoding="utf-8") or "{}")
    )
    on_disk = {p.stem for p in tts.glob("*.wav")}
    bad = {f"{h}.wav (missing)" for h in listed - on_disk}
    bad |= {f"{h}.wav (orphan)" for h in on_disk - listed}

    stt = ROOT / "stt"
    wavs = {p.stem for p in stt.glob("*.wav")}
    txts = {p.name[: -len(".expected.txt")] for p in stt.glob("*.expected.txt")}
    bad |= {f"{n}.expected.txt (missing)" for n in wavs - txts}
    bad |= {f"{n}.wav (orphan)" for n in txts - wavs}

    for problem in sorted(bad):
        print("FAIL", problem)
    print("OK" if not bad else f"{len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(check())
