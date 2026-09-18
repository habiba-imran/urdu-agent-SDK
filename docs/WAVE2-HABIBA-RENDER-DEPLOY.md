# Habiba — Render deploy guide (Wave 2 worker)

**Audience:** you (Habiba)  
**Goal:** get the Wave 2 worker code from branch `habiba` onto Render, with the **new health probe** and **safe PII defaults**.  
**Repo remote:** `origin` → `https://github.com/habiba-imran/urdu-agent-SDK.git`  
**Branch to deploy:** `habiba` (push this first, then point Render at it or merge to whatever branch your Render service already tracks)

This guide is written for the **Render Dashboard UI** (browser). Exact button labels can shift slightly; follow the section names.

---

## 0. Before you open Render

### 0.1 Confirm code is on GitHub

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent
git checkout habiba
git status
git log -1 --oneline
git push -u origin habiba
```

You want `origin/habiba` to include Wave 2 (health HTTP, dump defaults off, etc.).

### 0.2 Know which services you already have

This repo’s GitHub Actions expect **three** Render services (staging + prod hooks):

| Role | Typical name pattern (yours may differ) | What it runs |
|---|---|---|
| Control plane | e.g. `…-control-plane…` / `urdu-agent-sdk-1` | FastAPI mint / dispatch |
| **Voice worker** | e.g. `…-worker…` | `python -m worker.main start` ← **this guide focuses here** |
| Admin portal | e.g. `…-admin…` | Admin UI/API |

**Do this first in Render:**

1. Open [https://dashboard.render.com](https://dashboard.render.com)
2. Sign in
3. Open your **team / workspace** (Finova / personal — whichever owns the UVA services)
4. Click **Dashboard** → list of services
5. Find the **voice worker** service (look for Docker + command mentioning `worker.main`, or name containing `worker`)
6. Open it → note **Settings → Build & Deploy → Branch** (often `staging` or `main`, not always `habiba`)

**Decision:**

| If the worker’s Branch is… | What you do |
|---|---|
| Already `habiba` | After push, click **Manual Deploy → Deploy latest commit** (or wait for auto-deploy) |
| `staging` / `main` / other | Either (A) temporarily set Branch to `habiba` and deploy, or (B) merge `habiba` → that branch first, then deploy. Ask Ehsan/ops before changing a shared `staging` branch if you are unsure. |

---

## 1. Preferred path — update the **existing** worker service

Use this if the worker already exists (most likely).

### 1.1 Open the worker

1. Dashboard → click the **worker** service name  
2. You land on **Events** / **Logs** — fine  
3. Left sidebar (or top tabs): click **Settings**

### 1.2 Build & Deploy settings (read, don’t guess)

Scroll to **Build & Deploy** (sometimes labelled **Build** / **Deploy**).

Check and write down:

| Field | What you want for Wave 2 worker |
|---|---|
| **Language / Runtime** | **Docker** (repo has `docker/worker.Dockerfile`) |
| **Dockerfile Path** | `docker/worker.Dockerfile` |
| **Docker Context** | `.` (repo root) — leave default unless already customized |
| **Branch** | Branch that contains your Wave 2 commit (`habiba` or merged target) |
| **Auto-Deploy** | Optional: **Yes** on push to that branch |
| **Root Directory** | empty / `.` |

**Start / Docker CMD:** Dockerfile already ends with:

```text
CMD ["python", "-m", "worker.main", "start"]
```

Do **not** override with a random shell command unless you know why.

### 1.3 Service type (important for health checks)

Render types:

| Type | Can Render hit `/healthz`? | Typical for LiveKit agent |
|---|---|---|
| **Background Worker** | **No** (cannot receive HTTP) | Common historically |
| **Web Service** | **Yes** — set Health Check Path | **Recommended for F-M25** |
| **Private Service** | TCP only (no HTTP path setting) | OK if you only need “port open” |

**What to do:**

1. In **Settings**, find **Service type** / how it was created  
2. If it is already a **Web Service** → keep it; configure health below  
3. If it is a **Background Worker**:
   - Env vars below still matter for dump/transcript flags  
   - Render **cannot** HTTP-probe `/healthz` on a Background Worker  
   - To enable F-M25 properly: create a **new Web Service** for the worker (section 2) **or** ask Render support / ops to convert — do **not** delete the old service until the new one is healthy and LiveKit jobs work

### 1.4 Instance / plan (billing)

In Settings → **Instance Type** (or during create: **Select an instance type**):

| Plan | When to use |
|---|---|
| **Free** | Only short demos — spins down, bad for always-on voice |
| **Starter** | Light staging |
| **Standard / Pro** | Staging/prod voice worker (Silero VAD + providers need RAM) |

**Practical pick for staging voice worker:** start at **Standard** (or whatever you already pay for). Voice + VAD is heavier than a tiny API. If the existing service already has a plan, **do not downgrade** without a reason.

Click **Save changes** if you change plan (may restart).

### 1.5 Health check (Web Service only)

1. Settings → scroll to **Health Checks**  
2. Click **Edit**  
3. **Health Check Path:** type exactly:

```text
/healthz
```

4. Click **Save Changes**

Render will HTTP GET that path on the service’s public port (`PORT`, usually `10000`).

**Match our code to that port** (Environment section next):

```text
UVA_WORKER_HEALTH_PORT=10000
UVA_WORKER_HEALTH_BIND=0.0.0.0
```

If your service **Settings → Networking / Port** uses a custom port, set `UVA_WORKER_HEALTH_PORT` to **that same number**, not a random `8081`.

Use **`/healthz`** (liveness), not `/healthz/ready`, for the platform probe — readiness can fail while DB is briefly unhappy and block deploys. You can curl ready manually later.

### 1.6 Environment variables

1. Left sidebar / Settings → **Environment**  
2. Click **Add Environment Variable** (or **Edit** bulk)  
3. Add / confirm the Wave 2 rows below  
4. Click **Save Changes** (or **Save, rebuild, and deploy**)

#### A. Wave 2 — set these on the **worker** (required for this deploy)

| Key | Value to type | Why |
|---|---|---|
| `UVA_WORKER_HEALTH_PORT` | `10000` (or your service PORT) | Turns on `worker/health_http.py` |
| `UVA_WORKER_HEALTH_BIND` | `0.0.0.0` | So Render can reach the probe (not `127.0.0.1`) |
| `UVA_DUMP_PROMPTS` | `0` | F-M24 — never `1` on shared disks |
| `UVA_LOG_TRANSCRIPTS` | `0` | F-M24 — no full transcripts in logs |
| `UVA_PUBLISH_TURN_LATENCY` | `0` | F-L6 — no stage timings into the room |

#### B. Already required for the worker (keep / verify — do not wipe)

Copy from your existing working env or from local `.env.local` **values you already use** (do not invent secrets):

| Key | Notes |
|---|---|
| `LIVEKIT_URL` | `wss://…` LiveKit Cloud |
| `LIVEKIT_API_KEY` | |
| `LIVEKIT_API_SECRET` | |
| `LIVEKIT_AGENT_NAME` | Must match control-plane dispatch name |
| `SUPABASE_DB_URL` | Worker DB |
| `SUPABASE_URL` | Recording upload |
| `SUPABASE_SERVICE_ROLE` | Recording upload |
| `GROQ_API_KEY` | EN LLM |
| `GOOGLE_API_KEY` | Gemini / some paths |
| `DEEPGRAM_API_KEY` | EN STT |
| `CARTESIA_API_KEY` | EN TTS |
| `GLADIA_API_KEY` | Urdu STT (if used) |
| `UPLIFTAI_API_KEY` | Urdu TTS (exact name — not `UPLIFT_API_KEY`) |
| `ELEVEN_API_KEY` | If agents use ElevenLabs |
| `FISH_API_KEY` / `RIME_API_KEY` | If used |

Optional but already documented in `.env.example`:

| Key | Suggested staging | Notes |
|---|---|---|
| `UVA_PROVIDER_MAX_RETRY` | `2` | F-H10 |
| `UVA_FORCE_GROQ_ENGLISH` | `1` | Product default |
| `UVA_SESSION_RECORD_AUDIO` | **omit or `0`** | On Render, recording start is gated; do not rely on this for prod |
| `UVA_RECORDING_RETENTION_DAYS` | `30` | F-C4 purge helper |

#### C. Never set on Render staging/prod

| Key | Why |
|---|---|
| `UVA_DUMP_PROMPTS=1` | Writes personas/prompts to disk |
| `UVA_LOG_TRANSCRIPTS=1` | PII in log drains |
| `TELEPHONY_ALLOW_MOCK_MACHINE_AUTH=1` | Auth backdoor (portal service) |
| `TELEPHONY_PROVIDER_MODE=mock` | On real telephony services |

Render itself sets `RENDER=true` — you do **not** add that manually. Our recording policy uses it.

### 1.7 Deploy

1. Top right of the service page: **Manual Deploy**  
2. Choose **Deploy latest commit** (or **Clear build cache & deploy** if a weird cache issue)  
3. Watch **Events** until status is **Live**  
4. Open **Logs** — look for health start / no crash loop  

If build fails: open the failed deploy → build log. Common issues: wrong Dockerfile path, branch without `docker/worker.Dockerfile`, missing `requirements.txt` in context.

### 1.8 Verify health after deploy

**From your PC** (Web Service with public URL):

```powershell
curl.exe https://YOUR-WORKER-SERVICE.onrender.com/healthz
```

Expect JSON like:

```json
{"status":"ok","service":"uva-worker"}
```

Optional readiness:

```powershell
curl.exe https://YOUR-WORKER-SERVICE.onrender.com/healthz/ready
```

**From Render Shell** (if enabled): **Shell** tab → same `curl` to `http://127.0.0.1:10000/healthz` (port = your `UVA_WORKER_HEALTH_PORT`).

### 1.9 Smoke a real call

1. Ensure control plane is up (`/healthz` on the CP service)  
2. Make one browser (or telephony) call through your usual host/demo  
3. Confirm worker logs show session start, not crash  
4. Confirm you do **not** see full transcript dumps unless you intentionally set flags locally  

---

## 2. If you must **create** a new worker Web Service

Only if there is no worker yet, or you are migrating off Background Worker.

1. Dashboard → **New +** → **Web Service**  
2. Connect the GitHub repo `habiba-imran/urdu-agent-SDK` (or Finova fork if that is what Render uses)  
3. If prompted: authorize Render → select repo  
4. Fill the form:

| Field | What to enter |
|---|---|
| **Name** | e.g. `uva-voice-worker-staging` |
| **Region** | Same region as control plane / Supabase-adjacent (pick what you already use) |
| **Branch** | `habiba` (or your deploy branch) |
| **Runtime** | **Docker** |
| **Dockerfile Path** | `docker/worker.Dockerfile` |
| **Instance type** | Standard+ for voice |
| **Health Check Path** | `/healthz` |

5. **Advanced** → Environment Variables → paste section 1.6 A + B  
6. Click **Create Web Service**  
7. Wait for first deploy → run section 1.8–1.9  

**LiveKit note:** the worker still dials out to LiveKit Cloud; it does not need to be public for LiveKit. Public URL is mainly for **your** `/healthz` probe. Restrict abuse later with Render IP allow lists if needed.

---

## 3. Control plane / admin (only if you are redeploying them too)

Wave 2 Habiba worker changes do **not** require you to recreate CP/admin. If you also redeploy them:

| Service | Health path (typical) | Notes |
|---|---|---|
| Control plane | `/healthz` | Already exists in FastAPI |
| Admin | whatever that service already uses | Do not invent |

Telephony env for **tenant portal** (not worker) is documented in `docs/TELEPHONY_REAL_PROVIDER_STAGING.md` — Ehsan’s world unless you own that service.

---

## 4. Deploy hooks (optional)

Repo workflows:

- `.github/workflows/deploy-staging.yml` — push to `staging`/`dev` → curls Render deploy hooks  
- `.github/workflows/deploy-prod.yml` — production hooks  

Hooks live in GitHub **Secrets** (`RENDER_DEPLOY_HOOK_WORKER_STAGING`, etc.).  
If your worker tracks `habiba` and hooks still point at another branch’s service, **Manual Deploy** from the dashboard is safer until hooks are updated.

---

## 5. Checklist (tick as you go)

- [ ] `git push origin habiba` succeeded  
- [ ] Opened correct Render workspace  
- [ ] Identified **worker** service  
- [ ] Branch / commit includes Wave 2  
- [ ] Dockerfile path = `docker/worker.Dockerfile`  
- [ ] Service type allows health (Web) **or** accepted Background Worker limitation  
- [ ] `UVA_WORKER_HEALTH_PORT` = public `PORT` (usually `10000`)  
- [ ] `UVA_WORKER_HEALTH_BIND=0.0.0.0`  
- [ ] `UVA_DUMP_PROMPTS=0`  
- [ ] `UVA_LOG_TRANSCRIPTS=0`  
- [ ] `UVA_PUBLISH_TURN_LATENCY=0`  
- [ ] Provider + LiveKit + Supabase keys still present  
- [ ] Deploy **Live**  
- [ ] `curl …/healthz` returns ok  
- [ ] One test call works  

---

## 6. If something fails (plain language)

| Symptom | Likely cause | Fix |
|---|---|---|
| Health check fails / deploy rolls back | Port mismatch or bind `127.0.0.1` | Set bind `0.0.0.0`; port = Render `PORT` |
| Build can’t find Dockerfile | Wrong path / wrong root | `docker/worker.Dockerfile`, context `.` |
| Worker Live but no calls | `LIVEKIT_*` / `LIVEKIT_AGENT_NAME` mismatch with CP | Align names with control plane |
| “Recording” surprises | Agent flag / consent path | Leave `UVA_SESSION_RECORD_AUDIO` unset/`0` on Render |
| Huge log PII | Dump/transcript flags | Force `0` and redeploy |

---

## 7. Related docs

- Env template: `.env.example`  
- Habiba leftovers: `docs/WAVE2-HABIBA-HOST-FOLLOWUPS.md`  
- Ehsan (not your Render worker): `docs/WAVE2-EHSAN-HANDOFF.md`  
- Dockerfile: `docker/worker.Dockerfile`
