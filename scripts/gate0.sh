#!/usr/bin/env bash
# GATE 0 — Phase 0 harness self-check. Runs every check listed in docs/20-PHASE-0-HARNESS.md §GATE 0.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1" >&2; }

echo "=== GATE 0 ==="
echo ""

# --- node -v ---
echo "--- node -v ---"
if command -v node >/dev/null 2>&1; then
  node -v; pass "node found"
else
  fail "node not found"
fi
echo ""

# --- git status clean ---
echo "--- git status clean ---"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "not a git repo"
else
  pass "inside git work tree"
fi
# git diff --quiet exits 128 on repos with zero commits. Treat that as clean.
DIRTY=0
git diff --quiet 2>/dev/null || DIRTY=$?
if [ "$DIRTY" -ne 0 ] && [ "$DIRTY" -ne 128 ]; then
  fail "working tree is dirty"
else
  pass "working tree clean"
fi
DIRTY=0
git diff --cached --quiet 2>/dev/null || DIRTY=$?
if [ "$DIRTY" -ne 0 ] && [ "$DIRTY" -ne 128 ]; then
  fail "staging area is dirty"
else
  pass "staging area clean"
fi
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD (no commits yet)")
echo "  branch: $BRANCH"
echo ""

# --- .env gitignored and not tracked ---
echo "--- .env gitignored ---"
test -f .env.example && pass ".env.example exists" || fail ".env.example missing"
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  fail ".env is tracked by git"
else
  pass ".env not tracked by git"
fi
test ! -f .env && pass "no local .env file" || echo "  WARNING: .env file exists locally (not tracked — ok)"
echo ""

# --- hooks selftest ---
echo "--- hooks selftest ---"
if bash .claude/hooks/selftest.sh; then
  pass "hooks selftest (all BLOCK exit 2)"
else
  fail "hooks selftest returned non-zero"
fi
echo ""

# --- agents ---
echo "--- /agents ---"
AGENTS=$(ls .claude/agents/*.md 2>/dev/null | wc -l)
if [ "$AGENTS" -ne 4 ]; then
  fail "expected 4 agents, found $AGENTS"
else
  pass "4 agent files"
fi
if grep -q 'Write' .claude/agents/reviewer.md; then
  fail "reviewer agent has Write tool"
else
  pass "reviewer has no Write tool"
fi
echo ""

# --- fixtures dirs ---
echo "--- fixtures dirs ---"
test -d tests/fixtures/tts && pass "tests/fixtures/tts exists" || fail "tests/fixtures/tts missing"
test -d tests/fixtures/stt && pass "tests/fixtures/stt exists" || fail "tests/fixtures/stt missing"
echo ""

# --- ADR-004 ---
echo "--- ADR-004 measured numbers ---"
# Must contain actual numeric deltas (e.g., "-70%", "+27%"), not just the P0-T07 label
if grep -qE '\*\*-?[0-9]+%\*\*' docs/40-ADR.md 2>/dev/null; then
  pass "ADR-004 contains measured numeric deltas"
else
  fail "ADR-004 has no numeric measurement (must contain values like '-70%' or '+27%')"
fi
echo ""

# --- P0-T08 CER harness ---
echo "--- P0-T08 CER harness ---"
if command -v python >/dev/null 2>&1; then
  COLLECTED=$(python -m pytest tests/ -q --collect-only 2>/dev/null | grep -c '::' || true)
  if [ "$COLLECTED" -ge 1 ] 2>/dev/null; then
    pass "P0-T08: pytest collects $COLLECTED CER harness tests"
  else
    fail "P0-T08: pytest --collect-only found 0 tests (CER harness missing)"
  fi
else
  fail "P0-T08: python not found (cannot verify CER harness)"
fi
echo ""

# --- usage ledger ---
echo "--- usage ledger ---"
test -f state/usage_ledger.json && pass "usage_ledger.json exists" || fail "usage_ledger.json missing"
if python scripts/usage_guard.py --report 2>/dev/null; then
  pass "usage guard: under budget"
else
  fail "usage guard: over budget or error"
fi
echo ""

# --- summary ---
echo "========================================"
echo "GATE 0: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo "GATE 0: FAIL" >&2
  exit 1
else
  echo "GATE 0: PASS"
fi
