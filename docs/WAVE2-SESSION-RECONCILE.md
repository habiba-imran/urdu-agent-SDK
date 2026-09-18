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

## Scheduling (Ehsan — still required)

Nothing in this repo schedules these scripts (only unrelated `refresh-voice-previews.yml` has a cron).

Suggested cadence: every **5–15 minutes**. Options:

- Render cron job, or  
- GitHub Actions schedule (pattern: `.github/workflows/refresh-voice-previews.yml`), or  
- Interim: manual cadence with owner + date written in the Ehsan handoff sign-off box

**Do not** mark F-H18 fully ✅ until both scripts are scheduled (or interim accepted in writing).

## Env

Same DB URL as other scripts (`scripts/dbconn.py` / `SUPABASE_DB_URL` or project equivalent). No Render deploy is required to develop/test locally if a DB is available.

## Habiba Phase C status

- Runbook: this file  
- Unit tests: `tests/test_reconcile_sessions.py` (injected conn; no network)  
- Live staging dry-run / drill: **deferred** until a shared DB / deploy exists (Habiba confirmed Render not deployed yet)
