#!/usr/bin/env bash
# PreToolUse:Edit|Write. Blocks the #1 documented agent failure: rewriting tests to go green.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; . "$DIR/_lib.sh"
IN=$(cat); [ -z "$IN" ] && exit 0
FILE=$(json_field "$IN" "file_path")
if [ -z "$FILE" ] && printf '%s' "$IN" | grep -q '"file_path"'; then
  printf 'BLOCKED: hook could not parse file_path. Failing CLOSED. Install jq.\n' >&2; exit 2
fi
case "$FILE" in *test*|*spec*|*conftest*) ;; *) exit 0 ;; esac
grep -q 'ALLOW_TEST_EDIT' "${CLAUDE_PROJECT_DIR:-.}/state/PROGRESS.md" 2>/dev/null && exit 0
cat >&2 <<'MSG'
BLOCKED: test-file edit during an implementation task.

Tests are the contract. If a test is red, the CODE is wrong.
This is the best-documented agent failure mode: rewriting the test instead of fixing the bug.
(Real case: Playwright tests injecting JS at runtime so they passed while the bug shipped.)

Legitimately need to change this test?
  1. Say so out loud
  2. Justify it in state/PROGRESS.md -> "Live decisions"
  3. Add ALLOW_TEST_EDIT to that entry
  4. Retry
  5. Remove the token IMMEDIATELY after
docs/32-GUIDE-TESTING.md §2. If you cannot write the justification, you do not have one.
MSG
exit 2
