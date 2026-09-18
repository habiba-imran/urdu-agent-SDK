## 1. F-C7 — Host tools idempotency

**Ignore self-serve.** Use the in-repo stub: **`host-tools/`**.

### Done in repo (Habiba)

- `host-tools/` Express app matching worker paths (`book_slot`, reschedule, cancel, …)
- Dedupes on `Idempotency-Key` / body `idempotency_key`
- Tests: `cd host-tools && npm test`

### What you do locally

```bash
cd host-tools
cp .env.example .env
npm install
npm test
npm run dev
```

On a **test agent**: set `tools_base_url=http://127.0.0.1:3010` and `tools_auth_secret` = same as `TOOL_GATEWAY_SECRET` in `host-tools/.env`.

Full notes: `host-tools/README.md`.

### Later (production)

Replace in-memory store with Finova’s real calendar API; keep the same routes + idempotency behaviour. Do not use self-serve for this.

---

## 2. F-M24 — Worker log / dump env (Habiba deploy checklist)

**Ehsan: nothing to do.** Habiba Phase C landed 2026-09-19:

- Code default: `UVA_DUMP_PROMPTS` and `UVA_LOG_TRANSCRIPTS` **off** when unset
- `.env.example` documents both as `0`

At first Render/worker deploy, confirm you did **not** set either to `1` in prod (local debug only).

---

## 3. F-M25 — Worker health probe (Habiba deploy checklist)

**Ehsan: do not wire Render** — you own this.

1. Set on the worker service:
   - `UVA_WORKER_HEALTH_PORT=8081` (or another free port)
   - `UVA_WORKER_HEALTH_BIND=0.0.0.0` (so the platform can reach it)
2. Point Render (or your host) health check at `GET /healthz` (liveness). Optionally use `/healthz/ready` for stricter readiness.
3. Local smoke: start worker, then `curl http://127.0.0.1:8081/healthz` → `{"status":"ok","service":"uva-worker"}`.

Code: `worker/health_http.py` (Phase E).

---

## 4. F-L6 — Turn latency room publish (Habiba manual)

**Ehsan: nothing to do.** Habiba Phase F landed 2026-09-19:

- Code default: `UVA_PUBLISH_TURN_LATENCY` **off** when unset → worker does **not** `publish_data` stage timings into the room
- Server INFO `turn_latency room=…` logs still always run
- Opt-in: set `UVA_PUBLISH_TURN_LATENCY=1` for local/demo debug panels

### Manual (when convenient)

1. Browser call with flag **unset/0** — host/SDK should **not** receive `turn_latency` / `metrics_updated` data messages.
2. Set flag to `1`, repeat — debug panel / SDK events should appear again.

---

## 5. F-L10 / F-L15 — Low cleanup (Habiba code done)

**Ehsan: nothing to do.** Habiba Phase G landed 2026-09-19:

- **F-L10:** `_cartesia_agent_session_extra` removed; Cartesia tests import `_tts_agent_session_extra`
- **F-L15:** process-level bucket ensure proven by `tests/test_fl15_bucket_ensure.py` (two uploads → `list_buckets` once on success). First-upload-only ensure kept (no prewarm ensure) per plan D8.
