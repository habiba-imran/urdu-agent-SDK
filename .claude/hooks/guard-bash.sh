#!/usr/bin/env bash
# PreToolUse:Bash. exit 2 = BLOCK. FAILS CLOSED by design.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; . "$DIR/_lib.sh"
IN=$(cat)
block(){ printf 'BLOCKED: %s\n' "$1" >&2; exit 2; }
[ -z "$IN" ] && exit 0
CMD=$(json_field "$IN" "command")
# fail closed: input present but unparseable => block rather than wave it through
if [ -z "$CMD" ] && printf '%s' "$IN" | grep -q '"command"'; then
  block "hook could not parse tool_input.command. Failing CLOSED. Install jq: apt-get install -y jq"
fi
[ -z "$CMD" ] && exit 0
has(){ printf '%s' "$CMD" | grep -qE "$1"; }

has '\brm[[:space:]]+-[a-zA-Z]*[rR]'                        && block "rm -r/-rf. Use trash, or ask the human."
has 'git[[:space:]]+push([[:space:]]|$)' && has '(^|[[:space:]:])(main|master)([[:space:]]|:|$)' && block "No direct push to main/master. Branch phase/<n>-<name>; the HUMAN merges (AGENT_SYSTEM.md §5)."
has 'git[[:space:]]+reset[[:space:]]+--hard'                && block "No reset --hard. Use git revert — history is the audit trail."
has 'service_role|SERVICE_ROLE'                             && block "service_role bypasses RLS BY DESIGN. This is the documented Supabase exfil path (docs/33-GUIDE-SUPABASE.md §2). Scoped role only."
has 'UPLIFT_MODE=(record|live)|GLADIA_MODE=live|LLM_MODE=live' \
                                                            && block "Paid API call. Uplift free tier is 10 MINUTES TOTAL. Human approves every recording session (docs/30-GUIDE-FREE-TIER.md §3)."
has '(pip|npm|uv)[[:space:]]+(install|add)[^;|]*(twilio|telnyx|pjsua|pjsip|sipsimple|aiosip)' \
                                                            && block "Telephony is OUT OF SCOPE (docs/10-SPEC.md). Later project."
if has '(supabase|psql|migrat|db[- ]push)' && has '(prod|production|--linked)'; then
  block "PROD is off-limits. Dev project only (docs/33-GUIDE-SUPABASE.md §1)."
fi
if has '\.env' && has '(cat|echo|printf|curl|tee|less|head|tail|>|\|)'; then
  block "No .env read/exfil."
fi
exit 0
