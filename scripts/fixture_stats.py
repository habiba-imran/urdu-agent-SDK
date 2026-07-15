#!/usr/bin/env python3
"""Fixture cache health. Manifest must match disk."""

import json
import pathlib
import sys

FIX = pathlib.Path("tests/fixtures/tts")
MAN = FIX / "manifest.json"
FIX.mkdir(parents=True, exist_ok=True)
if not MAN.exists():
    MAN.write_text("{}")
man = json.loads(MAN.read_text())
disk = {p.stem for p in FIX.glob("*.wav")}
orphan_disk = disk - set(man)
orphan_man = set(man) - disk
total_ms = sum(v.get("ms", 0) for v in man.values())
print(
    f"fixtures: {len(disk)} wav | manifest: {len(man)} | recorded: {total_ms / 1000:.1f}s of 600s Uplift budget"
)
if orphan_disk:
    print(f"  wav with no manifest entry: {sorted(orphan_disk)[:5]}")
if orphan_man:
    print(f"  manifest entry with no wav:  {sorted(orphan_man)[:5]}")
if orphan_disk or orphan_man:
    print("GATE FAIL: fixture manifest out of sync", file=sys.stderr)
    sys.exit(1)
