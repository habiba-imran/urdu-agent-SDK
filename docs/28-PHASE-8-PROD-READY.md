# PHASE 8 — PRODUCTION READINESS
**Gate:** everything below. This is the last gate.

## Tasks
P8-T01 load test at 5 concurrent (Build cap). Record p50/p95.
P8-T02 🔴 **H9 answers recorded in ADR.** If Uplift's concurrency limit is below LiveKit's,
       **IT is our real ceiling** and 10-SPEC.md capacity numbers are wrong. Fix the spec.
P8-T03 runbook: what happens at the cap? what does the SDK show? does it queue or fail?
P8-T04 `/ponytail-debt` -> ledger empty, or every item explicitly accepted in the ADR.
P8-T05 dev→prod switch documented: `UPLIFT_MODE=live`, `STT_PROVIDER=soniox`, LiveKit Ship, prod Supabase.
P8-T06 rollback procedure tested (revert to `p7-gate-pass` tag).

## GATE 8
```
[ ] full suite green
[ ] security subagent PASS
[ ] H9 answered + spec updated to match reality
[ ] runbook exists and covers cap-exhaustion
[ ] ponytail debt resolved or accepted
[ ] every phase tag exists (p0..p7-gate-pass)
```
**HUMAN GATE:** you merge to main. **The agent never merges.**

## Then, and only then
Fund Soniox → flip `STT_PROVIDER`. Expect ~400ms faster, ~6x cheaper STT. One env var (ADR-002).
