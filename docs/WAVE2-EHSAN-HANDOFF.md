# Wave 2 — Ehsan handoff

**From:** Habiba  
**For:** Ehsan  
**Date:** 2026-09-19  
**Branch:** use current `staging` (Habiba Wave 2 worker code is already merged)

---

## What this document is

This is **not** “all of Wave 2 forever” and **not** shared env variables.

It is the checklist of **shared exits** for tickets Habiba already implemented on the **worker** side. Those tickets stay **incomplete in the priority list** until you finish the rows marked **Your part** below.

Habiba’s worker / code work for these tracks is done. Please **do not re-implement** worker paths unless you find a real bug against the landed code. Prefer the linked contracts and existing scripts.

---

## Do first — Critical / High (in this order)

| # | Ticket | Your job (summary) | Details |
|---|---|---|---|
| 1 | **F-H18** | Schedule **both** reconcile scripts | §1 |
| 2 | **F-C4** | Apply migration A.3 + schedule purge | §2 |
| 3 | **F-C7** | Mint/dispatch optional `verified_caller_phone` | §3 |

Then Medium/Low:

| # | Ticket | Your job | Details |
|---|---|---|---|
| 4 | **F-M1** | Portal / control_plane / telephony silent `except` handlers | §4 |
| — | **F-M15** | **Nothing** (product Gate A) | §5 |
| — | **F-M25** | **Nothing** for Render (Habiba). Optional Dockerfile `HEALTHCHECK` only if you do **F-M9** | §6 |

---

## Out of your scope (do not pick these up)

| Item | Owner |
|---|---|
| Render worker deploy + health probe wiring | Habiba (worker currently runs **local**; CP / admin / tenant portal are on Render) |
| Host calendar **idempotency** (`idempotency_key`) | Habiba / host (`host-tools/`) |
| Second Urdu provider | Product closed — **none** |
| Habiba worker F-M1 / F-M15 / F-M24 / F-L6 / F-L10 / F-L15 code | Already landed |

---

## Status snapshot (honest)

| Track | Habiba (done) | Your part | Full ticket ✅? |
|---|---|---|---|
| **F-C4** | Worker recording / consent / retention code | Migration A.3, purge cron, portal re-sign / agent toggle | **No** until your exits |
| **F-C7** | Write-tool gate + proof tests | Mint A.4 `verified_caller_phone` | **No** until A.4 (host idempotency = Habiba, not you) |
| **F-H18** | `session_close` + reconcile runbook/tests | Schedule **both** reconcile scripts | **No** until cron |
| **F-H10** | Bounded retries; no #2 provider | **Nothing** | Closed as residual |
| **F-M1** | Worker handlers | Portal / CP / telephony handlers | Split — your half open |
| **F-M15** | Honesty logs + `models` / `legacy_aliases` | **Nothing** | Habiba (Gate A) |
| **F-M24** | Dump/transcript defaults off | **Nothing** | Habiba |
| **F-M25** | `worker/health_http.py` | Optional F-M9 Dockerfile only | Habiba owns Render |
| **F-L6 / F-L10 / F-L15** | Landed | **Nothing** | Habiba |

---

## 1. F-H18 — Schedule reconcile (highest ops priority)

### Problem

Session close, quota, and `usage_events` run mainly in LiveKit **shutdown** callbacks. Crash/OOM → open sessions + stuck concurrency. Scripts exist; **nothing in this repo schedules them**.

Habiba already landed: `worker/session_close.py`, `docs/WAVE2-SESSION-RECONCILE.md`, `tests/test_reconcile_sessions.py`. That does **not** replace your cron.

### Scripts

```bash
python scripts/reconcile_sessions.py --dry-run
python scripts/reconcile_sessions.py --max-age-minutes 30

python scripts/reconcile_telephony.py          # dry-run
python scripts/reconcile_telephony.py --apply
```

Drill: `scripts/simulate_worker_crash.py`  
Runbook: `docs/WAVE2-SESSION-RECONCILE.md`

### Your C.3 checklist

1. Confirm whether any cron already exists **outside** git.  
2. Schedule **both** scripts (suggested every **5–15 minutes**) — GitHub Action (see `.github/workflows/refresh-voice-previews.yml` pattern) or ops cron.  
3. Prefer dry-run in logs first week, then apply.  
4. When convenient: fix README F-L1 so “Run migrations” does not point at `reconcile_sessions.py --dry-run`.  

### Sign-off — F-H18 / C.3

- [x] Confirmed schedule state: **none in git**. Only `refresh-voice-previews.yml` had a
  `schedule:` trigger; there is no `render.yaml` in the repo, so a Render-dashboard cron cannot be
  seen from here — **ops must still confirm no duplicate cron exists outside git**.
- [x] Both scripts scheduled: `.github/workflows/reconcile.yml`, every 15 min + manual dispatch.
  Runs on the default branch's schedule, so it covers staging once merged.
- [ ] Production schedule — same workflow once the branch reaches the production repo; needs
  `SUPABASE_DB_URL` set as a repo secret (the job fails loudly if it is missing).
- [x] Dry-run first: defaults to `--dry-run`; flip repository variable `RECONCILE_APPLY=true`
  after reading a week of counts. No code change needed to switch.
- [x] First dry-run counts (local Postgres with seeded data, not production): sessions
  `0 stale > 30m`, `1 tenant concurrency mismatch (0 -> 1)`; telephony `0 stale orders,
  0 stale calls, 0 quota leaks`.

**Signed:** Ehsan (via Claude) **Date:** 2026-09-19

---

## 2. F-C4 — Schema migration (A.3) + purge cron

### 2a. Migration (you own `supabase/migrations/`)

Full SQL proposal: `docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md` §A.3.

```text
agents:      recording_enabled (default false), recording_consent_mode (default disclosure)
sessions:    recording_consent_* + retention/deletion columns
escalations: retention/deletion columns
telephony_calls: DO NOT re-add retention cols (already in 0014)
```

Prefer a new filename e.g. `0028_session_recording_consent_retention.sql` (avoid another dual-`0014_`).

Worker already probes missing columns — migration unlocks real consent/retention writes.

### Sign-off — A.3

- [x] Column list accepted as proposed in A.3.
- [x] Migration written: `supabase/migrations/0028_session_recording_consent_retention.sql`
  (unique number; avoids the dual-`0014_` problem). Applied and verified on a throwaway
  PostgreSQL 18 instance with the **full migration chain** — not yet applied to staging Supabase,
  which is a human step.
- [x] Does not duplicate `telephony_calls` retention columns — verified each exists exactly once
  after the chain runs.
- [x] Portal toggle can lag: `agents.recording_enabled` defaults to **false**, so existing agents
  keep recording off until someone opts in.

Extras beyond the proposal: `CHECK` constraints on `recording_consent_mode`
('off'|'disclosure'|'verbal') and `recording_consent_status` (the four
`worker/recording_policy.py` values, or NULL), plus partial indexes for the purge query.

**Signed:** Ehsan (via Claude) **Date:** 2026-09-19

### 2b. Purge cron

Script: `scripts/purge_expired_session_media.py`  
Runbook: `docs/WAVE2-SESSION-MEDIA-ERASURE.md`

```bash
python scripts/purge_expired_session_media.py --dry-run
python scripts/purge_expired_session_media.py
```

Suggested: daily or every few hours. Until session retention columns exist, script still handles `telephony_calls` and reports missing session cols.

### Sign-off — purge

- [x] Purge scheduled: `.github/workflows/purge-session-media.yml`, daily 03:30 UTC + manual
  dispatch. Dry-run by default; set `PURGE_APPLY=true` to start deleting. Apply mode requires
  `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE` or the job fails rather than clearing rows whose audio
  is still in storage.
- [x] Verified against the migrated schema: with 0028 the script finds expired sessions; without
  it, it logs "sessions retention/deleted_at columns missing" and handles telephony only.
- [ ] Portal re-sign / deletion from `recording_storage_path` — still open (can lag).

**Signed:** Ehsan (via Claude) **Date:** 2026-09-19

---

## 3. F-C7 — Mint metadata (A.4)

Full contract: `docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md` §A.4.

Add optional field on dispatch **and** agreed participant/JWT metadata:

```json
{
  "tenant_id": "<uuid>",
  "agent_id": "<uuid>",
  "greeting": "<optional>",
  "verified_caller_phone": "+923001234567"
}
```

**Rules:**

- Optional at mint; required for **browser** cancel/reschedule after F-C7 (worker fail-closes without it).  
- Prefer E.164.  
- Worker already reads `verified_caller_phone` from dispatch / participant meta / SIP / `telephony_calls`.  
- **Never** treat trunk `e164_number` as verified caller.

### Sign-off — A.4

- [x] `POST /v1/session` accepts optional `verified_caller_phone`; `/v1/session/dev-mint`
  accepts `verifiedCallerPhone` (and the snake_case spelling).
- [x] Control plane forwards it into **both** LiveKit dispatch metadata and the session JWT
  metadata. Normalized the same way `worker/write_tool_gate.py::normalize_phone` does, so the
  worker compares the value it was sent. A non-empty but unusable value is rejected with 400
  rather than silently dropped (which would surface later as the worker refusing a cancel).
- [x] Extra keys are not stripped — **including on refresh**: `/v1/session/refresh` used to
  rebuild token metadata from `tenant_id`/`agent_id` only, so a mid-call refresh would have
  dropped this field and silently revoked write-tool ownership. It now preserves the metadata.
- [x] Round-trip verified: `worker/latency.py::parse_dispatch_metadata` and
  `worker/caller_identity.py::resolve_verified_caller_phone` both accept what the mint emits.

**Signed:** Ehsan (via Claude) **Date:** 2026-09-19

**Not your job:** calendar tool idempotency — Habiba/host.

---

## 4. F-M1 — Portal / control_plane silent handlers (your half)

**Habiba:** worker handlers landed (`tests/test_fm1_worker_handlers.py`).  
**You:** production handlers **outside** `worker/` from audit Appendix A.3.

### Problem

Bare `except Exception: pass` (or fake empty data) hides outages — e.g. DB failure looking like an empty voice catalogue.

### Sites (re-verify line numbers when you open files)

| Area | Historical sites | Fix bar |
|---|---|---|
| Control plane | `control_plane/app.py` — Sentry `pass`; `/v1/voices` swallow → fake catalogue | WARNING+ log; **no fake catalogue** on DB failure |
| Telephony credentials | `tenant_portal_api/telephony_credentials.py` | Log + surface failure |
| Telephony webhooks | `tenant_portal_api/telephony_webhooks.py` | Log; don’t pretend insert succeeded |
| Telnyx client | `tenant_portal_api/telnyx_client.py` | Log with stage |
| Admin | `admin/audit.py` → `return None` | Log or narrow |

Do **not** rewrite Habiba’s worker F-M1 list unless you find a shared helper bug.

### Sign-off — F-M1 portal

- [x] Inventory refreshed by AST scan (not the audit's stale line numbers): 28 silent handlers
  outside `worker/`, of which 13 are in production service code and the rest in dev scripts.
- [x] Each production site now logs WARNING+ or is a justified leave (see below).
- [x] `/v1/voices` no longer returns a fake catalogue on DB failure — it logs and returns **503**.
  An empty-but-reachable catalogue still serves the demo list (that is not the outage path).
- [x] Changes: `control_plane/app.py` (Sentry init failure, `/v1/voices`),
  `control_plane/secrets_db.py` (secret lookup falling back to the env map),
  `tenant_portal_api/telephony_credentials.py` (failed re-encryption),
  `tenant_portal_api/telephony_webhooks.py` (hidden event-insert failure),
  `tenant_portal_api/telnyx_client.py` (provider stage), `tenant_portal_api/telephony_queries.py`
  (idempotency reservation failure reading as "duplicate"), `admin/security.py` (malformed stored
  hash — logged without the value).

  Justified leaves: `admin/audit.py::_valid_uuid` and `telephony_webhooks.py:128` parse untrusted
  input where rejecting is the correct result, not an error; the connection-teardown handlers in
  `control_plane/mint_db.py` and `tenant_portal_api/db_pool.py` fire while the connection is
  already being discarded; dev-only scripts were left alone.

**Signed:** Ehsan (via Claude) **Date:** 2026-09-19

---

## 5. F-M15 — Nothing for you (Gate A)

Product chose Gate **A**. Habiba landed remap logs + shorter picker `models` + `legacy_aliases`.

**Do not** add portal `effective_providers` UI unless product re-opens Gate C.

- [x] N/A — Gate A (2026-09-19)

---

## 6. F-M25 — Optional Dockerfile only

Habiba owns Render worker health (`worker/health_http.py`). Worker is **not** on Render yet (Habiba runs it locally).

**You:** do **not** wire Render health for the worker.

**Optional** when you touch **F-M9** Dockerfiles — only if health port is enabled in image env:

```dockerfile
ENV UVA_WORKER_HEALTH_PORT=8081 \
    UVA_WORKER_HEALTH_BIND=0.0.0.0
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=2)" || exit 1
```

- [x] Render probe = Habiba
- [ ] Optional Dockerfile HEALTHCHECK — **not done**, deliberately: it is only useful once F-M9
  (Dockerfile hardening) is picked up, and the worker is not on Render yet.

**Signed:** Ehsan (via Claude) **Date:** 2026-09-19

---

## Your “done” definition

| Ticket | Done when |
|---|---|
| **F-H18** | Both reconcile scripts scheduled (or dated interim) |
| **F-C4** | A.3 applied + purge scheduled (or interim); portal toggle can lag |
| **F-C7** | A.4 `verified_caller_phone` live end-to-end |
| **F-H10** | No work |
| **F-M1** | Portal/CP/telephony handlers no longer silent |
| **F-M15 / F-M24 / F-L6 / F-L10 / F-L15** | Nothing |
| **F-M25** | Nothing required (optional F-M9 HEALTHCHECK) |

---

## Links (read when doing the ticket)

| Doc | Use for |
|---|---|
| `docs/WAVE2-SESSION-RECONCILE.md` | F-H18 |
| `docs/WAVE2-SESSION-MEDIA-ERASURE.md` | F-C4 purge |
| `docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md` | F-C4 A.3 SQL + F-C7 A.4 mint |
| `docs/WAVE2-P0-FC4-FC7-IMPLEMENTATION-PLAN.md` | FC4/FC7 plan + Habiba status |
| `docs/WAVE2-PHASE-F-CLOSEOUT.md` | FC4/FC7 Habiba proof |
| `docs/WAVE2-HIGH-PHASE-F-CLOSEOUT.md` | High Habiba closeout |
| `docs/WAVE2-MEDIUM-LOW-PHASE-H-CLOSEOUT.md` | Medium/Low Habiba closeout |
| `docs/WAVE2-HABIBA-HOST-FOLLOWUPS.md` | Habiba-only leftovers (ignore for your work) |

Landed worker code of interest: `worker/write_tool_gate.py`, `worker/session_close.py`, `worker/provider_retries.py`, `worker/health_http.py`.
