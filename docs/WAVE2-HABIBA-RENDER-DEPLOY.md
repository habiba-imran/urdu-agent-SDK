# Habiba — Render fresh start (full stack)

**Situation:** nothing is live on Render right now (old services were suspended). Treat this as a **brand-new** deploy from branch `habiba`.  
**Do not** look for old services to “update.” Create new ones.

**Repo already pushed:** `origin/habiba` on `https://github.com/habiba-imran/urdu-agent-SDK.git`

**How a browser call works (so you know what must be up):**

```text
Client host backend  →  Control plane (mint + LiveKit dispatch)
                              ↓
                     LiveKit Cloud room
                              ↓
                     Voice worker (joins room, runs STT/LLM/TTS)
```

Admin and tenant-portal are **Finova ops / telephony** — needed for full product, not for the thinnest “one browser call” path.

---

## 0. What exists in this repo (evidence, not guesses)

| # | Service | Dockerfile | Process command | Default container port | Health URL | In GitHub deploy hooks? |
|---|---|---|---|---|---|---|
| **1** | **Control plane** (session mint / dispatch) | `docker/control-plane.Dockerfile` | `uvicorn control_plane.app:app --host 0.0.0.0 --port 8000` | **8000** | `GET /healthz` | Yes (`CONTROL_PLANE`) |
| **2** | **Voice worker** (LiveKit agent) | `docker/worker.Dockerfile` | `python -m worker.main start` | health via env (see §3) | `GET /healthz` when enabled | Yes (`WORKER`) |
| **3** | **Admin API** (super-admin) | `docker/admin.Dockerfile` | `uvicorn admin.app:app --host 0.0.0.0 --port 8001` | **8001** | `GET /healthz` | Yes (`ADMIN`) |
| **4** | **Tenant portal API** (tenant UI backend + telephony) | `docker/tenant-portal-api.Dockerfile` | `uvicorn tenant_portal_api.app:app --host 0.0.0.0 --port 8000` | **8000** | `GET /healthz` | **No** (Dockerfile exists; hooks never listed it) |

**Not deployed from this repo’s Dockerfiles (do not create Render services for these unless you have a separate plan):**

| Thing | Why |
|---|---|
| `dashboard/` frontend | No Dockerfile; usually a static host (Vercel/Netlify) pointed at Admin/Tenant APIs |
| `demo-app/`, `host-tools/`, `client-integration-test/` | Client / local stubs — run on the **host** machine, not AwaazLabs Render |
| Supabase | External (DB + Storage) |
| LiveKit Cloud | External (rooms + agent jobs) |
| npm packages (`sdk/`, `sdk-server/`, `telephony/`) | Published to npm, not Render |

**Minimum for “voice works again”:** services **1 + 2** (control plane + worker), plus LiveKit + Supabase already configured.

**Full Finova staging:** **1 + 2 + 3**, and **4** if you need tenant portal / Telnyx.

---

## 1. Before Render — external prerequisites

You need these **outside** Render (copy values from your password manager / old notes / `.env.local` — never commit secrets):

### 1.1 LiveKit Cloud project

- `LIVEKIT_URL` (`wss://…`)
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- Pick one agent name, e.g. `uva-staging-agent` — you will set **the same** `LIVEKIT_AGENT_NAME` on **control plane and worker**

### 1.2 Supabase project

- `SUPABASE_DB_URL` (Postgres connection string — used by CP / admin / worker / portal)
- For worker recordings: `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE`
- Migrations applied on that DB (Ehsan’s Wave 2 schema work may still be pending — voice mint can work with current schema; recording/purge extras wait on him)

### 1.3 Provider API keys (worker)

At least the stack you actually use in staging:

| Key | Used for |
|---|---|
| `GROQ_API_KEY` | English LLM |
| `DEEPGRAM_API_KEY` | English STT |
| `CARTESIA_API_KEY` | English TTS |
| `GOOGLE_API_KEY` | Gemini paths |
| `GLADIA_API_KEY` | Urdu STT |
| `UPLIFTAI_API_KEY` | Urdu TTS (**exact name**) |
| Optional: `ELEVEN_API_KEY`, `FISH_API_KEY`, `RIME_API_KEY` | If agents select those TTS providers |

### 1.4 GitHub ↔ Render

1. Open [https://dashboard.render.com](https://dashboard.render.com)  
2. Sign in to the workspace that will own these services  
3. **Account Settings → Connected Accounts / GitHub** — connect `habiba-imran` (or the org that has the repo)  
4. Confirm Render can see `habiba-imran/urdu-agent-SDK`

---

## 2. Create service #1 — Control plane (Web Service)

### 2.1 Buttons

1. Dashboard → **New +** → **Web Service**  
2. **Build and deploy from a Git repository** → **Next**  
3. Select **`habiba-imran/urdu-agent-SDK`** → **Connect**  
4. Fill the form:

| Field | What to enter |
|---|---|
| **Name** | `uva-control-plane-staging` (or `…-prod` later) |
| **Region** | Pick one and **reuse it for every service below** (e.g. Oregon) |
| **Branch** | `habiba` |
| **Root Directory** | leave **empty** |
| **Runtime** | **Docker** |
| **Dockerfile Path** | `docker/control-plane.Dockerfile` |
| **Docker Build Context Directory** | `.` / empty |
| **Instance type** | **Starter** is usually enough for mint API; bump if load grows |
| **Health Check Path** | `/healthz` |

5. Open **Advanced** → **Environment Variables** → add §2.2  
6. Click **Create Web Service**  
7. Wait until status is **Live**

### 2.2 Environment variables (control plane)

From `docs/62-GUIDE-PROD-ENV-VARS.md` + current code:

| Key | Required? | Example / notes |
|---|---|---|
| `SUPABASE_DB_URL` | **Yes** | Postgres URL |
| `LIVEKIT_URL` | **Yes** | `wss://…` |
| `LIVEKIT_API_KEY` | **Yes** | |
| `LIVEKIT_API_SECRET` | **Yes** | secret |
| `LIVEKIT_AGENT_NAME` | **Yes** | e.g. `uva-staging-agent` — **must match worker** |
| `CP_TENANT_SECRETS` | **Yes** | JSON: `{"<tenant_uuid>":"<hmac_secret>"}` |
| `CP_ALLOWED_ORIGINS` | Recommended | Comma-separated host origins that call mint (your demo/host backends). Empty = permissive (dev-like; tighten for prod) |

Optional: `SENTRY_DSN`, `ENVIRONMENT=staging`

**Port note:** Dockerfile listens on **8000**. Render’s default `PORT` is `10000`, but Render usually **auto-detects** the bound port. If the deploy fails with “no open ports”, set a **Docker Command** override in Settings:

```text
uvicorn control_plane.app:app --host 0.0.0.0 --port 10000
```

and keep Health Check Path `/healthz`. Prefer leaving the Dockerfile CMD alone first.

### 2.3 Verify control plane

```powershell
curl.exe https://uva-control-plane-staging.onrender.com/healthz
```

Expect a healthy JSON/ok response (exact body can vary; HTTP **200** is the bar).

Copy the public URL — host backends need it as `UVA_CONTROL_PLANE_URL`.

---

## 3. Create service #2 — Voice worker (Web Service)

Use a **Web Service** (not Background Worker) so Render can HTTP-check `/healthz` (F-M25).

### 3.1 Buttons

1. **New +** → **Web Service** → same GitHub repo  
2. Form:

| Field | What to enter |
|---|---|
| **Name** | `uva-voice-worker-staging` |
| **Region** | **Same as control plane** |
| **Branch** | `habiba` |
| **Root Directory** | empty |
| **Runtime** | **Docker** |
| **Dockerfile Path** | `docker/worker.Dockerfile` |
| **Docker Build Context Directory** | `.` |
| **Instance type** | **Standard** (or higher) — VAD + providers need more RAM than the mint API |
| **Health Check Path** | `/healthz` |

3. **Environment** → §3.2  
4. **Create Web Service** → wait for **Live**

First worker image build is **slow** (full `requirements.txt` + LiveKit plugins). Don’t panic at 10–15+ minutes.

### 3.2 Environment variables (worker)

#### A. Must match control plane / LiveKit

| Key | Value |
|---|---|
| `LIVEKIT_URL` | same as CP |
| `LIVEKIT_API_KEY` | same as CP |
| `LIVEKIT_API_SECRET` | same as CP |
| `LIVEKIT_AGENT_NAME` | **identical** to CP (e.g. `uva-staging-agent`) |
| `SUPABASE_DB_URL` | same DB |

#### B. Health probe (Wave 2 F-M25) — required for Render health checks

Render probes the service’s public HTTP port (default **`PORT=10000`**). Our health server reads **`UVA_WORKER_HEALTH_PORT`**, not `PORT`.

| Key | Value |
|---|---|
| `UVA_WORKER_HEALTH_PORT` | `10000` |
| `UVA_WORKER_HEALTH_BIND` | `0.0.0.0` |

If you later change Render’s `PORT`, change `UVA_WORKER_HEALTH_PORT` to the **same number**.

#### C. Wave 2 safe defaults (set explicitly)

| Key | Value |
|---|---|
| `UVA_DUMP_PROMPTS` | `0` |
| `UVA_LOG_TRANSCRIPTS` | `0` |
| `UVA_PUBLISH_TURN_LATENCY` | `0` |
| `UVA_PROVIDER_MAX_RETRY` | `2` |
| `UVA_FORCE_GROQ_ENGLISH` | `1` |
| `UVA_SESSION_RECORD_AUDIO` | `0` (or omit) |

#### D. Provider keys

Set every key listed in §1.3 that you need for staging agents.

#### E. Recording upload (if agents record)

| Key | Value |
|---|---|
| `SUPABASE_URL` | project URL |
| `SUPABASE_SERVICE_ROLE` | service role key |
| `UVA_RECORDING_RETENTION_DAYS` | `30` |

Render sets `RENDER=true` automatically — do not invent it.

### 3.3 Verify worker

```powershell
curl.exe https://uva-voice-worker-staging.onrender.com/healthz
```

Expect something like:

```json
{"status":"ok","service":"uva-worker"}
```

Optional:

```powershell
curl.exe https://uva-voice-worker-staging.onrender.com/healthz/ready
```

(`ready` needs LiveKit env + VAD + DB — can be `503` briefly during cold start.)

In **Logs**, you should eventually see the LiveKit worker **register** (agent name matching CP).

---

## 4. Create service #3 — Admin API (Web Service)

Needed for Finova super-admin tooling. Not on the client voice hot path.

### 4.1 Buttons

| Field | Value |
|---|---|
| **Name** | `uva-admin-staging` |
| **Region** | same |
| **Branch** | `habiba` |
| **Runtime** | Docker |
| **Dockerfile Path** | `docker/admin.Dockerfile` |
| **Instance type** | Starter |
| **Health Check Path** | `/healthz` |

### 4.2 Environment variables (admin)

| Key | Required? | Notes |
|---|---|---|
| `SUPABASE_DB_URL` | **Yes** | same DB |
| `ADMIN_JWT_SECRET` | **Yes — set explicitly** | Generate once: `python -c "import secrets; print(secrets.token_hex(32))"`. Do **not** rely on auto-generate in a container. |
| `ADMIN_PORTAL_ORIGINS` | **Yes** | Comma-separated **admin frontend** origins only (never tenant/SDK origins) |

### 4.3 Verify

```powershell
curl.exe https://uva-admin-staging.onrender.com/healthz
```

**Port note:** Dockerfile uses **8001**. Same as CP — leave CMD; if Render complains about ports, override Docker Command to `--port 10000`.

---

## 5. Create service #4 — Tenant portal API (optional but recommended for telephony)

Has a Dockerfile; **not** in the old deploy-hook trio. Create it if you need tenant portal or Telnyx.

### 5.1 Buttons

| Field | Value |
|---|---|
| **Name** | `uva-tenant-portal-staging` |
| **Region** | same |
| **Branch** | `habiba` |
| **Runtime** | Docker |
| **Dockerfile Path** | `docker/tenant-portal-api.Dockerfile` |
| **Docker Build Context Directory** | `.` |
| **Instance type** | Starter / Standard |
| **Health Check Path** | `/healthz` |

> The image **must** include `control_plane/` (HMAC helpers). Current Dockerfile copies `tenant_portal_api/` + `control_plane/` + `scripts/`. If deploy crashes with `No module named 'control_plane'`, you are on an old image — redeploy latest `habiba`.

### 5.2 Environment variables (tenant portal) — core

| Key | Required? | Notes |
|---|---|---|
| `SUPABASE_DB_URL` | **Yes** | |
| `TENANT_PORTAL_JWT_SECRET` | **Yes — set explicitly** | Same rule as admin: generate once, store as secret |
| `TENANT_PORTAL_ORIGINS` | **Yes** | Real tenant dashboard origin(s) |

### 5.3 Telephony extras (only if enabling real Telnyx)

See also `docs/TELEPHONY_REAL_PROVIDER_STAGING.md`:

| Key | Value |
|---|---|
| `TELEPHONY_PROVIDER_MODE` | `real` |
| `TELEPHONY_CREDENTIAL_ENCRYPTION_KEY` | stable secret |
| `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | same project |
| `LIVEKIT_SIP_URI` | if using SIP |
| `LIVEKIT_AGENT_NAME` | same agent name |
| `TELNYX_PUBLIC_KEY` | webhook verify |
| `TELEPHONY_WEBHOOK_PUBLIC_BASE_URL` | `https://uva-tenant-portal-staging.onrender.com` (your real URL) |
| `CP_TENANT_SECRETS` | if machine auth uses env map |

**Never on Render:**

- `TELEPHONY_ALLOW_MOCK_MACHINE_AUTH=1`
- `TELEPHONY_ALLOW_MOCK_PORTAL_AUTH=1`

### 5.4 Verify

```powershell
curl.exe https://uva-tenant-portal-staging.onrender.com/healthz
```

---

## 6. Suggested create order

1. **Control plane** → curl `/healthz`  
2. **Worker** → curl `/healthz` → confirm LiveKit registration in logs  
3. **Admin** (ops)  
4. **Tenant portal** (portal / telephony)  

Then run one browser call through your **host backend** (`demo-app` / client) pointed at the new control-plane URL.

---

## 7. After services are Live — wire the client side (not Render)

On your laptop / host backend `.env` (example names from `docs/CLIENT_QUICKSTART.md`):

| Host var | Points to |
|---|---|
| `UVA_CONTROL_PLANE_URL` | `https://uva-control-plane-staging.onrender.com` |
| `UVA_API_BASE_URL` | tenant portal URL if you use provider picker / portal APIs |
| `UVA_TENANT_ID` / `UVA_HMAC_SECRET` / publishable key | from onboarding / DB — must match `CP_TENANT_SECRETS` |

`host-tools/` stays local unless you deliberately deploy a calendar stub elsewhere.

---

## 8. Plans / money (plain language)

| Service | Suggested starting plan | Why |
|---|---|---|
| Control plane | Starter | Light HTTP |
| Voice worker | **Standard+** | LiveKit agent + Silero + providers |
| Admin | Starter | Light HTTP |
| Tenant portal | Starter → Standard if telephony busy | HTTP + webhooks |

Avoid **Free** for worker (spins down → missed calls / cold starts).

Same **region** for all four reduces latency and keeps private networking simple if you use it later.

---

## 9. Deploy hooks (do later)

Old automation (`.github/workflows/deploy-staging.yml` / `deploy-prod.yml`) curls three secrets:

- `RENDER_DEPLOY_HOOK_CONTROL_PLANE_STAGING` / prod  
- `RENDER_DEPLOY_HOOK_WORKER_STAGING` / prod  
- `RENDER_DEPLOY_HOOK_ADMIN_STAGING` / prod  

**After** services exist:

1. Each service → **Settings → Deploy Hook** → create hook → copy URL  
2. GitHub repo → **Settings → Secrets and variables → Actions** → paste into the secret names above  
3. Until hooks exist, use dashboard **Manual Deploy → Deploy latest commit**

Tenant portal has **no** hook in those workflows — add one yourself if you want auto-deploy for service #4.

---

## 10. Master checklist

### External
- [ ] LiveKit project + keys  
- [ ] Supabase DB URL (+ service role if recording)  
- [ ] Provider keys  
- [ ] GitHub connected to Render  

### Render services
- [ ] `uva-control-plane-…` Live + `/healthz`  
- [ ] `uva-voice-worker-…` Live + `/healthz` + agent registered  
- [ ] Same `LIVEKIT_AGENT_NAME` on CP and worker  
- [ ] Worker: health port `10000` + bind `0.0.0.0`  
- [ ] Worker: dump/transcript/latency flags = `0`  
- [ ] `uva-admin-…` Live (if needed) + `ADMIN_JWT_SECRET` set  
- [ ] `uva-tenant-portal-…` Live (if needed) + JWT secret set  

### Smoke
- [ ] Host backend points at new CP URL  
- [ ] One browser call hears audio  

---

## 11. Common failures

| Symptom | Fix |
|---|---|
| Deploy: no open port | Override Docker CMD to `--port 10000`, or confirm Render detected 8000/8001 |
| Worker health check fails | `UVA_WORKER_HEALTH_PORT=10000` and `UVA_WORKER_HEALTH_BIND=0.0.0.0` |
| Worker Live but no jobs | `LIVEKIT_AGENT_NAME` mismatch CP ↔ worker |
| Mint fails auth | `CP_TENANT_SECRETS` tenant id / HMAC wrong |
| Admin logs you out every deploy | `ADMIN_JWT_SECRET` not set (auto-gen died with container) |
| Build OOM on worker | Bump instance type / clear build cache |

---

## 12. Related docs

- Env inventory (CP/admin): `docs/62-GUIDE-PROD-ENV-VARS.md`  
- Local template: `.env.example`  
- Telephony staging: `docs/TELEPHONY_REAL_PROVIDER_STAGING.md`  
- Ehsan leftovers: `docs/WAVE2-EHSAN-HANDOFF.md`  
- Habiba non-Render leftovers: `docs/WAVE2-HABIBA-HOST-FOLLOWUPS.md`
