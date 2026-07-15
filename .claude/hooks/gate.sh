#!/usr/bin/env bash
# Stop hook. Nothing is "done" until this is green. exit 2 = you are not done.
cd "$CLAUDE_PROJECT_DIR" || exit 0
[ -f Makefile ] || exit 0
if ! make gate >/tmp/gate.log 2>&1; then
  echo "GATE FAILED — you are NOT done. Fix the code. Do not rationalise. Do not edit the test." >&2
  tail -40 /tmp/gate.log >&2; exit 2
fi
SHA=$(git rev-parse --short HEAD 2>/dev/null)
if [ -n "$SHA" ] && ! grep -q "$SHA" state/PROGRESS.md 2>/dev/null; then
  echo "GATE FAILED: state/PROGRESS.md has no entry for commit $SHA. RECORD before you stop." >&2
  exit 2
fi
exit 0
