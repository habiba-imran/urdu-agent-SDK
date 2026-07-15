#!/usr/bin/env python3
"""Reproducible size comparison for the P0-T07 ponytail measurement.

Counts total lines, code lines (non-blank, non-comment, non-docstring),
characters and bytes for the two arms committed under
``bench/ponytail/{off,on}/`` and prints the delta. Run it to reproduce the
numbers recorded in docs/40-ADR.md ADR-004::

    python scripts/ponytail_measure.py

Scope, stated plainly: this measures DELIVERABLE SIZE only — the code the agent
produced — which is exact and reproducible from the committed files. It does
NOT measure end-to-end agent session tokens or wall-clock time; those are not
observable from inside the agent harness and are deliberately not reported
(AGENT_SYSTEM.md rule 8.3: measured or cited, never estimated).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARMS = {
    "off": ROOT / "bench" / "ponytail" / "off" / "validate_fixtures.py",
    "default": ROOT / "bench" / "ponytail" / "on" / "validate_fixtures.py",
}


def code_lines(text: str) -> int:
    """Count executable lines, skipping blanks, comments and triple-quoted docstrings."""
    count = 0
    in_doc = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(('"""', "'''")):
            if (line.count('"""') + line.count("'''")) % 2 == 1:
                in_doc = not in_doc
            continue
        if in_doc or not line or line.startswith("#"):
            continue
        count += 1
    return count


def measure(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    return {
        "total_lines": len(text.splitlines()),
        "code_lines": code_lines(text),
        "chars": len(text),
        "bytes": len(text.encode("utf-8")),
    }


def pct(off: int, on: int) -> str:
    return "n/a" if off == 0 else f"{round((on - off) / off * 100):+d}%"


def main() -> int:
    stats = {name: measure(path) for name, path in ARMS.items()}
    off, on = stats["off"], stats["default"]
    print(f"{'metric':<13}{'off':>8}{'default':>10}{'delta':>9}")
    for metric in ("total_lines", "code_lines", "chars", "bytes"):
        print(
            f"{metric:<13}{off[metric]:>8}{on[metric]:>10}{pct(off[metric], on[metric]):>9}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
