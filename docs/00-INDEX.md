# 00-INDEX.md — ROUTING TABLE

**Load ONE guide. Not all of them.** Match your current task to a row, read that file, stop.

## By phase (sequential — no phase starts until the previous gate passes)

| Phase | Guide | Gate command | Status |
|---|---|---|---|
| 0 Harness | `20-PHASE-0-HARNESS.md` | `make gate0` | ☐ |
| 1 Supabase | `21-PHASE-1-SUPABASE.md` | `make gate` + `rls_check.py` | ☐ |
| 2 Control plane | `22-PHASE-2-CONTROL-PLANE.md` | `pytest tests/test_mint.py` | ☐ |
| 3 Worker | `23-PHASE-3-WORKER.md` | `pytest tests/test_worker.py` | ☐ |
| 4 Client SDK | `24-PHASE-4-CLIENT-SDK.md` | `make bundle-check` | ☐ |
| 5 Voice picker | `25-PHASE-5-VOICE-PICKER.md` | `pytest tests/test_picker.py` | ☐ |
| 6 Admin portal | `26-PHASE-6-ADMIN.md` | `pytest tests/test_admin.py` | ☐ |
| 7 Security | `27-PHASE-7-SECURITY.md` | `security` subagent = PASS | ☐ |
| 8 Prod-ready | `28-PHASE-8-PROD-READY.md` | full suite + H9 answered | ☐ |

## By topic — read ALSO when the task touches it

| If your task touches… | Read |
|---|---|
| **any** paid API (TTS/STT/LLM) | `30-GUIDE-FREE-TIER.md` ← **read before your first API call, always** |
| auth, tokens, keys, RLS, tenancy | `31-GUIDE-SECURITY.md` |
| writing/changing a test | `32-GUIDE-TESTING.md` |
| schema, migrations, MCP | `33-GUIDE-SUPABASE.md` |
| a stack/design choice | `40-ADR.md` (read before deciding; append after) |
| something only a human can do | `41-HUMAN-TASKS.md` |
| a question you cannot answer | `42-RESEARCH-QUEUE.md` |

## Reference (read once, at Phase 0)

| File | What |
|---|---|
| `10-SPEC.md` | What we're building. Out-of-scope list. |
| `11-ARCHITECTURE.md` | System design, data flow, the multi-tenant model. |
| `60-RUNBOOK-CAP-EXHAUSTION.md` | P8-T03. What happens (server + SDK) when a tenant hits a cap — fails, does not queue. Read before building any host-platform integration UX. |
| `61-GUIDE-DEV-TO-PROD.md` | P8-T05. Every env-var/config/account change needed to flip dev → prod, and what does NOT change. Read before any prod deploy. |
| `62-GUIDE-PROD-ENV-VARS.md` | P9. Literal, exhaustive per-service env-var inventory for control_plane/admin, verified against real code reads. Read before setting platform secrets. |
| `63-GUIDE-WORKER-DEPLOYMENT-DEFERRAL.md` | P9. Why the worker gets no Dockerfile yet — persistent-process host vs. request-triggered services — deferred to Phase 12. |
| `64-GUIDE-LIVE-LISTEN-CHECKLIST.md` | P10. Structured listening checklist + staged (not run) commands for the next live-listen session. Read before that session starts. |

## Live state (never in docs/ — always current)

| File | Update cadence |
|---|---|
| `../state/PROGRESS.md` | **every task** |
| `../state/HANDOFF.md` | every checkpoint |
| `../state/BLOCKERS.md` | on 3rd strike |
| `../supabase/SCHEMA.md`, `RLS.md` | after every migration (`db-inspector` regenerates — never hand-edit) |
