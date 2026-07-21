# 🎯 VaaS GOD-TIER MASTER PLAN
## Urdu Voice-Agent-as-a-Service — Complete Production Blueprint
### Dual-Track: Hamza (Track A) & Habiba (Track B)

> **Reading Key**: Every phase specifies `[H]` = Hamza, `[B]` = Habiba. Files owned by each developer never overlap in the same phase. GitHub branch naming conventions are included. Merge points are clearly marked.

---

## 🧠 WHAT YOU HAVE BUILT — CODEBASE AUDIT

Before the plan, here is exactly what exists today so there's no confusion about the starting point.

### ✅ FULLY WORKING TODAY

| Component | File(s) | What It Does |
|---|---|---|
| **Control Plane** | `control_plane/app.py`, `mint.py`, `secrets.py` | FastAPI token minter — handles `POST /v1/session`, `POST /v1/session/refresh`, `POST /v1/session/dev-mint`. Validates HMAC signatures, checks quotas, dispatches LiveKit agent, returns JWT. |
| **Voice Worker** | `worker/main.py`, `factories.py`, `config.py`, `usage.py`, `tools.py` | LiveKit agent worker. Reads `tenant_id`/`agent_id` from participant metadata, loads agent config from Supabase (RLS-scoped), runs Silero VAD → Gladia STT → Gemini LLM → Uplift TTS pipeline. Adaptive interruption is wired. |
| **Client SDK** | `sdk/src/index.ts` | TypeScript SDK `@uva/voice`. Class `UrduVoiceAgent` — handles microphone, LiveKit room connection, token auto-refresh (at `T-60s`), transcript events, agent speaking events, metrics events. |
| **Admin Backend** | `admin/app.py`, `auth.py`, `audit.py`, `queries.py`, `security.py` | Super-admin FastAPI app on a separate port. Login with TOTP, list tenants/agents/sessions/usage/quota/concurrency. Every action writes `admin_audit_log`. |
| **Database Schema** | `supabase/migrations/0001–0008` | Full schema: `tenants`, `agents`, `sessions`, `quota_state`, `used_nonces`, `usage_events`, `voices_catalogue`, `admin_users`, `tools`, RLS policies. |
| **Docker Images** | `docker/control-plane.Dockerfile`, `worker.Dockerfile`, `admin.Dockerfile` | Container images for all three services. |
| **Dev Sandbox** | `Client-Side-SDK/` (Vite), `sdk_test_harness.html` | Local test harness — already working with `npm run dev`. |

### ⚠️ CRITICAL GAPS THAT BLOCK COMMERCIAL LAUNCH

| Gap | Impact | Which Phase Fixes It |
|---|---|---|
| `CP_TENANT_SECRETS` is a static env var JSON blob | Cannot add new clients without redeploying | Phase 3 |
| No session-end quota decrement in worker | `concurrent_now` drifts up and caps out | Phase 0 (hotfix) |
| No `/healthz` endpoint on control plane | Render can't health-check the service | Phase 1 |
| No tenant self-service dashboard | Every new client requires manual DB inserts | Phase 4 |
| No Stripe billing | Usage is tracked but nobody is billed | Phase 5 |
| No worker autoscaling config | Single worker crashes under concurrent load | Phase 1 |
| SDK not published to npm | Clients can't `npm install` it | Phase 3 |
| No CI/CD pipeline | Every deploy is manual | Phase 1 |
| CORS on control plane is `allow_origins=["*"]` | Any origin can call the mint | Phase 2 |
| Latency metrics not emitted by worker | SDK has the receiver wired, sender is missing | Phase 6 |

---

## 🗺️ FULL PHASE MAP — OVERVIEW

```
PHASE 0  │ Critical Hotfixes (Both, 1 day)
PHASE 1  │ Production Infrastructure & CI/CD (Both, 3–4 days)
PHASE 2  │ Security Hardening (Hamza, 2 days)
PHASE 3  │ Tenant Secret Migration & SDK Publishing (Habiba, 2 days)
PHASE 4  │ Tenant Dashboard — Frontend + Backend (Both, 5–7 days)
PHASE 5  │ Billing & Metering (Habiba, 3 days)
PHASE 6  │ Observability & Latency Telemetry (Hamza, 2 days)
PHASE 7  │ SDK Documentation & Client Onboarding Portal (Both, 3 days)
PHASE 8  │ Load Testing & Autoscaling Validation (Both, 2 days)
PHASE 9  │ Public Launch Readiness Checklist (Both, 1 day)
```

**Total estimated duration: ~4–5 weeks for two developers working in parallel.**

---

---

# ⚡ PHASE 0: CRITICAL HOTFIXES
### "Before we deploy anything, these bugs must be fixed or the whole system breaks under real load."
**Timeline: Day 1 | Both developers | Branch: `fix/phase-0-hotfixes`**

---

## [H] Hamza — Task 0.1: Fix Session-End Quota Decrement

**The Problem (Layman):** When a call starts, the system increments a counter (`concurrent_now`) that tracks how many calls are live. When the call ends, nobody decrements it. After a few calls end, the counter thinks the system is full and blocks new calls. The only existing workaround is the `dev-mint` auto-reset, which is **dev-only** and must never run in production.

**File to Edit:** `worker/main.py`

**Exact Change:**
1. In the `entrypoint()` function, find `_record_agent_minutes` — the shutdown callback.
2. Add a second shutdown callback `_release_quota_slot` that runs a direct SQL update:
   ```python
   async def _release_quota_slot(reason: str = "") -> None:
       import sys as _sys
       from pathlib import Path as _Path
       _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "scripts"))
       from dbconn import conn_kwargs
       import psycopg
       tenant_id = md.get("tenant_id", "")
       room_name = ctx.room.name
       if not tenant_id:
           return
       try:
           with psycopg.connect(**conn_kwargs(), connect_timeout=5, autocommit=True) as conn:
               conn.execute(
                   "update quota_state set concurrent_now = greatest(concurrent_now - 1, 0) "
                   "where tenant_id = %s",
                   (tenant_id,),
               )
               conn.execute(
                   "update sessions set ended_at = now(), end_reason = %s "
                   "where room_name = %s and ended_at is null",
                   (reason or "normal", room_name),
               )
       except Exception:
           pass  # best-effort; do not crash the shutdown path
   
   ctx.add_shutdown_callback(_release_quota_slot)
   ```
3. Register `_release_quota_slot` **before** `_record_agent_minutes` so quota is released first.

**Why `md` is accessible:** The `md` dict is parsed at line 126 in `entrypoint()` and is in the enclosing scope — the nested async function closes over it.

---

## [B] Habiba — Task 0.2: Add `/healthz` Endpoint to Control Plane

**The Problem (Layman):** Render (and any load balancer) needs a URL it can ping every 30 seconds to verify the service is alive. Without it, Render either never marks the service "healthy" or keeps restarting it. Right now the docs suggest using `/docs`, which is not a real health endpoint.

**File to Edit:** `control_plane/app.py`

**Exact Change:** Add this route directly after the `app = FastAPI(...)` declaration (around line 77):
```python
@app.get("/healthz")
def health_check():
    """Minimal liveness probe — does not verify DB/LK connectivity, just confirms the process is up."""
    return {"status": "ok", "service": "uva-control-plane"}
```

**Also add to `admin/app.py`:**
```python
@app.get("/healthz")
def admin_health():
    return {"status": "ok", "service": "uva-admin"}
```

---

## [H] Hamza — Task 0.3: Tighten CORS on Control Plane

**The Problem (Layman):** Right now `control_plane/app.py` has `allow_origins=["*"]`, meaning literally any website in the world can call `POST /v1/session`. The HMAC signature is the real guard, but `allow_origins=["*"]` also exposes a browser preflight bypass. We need to lock this down to only our own known origins.

**File to Edit:** `control_plane/app.py`

**Exact Change:** Replace the static `CORSMiddleware` block (lines 79–85) with a dynamic version that reads allowed origins from env:
```python
_CORS_ORIGINS_RAW = (
    os.environ.get("CP_ALLOWED_ORIGINS")
    or _ENV.get("CP_ALLOWED_ORIGINS", "")
)
_CORS_ORIGINS = [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Tenant-Id", "X-Timestamp", "X-Nonce", "X-Signature"],
)
```

**New Env Var:** `CP_ALLOWED_ORIGINS` — comma-separated list of client dashboard and SDK test harness origins. Example: `https://dashboard.yourdomain.com,https://yourapp.com`.

---

## PHASE 0 MERGE POINT
```
Hamza pushes: fix/phase-0-hotfixes
Habiba pushes: fix/phase-0-hotfixes
One person opens PR → other reviews → squash merge to main
```

---

---

# 🏗️ PHASE 1: PRODUCTION INFRASTRUCTURE & CI/CD
### "Deploy everything to the cloud so you stop running servers on your laptop."
**Timeline: Days 2–5 | Both developers | Branches: `infra/render-deploy` (H), `infra/cicd` (B)**

---

## [H] Hamza — Task 1.1: Deploy Control Plane to Render

**Layman Explanation:** Your control plane currently only runs when you type `python dev.py` on your computer. This means the moment your laptop closes, your entire platform goes offline. Render is a cloud hosting platform — you push your GitHub code, and it runs the service 24/7 on their servers.

**Step-by-step:**

1. **Go to [render.com](https://render.com) → New → Web Service**
2. Connect your GitHub repo: `habiba-imran/urdu-agent-SDK`
3. Configure:
   - **Name**: `uva-control-plane`
   - **Region**: Singapore (closest to South Asia/Middle East audience)
   - **Branch**: `main`
   - **Root Directory**: *(leave blank — Dockerfile copies from root)*
   - **Runtime**: `Docker`
   - **Dockerfile Path**: `docker/control-plane.Dockerfile`
   - **Health Check Path**: `/healthz` *(added in Phase 0)*
   - **Port**: `8000`
4. **Environment Variables** (set in Render dashboard, mark secrets as "Secret"):

| Variable | Value | Secret? |
|---|---|---|
| `LIVEKIT_URL` | `wss://your-project.livekit.cloud` | No |
| `LIVEKIT_API_KEY` | From LiveKit dashboard | No |
| `LIVEKIT_API_SECRET` | From LiveKit dashboard | **Yes** |
| `LIVEKIT_AGENT_NAME` | `uva-prod-agent` | No |
| `SUPABASE_DB_URL` | Postgres pooler URL from Supabase | **Yes** |
| `CP_TENANT_SECRETS` | `{"tenant-uuid": "raw-hmac-secret"}` | **Yes** |
| `CP_ALLOWED_ORIGINS` | `https://dashboard.yourdomain.com` | No |

5. Click **Deploy**. Wait for the build to succeed (~3–4 minutes).
6. Note the public URL: `https://uva-control-plane.onrender.com`
7. Test: `curl https://uva-control-plane.onrender.com/healthz` → should return `{"status":"ok"}`

---

## [H] Hamza — Task 1.2: Deploy Voice Worker to Render

**Layman Explanation:** The voice worker is the AI brain. It's a background process — it has no public web address, but it maintains a persistent connection to LiveKit Cloud and waits for call jobs. Render's "Background Worker" service type is exactly for this.

**Step-by-step:**

1. **Go to Render → New → Background Worker**
2. Same GitHub repo and `main` branch
3. Configure:
   - **Name**: `uva-voice-worker`
   - **Runtime**: `Docker`
   - **Dockerfile Path**: `docker/worker.Dockerfile`
   - **Start Command**: *(already in Dockerfile `CMD` — leave as Docker default)*
4. **Environment Variables**:

| Variable | Value | Secret? |
|---|---|---|
| `LIVEKIT_URL` | Same as control plane | No |
| `LIVEKIT_API_KEY` | Same as control plane | No |
| `LIVEKIT_API_SECRET` | Same as control plane | **Yes** |
| `LIVEKIT_AGENT_NAME` | `uva-prod-agent` *(must match control plane!)* | No |
| `SUPABASE_DB_URL` | Same Postgres pooler URL | **Yes** |
| `GOOGLE_API_KEY` | Gemini API key | **Yes** |
| `GLADIA_API_KEY` | Gladia STT key | **Yes** |
| `UPLIFTAI_API_KEY` | Uplift TTS key | **Yes** |
| `STT_PROVIDER` | `gladia` | No |
| `UPLIFT_MODE` | `live` | No |

> ⚠️ **CRITICAL**: `LIVEKIT_AGENT_NAME` must be **identical** in both control plane and worker. If they differ, the control plane dispatches to `uva-prod-agent` but the worker registers as something else — the browser joins the room alone with no AI response.

5. Deploy and verify the boot log shows:
   - `[prewarm] confirmed in sys.modules before any job thread: [...]`
   - `registered worker {"agent_name": "uva-prod-agent", ...}`

---

## [H] Hamza — Task 1.3: Deploy Admin Portal to Render

**Layman Explanation:** The admin portal (your super-admin dashboard) runs as its own FastAPI app on a separate port. It needs its own Render service.

1. **Render → New → Web Service**
2. Configure:
   - **Name**: `uva-admin-portal`
   - **Dockerfile Path**: `docker/admin.Dockerfile`
   - **Health Check Path**: `/healthz`
   - **Port**: `8001`
3. **Environment Variables**:

| Variable | Value |
|---|---|
| `SUPABASE_DB_URL` | Same Postgres pooler |
| `ADMIN_JWT_SECRET` | Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_PORTAL_ORIGINS` | `https://admin.yourdomain.com` |

---

## [B] Habiba — Task 1.4: Set Up GitHub Actions CI/CD

**Layman Explanation:** Right now, every time you change code, someone has to manually go to Render and click "Deploy". CI/CD (Continuous Integration / Continuous Deployment) means that the moment code is pushed to `main`, GitHub automatically runs tests and tells Render to redeploy. This is non-negotiable for a production SaaS.

**New File to Create:** `.github/workflows/deploy.yml`

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  # --- Job 1: Run Tests (on every PR and push to main) ---
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: pip install -r requirements.txt pytest
      
      - name: Run test suite
        env:
          # Use dummy values — tests should mock external calls
          LIVEKIT_URL: "wss://test.livekit.cloud"
          LIVEKIT_API_KEY: "test-key"
          LIVEKIT_API_SECRET: "test-secret"
          SUPABASE_DB_URL: "postgresql://test:test@localhost:5432/test"
          CP_TENANT_SECRETS: "{}"
        run: pytest tests/ -v --tb=short
  
  # --- Job 2: Build SDK (on push to main) ---
  build-sdk:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Build SDK
        working-directory: sdk
        run: |
          npm ci
          npm run build
      - name: Upload SDK dist as artifact
        uses: actions/upload-artifact@v4
        with:
          name: sdk-dist
          path: sdk/dist/
  
  # --- Job 3: Deploy to Render (on push to main only) ---
  deploy:
    runs-on: ubuntu-latest
    needs: [test, build-sdk]
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Deploy Control Plane to Render
        run: |
          curl -X POST "${{ secrets.RENDER_DEPLOY_HOOK_CONTROL_PLANE }}"
      
      - name: Deploy Voice Worker to Render
        run: |
          curl -X POST "${{ secrets.RENDER_DEPLOY_HOOK_WORKER }}"
      
      - name: Deploy Admin Portal to Render
        run: |
          curl -X POST "${{ secrets.RENDER_DEPLOY_HOOK_ADMIN }}"
```

**GitHub Secrets to Set** (in GitHub repo → Settings → Secrets and variables → Actions):

| Secret Name | Value |
|---|---|
| `RENDER_DEPLOY_HOOK_CONTROL_PLANE` | Render webhook URL for control plane |
| `RENDER_DEPLOY_HOOK_WORKER` | Render webhook URL for worker |
| `RENDER_DEPLOY_HOOK_ADMIN` | Render webhook URL for admin |

> **How to get Render deploy hooks:** Render service dashboard → Settings → Deploy Hook → Copy URL.

---

## [B] Habiba — Task 1.5: Configure Staging Environment

**Layman Explanation:** "Staging" is a copy of your production system where you test changes before they go live. Clients never use staging — it's your personal sandbox for risky changes.

**Step-by-step:**

1. Create a **second Supabase project** called `uva-staging`. Run the same migrations.
2. Create **duplicate Render services** with `-staging` suffix:
   - `uva-control-plane-staging`
   - `uva-voice-worker-staging`
3. Update CI/CD pipeline: add a `staging` environment job that deploys to staging on pushes to the `dev` branch.

**New File:** `.github/workflows/staging.yml`
```yaml
name: Staging Deploy

on:
  push:
    branches: [dev]

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Staging Control Plane
        run: curl -X POST "${{ secrets.RENDER_DEPLOY_HOOK_CONTROL_PLANE_STAGING }}"
      - name: Deploy to Staging Worker
        run: curl -X POST "${{ secrets.RENDER_DEPLOY_HOOK_WORKER_STAGING }}"
```

**Branch Convention Going Forward:**
- `main` → Production
- `dev` → Staging
- `feature/xxx` → Feature branches, merged to `dev` first, then `main`

---

## PHASE 1 MERGE POINT
```
Hamza: infra/render-deploy → dev → main (PRs)
Habiba: infra/cicd → dev (PR review by Hamza)
After both merge: run full end-to-end call test on deployed services
```

---

---

# 🔒 PHASE 2: SECURITY HARDENING
### "Lock the doors before you invite strangers in."
**Timeline: Days 5–7 | Hamza only | Branch: `security/phase-2`**

---

## [H] Hamza — Task 2.1: Migrate `CP_TENANT_SECRETS` to Database

**The Problem (Layman):** Right now, your client HMAC secrets are stored as a JSON blob in a Render environment variable (`CP_TENANT_SECRETS`). This means to add a new client, you have to edit a JSON string, redeploy the whole control plane, and take it down for 1–2 minutes. This is completely unacceptable for a commercial SaaS.

**Solution:** Move secrets into the `tenants` database table. The column `hmac_secret_hash` already exists in `0001_schema.sql`. The raw secret needs to be stored separately (or the raw secret column needs to be added) so the control plane can look it up per-tenant at mint time.

**New File:** `control_plane/secrets_db.py`
```python
"""Database-backed secret provider — reads raw HMAC secrets from tenants.hmac_secret column.

This replaces EnvSecretProvider (control_plane/secrets.py) in production. 
The database column `tenants.hmac_secret` stores the raw URLSAFE-base64 secret
(NOT the hash — the mint verifies via HMAC comparison, not hash comparison).
"""
from __future__ import annotations
import psycopg
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dbconn import conn_kwargs

class DbSecretProvider:
    """Reads the raw HMAC secret for a tenant_id from the DB.
    Falls back to EnvSecretProvider for backwards compatibility during migration.
    """
    def __init__(self, env_fallback=None):
        self._fallback = env_fallback

    def get(self, tenant_id: str) -> str | None:
        try:
            with psycopg.connect(**conn_kwargs(), connect_timeout=5) as conn:
                row = conn.execute(
                    "select hmac_secret from tenants where id = %s",
                    (tenant_id,),
                ).fetchone()
            if row and row[0]:
                return row[0]
        except Exception:
            pass  # DB unreachable — fall through to env fallback
        if self._fallback:
            return self._fallback.get(tenant_id)
        return None
```

**New SQL Migration:** `supabase/migrations/0009_tenant_secrets.sql`
```sql
-- Add raw HMAC secret column to tenants table.
-- This replaces the CP_TENANT_SECRETS env var approach.
-- The raw secret is what the control plane uses for HMAC signing.
-- The hmac_secret_hash column (existing) can be used for display/audit purposes.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS hmac_secret TEXT;

-- RLS: Only the service_role (control plane direct DB connection, bypasses RLS) can read this.
-- Tenant users (anon/authenticated JWT) must NEVER see their own raw secret via RLS.
-- The raw secret is only readable by the service that owns the postgres owner connection.
COMMENT ON COLUMN tenants.hmac_secret IS 
  'Raw URLSAFE HMAC secret. Only readable via service_role / owner connection. Never exposed to tenant JWTs.';
```

**Update `control_plane/app.py`:**
- Import `DbSecretProvider` and `EnvSecretProvider`
- Change `_secrets = EnvSecretProvider()` to:
```python
from .secrets import EnvSecretProvider
from .secrets_db import DbSecretProvider
_env_secrets = EnvSecretProvider()
_secrets = DbSecretProvider(env_fallback=_env_secrets)
```
This ensures **zero downtime migration** — existing env-var secrets continue to work while you migrate tenants to DB storage.

---

## [H] Hamza — Task 2.2: Implement HMAC Secret Rotation API

**Layman Explanation:** Clients need to be able to regenerate their secret key (e.g., if they suspect it was leaked). The control plane needs an API endpoint for this that only the client themselves (or an admin) can call.

**New Routes in `control_plane/app.py`:**
```python
class RotateSecretBody(BaseModel):
    tenant_id: str
    current_token: str  # The client presents their current LiveKit JWT as proof of identity

@app.post("/v1/tenant/rotate-secret")
def rotate_tenant_secret(body: RotateSecretBody):
    """
    Generates a new HMAC secret for the tenant and stores it in the DB.
    The old secret is immediately invalidated — any in-flight requests using the old
    secret will start failing within the 60s replay window.
    Returns the new raw secret EXACTLY ONCE. It is not stored in plaintext after this response.
    """
    import secrets as _secrets_lib
    # Verify the caller is who they say they are
    try:
        claims = api.TokenVerifier(_LK_KEY, _LK_SECRET).verify(body.current_token)
        metadata = json.loads(claims.metadata or "{}")
        verified_tenant_id = metadata.get("tenant_id")
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")
    
    if verified_tenant_id != body.tenant_id:
        raise HTTPException(status_code=403, detail="token does not match tenant_id")
    
    new_secret = _secrets_lib.token_urlsafe(32)
    new_hash = hashlib.sha256(new_secret.encode()).hexdigest()
    
    with psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        conn.execute(
            "update tenants set hmac_secret = %s, hmac_secret_hash = %s where id = %s",
            (new_secret, new_hash, body.tenant_id),
        )
    
    return {"new_secret": new_secret, "warning": "Store this immediately. It will not be shown again."}
```

---

## [H] Hamza — Task 2.3: Add Rate Limiting per Tenant per Endpoint

**Layman Explanation:** Right now, the rate limiter (`RATE_LIMIT_PER_MIN = 120`) counts raw HTTP hits per tenant ID on the session endpoint. You also need rate limiting on the `/v1/session/refresh` endpoint to prevent token-refresh abuse.

**Update `control_plane/app.py`:**
```python
REFRESH_RATE_LIMIT_PER_MIN = 240  # Allow 2x session rate for refresh
_refresh_hits: dict[str, list[float]] = defaultdict(list)

def _refresh_rate_limited(tenant_id: str) -> bool:
    now = time.time()
    window = _refresh_hits[tenant_id]
    window[:] = [t for t in window if now - t < 60]
    if len(window) >= REFRESH_RATE_LIMIT_PER_MIN:
        return True
    window.append(now)
    return False
```

Apply to the refresh endpoint by extracting `tenant_id` from the JWT metadata before the refresh.

---

## PHASE 2 MERGE POINT
```
Hamza: security/phase-2 → dev (PR reviewed by Habiba)
Run SQL migration 0009 on staging Supabase first
Verify existing dev tenant still works via env fallback
Merge to main
```

---

---

# 📦 PHASE 3: TENANT SECRET MIGRATION & SDK PUBLISHING
### "Make the SDK installable for real clients and migrate secrets to database."
**Timeline: Days 6–8 | Habiba only | Branch: `feature/sdk-publish`**

---

## [B] Habiba — Task 3.1: Provision Tenants via Script (Migration Path)

**Layman Explanation:** Right now, you add a new client by manually editing a JSON env var. The Phase 2 code now reads secrets from the database. But you still need a script to actually INSERT a new tenant into the DB with their credentials, so you don't have to write raw SQL every time.

**New File:** `scripts/provision_tenant.py`
```python
#!/usr/bin/env python3
"""
Provision a new tenant in production.
Usage: python scripts/provision_tenant.py --name "Client Corp" --email "admin@client.com" --origins "https://client.com"

Outputs the Publishable Key (tenant_id), HMAC secret, and first agent ID.
"""
import argparse
import hashlib
import secrets
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dbconn import conn_kwargs
import psycopg

def provision(name: str, email: str, origins: list[str], max_concurrent: int = 3, max_minutes: int = 1000):
    tenant_id = str(uuid.uuid4())
    hmac_secret = secrets.token_urlsafe(32)
    hmac_hash = hashlib.sha256(hmac_secret.encode()).hexdigest()
    
    with psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO tenants (id, name, hmac_secret, hmac_secret_hash, allowed_origins, 
                                  max_concurrent, max_minutes_month, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'active')
            """,
            (tenant_id, name, hmac_secret, hmac_hash, origins, max_concurrent, max_minutes)
        )
        # Also initialize quota_state
        conn.execute(
            "INSERT INTO quota_state (tenant_id, concurrent_now, minutes_this_month) VALUES (%s, 0, 0)",
            (tenant_id,)
        )
    
    print("\n" + "="*60)
    print(f"✅ Tenant Provisioned: {name}")
    print(f"   Publishable Key (tenant_id): {tenant_id}")
    print(f"   HMAC Secret (KEEP PRIVATE):  {hmac_secret}")
    print(f"   Allowed Origins: {origins}")
    print("="*60 + "\n")
    print("⚠️  The HMAC secret is shown ONCE. Copy it now.")
    return tenant_id, hmac_secret

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--origins", default="", help="Comma-separated allowed origins")
    parser.add_argument("--max-concurrent", type=int, default=3)
    parser.add_argument("--max-minutes", type=int, default=1000)
    args = parser.parse_args()
    
    origins = [o.strip() for o in args.origins.split(",") if o.strip()]
    provision(args.name, args.email, origins, args.max_concurrent, args.max_minutes)
```

---

## [B] Habiba — Task 3.2: Publish SDK to npm

**Layman Explanation:** Right now, clients can only use the SDK by copying a `.tgz` file. For real commercial adoption, the SDK must be on npm — the universal JavaScript package registry — so clients can simply run `npm install @uva/voice` to get it.

**Pre-requisites:**
1. Create an npm account: https://www.npmjs.com/
2. Create an organization: `@uva` (may need to change if name is taken — try `@uva-voice` or `@urduvoice`)
3. Run `npm login` locally

**Update `sdk/package.json`:**
```json
{
  "name": "@uva/voice",
  "version": "0.1.0",
  "description": "Urdu Voice Agent client SDK for VaaS platform",
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js",
      "default": "./dist/index.js"
    }
  },
  "files": ["dist", "README.md"],
  "scripts": {
    "build": "tsc",
    "lint": "tsc --noEmit",
    "prepublishOnly": "npm run build"
  },
  "dependencies": {
    "livekit-client": "^2.0.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0"
  },
  "publishConfig": {
    "access": "public"
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/habiba-imran/urdu-agent-SDK.git"
  },
  "keywords": ["urdu", "voice", "agent", "ai", "sdk", "livekit", "webrtc"]
}
```

**Publish Command (run in `sdk/` directory):**
```bash
cd sdk
npm run build
npm publish --access public
```

**Add npm publish to CI/CD** (update `.github/workflows/deploy.yml`):
```yaml
  publish-sdk:
    runs-on: ubuntu-latest
    needs: [test]
    if: github.ref == 'refs/heads/main' && startsWith(github.event.head_commit.message, 'release:')
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          registry-url: 'https://registry.npmjs.org'
      - name: Build and publish SDK
        working-directory: sdk
        run: |
          npm ci
          npm run build
          npm publish --access public
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

> **Convention:** The SDK only auto-publishes when the commit message starts with `release:` (e.g., `release: v0.2.0 — added mute API`).

**GitHub Secret to add:** `NPM_TOKEN` — get from npm.js → Profile → Access Tokens → Generate New Token (Publish).

---

## [B] Habiba — Task 3.3: Write `sdk/README.md`

**This is the first thing every client developer sees on npm.** It must be clear, professional, and complete. Use the existing `CLIENT_INTEGRATION_GUIDE.md` as source material but format it for npm.

**File:** `sdk/README.md`
```markdown
# @uva/voice — Urdu Voice Agent SDK

Drop-in browser SDK for the Urdu Voice-Agent-as-a-Service (VaaS) platform.

## Installation
npm install @uva/voice

## Quick Start
See full guide: [Client Integration Guide](...)

## Events
| Event | Payload | When |
|---|---|---|
| `connected` | — | Room joined, mic active |
| `transcript` | `{text, final}` | Speech transcription |
| `agent_speaking` | `boolean` | Agent audio state |
| `error` | `UvaError` | Any error |
| `disconnected` | reason | Call ended |
| `metrics_updated` | metrics object | Latency telemetry |
```

---

## PHASE 3 MERGE POINT
```
Habiba: feature/sdk-publish → dev (PR reviewed by Hamza)
Test the npm publish on staging: npm install @uva/voice in a blank project
Merge to main → npm auto-publishes via CI/CD
```

---

---

# 🖥️ PHASE 4: TENANT SELF-SERVICE DASHBOARD
### "Build the web portal that clients log in to and manage their agents — the face of your product."
**Timeline: Days 8–15 | Both developers | Diverging branches**

This is the largest phase. It is split into two parallel sub-tracks that do NOT touch the same files.

---

## [H] Hamza — Track A: Dashboard Backend API (New Service)

**Layman Explanation:** The tenant dashboard needs a backend to power it. This is NOT the control plane (which mints audio tokens) and NOT the admin portal (which is for you). This is a **Tenant API** — it handles client logins, agent CRUD, and credentials display. It talks directly to Supabase using the Supabase JavaScript client with row-level security.

**Decision: Use Supabase as the backend.** Instead of building a custom Python FastAPI for tenant operations, use Supabase's built-in Auth + Row-Level Security + REST API. This saves 3–5 days of backend work.

**New Directory:** `dashboard/` (Habiba will handle the frontend, Hamza handles the Supabase configuration for dashboard access)

**Hamza's Tasks:**

### Task 4H.1: Configure Supabase Auth for Tenants

1. Go to your **production Supabase project**
2. Navigate to **Authentication → Providers → Email** — ensure it is enabled
3. Configure **Redirect URLs** to your dashboard domain: `https://dashboard.yourdomain.com/**`
4. Set **Email templates** (in Authentication → Email Templates):
   - Confirm signup email
   - Password reset email
   Brand with your product name

### Task 4H.2: Write Dashboard-Specific RLS Policies

**New SQL Migration:** `supabase/migrations/0010_dashboard_rls.sql`
```sql
-- =========================================================
-- Dashboard RLS: Allows Supabase Auth (authenticated) users
-- to manage their OWN tenant data through the dashboard.
-- The control plane uses a direct postgres owner connection
-- (bypasses RLS) — these policies ONLY apply to dashboard
-- Supabase client calls using anon/authenticated keys.
-- =========================================================

-- Tenants: Users can only read their own tenant row
DROP POLICY IF EXISTS tenant_self_read ON tenants;
CREATE POLICY tenant_self_read ON tenants
  FOR SELECT TO authenticated
  USING (id::text = auth.jwt() ->> 'sub');

-- Tenants: Users can update their own tenant row (e.g., name, allowed_origins)
CREATE POLICY tenant_self_update ON tenants
  FOR UPDATE TO authenticated
  USING (id::text = auth.jwt() ->> 'sub')
  WITH CHECK (id::text = auth.jwt() ->> 'sub');

-- Agents: Users can CRUD their own agents
CREATE POLICY agent_tenant_all ON agents
  FOR ALL TO authenticated
  USING (tenant_id::text = auth.jwt() ->> 'sub')
  WITH CHECK (tenant_id::text = auth.jwt() ->> 'sub');

-- Sessions: Users can read their own call history
CREATE POLICY session_tenant_read ON sessions
  FOR SELECT TO authenticated
  USING (tenant_id::text = auth.jwt() ->> 'sub');

-- Quota: Users can see their own quota
CREATE POLICY quota_tenant_read ON quota_state
  FOR SELECT TO authenticated
  USING (tenant_id::text = auth.jwt() ->> 'sub');

-- Voices catalogue: Public read (anyone logged in can see available voices)
DROP POLICY IF EXISTS voices_public_read ON voices_catalogue;
CREATE POLICY voices_public_read ON voices_catalogue
  FOR SELECT TO authenticated USING (true);

-- BLOCK: Tenants must NEVER read hmac_secret via the Supabase JS client
-- The RLS policy above allows SELECT on tenants, but we hide the secret column.
-- This is enforced by NOT including hmac_secret in any dashboard query.
-- For extra safety, create a view:
CREATE OR REPLACE VIEW tenant_profile AS
  SELECT id, name, allowed_origins, hmac_secret_hash, 
         max_concurrent, max_minutes_month, status, created_at
  FROM tenants;
-- Grant view to authenticated role but not the base table direct access to hmac_secret
GRANT SELECT ON tenant_profile TO authenticated;
```

### Task 4H.3: Write Tenant Onboarding Trigger

**New SQL Migration:** `supabase/migrations/0011_onboarding_trigger.sql`
```sql
-- When a new user signs up via Supabase Auth, automatically create their tenant row.
-- This links auth.users.id → tenants.id (same UUID).
-- The HMAC secret is generated here and stored. It is displayed ONCE via the dashboard.

CREATE OR REPLACE FUNCTION handle_new_tenant_signup()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql
AS $$
DECLARE
  new_secret TEXT;
  secret_hash TEXT;
BEGIN
  -- Generate a cryptographically random 256-bit URL-safe secret
  new_secret := encode(gen_random_bytes(32), 'base64');
  secret_hash := encode(digest(new_secret, 'sha256'), 'hex');
  
  INSERT INTO public.tenants (
    id, name, hmac_secret, hmac_secret_hash, 
    allowed_origins, max_concurrent, max_minutes_month, status
  ) VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'company_name', 'My Company'),
    new_secret,
    secret_hash,
    '{}',
    3,        -- default: 3 concurrent calls
    500,      -- default: 500 minutes/month free tier
    'active'
  );
  
  INSERT INTO quota_state (tenant_id, concurrent_now, minutes_this_month)
  VALUES (NEW.id, 0, 0);
  
  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_tenant_signup();
```

> **Important:** This trigger runs with `SECURITY DEFINER` so it can bypass RLS and insert into `tenants`. This is the correct Supabase pattern.

---

## [B] Habiba — Track B: Dashboard Frontend (Next.js App)

**Layman Explanation:** The dashboard is the website your clients log into. Think of it like a Stripe or Twilio dashboard — clean, professional, shows usage numbers, lets them configure their AI agent, and gives them their API credentials. You'll build this in Next.js hosted on Vercel (free tier, zero-config deploys).

### Task 4B.1: Create Next.js Dashboard App

```bash
# Run in the repo root
npx -y create-next-app@latest dashboard --typescript --tailwind --app --src-dir --no-git
cd dashboard
npm install @supabase/supabase-js @supabase/auth-helpers-nextjs @supabase/auth-ui-react recharts lucide-react
```

**Directory Structure:**
```
dashboard/
├── src/
│   ├── app/
│   │   ├── layout.tsx              # Root layout with auth provider
│   │   ├── page.tsx                # Landing/redirect page
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx      # Login page
│   │   │   └── signup/page.tsx     # Signup page
│   │   └── (dashboard)/
│   │       ├── layout.tsx          # Dashboard shell (sidebar + header)
│   │       ├── overview/page.tsx   # Analytics overview
│   │       ├── agents/
│   │       │   ├── page.tsx        # Agent list
│   │       │   └── [id]/page.tsx   # Agent edit form
│   │       ├── credentials/page.tsx # API keys display
│   │       └── calls/page.tsx      # Call history table
│   ├── components/
│   │   ├── ui/                     # Reusable UI components
│   │   ├── AgentForm.tsx
│   │   ├── CallLogTable.tsx
│   │   ├── CredentialsPanel.tsx
│   │   └── UsageChart.tsx
│   ├── lib/
│   │   ├── supabase.ts             # Supabase client
│   │   └── api.ts                  # Helper functions
│   └── middleware.ts               # Auth protection middleware
├── package.json
└── next.config.js
```

### Task 4B.2: Core Dashboard Pages Implementation

**`src/lib/supabase.ts`:**
```typescript
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'

export const supabase = createClientComponentClient({
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL!,
  supabaseKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
})
```

**`src/app/(dashboard)/overview/page.tsx` — Analytics Overview:**
```typescript
'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

export default function OverviewPage() {
  const [quota, setQuota] = useState<{concurrent_now: number, minutes_this_month: number} | null>(null)
  const [sessions, setSessions] = useState<any[]>([])

  useEffect(() => {
    const load = async () => {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) return

      const [quotaRes, sessRes] = await Promise.all([
        supabase.from('quota_state').select('*').eq('tenant_id', user.id).single(),
        supabase.from('sessions').select('*').eq('tenant_id', user.id).order('created_at', {ascending: false}).limit(50)
      ])

      if (quotaRes.data) setQuota(quotaRes.data)
      if (sessRes.data) setSessions(sessRes.data)
    }
    load()
  }, [])

  return (
    <div className="grid grid-cols-3 gap-6 p-8">
      <div className="bg-white rounded-xl shadow p-6">
        <h3 className="text-sm text-gray-500">Live Calls</h3>
        <p className="text-4xl font-bold text-indigo-600">{quota?.concurrent_now ?? 0}</p>
      </div>
      <div className="bg-white rounded-xl shadow p-6">
        <h3 className="text-sm text-gray-500">Minutes This Month</h3>
        <p className="text-4xl font-bold">{quota?.minutes_this_month ?? 0}</p>
      </div>
      <div className="bg-white rounded-xl shadow p-6">
        <h3 className="text-sm text-gray-500">Total Calls</h3>
        <p className="text-4xl font-bold">{sessions.length}</p>
      </div>
    </div>
  )
}
```

**`src/app/(dashboard)/agents/page.tsx` — Agent Management:**
```typescript
'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

export default function AgentsPage() {
  const [agents, setAgents] = useState<any[]>([])
  const [voices, setVoices] = useState<any[]>([])
  const [form, setForm] = useState({name: '', prompt: '', voice_id: '', llm_model: 'gemini-3.1-flash-lite'})

  useEffect(() => {
    supabase.from('agents').select('*').then(({data}) => setAgents(data ?? []))
    supabase.from('voices_catalogue').select('id, display_name, language').then(({data}) => setVoices(data ?? []))
  }, [])

  const createAgent = async () => {
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return
    const { data } = await supabase.from('agents').insert({
      ...form,
      tenant_id: user.id,
    }).select().single()
    if (data) setAgents(prev => [...prev, data])
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-6">My Agents</h1>
      {/* Agent creation form */}
      <div className="bg-white rounded-xl shadow p-6 mb-8">
        <h2 className="font-semibold mb-4">Create New Agent</h2>
        <input className="w-full border rounded p-2 mb-3" placeholder="Agent Name (e.g. Support Receptionist)"
          value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} />
        <textarea className="w-full border rounded p-2 mb-3 h-32" 
          placeholder="Urdu System Prompt (e.g. آپ ایک ریسیپشنسٹ ہیں...)"
          value={form.prompt} onChange={e => setForm(f => ({...f, prompt: e.target.value}))} />
        <select className="w-full border rounded p-2 mb-3"
          value={form.voice_id} onChange={e => setForm(f => ({...f, voice_id: e.target.value}))}>
          <option value="">Select an Urdu Voice</option>
          {voices.map(v => <option key={v.id} value={v.id}>{v.display_name}</option>)}
        </select>
        <button onClick={createAgent} className="bg-indigo-600 text-white rounded px-4 py-2">
          Create Agent
        </button>
      </div>
      {/* Agent list */}
      {agents.map(agent => (
        <div key={agent.id} className="bg-white rounded-xl shadow p-4 mb-3 flex justify-between">
          <div>
            <p className="font-semibold">{agent.name}</p>
            <p className="text-xs text-gray-400 font-mono">{agent.id}</p>
          </div>
          <span className="text-xs bg-green-100 text-green-700 rounded px-2 py-1 self-start">Active</span>
        </div>
      ))}
    </div>
  )
}
```

**`src/app/(dashboard)/credentials/page.tsx` — API Keys:**
```typescript
'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

export default function CredentialsPage() {
  const [user, setUser] = useState<any>(null)
  const [secretVisible, setSecretVisible] = useState(false)

  useEffect(() => {
    supabase.auth.getUser().then(({data}) => setUser(data.user))
  }, [])

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">API Credentials</h1>
      <div className="bg-white rounded-xl shadow divide-y">
        <div className="p-6">
          <p className="text-sm text-gray-500 mb-1">Publishable Key (safe to expose in frontend)</p>
          <code className="bg-gray-100 p-2 rounded block text-sm font-mono">
            pk_live_{user?.id}
          </code>
        </div>
        <div className="p-6">
          <p className="text-sm text-gray-500 mb-1">HMAC Secret (keep on backend server ONLY)</p>
          <div className="flex gap-2">
            <code className="bg-yellow-50 border border-yellow-200 p-2 rounded block text-sm font-mono flex-1">
              {secretVisible ? '••••••••••••••••••••••••••••••••' : 'Click reveal to show'}
            </code>
            <button onClick={() => setSecretVisible(!secretVisible)}
              className="border rounded px-3 text-sm">
              {secretVisible ? 'Hide' : 'Reveal'}
            </button>
          </div>
          <p className="text-xs text-amber-600 mt-2">
            ⚠️ Never expose this in frontend code or commit it to Git.
          </p>
        </div>
      </div>
    </div>
  )
}
```

### Task 4B.3: Deploy Dashboard to Vercel

1. Push `dashboard/` to GitHub
2. Go to [vercel.com](https://vercel.com) → New Project → Import from GitHub
3. Set **Root Directory** to `dashboard`
4. Add environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL`: Your Supabase project URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Supabase anon (public) key
5. Deploy — Vercel gives you `https://dashboard.yourdomain.vercel.app`

---

## PHASE 4 MERGE POINT
```
Hamza: feature/dashboard-backend → dev (Supabase migrations applied to staging)
Habiba: feature/dashboard-frontend → dev (Vercel staging URL pointed at staging Supabase)
Integration test: Sign up → Create agent → Note agent_id → Use in SDK test harness
Both PR to main after integration test passes
```

---

---

# 💳 PHASE 5: BILLING & METERING (STRIPE)
### "Make money. Log every minute. Bill every month."
**Timeline: Days 12–15 | Habiba only | Branch: `feature/billing`**

---

## [B] Habiba — Task 5.1: Set Up Stripe Metered Billing

**Layman Explanation:** Your system already logs voice minutes in `quota_state.minutes_this_month`. Stripe is the payment processor. You need to wire them together so that at the end of each billing cycle, Stripe automatically charges each client based on their minute count.

**Step-by-step:**

1. **Create Stripe Account**: https://stripe.com
2. **Create a Product** in Stripe: "Urdu Voice Agent Minutes"
3. **Create a Price** (metered billing):
   - Billing: Per unit
   - Unit: 1 voice minute
   - Price: e.g., $0.08 per minute (your choice)
   - Aggregation: Sum of usage during period
4. Note your `STRIPE_SECRET_KEY` and `STRIPE_PRICE_ID`

### Task 5.2: Add Stripe Customer ID to Tenants Table

**New SQL Migration:** `supabase/migrations/0012_stripe_integration.sql`
```sql
ALTER TABLE tenants 
  ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
  ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT,
  ADD COLUMN IF NOT EXISTS stripe_subscription_item_id TEXT;

COMMENT ON COLUMN tenants.stripe_customer_id IS 'Stripe customer ID for billing';
COMMENT ON COLUMN tenants.stripe_subscription_id IS 'Active Stripe metered subscription ID';
COMMENT ON COLUMN tenants.stripe_subscription_item_id IS 'Subscription item ID for usage reporting';
```

### Task 5.3: Build Billing Daemon (Cron Job)

**New File:** `billing/daemon.py`
```python
"""
Billing daemon — runs nightly (or monthly) and reports usage to Stripe.
Deploy as a Render Cron Job: schedule "0 1 * * *" (1 AM daily).

What it does (Layman):
  1. Reads each tenant's voice minutes from the database.
  2. Sends those minutes to Stripe as "usage records".
  3. Stripe automatically invoices the client at their billing cycle end.
"""
import os
import sys
from pathlib import Path
import psycopg
import stripe

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dbconn import conn_kwargs

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

def report_daily_usage():
    with psycopg.connect(**conn_kwargs(), connect_timeout=10) as conn:
        rows = conn.execute("""
            SELECT t.id, t.stripe_subscription_item_id,
                   COALESCE(SUM(ue.quantity), 0) as minutes_today
            FROM tenants t
            LEFT JOIN usage_events ue ON ue.tenant_id = t.id 
                AND ue.kind = 'livekit_agent_min'
                AND ue.created_at >= NOW() - INTERVAL '1 day'
            WHERE t.stripe_subscription_item_id IS NOT NULL
              AND t.status = 'active'
            GROUP BY t.id, t.stripe_subscription_item_id
        """).fetchall()

    for tenant_id, sub_item_id, minutes in rows:
        if minutes <= 0:
            continue
        try:
            stripe.SubscriptionItem.create_usage_record(
                sub_item_id,
                quantity=int(minutes),
                action='increment',
                timestamp='now',
            )
            print(f"✅ Reported {minutes} minutes for tenant {tenant_id}")
        except stripe.error.StripeError as e:
            print(f"❌ Stripe error for tenant {tenant_id}: {e}")

if __name__ == "__main__":
    report_daily_usage()
```

**New Dockerfile:** `docker/billing.Dockerfile`
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY docker/requirements-billing.txt .
RUN pip install --no-cache-dir -r requirements-billing.txt
COPY billing/ billing/
COPY scripts/dbconn.py scripts/
CMD ["python", "-m", "billing.daemon"]
```

**New Requirements:** `docker/requirements-billing.txt`
```
psycopg[binary]~=3.2
stripe~=8.0
python-dotenv~=1.0
```

**Render Cron Job Setup:**
- Render → New → Cron Job
- Name: `uva-billing-daemon`
- Schedule: `0 1 * * *` (runs at 1 AM every day)
- Dockerfile: `docker/billing.Dockerfile`
- Environment: `STRIPE_SECRET_KEY`, `SUPABASE_DB_URL`

### Task 5.4: Stripe Customer Creation at Signup

**Update the Supabase trigger** `handle_new_tenant_signup()` OR add a webhook:

**Option (recommended): Next.js API route** `dashboard/src/app/api/billing/create-customer/route.ts`:
```typescript
import Stripe from 'stripe'
import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs'
import { cookies } from 'next/headers'

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!)

export async function POST() {
  const supabase = createRouteHandlerClient({ cookies })
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return Response.json({ error: 'unauthorized' }, { status: 401 })

  // Create Stripe customer
  const customer = await stripe.customers.create({
    email: user.email,
    metadata: { tenant_id: user.id },
  })

  // Create metered subscription
  const subscription = await stripe.subscriptions.create({
    customer: customer.id,
    items: [{ price: process.env.STRIPE_PRICE_ID! }],
  })

  // Store IDs in Supabase
  await supabase.from('tenants').update({
    stripe_customer_id: customer.id,
    stripe_subscription_id: subscription.id,
    stripe_subscription_item_id: subscription.items.data[0].id,
  }).eq('id', user.id)

  return Response.json({ success: true })
}
```

Call this API route from the dashboard `onboarding/page.tsx` after first sign-up.

---

## PHASE 5 MERGE POINT
```
Habiba: feature/billing → dev
Apply migration 0012 to staging Supabase
Test with Stripe test mode keys
Verify usage_records appear in Stripe dashboard after running daemon
PR to main
```

---

---

# 📊 PHASE 6: OBSERVABILITY & LATENCY TELEMETRY
### "You can't fix what you can't see. Wire up the metrics pipeline."
**Timeline: Days 14–16 | Hamza only | Branch: `feature/telemetry`**

---

## [H] Hamza — Task 6.1: Emit Latency Metrics from Worker

**Layman Explanation:** The SDK already has code to receive latency measurements (e.g., "How long did it take for the AI to start speaking after you finished?"). But the worker never sends these measurements. This is a known gap in `INTERNAL_DEPLOYMENT_AND_ARCHITECTURE.md` (Section 5). This task wires it.

**New File:** `worker/metrics.py`
```python
"""Per-turn latency measurement and emission via LiveKit data channel."""
from __future__ import annotations
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass
class TurnMetrics:
    session_id: str
    room_name: str
    tenant_id: str
    agent_id: str
    stt_final_ms: int = 0
    llm_ttft_ms: int = 0
    tts_first_byte_ms: int = 0
    turn_round_trip_ms: int = 0
    at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_payload(self) -> bytes:
        data = asdict(self)
        data["type"] = "turn_latency"
        return json.dumps(data).encode()

async def emit_turn_metrics(room: Any, metrics: TurnMetrics) -> None:
    """Publish metrics as a LiveKit data channel message to all participants."""
    try:
        await room.local_participant.publish_data(
            metrics.to_payload(),
            reliable=False,  # Best-effort, don't block audio for metrics
        )
    except Exception:
        pass  # Never let metrics emit crash the audio pipeline
```

**Update `worker/main.py`** — instrument `build_session()` with timing:
```python
# After build_session(), add timing hooks:
# These are injected at session lifecycle events — see livekit.agents AgentSession events
```

**New SQL Migration:** `supabase/migrations/0013_turn_metrics.sql`
```sql
CREATE TABLE IF NOT EXISTS turn_metrics (
  id          BIGSERIAL PRIMARY KEY,
  session_id  TEXT        NOT NULL,
  tenant_id   UUID        NOT NULL REFERENCES tenants(id),
  agent_id    UUID        NOT NULL REFERENCES agents(id),
  room_name   TEXT        NOT NULL,
  stt_final_ms    INTEGER DEFAULT 0,
  llm_ttft_ms     INTEGER DEFAULT 0,
  tts_first_byte_ms INTEGER DEFAULT 0,
  turn_round_trip_ms INTEGER DEFAULT 0,
  at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX turn_metrics_tenant_idx ON turn_metrics(tenant_id, at DESC);
ALTER TABLE turn_metrics ENABLE ROW LEVEL SECURITY;
CREATE POLICY turn_metrics_tenant_read ON turn_metrics
  FOR SELECT TO authenticated
  USING (tenant_id::text = auth.jwt() ->> 'sub');
```

---

## [H] Hamza — Task 6.2: Add Metrics Tab to Admin Dashboard

**File to update:** `admin/queries.py`

Add:
```python
def avg_latency_by_tenant(conn: psycopg.Connection, days: int = 7) -> list[dict]:
    rows = conn.execute("""
        SELECT tenant_id, 
               ROUND(AVG(stt_final_ms)) as avg_stt_ms,
               ROUND(AVG(llm_ttft_ms)) as avg_llm_ms,
               ROUND(AVG(tts_first_byte_ms)) as avg_tts_ms,
               ROUND(AVG(turn_round_trip_ms)) as avg_rtt_ms,
               COUNT(*) as turn_count
        FROM turn_metrics
        WHERE at > NOW() - INTERVAL '%s days'
        GROUP BY tenant_id
        ORDER BY avg_rtt_ms DESC
    """, (days,)).fetchall()
    return [dict(zip(("tenant_id","avg_stt_ms","avg_llm_ms","avg_tts_ms","avg_rtt_ms","turn_count"), r)) for r in rows]
```

---

## PHASE 6 MERGE POINT
```
Hamza: feature/telemetry → dev → main
Run a live test call after deploy, check Supabase turn_metrics table populates
```

---

---

# 📖 PHASE 7: DOCUMENTATION & CLIENT ONBOARDING PORTAL
### "If clients can't figure out how to use it, they won't use it."
**Timeline: Days 14–17 | Both developers | Diverging branches**

---

## [H] Hamza — Task 7.1: Interactive API Documentation

**New File:** `docs/api-reference.md`

Write comprehensive OpenAPI-style reference for:
- `POST /v1/session` — all request headers, body, response fields, error codes
- `POST /v1/session/refresh` — bearer token refresh
- `POST /v1/session/dev-mint` — dev-only quick start

Also add to `control_plane/app.py`:
```python
# Add description to app metadata
app = FastAPI(
    title="UVA Control Plane",
    description="Voice-Agent-as-a-Service token minting and session management API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
```

This auto-generates interactive Swagger UI at `https://uva-control-plane.onrender.com/docs`.

---

## [B] Habiba — Task 7.2: Add "Getting Started" Page to Dashboard

**New Dashboard Page:** `dashboard/src/app/(dashboard)/getting-started/page.tsx`

This page shows clients exactly what they need to integrate:
1. Their credentials (from credentials page)
2. Copy-paste Node.js backend snippet (pre-filled with their tenant ID)
3. Copy-paste frontend SDK snippet (pre-filled with their publishable key and agent ID)
4. A test button that fires a real session request to prove the integration works

---

## [B] Habiba — Task 7.3: Client Integration Email Template

When a new tenant signs up, send them a welcome email with:
- Their publishable key
- Link to the Getting Started guide
- Sample code for their first agent

Implement via Supabase Edge Functions + Resend (email API):
**New File:** `supabase/functions/welcome-email/index.ts`

---

## PHASE 7 MERGE POINT
```
Both PR to dev, integration review, then main
```

---

---

# 🔥 PHASE 8: LOAD TESTING & AUTOSCALING
### "Break it before a real client does."
**Timeline: Days 16–18 | Both developers | Branch: `test/load-testing`**

---

## [H] Hamza — Task 8.1: Write Load Test Script

**Layman Explanation:** A load test simulates multiple clients calling your system at the same time. This reveals at what point things break — which sets the ceiling for how many clients you can take before needing more servers.

**New File:** `bench/load_test.py`
```python
"""
Concurrent session load test. Mints N sessions simultaneously against the deployed control plane.
Does NOT actually start audio — just measures mint throughput and quota enforcement.
"""
import asyncio
import aiohttp
import time

CONTROL_PLANE_URL = "https://uva-control-plane.onrender.com"
N_CONCURRENT = 10  # Number of simultaneous session requests

async def mint_one(session: aiohttp.ClientSession, agent_id: str, tenant_id: str, secret: str) -> dict:
    import hmac, hashlib, secrets as _s, time as _t
    ts = str(int(_t.time()))
    nonce = _s.token_hex(8)
    msg = f"{tenant_id}.{ts}.{nonce}.{agent_id}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    
    async with session.post(
        f"{CONTROL_PLANE_URL}/v1/session",
        json={"agent_id": agent_id},
        headers={
            "X-Tenant-Id": tenant_id,
            "X-Timestamp": ts,
            "X-Nonce": nonce,
            "X-Signature": sig,
        }
    ) as resp:
        return {"status": resp.status, "body": await resp.json()}

async def run_load_test():
    async with aiohttp.ClientSession() as session:
        start = time.time()
        tasks = [mint_one(session, AGENT_ID, TENANT_ID, HMAC_SECRET) for _ in range(N_CONCURRENT)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start
        
        successes = sum(1 for r in results if isinstance(r, dict) and r["status"] == 200)
        quota_hits = sum(1 for r in results if isinstance(r, dict) and r["status"] == 429)
        print(f"✅ Successes: {successes}/{N_CONCURRENT}")
        print(f"🚫 Quota hits: {quota_hits}/{N_CONCURRENT}")
        print(f"⏱️  Total time: {elapsed:.2f}s")
```

---

## [B] Habiba — Task 8.2: Configure Render Autoscaling

**Step-by-step:**

1. Go to Render → `uva-voice-worker` service → Settings → **Scaling**
2. Enable **Autoscaling**:
   - Min instances: `2`
   - Max instances: `10`
   - Scale up trigger: CPU > `70%` for 30 seconds
   - Scale down trigger: CPU < `30%` for 5 minutes
3. Enable **Autoscaling** on `uva-control-plane` too:
   - Min: `1`
   - Max: `5`
   - Trigger: Request latency > 500ms p95

**Important Note on Worker Scaling:** When you scale to multiple worker instances, LiveKit's `explicit dispatch` model (used in `control_plane/app.py::_dispatch_agent()`) ensures each call is routed to a **specific** worker instance by agent name. Multiple workers with the same `LIVEKIT_AGENT_NAME` register as a pool — LiveKit distributes dispatch jobs across the pool automatically. No extra configuration needed.

---

## PHASE 8 MERGE POINT
```
Load test results documented in bench/LOAD_TEST_RESULTS.md
Autoscaling configs verified in Render staging
PR to main
```

---

---

# 🚀 PHASE 9: PUBLIC LAUNCH READINESS
### "Final checklist before you take money from real clients."
**Timeline: Day 19–20 | Both developers**

---

## Joint Checklist

### Infrastructure
- [ ] All three Render services (`control-plane`, `worker`, `admin`) green health checks
- [ ] CI/CD pipeline runs all tests on every PR
- [ ] Staging environment is a working mirror of production
- [ ] Worker autoscaling tested with N=5 concurrent sessions
- [ ] `LIVEKIT_AGENT_NAME` identical in control plane and worker env vars

### Security
- [ ] `CP_ALLOWED_ORIGINS` set to only dashboard domain (not `*`)
- [ ] All Render secret env vars marked as "Secret" (hidden in UI)
- [ ] `hmac_secret` column never returned in any dashboard API query
- [ ] Admin portal only accessible from `ADMIN_PORTAL_ORIGINS` whitelist
- [ ] No API keys committed to GitHub (run `gitleaks detect` to verify)
- [ ] Session-end quota decrement verified (watch `quota_state.concurrent_now` reset after call)

### Database
- [ ] All 13 SQL migrations applied to production Supabase
- [ ] RLS enabled on all tenant-facing tables
- [ ] Onboarding trigger tested (sign up → tenant row auto-created)
- [ ] Supabase connection pooler used (not direct connection, for scale)

### SDK
- [ ] `@uva/voice` version `0.1.0` published on npm
- [ ] SDK `README.md` complete with working code examples
- [ ] SDK tested in a completely blank Vite project by following own documentation
- [ ] `sdk/dist/` committed and up-to-date

### Dashboard
- [ ] Signup → Login → Create Agent → Copy Agent ID → Use in SDK → Hear voice — end-to-end working
- [ ] Call history table shows real sessions
- [ ] Credentials page shows publishable key and masked HMAC secret
- [ ] Getting Started page has copy-paste ready code

### Billing
- [ ] Stripe test mode verified: usage records appear in Stripe dashboard after daemon runs
- [ ] Switch Stripe to **live mode** keys for real billing
- [ ] First real tenant onboarded via dashboard (not script)

### Monitoring
- [ ] Set up Render email alerts for service crashes
- [ ] Set up UptimeRobot or similar to ping `/healthz` every 5 minutes with SMS alert
- [ ] Check `turn_metrics` table is populating after live calls

---

---

# 📋 COMPLETE GITHUB BRANCH MAP

| Branch | Owner | Purpose | Merge Target |
|---|---|---|---|
| `fix/phase-0-hotfixes` | Both | Quota decrement + healthz + CORS | `main` |
| `infra/render-deploy` | Hamza | All 3 Render services deployed | `main` |
| `infra/cicd` | Habiba | GitHub Actions CI/CD pipeline | `main` |
| `security/phase-2` | Hamza | DB secrets, rotation API | `dev → main` |
| `feature/sdk-publish` | Habiba | npm publish + README | `dev → main` |
| `feature/dashboard-backend` | Hamza | Supabase RLS + triggers | `dev → main` |
| `feature/dashboard-frontend` | Habiba | Next.js tenant dashboard | `dev → main` |
| `feature/billing` | Habiba | Stripe integration + daemon | `dev → main` |
| `feature/telemetry` | Hamza | Worker latency metrics | `dev → main` |
| `test/load-testing` | Both | Bench scripts + autoscaling | `dev → main` |

---

# 📅 MASTER TIMELINE SUMMARY

```
Week 1  │ Phase 0 (hotfixes) + Phase 1 (infra + CI/CD)
         │ ├── [H] Deploy control plane, worker, admin to Render
         │ └── [B] GitHub Actions CI/CD + staging environment

Week 2  │ Phase 2 (security) + Phase 3 (SDK publish)
         │ ├── [H] DB secrets migration + CORS + rotation API  
         │ └── [B] SDK npm publish + tenant provisioning script

Week 3  │ Phase 4 (dashboard) — parallel tracks
         │ ├── [H] Supabase RLS policies + onboarding trigger
         │ └── [B] Next.js dashboard app + Vercel deploy

Week 4  │ Phase 5 (billing) + Phase 6 (telemetry)
         │ ├── [H] Worker latency metrics + admin queries
         │ └── [B] Stripe metered billing + cron daemon

Week 5  │ Phase 7 (docs) + Phase 8 (load test) + Phase 9 (launch)
         │ ├── [H] API reference docs + load test script
         │ └── [B] Getting started page + autoscaling config
         │ [Both] Final launch checklist + first real client
```

---

# 🆘 CONFLICT AVOIDANCE PROTOCOL

These files are **SHARED** and need explicit coordination before editing:

| File | Risk | Protocol |
|---|---|---|
| `control_plane/app.py` | Both may need to add routes | Coordinate on WhatsApp before pushing. Always `git pull` before editing. |
| `supabase/migrations/` | Must be sequential numbered | Habiba owns even numbers (0010, 0012), Hamza owns odd (0009, 0011, 0013). |
| `requirements.txt` | Dependency conflicts | Never add packages without checking with each other. |
| `docker/worker.Dockerfile` | May need new deps | Hamza owns worker Dockerfile changes. |
| `.github/workflows/` | CI config | Habiba owns CI. Hamza reviews PRs. |

**The Golden Rule:** If a file isn't listed in your task for the current phase, **do not touch it** without messaging the other person first.

---

*Generated: 2026-07-21 | Based on full codebase analysis of `urdu-agent-SDK` repository*
*This plan reflects the exact current state of the codebase including all known gaps documented in the internal architecture files.*
