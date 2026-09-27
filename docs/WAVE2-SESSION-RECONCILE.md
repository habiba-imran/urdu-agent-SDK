# Session + telephony reconcile runbook (F-H18 Phase C)

**Owner (script correctness / this runbook):** Habiba  
**Owner (schedule on staging/prod):** Ehsan — see `docs/WAVE2-EHSAN-HANDOFF.md` §1  
**Related:** `docs/WAVE2-HIGH-FH10-FH18-IMPLEMENTATION-PLAN.md` Phase C; Phase B clean-close is `worker/session_close.py`

## Why this exists

Clean hang-up closes the `sessions` row and frees `quota_state.concurrent_now` in the worker shutdown path.  
If the worker **crashes / OOM / hard kill**, those callbacks never run. These scripts repair:

| Script | Repairs |
|---|---|
| `scripts/reconcile_sessions.py` | Open sessions older than N minutes → `ended_at` + `end_reason='reconciled_stale'`; realign `concurrent_now` to true open count |
| `scripts/reconcile_telephony.py` | Stale telephony orders / stuck calls / telephony quota leaks (`tenant_portal_api.telephony_reconcile`) |

**Billing note:** `reconciled_stale` closes the row and fixes concurrency. It does **not** invent missing `usage_events` for the crashed call. Treat it as a capacity / open-row repair, not a full billing reconstruct.

## Commands

### Sessions (default max age = 30 minutes)

```bash
# Preview only — no writes
python scripts/reconcile_sessions.py --dry-run

# Apply (same as omitting --dry-run)
python scripts/reconcile_sessions.py --max-age-minutes 30
```

`--max-age-minutes` = how old an **open** session (`ended_at IS NULL`) must be before it is treated as stale. Younger opens are left alone (they may still be live calls).

### Telephony (default = dry-run)

```bash
python scripts/reconcile_telephony.py          # dry-run
python scripts/reconcile_telephony.py --apply  # write
```

### Crash drill (needs live DB)

```bash
python scripts/simulate_worker_crash.py
```

Inserts a fake open session older than 30m, runs reconcile, checks `concurrent_now` and `end_reason`.

## What operators should see after a worker kill

1. Immediately: `sessions.ended_at` still null; `quota_state.concurrent_now` may stay high for that tenant.  
2. After reconcile apply (or cron): that session has `ended_at` set, `end_reason='reconciled_stale'`, and `concurrent_now` matches remaining truly open sessions.  
3. Dry-run first: prints how many stale sessions / mismatched tenants **would** change, then `DRY RUN complete — no changes were committed.`

## Scheduling (2026-09-27)

**Landed:** `.github/workflows/reconcile.yml` — both scripts every 15 minutes + `workflow_dispatch`. Dry-run by default; set repo variable `RECONCILE_APPLY=true` to write.

Habiba set `SUPABASE_DB_URL` and manually dry-ran successfully. Wave 2 closed with dry-run as the safe default; set `RECONCILE_APPLY=true` when dry-run counts look right. Ops should still confirm no duplicate cron outside git.

## Env

Same DB URL as other scripts (`scripts/dbconn.py` / `SUPABASE_DB_URL` or project equivalent).

## Habiba Phase C status

- Runbook: this file  
- Unit tests: `tests/test_reconcile_sessions.py` (injected conn; no network)  
- Staging dry-run: **done** 2026-09-21 (Actions #1 success); apply mode still off
