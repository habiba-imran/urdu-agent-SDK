# Habiba Wave 2 — followups / ops status

**Updated:** 2026-09-27  
**Wave 2:** **CLOSED** — see [`WAVE2-CLOSED.md`](./WAVE2-CLOSED.md)  
**Branch tip:** `staging`

Honest snapshot after close. Dashboard login/signup and Render worker remain deferred.

---

## Status snapshot (2026-09-27 — closed)

| Item | Status |
|---|---|
| Ehsan shared exits (F-H18 cron, F-C4 mig+purge job, F-C7 mint phone, F-M1 portal) | **Done** (merged) |
| Migrations **0028–0033** applied on staging DB | **Done** |
| `TENANT_SECRET_ENCRYPTION_KEY` on CP + portal + admin + local; encrypt + `--finalize` + `--agents` | **Done** |
| Hosted fail-fast env (`UVA_ENV`, `CP_ALLOWED_ORIGINS`, JWT secrets) on Render staging | **Done** |
| `TELNYX_OUTBOUND_DESTINATIONS=all` on **uva-tenant-portal-staging** | **Done** |
| Reconcile + purge GitHub Actions dry-runs (secrets set) | **Done** — purge stays dry-run; reconcile apply optional post-close |
| `host-tools/` idempotency stub + curl proof | **Done** |
| Live injection (`python tests/test_injection_live.py`) | **Gemini green**; Groq secrecy harden shipped |
| Greeting-cache / schema backfill / Gladia / lint residuals | **Done** |
| Portal recording toggle + session re-sign | **Done** (API + Advanced Settings + `recording_urls.py`) |
| **F-M25** Render worker + `/healthz` | **Deferred** — worker stays **local** |
| Dashboard login/signup / first-run UX | **Deferred** — Habiba later |
| Flip `PURGE_APPLY` | **Deferred** — after dry-run week |
| Real Finova calendar instead of `host-tools` | **Later** (prod) |

---

## 1. F-C7 — Host tools idempotency

### Done

- `host-tools/` Express stub matching worker paths (`book_slot`, reschedule, cancel, …)
- Dedupes on `Idempotency-Key` / body `idempotency_key`
- Local proof: double `book_slot` with same key → same `appointment_id`, one row
- Tests: `cd host-tools && npm test`

### Local run (when needed)

```bash
cd host-tools
cp .env.example .env   # if missing
npm install
npm test
npm run dev            # http://127.0.0.1:3010
```

On a **test agent**: `tools_base_url=http://127.0.0.1:3010`, `tools_auth_secret` = `TOOL_GATEWAY_SECRET`.

### Later (production)

Replace in-memory store with Finova’s real calendar API; keep routes + idempotency. Do not use self-serve for this.

---

## 2. F-M24 — Worker log / dump env

**Code:** defaults **off**. Staging/local confirmed not forced on (`.env.local` unset / `0`).

At first **paid** Render worker deploy, confirm neither `UVA_DUMP_PROMPTS` nor `UVA_LOG_TRANSCRIPTS` is `1`.

---

## 3. F-M25 — Worker health probe (deferred)

**Code:** `worker/health_http.py` landed.  
**Ops:** worker runs **local** for now — **do not** treat Render worker health as blocking Wave 2 close.

When you pay for a worker Web Service, see **`docs/WAVE2-HABIBA-RENDER-DEPLOY.md`**:

1. `UVA_WORKER_HEALTH_PORT=10000` (match Render `PORT`)
2. `UVA_WORKER_HEALTH_BIND=0.0.0.0`
3. Health Check Path = `/healthz`

---

## 4. F-L6 — Turn latency room publish

Code landed; optional browser confirm remains non-blocking.

---

## 5. F-C4 — Recording portal surface

- `recording_enabled` on create/PATCH (portal + machine) and dashboard Advanced Settings
- Session list / machine session get re-sign short-lived URLs from `recording_storage_path` (storage path not returned to clients)

---

## Related docs

| Doc | Role |
|---|---|
| `docs/WAVE2-CLOSED.md` | Wave 2 closed declaration |
| `docs/WAVE2-EHSAN-HANDOFF.md` | Shared exits checklist |
| `docs/WAVE2-HABIBA-RENDER-DEPLOY.md` | Full Render stack (worker section deferred) |
| `docs/WAVE2-PHASE-F-CLOSEOUT.md` | F-C4/F-C7 proof + live injection |
| `docs/WAVE2-SESSION-RECONCILE.md` | F-H18 reconcile |
| `docs/WAVE2-SESSION-MEDIA-ERASURE.md` | F-C4 purge |
