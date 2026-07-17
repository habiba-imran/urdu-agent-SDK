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
ADMIN BOUNDARY   (added by ADR-021, 2026-07-18 — Phase 6 postdates the rest of this checklist)
[ ] admin JWT cannot be used as a tenant/LiveKit token on any control_plane/ endpoint -> rejected
[ ] tenant/LiveKit token cannot be used as an admin JWT on any admin/ endpoint -> 401
[ ] expired admin JWT -> 401
[ ] tampered admin JWT (re-signed with a wrong secret, or with `video` grafted on) -> 401
[ ] admin login without correct TOTP code -> 401 (password alone insufficient)
```

## HUMAN GATE — you personally attempt these. All three must fail.
1. Read tenant B's agents using tenant A's credentials.
2. Take a minted token and join a different room.
3. (ADR-021, 2026-07-18) Attempt to reach an admin-only endpoint (e.g. GET /admin/tenants) using
   a tenant-scoped LiveKit AccessToken, and separately using a real minted-session token. Both
   must fail. Then attempt the same endpoint with an expired admin JWT, and with a tampered admin
   JWT (claims edited, re-signed with a secret you do not have). All four attempts must fail.

If any succeeds, Phase 7 fails. No exceptions, no "it's unlikely in practice."
