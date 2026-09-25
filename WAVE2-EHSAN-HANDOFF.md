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

- [ ] Confirmed schedule state (none / already exists — where: _________)  
- [ ] Both scripts scheduled in staging  
- [ ] Both scripts scheduled in production (or dated interim: _________)  
- [ ] First dry-run counts noted: _________  

**Signed:** _____________ **Date:** _____________

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

- [ ] Column list accepted  
- [ ] Migration applied to staging  
- [ ] Will not duplicate `telephony_calls` retention columns  
- [ ] Portal `recording_enabled` toggle can lag (default false OK)  

**Signed:** _____________ **Date:** _____________

### 2b. Purge cron

Script: `scripts/purge_expired_session_media.py`  
Runbook: `docs/WAVE2-SESSION-MEDIA-ERASURE.md`

```bash
python scripts/purge_expired_session_media.py --dry-run
python scripts/purge_expired_session_media.py
```

Suggested: daily or every few hours. Until session retention columns exist, script still handles `telephony_calls` and reports missing session cols.

### Sign-off — purge

- [ ] Purge scheduled (or interim manual + owner+date)  
- [ ] Portal re-sign / deletion from `recording_storage_path` tracked (can lag)  

**Signed:** _____________ **Date:** _____________

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

- [ ] Host mint/session API may accept optional `verified_caller_phone`  
- [ ] Control plane forwards it into dispatch metadata (and token/participant meta as agreed)  
- [ ] Extra keys are not stripped  

**Signed:** _____________ **Date:** _____________

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

- [ ] Inventory refreshed against current lines  
- [ ] Each site logs WARNING+ (or justified leave)  
- [ ] `/v1/voices` no longer returns a fake catalogue on failure  
- [ ] Note of changes: _________  

**Signed:** _____________ **Date:** _____________

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
- [ ] Optional Dockerfile HEALTHCHECK with F-M9: _________  

**Signed:** _____________ **Date:** _____________

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
