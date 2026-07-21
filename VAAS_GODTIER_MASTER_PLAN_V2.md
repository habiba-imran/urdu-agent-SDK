# VaaS GOD-TIER MASTER PLAN V2
## Urdu Voice-Agent-as-a-Service
### Repo-grounded production blueprint for Hamza and Habiba

This plan replaces the earlier master plan with a version grounded in the code that actually exists in `C:\Users\habib\urdu-agent-SDK` on **July 21, 2026**.

It is written for two developers working remotely in parallel over GitHub and WhatsApp. The split is designed to:

- keep file ownership clean
- minimize merge collisions
- preserve deployment safety
- produce a real client-deliverable SDK package, not just internal infrastructure

---

## 0. What Exists Right Now

### Active production-facing components in this repo

| Area | Current paths | What exists today |
|---|---|---|
| Control plane | `control_plane/app.py`, `control_plane/mint.py`, `control_plane/secrets.py` | FastAPI token mint, refresh, dev-mint, explicit LiveKit dispatch, HMAC validation, tenant quota/origin checks |
| Worker | `worker/main.py`, `worker/factories.py`, `worker/config.py`, `worker/tools.py`, `worker/usage.py` | LiveKit worker with Gladia/Google/Uplift pipeline, adaptive interruption, tenant prompt isolation, fixed tools |
| SDK | `sdk/src/index.ts`, `sdk/package.json`, `sdk/README.md` | Browser SDK package `@uva/voice` with connect, disconnect, transcript, speaking, metrics, token refresh |
| Admin backend | `admin/app.py`, `admin/auth.py`, `admin/audit.py`, `admin/queries.py`, `admin/security.py` | Super-admin backend with JWT auth, TOTP, audit logging, tenant/session/usage queries |
| Voice picker | `voice-picker/index.html`, `voice-picker/render_config.py` | Voice preview/catalog surface |
| Dev sandbox | `control_plane/static/dev_sandbox.html` | Browser harness for local end-to-end testing |
| Docker | `docker/control-plane.Dockerfile`, `docker/worker.Dockerfile`, `docker/admin.Dockerfile` | Runtime images for deployable services |
| Data model | `supabase/migrations/0001` to `0008` | Tenants, agents, sessions, quota, nonces, admin, tools, voices |
| Tests | `tests/` | Mint, isolation, admin, worker, schema, latency, STT/TTS, live checks |

### Important repo truths this plan accepts

1. The product is **SDK-first**. The public integration path is the browser SDK plus a host-owned backend.
2. The host platform must never receive provider secrets.
3. The current SDK is intentionally small and transport-focused.
4. A tenant-facing self-service dashboard does **not** exist yet in this repo.
5. The control plane currently uses `CP_TENANT_SECRETS` as a secret map.
6. The control plane currently has wildcard CORS in `control_plane/app.py`.
7. The worker still needs stronger session-end accounting and production telemetry completion.

---

## 1. What “Production Ready” Means For This Repo

This plan defines production-ready as all of the following:

1. Render-hosted control plane, worker, and admin backend are stable.
2. The SDK can be installed and integrated by an external team with only:
   - npm package
   - reference host-backend starter
   - integration guide
   - example app
3. Tenant secrets, quotas, and session lifecycle are correct under failure conditions.
4. Multi-tenant isolation is still provable.
5. Admin can inspect sessions, usage, blockers, and latency.
6. A first customer can be onboarded without manual code edits or risky prod shell work.

### Non-goals in this plan

- PSTN, SIP, telephony, Pakistan numbers
- native mobile SDKs
- self-hosted LiveKit
- voice cloning
- general-purpose workflow builder

---

## 2. The Missing Pieces The Old Plan Did Not Close

These are the gaps this V2 plan explicitly closes:

1. **Reference host backend starter**
   - clients need more than SDK docs
   - they need a server route that signs requests and relays refresh safely

2. **Session closeout and reconciliation**
   - worker shutdown callbacks alone are not enough
   - production needs end-of-session accounting plus a repair job

3. **Client certification**
   - “published SDK” is not the same as “client can succeed”
   - one external-style blank app must integrate from docs only

4. **Secret lifecycle**
   - secret storage, rotation, and masking must use the right trust boundary
   - browser/session tokens must not rotate backend signing secrets

5. **Repo-realistic scope**
   - dashboard work is net-new product work
   - this plan treats it as such instead of assuming it already exists

---

## 3. Team Split Rules

### Hamza owns

- control plane
- worker runtime
- Supabase migrations
- Render deployment
- failure recovery
- security-critical flows

### Habiba owns

- SDK packaging and examples
- reference host-backend starter
- tenant-facing dashboard
- onboarding flows
- billing
- client docs polish

### Shared files that require coordination

| Path | Rule |
|---|---|
| `control_plane/app.py` | One owner per phase only |
| `worker/main.py` | One owner per phase only |
| `supabase/migrations/*` | Sequential numbering, one person authors each migration |
| `sdk/src/index.ts` | Habiba leads, Hamza reviews only |
| `admin/queries.py` | Hamza leads, Habiba only consumes via dashboard API layer |
| `.github/workflows/*` | Habiba authors, Hamza reviews |
| `docker/*` | Hamza owns runtime image changes |

### Branch strategy

- `main`: production
- `dev`: shared staging integration branch
- `feature/<owner>-<phase-topic>`: work branches

Examples:

- `feature/hamza-runtime-hardening`
- `feature/habiba-sdk-starter`
- `feature/hamza-render-prod`
- `feature/habiba-tenant-dashboard`

---

## 4. Phase Map

```text
Phase 0  Runtime hardening and deploy blockers
Phase 1  Render infrastructure and CI/CD
Phase 2  Security and secret lifecycle
Phase 3  SDK release and host-backend starter
Phase 4  Tenant dashboard MVP
Phase 5  Usage billing and metering correctness
Phase 6  Telemetry, latency, and admin observability
Phase 7  Client onboarding package and certification
Phase 8  Load, reconciliation, and recovery validation
Phase 9  Launch gate
```

Estimated duration with two people in parallel: **4 to 6 weeks** depending on how much of the dashboard and billing you want in v1.

---

## Phase 0: Runtime Hardening And Deploy Blockers
### Goal
Fix the things that can make production unstable even if deployment succeeds.

### Timeline
2 to 3 days

### Hamza track

#### Task H0.1: Add health endpoints

**Files**

- `control_plane/app.py`
- `admin/app.py`

**Why this matters in plain language**

Render needs a dead-simple liveness URL. Without one, you end up guessing whether a service is healthy or just happened to boot once.

**Deliverable**

- `GET /healthz` on control plane
- `GET /healthz` on admin backend

#### Task H0.2: Finalize session end closeout in the worker

**Files**

- `worker/main.py`
- possibly `worker/usage.py`

**Why this matters**

The system increments active concurrency during mint. If call end cleanup is incomplete, quota drifts upward and blocks real customers later.

**Required outcome**

- decrement `quota_state.concurrent_now` on normal worker shutdown
- write `sessions.ended_at`, `duration_sec`, and `end_reason`
- ensure the logic is idempotent

#### Task H0.3: Add quota repair script

**New file**

- `scripts/reconcile_sessions.py`

**Why this matters**

Even a good shutdown callback does not protect you from container crashes, LiveKit disconnect edge cases, or deploy restarts.

**Required outcome**

- compare open `sessions` rows against live/known activity
- repair stale `quota_state.concurrent_now`
- safe to run manually and from cron

#### Task H0.4: Tighten control-plane CORS

**Files**

- `control_plane/app.py`
- `.env.example`
- `docs/62-GUIDE-PROD-ENV-VARS.md`

**Why this matters**

The HMAC check is the real guard, but wildcard browser CORS still makes the public surface sloppier than it should be.

**Required outcome**

- replace `allow_origins=["*"]` with environment-driven allowlist
- default can remain permissive only in local dev if you choose

### Habiba track

#### Task B0.1: Audit and normalize SDK public contract

**Files**

- `sdk/src/index.ts`
- `sdk/README.md`

**Why this matters**

Before publishing a package, the public API must be intentional. Right now the SDK is usable, but still “thin.”

**Required outcome**

- decide v1 surface explicitly
- keep or add only what you are willing to support
- document omissions clearly

#### Task B0.2: Create example consumer app

**New directory**

- `examples/basic-web-client/`

**Why this matters**

A real example is worth more than ten pages of docs. This becomes the first client-certification target later.

**Required outcome**

- blank web app using `@uva/voice`
- reads config from env
- can connect/disconnect and show transcript/speaking state

### Merge gate

- services expose `/healthz`
- worker end-of-session cleanup works in a local or staging call
- quota reconciliation script can safely correct stale concurrency
- example consumer app runs locally

---

## Phase 1: Render Infrastructure And CI/CD
### Goal
Make deployments repeatable and safe.

### Timeline
3 to 4 days

### Hamza track

#### Task H1.1: Deploy control plane to Render

**Files touched**

- none in app code unless env or health issues appear
- possibly `docker/control-plane.Dockerfile`

**Required Render settings**

- Web Service
- Docker runtime
- health check `/healthz`
- env vars:
  - `LIVEKIT_URL`
  - `LIVEKIT_API_KEY`
  - `LIVEKIT_API_SECRET`
  - `LIVEKIT_AGENT_NAME`
  - `SUPABASE_DB_URL`
  - `CP_TENANT_SECRETS`
  - `CP_ALLOWED_ORIGINS`

#### Task H1.2: Deploy worker to Render

**Files touched**

- possibly `docker/worker.Dockerfile`
- `docs/63-GUIDE-WORKER-DEPLOYMENT-DEFERRAL.md` should be superseded by actual deploy notes

**Required outcome**

- worker boots cleanly
- worker registers with the exact `LIVEKIT_AGENT_NAME`
- dispatch path succeeds

#### Task H1.3: Deploy admin backend to Render

**Required env**

- `SUPABASE_DB_URL`
- `ADMIN_JWT_SECRET`
- `ADMIN_PORTAL_ORIGINS`

#### Task H1.4: Create production and staging env matrices

**New file**

- `docs/RENDER_ENV_MATRIX.md`

**Why**

You want one place listing every env var by service and environment.

### Habiba track

#### Task B1.1: Add CI pipeline

**New files**

- `.github/workflows/ci.yml`

**Required jobs**

- Python lint/test
- SDK install/build/lint
- Docker build smoke for control plane and worker

#### Task B1.2: Add CD pipeline

**New files**

- `.github/workflows/deploy-staging.yml`
- `.github/workflows/deploy-prod.yml`

**Required behavior**

- `dev` deploys staging
- `main` deploys prod

#### Task B1.3: Add release checklist issue template

**New file**

- `.github/ISSUE_TEMPLATE/release-checklist.md`

### Merge gate

- staging control plane, worker, and admin are live
- one end-to-end staging call succeeds
- CI runs on PR
- production deploy hook path exists but is not used until Phase 9

---

## Phase 2: Security And Secret Lifecycle
### Goal
Make client onboarding scalable without violating the trust boundary.

### Timeline
3 to 4 days

### Hamza track

#### Task H2.1: Move tenant secret lookup behind a provider abstraction suitable for production

**Files**

- `control_plane/secrets.py`
- `control_plane/app.py`
- new `control_plane/secrets_db.py` or `control_plane/secrets_store.py`
- new migration under `supabase/migrations/`

**Important design rule**

Do not let browser-visible session credentials rotate or reveal backend HMAC secrets.

**Recommended implementation**

- store encrypted or raw secret in a service-only readable column or secret store
- keep `hmac_secret_hash` for audit/comparison purposes
- use env fallback during migration

#### Task H2.2: Build admin-only secret rotation

**Files**

- `admin/app.py`
- `admin/queries.py`
- control-plane provider layer

**Why this is better**

The browser SDK is not the owner of the host signing secret. Secret lifecycle belongs to trusted admin/backend flows only.

#### Task H2.3: Add masked credentials read model

**Why**

Clients need to retrieve:

- publishable key
- tenant ID
- secret status

But never raw HMAC secret after initial creation.

### Habiba track

#### Task B2.1: Build secure credential bootstrap flow

**New directory**

- `tenant-portal/` or `dashboard/` if that is the product name you want

**Initial pages**

- login
- first-time credential creation
- credential copy screen

#### Task B2.2: First-time secret display UX

**Rule**

- show raw secret once
- require user acknowledgement
- never re-display full secret later

### Merge gate

- new tenant can be provisioned without editing `CP_TENANT_SECRETS`
- raw secret is shown only during creation/rotation flow
- browser/session token cannot rotate secrets

---

## Phase 3: SDK Release And Host-Backend Starter
### Goal
Ship something clients can actually integrate.

### Timeline
4 to 5 days

### Hamza track

#### Task H3.1: Define the control-plane-facing host backend contract

**New file**

- `docs/HOST_BACKEND_CONTRACT.md`

**Must specify**

- required HMAC headers
- request body shape
- refresh behavior
- error mapping
- replay window expectations

#### Task H3.2: Add official test fixtures for host integration

**New files**

- `tests/test_host_backend_contract.py`
- `scripts/mint_demo_token.py` may be extended

### Habiba track

#### Task B3.1: Build reference host backend starter

**New directory**

- `examples/host-backend-node/`

**Recommended stack**

- Node + Express or Next.js route handlers

**Required endpoints**

- `POST /api/voice/session`
- `POST /api/voice/session/refresh`

**Why this matters in plain language**

Your customers need the missing middle piece between browser SDK and your control plane. Without it, they still have to invent security-critical code themselves.

#### Task B3.2: Publish SDK to npm

**Files**

- `sdk/package.json`
- `sdk/README.md`
- optional `.github/workflows/release-sdk.yml`

**Required outcome**

- stable package name
- semver tag
- published install path

#### Task B3.3: Add example app that consumes the published package

**Files**

- `examples/basic-web-client/`
- `examples/host-backend-node/`

### Merge gate

- a fresh machine can install the SDK
- the Node host-backend starter can sign requests correctly
- example browser app can connect via the starter backend

---

## Phase 4: Tenant Dashboard MVP
### Goal
Let customers self-serve the minimum viable product flow.

### Timeline
5 to 7 days

### Scope for MVP

Tenant-facing dashboard should support:

1. sign in
2. create agent
3. choose voice
4. edit prompt
5. see agent ID
6. see publishable key / credential instructions
7. see recent calls and usage summary

### Hamza track

#### Task H4.1: Build dashboard backend/API layer

**New area**

- `tenant_portal_api/` or extend an app layer under a new folder

**Do not overload**

- `admin/`
- `control_plane/`

**Required APIs**

- list/create/update agents
- fetch tenant credential metadata
- list recent sessions for tenant
- usage summary for tenant

#### Task H4.2: Add tenant-safe read/write queries

**Files**

- `supabase/migrations/*`
- new query layer under portal backend

### Habiba track

#### Task B4.1: Build tenant dashboard frontend

**New directory**

- `dashboard/`

**Recommended stack**

- Next.js
- server routes for authenticated portal actions

#### Task B4.2: Integrate voice picker into dashboard

**Existing assets**

- `voice-picker/index.html`
- `scripts/record_voice_previews.py`
- `scripts/upload_voice_previews.py`

### Merge gate

- tenant can create an agent with prompt + voice
- agent row is immediately usable by SDK
- tenant sees agent ID and integration instructions

---

## Phase 5: Billing And Metering Correctness
### Goal
Bill from the actual schema and actual usage events, not from invented fields.

### Timeline
3 to 4 days

### Hamza track

#### Task H5.1: Normalize usage truth

**Files**

- `worker/usage.py`
- `admin/queries.py`
- `supabase/SCHEMA.md`

**Why this matters**

Billing built on the wrong event names will silently invoice wrong amounts or nothing at all.

**Required outcome**

- choose the billable source of truth:
  - `agent_sec` converted to minutes, or
  - a new explicit billable event kind

#### Task H5.2: Add billing aggregation SQL

**New file**

- `billing/sql.py` or equivalent

### Habiba track

#### Task B5.1: Build Stripe integration against the real schema

**New directory**

- `billing/`

**Required files**

- `billing/daemon.py`
- `docker/billing.Dockerfile`
- `docker/requirements-billing.txt`

#### Task B5.2: Add customer/subscription management in tenant dashboard

**Files**

- `dashboard/...`
- portal backend routes
- new migration for Stripe IDs

### Merge gate

- usage aggregation matches real `usage_events`
- Stripe test mode records are created from real data
- admin can reconcile billable totals against raw DB values

---

## Phase 6: Telemetry, Latency, And Admin Observability
### Goal
Close the current metrics gap end to end.

### Timeline
3 to 4 days

### Hamza track

#### Task H6.1: Emit worker turn metrics

**Files**

- new `worker/metrics.py`
- `worker/main.py`

**Required metrics**

- `stt_final_ms`
- `llm_ttft_ms`
- `tts_first_byte_ms`
- `turn_round_trip_ms`

**Output paths**

- LiveKit data channel for SDK consumption
- Supabase persistence for admin analytics

#### Task H6.2: Add turn metrics storage/query layer

**Files**

- new migration
- `admin/queries.py`

### Habiba track

#### Task B6.1: Add metrics panels to tenant dashboard

**Views**

- recent session latency
- rolling averages
- failure indicators

#### Task B6.2: Add metrics visualization to example app

**Why**

This proves the SDK metrics event surface is useful to clients.

### Merge gate

- live call publishes metrics to browser
- metrics persist in DB
- admin can query by tenant

---

## Phase 7: Client Onboarding Package And Certification
### Goal
Produce the actual client-deliverable package.

### Timeline
3 to 4 days

### Hamza track

#### Task H7.1: Write authoritative API and architecture docs

**Files**

- `docs/api-reference.md`
- update `README.md`
- update deployment docs as needed

### Habiba track

#### Task B7.1: Finalize client integration guide

**Files**

- `sdk/README.md`
- new `docs/CLIENT_QUICKSTART.md`

#### Task B7.2: Build onboarding email/template flow

**Files**

- dashboard or portal backend
- optional `supabase/functions/`

### Joint certification step

One of you acts as the client and uses only:

- npm package
- host-backend starter
- client docs

The other does not help except clarifying documentation bugs after they are found.

**The certification scenario**

1. clone blank sample app
2. install SDK
3. configure starter backend
4. use issued credentials
5. connect to a real staging agent
6. verify refresh
7. verify disconnect/reconnect
8. verify expected error display

### Merge gate

- external-style blank integration succeeds from docs only
- all missing steps discovered during certification are fixed in docs/code

---

## Phase 8: Load, Reconciliation, And Recovery Validation
### Goal
Make sure production survives non-happy-path conditions.

### Timeline
3 days

### Hamza track

#### Task H8.1: Upgrade load testing beyond mint-only

**Files**

- `bench/load_test.py`
- `scripts/concurrency_test.py`

**Required scenarios**

- mint-only burst
- full session join burst
- worker dispatch saturation
- refresh under load

#### Task H8.2: Failure-recovery drills

**Scenarios**

- worker restart during active call
- control-plane deploy during session churn
- stale session cleanup
- quota repair job correctness

### Habiba track

#### Task B8.1: Dashboard and SDK soak testing

**Scenarios**

- multiple tenant agents
- concurrent dashboard usage
- long-running browser session

#### Task B8.2: Release candidate assembly

**Artifacts**

- SDK version candidate
- dashboard staging URL
- host-backend starter tag

### Merge gate

- no unreconciled quota drift after tests
- worker pool scaling works with explicit dispatch
- refresh keeps long sessions alive

---

## Phase 9: Launch Gate
### Goal
Only ship when the whole package is coherent.

### Infrastructure

- [ ] control plane healthy on prod Render
- [ ] worker healthy on prod Render
- [ ] admin healthy on prod Render
- [ ] staging mirrors prod topology
- [ ] deploys are CI-driven, not manual-only

### Runtime correctness

- [ ] session start increments concurrency
- [ ] session end decrements concurrency
- [ ] reconciliation script repairs stale state safely
- [ ] dispatch failure rolls back session/quota cleanly
- [ ] refresh works for calls longer than 2 minutes

### Security

- [ ] CORS is no longer wildcard in production
- [ ] tenant secret storage is no longer manual env editing for onboarding
- [ ] secret rotation is admin/trusted-flow only
- [ ] raw HMAC secret is never re-displayed after initial issuance

### SDK and client package

- [ ] SDK published
- [ ] example browser app works
- [ ] example host backend works
- [ ] client docs are sufficient for an external-style integration
- [ ] package version and docs reference the same API surface

### Tenant product

- [ ] tenant can sign in
- [ ] tenant can create agent
- [ ] tenant can choose voice
- [ ] tenant can retrieve integration credentials safely
- [ ] tenant can see recent sessions and usage

### Billing and telemetry

- [ ] Stripe test billing matches DB truth
- [ ] turn metrics flow end to end
- [ ] admin sees blocker and usage visibility

### Human signoff

- [ ] Hamza signs off runtime/security
- [ ] Habiba signs off SDK/dashboard/client onboarding
- [ ] first real client dry run completed in staging

---

## 5. Detailed Ownership Summary

| Phase | Hamza | Habiba |
|---|---|---|
| Phase 0 | healthz, worker closeout, reconciliation, CORS | SDK contract audit, example consumer app |
| Phase 1 | Render deploys, env matrix | CI/CD, release automation |
| Phase 2 | secret provider, rotation, secure credential model | credential bootstrap UX, first-time secret display |
| Phase 3 | host backend contract, contract tests | host backend starter, npm publish, examples |
| Phase 4 | tenant backend/API, tenant-safe queries | dashboard frontend, voice picker integration |
| Phase 5 | billable truth, aggregation | Stripe integration, tenant billing UX |
| Phase 6 | worker metrics, admin metrics queries | tenant metrics UI, example metrics view |
| Phase 7 | API/docs authority | onboarding docs, onboarding email, certification fixes |
| Phase 8 | load/failure drills | soak testing, release candidate assembly |
| Phase 9 | runtime/security signoff | client/package/product signoff |

---

## 6. Recommended Execution Order This Week

If you want the shortest path to momentum, start in this exact order:

1. Phase 0
2. Phase 1
3. Phase 3
4. Phase 2
5. Phase 7
6. Then decide whether Phase 4 and Phase 5 are required for your first paying client

### Why this order

- Phase 0 and 1 make the system deployable and less fragile
- Phase 3 makes the product consumable by a client
- Phase 2 makes scaling onboarding safe
- Phase 7 proves the deliverable is real
- Phase 4 and 5 are commercial-product multipliers, but may not both be necessary for the first pilot if you are still onboarding manually

---

## 7. Hard Truths

1. **You do not have a production-ready client package until the host-backend starter exists.**
2. **You do not have reliable production concurrency until reconciliation exists, not just shutdown callbacks.**
3. **You do not have real billing until it runs against the actual usage schema.**
4. **You do not have client readiness until a blank external app succeeds from docs only.**

---

## 8. Immediate Next Step

Open two branches now:

- Hamza: `feature/hamza-runtime-hardening`
- Habiba: `feature/habiba-sdk-starter`

Start with:

- Hamza: Phase 0 tasks H0.1 through H0.4
- Habiba: Phase 0 task B0.1 and Phase 3 task B3.1 scaffold

That pairing gives you the fastest route to a real deployable core plus a real client-consumable integration path.

