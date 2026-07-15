# PHASE 6 — SUPER-ADMIN PORTAL
**Goal:** total visibility for US. Every tenant, agent, session, minute.
**Gate:** `pytest tests/test_admin.py -q`

## Views
tenants (status, quota, live concurrency) · agents (prompt, voice, tenant, usage)
sessions (live + history, duration, end_reason) · usage (per tenant/day/kind, cost estimate)
quota (who's near a cap) · blockers (429/403 rates — is a tenant being throttled?)

## Rules
🔴 Admin auth is **completely separate** from tenant auth. Different table, different JWT audience, MFA.
🔴 Admin **bypasses RLS by design** — so it is the highest-value target in the system. Treat accordingly.
🔴 Every number reconciles against `usage_events`. It is the only billing truth.

## Tasks
P6-T01 admin auth (separate) · P6-T02 tenant/agent list · P6-T03 session explorer
P6-T04 usage aggregation + cost estimate ($0.0044/min marginal — 10-SPEC.md)
P6-T05 live concurrency vs LiveKit cap · P6-T06 audit log of admin actions

## GATE 6
```
[ ] every dashboard number == a SQL query over usage_events
[ ] admin JWT cannot be used as a tenant JWT (and vice versa)
[ ] every admin action written to an audit log
[ ] admin portal is NOT reachable from the SDK's origin
```
