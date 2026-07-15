# PHASE 7 — SECURITY HARDENING
**Read first:** 31-GUIDE-SECURITY.md (all of it)
**Gate:** `security` subagent verdict = PASS + human attack attempts fail

## Full checklist — the `security` subagent runs this
```
SECRETS
[ ] gitleaks detect                              -> 0
[ ] git log -p | grep -iE 'api[_-]?key|secret'   -> 0   (history too, not just HEAD)
[ ] dist/ scan                                   -> 0
[ ] no service_role outside .env.local
TENANCY
[ ] every table rowsecurity=true
[ ] cross-tenant read -> 0 rows
[ ] IDOR: agent_id of tenant B via tenant A -> 403
TOKEN MINT
[ ] TTL <=120s | room+identity scoped | no roomAdmin/roomCreate/roomList
[ ] replay rejected | expired rejected | widening impossible
[ ] quota enforced BEFORE issue
INJECTION
[ ] tenant prompt never in a tool-visible position
[ ] tenant prompt with "ignore previous instructions..." -> agent does NOT comply
[ ] DB content never re-enters a privileged tool
ABUSE
[ ] picker cannot trigger live TTS
[ ] per-tenant concurrent + monthly caps enforced
[ ] rate limit per tenant
DEPS
[ ] pip-audit && npm audit --audit-level=high -> 0 high/critical
[ ] all deps pinned (requirements.txt ==, package-lock.json committed)
```

## HUMAN GATE — you personally attempt these. Both must fail.
1. Read tenant B's agents using tenant A's credentials.
2. Take a minted token and join a different room.

If either succeeds, Phase 7 fails. No exceptions, no "it's unlikely in practice."
