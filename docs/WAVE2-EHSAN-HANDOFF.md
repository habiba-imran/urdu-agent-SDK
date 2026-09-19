# Wave 2 — Ehsan handoff (read this tomorrow)

**From:** Habiba  
**Date:** 2026-09-18 (Critical/High) · **updated 2026-09-19** (Medium/Low §7–§9; Habiba Phase H closeout)  
**Habiba High Phase F (done):** Closeout `docs/WAVE2-HIGH-PHASE-F-CLOSEOUT.md`. Regression **74 passed**.  
**Habiba Medium/Low:** Phase A gates **A/A/A**; **Phases B–H done** 2026-09-19. Closeout `docs/WAVE2-MEDIUM-LOW-PHASE-H-CLOSEOUT.md` (regression **55 passed**). Your Medium/Low exits remain §7–§9 — do them **after** Critical/High §1–§3. **F-M15/F-M24/F-L6/F-L10/F-L15** → nothing for you. **F-M25 Render** → Habiba; optional Dockerfile HEALTHCHECK when you do F-M9 (§9). **F-M1 portal half** → you (§7).

**Why:** Habiba finishes Habiba-owned Wave 2 worker code first. You own the shared exits below (schema, mint, crons, portal, plus Medium/Low portal/ops). This doc is the single checklist so you do not hunt across chats.

**Do not re-implement Habiba worker paths** unless you find a bug against the landed code. Prefer reading the linked contracts and running the existing scripts.

**Out of your scope (Habiba / host owns):** Render worker deploy + `UVA_SESSION_RECORD_AUDIO` (Habiba host followups); host calendar **idempotency**; second Urdu provider (product closed — none); Habiba worker F-M1 / F-M15 / F-M24 / F-L6 / F-L10 / F-L15 code. See `docs/WAVE2-HABIBA-HOST-FOLLOWUPS.md` if curious — **do not action those.**

---

## 0. Status snapshot (honest)

| Track | Habiba | Your part | Full ticket ✅? |
|---|---|---|---|
| **F-C4** recording / consent / retention | Worker Phases B–D done | Migration A.3, purge cron, portal re-sign / agent toggle | **No** until shared exits |
| **F-C7** write-tool gate / ownership | Worker Phase E + F proof done | Mint A.4 `verified_caller_phone` only | **No** until A.4 (+ Habiba host idempotency — not you) |
| **F-H18** quota/billing on crash | Phase B close harden + Phase C runbook/tests **landed** | **Schedule both reconcile scripts** (C.3) | **No** until cron |
| **F-H10** Urdu | Retries landed; **no second provider** (product) | **Nothing** — do not invent fallback columns | Closed as residual (retries only) |
| **F-M1** silent `except` | Worker Phase B **landed** 2026-09-19 | **Portal / control_plane / telephony** silent handlers (Appendix A.3) — §7 | Split ticket |
| **F-M15** provider honesty | Worker Phase D **landed** (Gate A: logs + `models`/`legacy_aliases`) | **Nothing** — §8 N/A; API already exposes shorter `models` + optional `legacyAliases` | Habiba |
| **F-M24** dump/transcript PII | Worker Phase C **landed** (defaults off) | **Nothing** | Habiba |
| **F-M25** worker health | Worker Phase E **landed** (`worker/health_http.py`) | Optional Dockerfile `HEALTHCHECK` with F-M9 — §9 (**Render = Habiba**) | Habiba deploy |
| **F-L6** latency room publish | Worker Phase F **landed** (`UVA_PUBLISH_TURN_LATENCY` default off) | **Nothing** | Habiba |
| **F-L10** Cartesia alias | Worker Phase G **landed** (alias deleted; tests use `_tts_agent_session_extra`) | **Nothing** | Habiba |
| **F-L15** bucket ensure once | Worker Phase G **landed** (process cache + unit test; no prewarm ensure) | **Nothing** | Habiba |

---

## 1. F-H18 — Schedule reconcile (highest ops priority)

### Problem

Session close, quota decrement, and `usage_events` run only in LiveKit **shutdown callbacks**. Crash/OOM → open sessions forever + stuck `concurrent_now`. Scripts exist; **nothing in this repo schedules them**.

**Habiba Phase B (done):** `worker/session_close.py`. **Does not replace your cron.**

**Habiba Phase C (done):** `docs/WAVE2-SESSION-RECONCILE.md` + `tests/test_reconcile_sessions.py`. **Your C.3 schedule is the Gate 5 exit.**

### Scripts (already on disk)

```bash
# Sessions + concurrency (default closes opens older than 30m)
python scripts/reconcile_sessions.py --dry-run
python scripts/reconcile_sessions.py --max-age-minutes 30

# Telephony stale orders / stuck calls / quota leaks
python scripts/reconcile_telephony.py          # dry-run
python scripts/reconcile_telephony.py --apply  # write
```

Drill: `scripts/simulate_worker_crash.py`.  
Runbook: **`docs/WAVE2-SESSION-RECONCILE.md`**.

### What you should do (C.3)

1. Confirm whether any cron already exists **outside** git.  
2. Schedule **both** scripts (suggested every **5–15 minutes**). Pattern: `.github/workflows/refresh-voice-previews.yml` or your ops host’s cron.  
3. Prefer dry-run in logs first week, then apply.  
4. Fix README F-L1 when convenient: “Run migrations” must not point at `reconcile_sessions.py --dry-run`.  
5. Optional interim: owner + date + manual cadence in the sign-off box (still not full ✅).

### Sign-off (Ehsan) — C.3

- [ ] Confirmed current schedule state (none / already exists — note where: _________)  
- [ ] Both scripts scheduled in staging  
- [ ] Both scripts scheduled in production (or dated interim: manual cadence _________)  
- [ ] First dry-run counts pasted (sessions stale / tenants mismatched; telephony stale orders/calls/quota): _________

**Signed:** _____________ **Date:** _____________

---

## 2. F-C4 — Schema migration (A.3) + purge cron

### 2a. Migration (you own `supabase/migrations/`)

Full SQL proposal: `docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md` §A.3.

Summary:

```text
agents:     recording_enabled (default false), recording_consent_mode (default disclosure)
sessions:   recording_consent_* + retention/deletion columns
escalations: retention/deletion columns
telephony_calls: DO NOT re-add retention cols (already 0014)
```

Prefer new filename e.g. `0028_session_recording_consent_retention.sql` (avoid another dual-`0014_`).

Worker already feature-flags / probes missing columns — migration unblocks real consent/retention writes.

### Sign-off (Ehsan) — A.3

- [ ] Column list accepted  
- [ ] Migration filename reserved + applied to staging  
- [ ] Will not duplicate `telephony_calls` retention columns  
- [ ] Portal toggle for `recording_enabled` can lag (default false OK)

**Signed:** _____________ **Date:** _____________

### 2b. Purge cron

Script: `scripts/purge_expired_session_media.py`  
Runbook: `docs/WAVE2-SESSION-MEDIA-ERASURE.md`

```bash
python scripts/purge_expired_session_media.py --dry-run
python scripts/purge_expired_session_media.py
```

Suggested: daily or every few hours. Until `sessions` retention columns exist, script still handles `telephony_calls` and reports missing session cols.

### Sign-off (Ehsan) — purge

- [ ] Purge scheduled (or interim manual + owner+date)  
- [ ] Portal “request deletion” / re-sign from `recording_storage_path` tracked (can lag)

**Signed:** _____________ **Date:** _____________

---

## 3. F-C7 — Mint metadata (A.4)

### Contract

Full text: `docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md` §A.4.

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
- Worker already reads `verified_caller_phone` via `parse_dispatch_metadata` / participant meta / SIP `sip.phoneNumber` / `telephony_calls` remote party.  
- **Never** treat trunk `e164_number` as verified caller (worker already avoids this).

### Sign-off (Ehsan) — A.4

- [ ] Host mint/session API may accept optional `verified_caller_phone`  
- [ ] CP forwards it into dispatch metadata (and token/participant meta as agreed)  
- [ ] Extra keys are not stripped  

**Signed:** _____________ **Date:** _____________

**Not your job:** Calendar tool **idempotency** (`idempotency_key` / `Idempotency-Key`) — Habiba/host. Do not block A.4 on that.

---

## 4. Suggested order for you tomorrow

1. **Ack** this handoff (cron ownership for reconcile + purge).  
2. **A.3 migration** draft/apply staging.  
3. **Schedule** `reconcile_sessions` + `reconcile_telephony` (+ purge).  
4. **A.4** mint `verified_caller_phone`.  
5. Portal re-sign / recording toggle when you have bandwidth (can lag).  
6. **Then** Medium/Low §7 (F-M1 portal) → §9 (worker HEALTHCHECK when Habiba Phase E lands) → §8 only if product Gate C.

---

## 5. Links (Habiba already landed)

| Doc / code | Purpose |
|---|---|
| `docs/WAVE2-P0-FC4-FC7-IMPLEMENTATION-PLAN.md` | FC4/FC7 full plan + Habiba status |
| `docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md` | FC4/FC7 A.3/A.4 SQL + mint |
| `docs/WAVE2-PHASE-F-CLOSEOUT.md` | FC4/FC7 proof |
| `docs/WAVE2-FC4-FC7-STATUS-HANDOFF.md` | Short status for new chats |
| `docs/WAVE2-HIGH-FH10-FH18-IMPLEMENTATION-PLAN.md` | F-H18/F-H10 plan |
| `docs/WAVE2-HIGH-PHASE-A-BASELINE-AND-CONTRACTS.md` | High Phase A baseline |
| `docs/WAVE2-SESSION-MEDIA-ERASURE.md` | FC4 purge runbook |
| `docs/WAVE2-SESSION-RECONCILE.md` | F-H18 reconcile runbook |
| `docs/WAVE2-HIGH-PHASE-F-CLOSEOUT.md` | High track Habiba closeout |
| `docs/WAVE2-MEDIUM-LOW-IMPLEMENTATION-PLAN.md` | Habiba Medium/Low plan |
| `docs/WAVE2-MEDIUM-LOW-PHASE-A-BASELINE.md` | Medium/Low Phase A inventories + gates |
| `worker/write_tool_gate.py`, `worker/session_close.py`, `worker/provider_retries.py`, … | Landed worker code |

---

## 6. What “done” means for your exits (Critical / High)

| Ticket | Your exit |
|---|---|
| F-C4 | A.3 applied + purge scheduled (or interim) + portal toggle when ready |
| F-C7 | A.4 mint `verified_caller_phone` live end-to-end |
| F-H18 | Both reconcile scripts scheduled (or dated interim) |
| F-H10 | **No work** — product closed second provider |

---

## 7. F-M1 — Portal / control_plane silent exception handlers (your half)

**Habiba owns:** worker handlers — Phase B **landed** 2026-09-19 (`tests/test_fm1_worker_handlers.py`).  
**You own:** production service handlers outside `worker/` from audit Appendix A.3.

### Problem (plain language)

Some `except Exception: pass` (or return fake data) hide real outages — e.g. a DB failure can look like an empty voice catalogue, or a failed credential rewrite never surfaces.

### Sites to fix (start from audit; re-verify line numbers when you open the files)

| Area | Historical audit sites | Fix bar |
|---|---|---|
| Control plane | `control_plane/app.py` — Sentry init `pass`; `/v1/voices` swallow → fake catalogue | Log WARNING+ with context; do **not** return a fake catalogue on DB failure (fail honestly) |
| Telephony credentials | `tenant_portal_api/telephony_credentials.py` re-encryption `pass` | Log + surface failure to caller/ops |
| Telephony webhooks | `tenant_portal_api/telephony_webhooks.py` event insert `pass` | Log; do not pretend insert succeeded |
| Telnyx client | `tenant_portal_api/telnyx_client.py` `pass` | Log with stage |
| Admin | `admin/audit.py` → `return None` | Log or narrow |

**Do not** edit Habiba’s worker Phase B list unless you find a shared helper bug.

### Sign-off (Ehsan) — F-M1 portal

- [ ] Inventory refreshed against current line numbers  
- [ ] Each site logs WARNING+ (or justified leave with comment)  
- [ ] `/v1/voices` no longer returns a fake catalogue on failure  
- [ ] Brief note of what you changed: _________

**Signed:** _____________ **Date:** _____________

---

## 8. F-M15 — Portal / API “effective providers” (**N/A — Gate A**)

**Product Gate 1 signed 2026-09-19: A.** Habiba Phase D **landed**:

- Adapter logs `requested` → `effective` on model remap  
- Capabilities: picker `models` = live IDs only; `legacy_aliases` still validate old agent rows  
- Public API: `models` + optional `legacyAliases` (dashboard already reads `models` for pickers — no portal PR required)  
- Session start logs `effective_providers … requested_llm=… effective_llm=…`

**You do nothing for F-M15.** Do not add portal `effective_providers` UI unless product re-opens Gate C later.

### Sign-off (Ehsan) — F-M15 portal

- [x] **N/A** — Gate A (2026-09-19)

---

## 9. F-M25 — Worker health (Habiba deploys; optional Dockerfile only)

**Habiba Phase E landed 2026-09-19:** `worker/health_http.py`

| Env | Meaning |
|---|---|
| `UVA_WORKER_HEALTH_PORT` | Unset/`0` = **off**. Set e.g. `8081` to enable. |
| `UVA_WORKER_HEALTH_BIND` | Default `127.0.0.1`. Use `0.0.0.0` for Docker/Render probes. |

| Path | Meaning |
|---|---|
| `GET /healthz` | Liveness — process up (`200`) |
| `GET /healthz/ready` | Ready — LiveKit env + VAD prewarmed + DB `SELECT 1` (`200` / `503`) |

**Habiba owns Render / staging/prod probe wiring.**

### What you should do

1. **Do not** configure Render health for the worker — Habiba will.  
2. **Optional** when you touch **F-M9** Dockerfiles — example for `docker/worker.Dockerfile` (only if port is enabled in the image env):

```dockerfile
ENV UVA_WORKER_HEALTH_PORT=8081 \
    UVA_WORKER_HEALTH_BIND=0.0.0.0
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=2)" || exit 1
```

3. Do not invent a health stack in `tenant_portal_api` for the LiveKit worker.

### Sign-off (Ehsan) — F-M25

- [x] **Render probe = Habiba** (not you)  
- [ ] Optional Dockerfile HEALTHCHECK if/when you do F-M9: _________

**Signed:** _____________ **Date:** _____________

---

## 10. What “done” means for your Medium/Low exits

| Ticket | Your exit |
|---|---|
| F-M1 (portal half) | §7 handlers logged / no fake catalogue |
| F-M15 | **Nothing** — Gate A |
| F-M25 | **Nothing required** for Render; optional F-M9 Dockerfile HEALTHCHECK |
| F-M24, F-L6, F-L10, F-L15 | **Nothing** — Habiba (F-L6 Phase F + F-L10/F-L15 Phase G landed) |
