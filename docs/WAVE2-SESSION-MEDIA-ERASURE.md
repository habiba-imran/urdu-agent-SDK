# Session media erasure runbook (F-C4 Phase D)

**Owner (script correctness):** Habiba — `scripts/purge_expired_session_media.py`  
**Owner (schedule / portal UX):** Ehsan — cron or workflow + optional portal “request deletion”  
**Related:** `docs/WAVE2-P0-FC4-FC7-IMPLEMENTATION-PLAN.md` Phase D; `docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md` A.3

## What is deleted

For each eligible row:

1. Supabase Storage object at `recording_storage_path` in bucket `session-recordings`
2. DB fields cleared: `recording_url`, `recording_storage_path`, `sessions.transcript`
3. `escalations.contact_info` null for linked `session_id`
4. `deleted_at` / `redacted_at` set when those columns exist

## When a row is eligible

- `retention_until < now()`, **or**
- `deletion_requested_at` is set  
- and `deleted_at` is still null

`telephony_calls` already has retention columns (migration `0014`).  
`sessions` / `escalations` get them from Ehsan’s A.3 migration. Until then the purge script still cleans **telephony_calls** and prints that session columns are missing.

## Tenant / end-user erasure request

1. Identify the session (`room_name` or `sessions.id`) and any linked `telephony_calls` row.
2. Set `deletion_requested_at = now()` on that row (SQL or future portal API — Ehsan).
3. Run purge (or wait for scheduled run):

```bash
python scripts/purge_expired_session_media.py --dry-run
python scripts/purge_expired_session_media.py
```

4. Verify:
   - Storage object gone (or never existed)
   - `recording_storage_path` / `recording_url` / `transcript` null
   - `deleted_at` set
   - Escalation `contact_info` null when linked

## Worker behaviour (already in code)

- On session close, worker sets `retention_until` via `worker/session_retention.py` (default **30 days**, env `UVA_RECORDING_RETENTION_DAYS`).
- Uploads store **`recording_storage_path` only** — long-lived signed `recording_url` is no longer written (portal should re-sign from path on read — Ehsan follow-up).

## Scheduling (Ehsan — still open)

Nothing in this repo schedules the purge yet (same gap as F-H18 reconcile). Options:

- GitHub Actions cron (see `refresh-voice-previews.yml` pattern), or
- Render cron job, or
- Ops runbook until automation lands

**Interim:** run `--dry-run` then live purge manually after any deletion request; file a ticket with owner + date for cron.

## Env required for storage deletes

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE`
- `SUPABASE_DB_URL` (or whatever `scripts/dbconn.py` uses)
