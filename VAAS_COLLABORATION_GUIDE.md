# VaaS Dual-Track Collaboration Guide
## Hamza × Habiba — Parallel & Sequential Task Map
> **Source of truth**: V2 Master Plan. This guide is the operational layer on top of it.

---

## How to Read This Guide

Each phase shows two columns — **Hamza's lane** and **Habiba's lane** — running side by side.

- **🟢 Parallel** = both developers work at the same time, no dependency
- **🔴 SYNC POINT** = a hard stop. One or both of you must wait for a specific condition before the next phase begins
- **⚡ Feeds into** = your output becomes the other person's input

When you see a SYNC POINT, message each other on WhatsApp and confirm the condition is met before either of you moves on.

---

## Phase Map at a Glance

```
Phase 0  ──── Both start immediately, in parallel
    │
🔴 SYNC 0
    │
Phase 1  ──── Parallel tracks (H: Render deploy, B: CI/CD)
    │
🔴 SYNC 1
    │
Phase 2 & 3 ──── Both run in parallel across phases
    │
🔴 SYNC 2+3
    │
Phase 4  ──── Both run in parallel (H: backend API, B: frontend)
    │
🔴 SYNC 4
    │
Phase 5 & 6 ──── Both run in parallel across phases
    │
🔴 SYNC 5+6
    │
Phase 7  ──── Both run in parallel, then a JOINT certification step
    │
🔴 SYNC 7 (joint)
    │
Phase 8  ──── Both run in parallel (stress tests)
    │
🔴 SYNC 8
    │
Phase 9  ──── Joint launch signoff
```

---

---

## PHASE 0 — Runtime Hardening & Deploy Blockers
> **Goal**: Fix the things that break production even if deployment succeeds.
> **Duration**: 2–3 days
> **Branch**: Hamza → `feature/hamza-runtime-hardening` | Habiba → `feature/habiba-sdk-starter`

### 🟢 Parallel Work

| Step | Hamza | Habiba |
|---|---|---|
| **0-A** | **H0.1**: Add `GET /healthz` to `control_plane/app.py` | **B0.1**: Audit `sdk/src/index.ts` — decide the v1 public API surface explicitly |
| **0-B** | **H0.2**: Add session-end closeout to `worker/main.py` — decrement `quota_state.concurrent_now`, write `sessions.ended_at`, `duration_sec`, `end_reason` | **B0.1 (cont.)**: Update `sdk/README.md` to match the decided v1 surface |
| **0-C** | **H0.3**: Write `scripts/reconcile_sessions.py` — compare open session rows to reality, repair stale quota | **B0.2**: Scaffold `examples/basic-web-client/` — blank web app that uses `@uva/voice`, reads config from env, shows transcript and speaking state |
| **0-D** | **H0.4**: Replace wildcard CORS in `control_plane/app.py` with env-driven `CP_ALLOWED_ORIGINS` allowlist. Update `.env.example` and `docs/62-GUIDE-PROD-ENV-VARS.md` | (Continue B0.2 or review Hamza's SDK audit) |
| **0-E** | Add `GET /healthz` to `admin/app.py` (also part of H0.1) | — |

> **Note on file ownership this phase:** `control_plane/app.py` and `worker/main.py` are **Hamza-only** in Phase 0. Habiba does not touch those files at all.

---

### 🔴 SYNC POINT 0 — Before Phase 1 Begins

**Hamza must confirm all of the following via WhatsApp:**
- [ ] `GET /healthz` returns `{"status": "ok"}` on both control plane and admin
- [ ] A test call (local or staging) ends and `quota_state.concurrent_now` goes back to 0
- [ ] `reconcile_sessions.py` runs cleanly without errors against the dev database
- [ ] CORS is no longer `["*"]` — `CP_ALLOWED_ORIGINS` env var is wired

**Habiba must confirm:**
- [ ] `examples/basic-web-client/` runs locally — can connect, disconnect, show transcript
- [ ] `sdk/README.md` reflects the actual v1 surface (no promise about unimplemented features)

**Neither person starts Phase 1 until both sets of checkboxes are ticked.**

---

---

## PHASE 1 — Render Infrastructure & CI/CD
> **Goal**: Make deployments repeatable and safe.
> **Duration**: 3–4 days

### 🟢 Parallel Work

| Step | Hamza | Habiba |
|---|---|---|
| **1-A** | **H1.1**: Deploy control plane to Render as a Web Service using `docker/control-plane.Dockerfile`. Health check → `/healthz`. Set all env vars. | **B1.1**: Create `.github/workflows/ci.yml` — Python lint/test, SDK install/build/lint, Docker build smoke for control plane and worker |
| **1-B** | **H1.2**: Deploy worker to Render as a Background Worker using `docker/worker.Dockerfile`. Verify boot log shows `agent_name` registration. | **B1.2**: Create `.github/workflows/deploy-staging.yml` — auto-deploy to staging on push to `dev` branch |
| **1-C** | **H1.3**: Deploy admin backend to Render as a separate Web Service. Set `ADMIN_JWT_SECRET`, `ADMIN_PORTAL_ORIGINS`. | **B1.2 (cont.)**: Create `.github/workflows/deploy-prod.yml` — production deploy hook path (wired but not triggered until Phase 9) |
| **1-D** | **H1.4**: Create `docs/RENDER_ENV_MATRIX.md` — full table of every env var by service and environment (staging + prod) | **B1.3**: Create `.github/ISSUE_TEMPLATE/release-checklist.md` |
| **1-E** | Run end-to-end staging call: mint → worker join → audio stream → clean disconnect | Share Render deploy hook URLs with Habiba so CI/CD can trigger them |

> **Habiba's CI/CD work requires** the Render deploy hook URLs from Hamza. Hamza should send these over WhatsApp mid-phase, not wait until the end.

---

### 🔴 SYNC POINT 1 — Before Phase 2 or 3 Begins

**Hamza confirms:**
- [ ] Staging control plane is live and `/healthz` passes
- [ ] Staging worker is live and registered with correct `LIVEKIT_AGENT_NAME`
- [ ] Staging admin is live
- [ ] One end-to-end staging call completed successfully (mint → join → stream → disconnect)
- [ ] `docs/RENDER_ENV_MATRIX.md` is pushed to `dev`

**Habiba confirms:**
- [ ] CI runs on every PR (test with a dummy PR)
- [ ] Push to `dev` branch triggers staging deploy
- [ ] Production deploy workflow file exists but has no live trigger yet

**After this sync, Phases 2 and 3 run simultaneously — Hamza on Phase 2, Habiba on Phase 3.**

---

---

## PHASES 2 & 3 — Security + SDK Release (Simultaneous)
> **These two phases run at the same time.** Hamza is fully on Phase 2. Habiba is fully on Phase 3. They do not share files in this window.

### 🟢 Parallel Work

| Step | Hamza (Phase 2 — Security) | Habiba (Phase 3 — SDK & Host Backend) |
|---|---|---|
| **2/3-A** | **H2.1**: Create `control_plane/secrets_db.py` (or `secrets_store.py`). Add new Supabase migration to store tenant HMAC secret in a service-role-only readable column. Wire `DbSecretProvider` with env fallback so existing tenants don't break. | **B3.1**: Build `examples/host-backend-node/` — Node + Express starter with `POST /api/voice/session` and `POST /api/voice/session/refresh`. Signs requests using HMAC exactly per the control-plane spec. |
| **2/3-B** | **H2.2**: Build admin-only secret rotation endpoint in `admin/app.py` and `admin/queries.py`. Secret lifecycle must never touch the browser SDK or session token path. | **B3.2**: Publish `@uva/voice` to npm. Update `sdk/package.json` semver. Add `prepublishOnly: npm run build`. Set `publishConfig.access: "public"`. |
| **2/3-C** | **H2.3**: Add masked credentials read model — endpoints that return publishable key and secret status (masked), never raw HMAC after creation. | **B3.3**: Wire `examples/basic-web-client/` to consume the published npm package (not a local `tgz`). Test it against `examples/host-backend-node/`. |
| **2/3-D** | **H3.1**: Write `docs/HOST_BACKEND_CONTRACT.md` — the exact spec for HMAC headers, request body shape, refresh behavior, error mapping, replay window. | (Habiba uses H3.1 as the spec for B3.1 — send a draft over WhatsApp first so Habiba doesn't have to wait for the final doc) |
| **2/3-E** | **H3.2**: Write `tests/test_host_backend_contract.py` against the new contract doc | Review Habiba's starter backend against the contract doc |

> ⚡ **Hamza's `HOST_BACKEND_CONTRACT.md` feeds directly into Habiba's host-backend starter.** Hamza should share a WhatsApp draft of the HMAC header spec at the beginning of this window, before the doc is finished, so Habiba doesn't block.

---

### 🔴 SYNC POINT 2+3 — Before Phase 4 Begins

**Hamza confirms:**
- [ ] New tenant can be provisioned without editing `CP_TENANT_SECRETS` — the DB secret provider works
- [ ] Secret rotation runs through `admin/` only, not through the browser SDK
- [ ] Raw HMAC secret is never returned in any endpoint after initial creation
- [ ] `docs/HOST_BACKEND_CONTRACT.md` is merged to `dev`
- [ ] Contract tests pass in CI

**Habiba confirms:**
- [ ] Fresh machine can `npm install @uva/voice` and it resolves
- [ ] `examples/host-backend-node/` correctly signs requests — verified against the control plane contract test
- [ ] Example browser app in `examples/basic-web-client/` connects through the node starter backend against the staging control plane

**Critical integration test (run together):**
> Habiba runs the example app + node starter. Hamza watches the staging control plane logs. Confirm: HMAC signature validates, agent dispatches, worker joins, call completes, quota decrements to 0.

---

---

## PHASE 4 — Tenant Dashboard MVP
> **Goal**: Let customers self-serve the minimum viable product flow.
> **Duration**: 5–7 days
> **Branch**: Hamza → `feature/hamza-tenant-api` | Habiba → `feature/habiba-tenant-dashboard`

### 🟢 Parallel Work

| Step | Hamza (Backend API) | Habiba (Frontend) |
|---|---|---|
| **4-A** | **H4.1**: Create `tenant_portal_api/` (separate from `admin/` and `control_plane/`). Define routes: list/create/update agents, fetch tenant credential metadata, list recent sessions, usage summary. | **B4.1**: Create `dashboard/` — Next.js app. Start with auth pages (login, signup) and the shell layout (sidebar, header). Do not wire real data yet. |
| **4-B** | **H4.2**: Write tenant-safe Supabase migrations — RLS policies so authenticated users only see their own rows (agents, sessions, quota). Write the onboarding trigger that auto-creates tenant row on signup. | **B4.1 (cont.)**: Build agent list and agent edit form pages. Wire to mock data to unblock UI work before the API is ready. |
| **4-C** | Send Hamza's API route schema to Habiba over WhatsApp (route paths, request/response shape) — even before the routes work | **B4.1 (cont.)**: Replace mock data with real calls to Hamza's API once routes are deployed to staging |
| **4-D** | Test H4.1 routes with Postman/curl against staging DB | **B4.2**: Integrate the existing `voice-picker/index.html` assets into the dashboard voice selection UI |
| **4-E** | Code-review Habiba's dashboard API integration against the API layer | Build credentials display page — publishable key visible, HMAC secret status shown (masked), link to rotation docs |

> **Hamza's API must come first** for the dashboard's real data to work, but Habiba can start building pages with mocked responses immediately. The unblock happens in step 4-C.

---

### 🔴 SYNC POINT 4 — Before Phase 5 or 6 Begins

**Hamza confirms:**
- [ ] Tenant API routes are deployed to staging and pass basic curl tests
- [ ] RLS migrations are applied — verified that Tenant A cannot read Tenant B's agents
- [ ] Onboarding trigger tested: new signup → tenant row auto-created

**Habiba confirms:**
- [ ] Dashboard deployed to Vercel (or Render static site) pointing at staging
- [ ] End-to-end flow works: Sign Up → Create Agent → See Agent ID → See Publishable Key
- [ ] Voice picker works inside the dashboard

**Joint test:**
> Habiba signs up a new account in the dashboard. Hamza verifies in Supabase that the tenant row, quota row, and first agent row were created correctly.

**After this sync, Phases 5 and 6 run simultaneously — Habiba on Phase 5, Hamza on Phase 6.**

---

---

## PHASES 5 & 6 — Billing + Telemetry (Simultaneous)
> **These two phases run at the same time.** Hamza is on Phase 6 (telemetry). Habiba is on Phase 5 (billing).

### 🟢 Parallel Work

| Step | Hamza (Phase 6 — Telemetry) | Habiba (Phase 5 — Billing) |
|---|---|---|
| **5/6-A** | **H5.1**: Audit `worker/usage.py` and `admin/queries.py` — confirm the exact billable event kind (`agent_sec` or a new explicit kind). Update `supabase/SCHEMA.md`. | **B5.1**: Set up Stripe account. Create metered Product + Price. Note `STRIPE_PRICE_ID`. |
| **5/6-B** | **H5.2**: Write `billing/sql.py` — the SQL aggregation that turns `usage_events` rows into per-tenant billable minute totals. This is what Habiba's daemon will call. | **B5.1 (cont.)**: Build `billing/daemon.py` — queries Hamza's aggregation SQL, posts to Stripe `create_usage_record`. |
| **5/6-C** | **H6.1**: Create `worker/metrics.py`. Add per-turn latency capture to `worker/main.py`: `stt_final_ms`, `llm_ttft_ms`, `tts_first_byte_ms`, `turn_round_trip_ms`. Emit via LiveKit data channel. | **B5.1 (cont.)**: Add `docker/billing.Dockerfile` and `docker/requirements-billing.txt`. Configure as Render Cron Job (daily). |
| **5/6-D** | **H6.2**: Write new Supabase migration for `turn_metrics` table. Add `admin/queries.py` function to query latency by tenant. | **B5.2**: Add Stripe customer/subscription management to the `dashboard/` — subscription status page, billing history. Add new Supabase migration for `stripe_customer_id`, `stripe_subscription_item_id`. |
| **5/6-E** | — | **B6.1**: Add metrics panels to `dashboard/` — recent session latency chart, rolling averages. (Consumes H6.2's admin query endpoint) |
| **5/6-F** | — | **B6.2**: Add basic latency display to `examples/basic-web-client/` to prove the SDK `metrics_updated` event works for clients |

> ⚡ **Hamza's H5.2 billing SQL feeds into Habiba's B5.1 daemon.** Hamza should share the SQL query over WhatsApp before it's merged so Habiba can wire the daemon call.
>
> ⚡ **Hamza's H6.2 admin query endpoint feeds into Habiba's B6.1 dashboard metrics panels.** Same pattern — share route shape early.

---

### 🔴 SYNC POINT 5+6 — Before Phase 7 Begins

**Hamza confirms:**
- [ ] Turn metrics are emitted from a live call via LiveKit data channel
- [ ] Turn metrics are persisted in the new `turn_metrics` Supabase table
- [ ] Admin can query latency by tenant via `admin/queries.py`
- [ ] Billing aggregation SQL returns correct per-tenant minute totals against real `usage_events` data

**Habiba confirms:**
- [ ] Stripe test mode: usage records appear in Stripe after daemon runs
- [ ] Daemon billing matches the DB aggregation totals (reconcile manually once)
- [ ] Dashboard metrics panels show real data from a live call
- [ ] Example app shows latency from `metrics_updated` event

---

---

## PHASE 7 — Client Onboarding Package & Certification
> **Goal**: Produce the actual client-deliverable package. Prove it works without hand-holding.
> **Duration**: 3–4 days
> **Branch**: Hamza → `feature/hamza-api-docs` | Habiba → `feature/habiba-client-docs`

### 🟢 Parallel Work (First Half)

| Step | Hamza | Habiba |
|---|---|---|
| **7-A** | **H7.1**: Write `docs/api-reference.md` — authoritative spec for all public control-plane endpoints (`/v1/session`, `/v1/session/refresh`). Update `README.md`. | **B7.1**: Write `docs/CLIENT_QUICKSTART.md` — step-by-step guide from zero to first call using only npm, the host-backend starter, and issued credentials |
| **7-B** | Update FastAPI `app = FastAPI(title=..., description=..., version="1.0.0")` so Swagger UI at `/docs` matches the written spec | **B7.2**: Build onboarding email/template flow — triggered on new tenant signup via `supabase/functions/` or dashboard backend |
| **7-C** | Review Habiba's quickstart doc against the actual API spec — flag any mismatches | Polish `sdk/README.md` to reference both the quickstart and the host-backend starter |

### 🔴 JOINT CERTIFICATION STEP (Phase 7 — Hard Stop for Both)

> This step is mandatory. It cannot be skipped. Do it together on a call or in real-time on WhatsApp.

**The scenario:** One of you acts as a brand-new client (the "client dev"). The other watches silently and only responds to clarify documentation bugs.

**The client dev will use only:**
- The published npm package (`npm install @uva/voice`)
- The host-backend starter in `examples/host-backend-node/`
- `docs/CLIENT_QUICKSTART.md`
- Credentials issued from the staging dashboard

**The certification checklist (the "client dev" must complete all of these):**
1. [ ] Clone `examples/basic-web-client/` from scratch
2. [ ] Install SDK from npm — no local tgz
3. [ ] Configure and run the host-backend starter using their staging credentials
4. [ ] Connect to a live staging agent
5. [ ] Verify token refresh (wait 60+ seconds while connected)
6. [ ] Verify disconnect and reconnect
7. [ ] Trigger a quota error (call twice simultaneously) — confirm the error message is clear
8. [ ] See transcript appear in the browser

**Every step that requires help, guessing, or source-code reading is a documentation bug.** Fix it before proceeding to Phase 8.

---

### 🔴 SYNC POINT 7 — Before Phase 8 Begins

**Both confirm:**
- [ ] All 8 certification steps pass without reading source code
- [ ] All discovered doc gaps are fixed and merged to `dev`
- [ ] `docs/api-reference.md`, `docs/CLIENT_QUICKSTART.md`, and `sdk/README.md` are consistent with each other

---

---

## PHASE 8 — Load, Reconciliation & Recovery Validation
> **Goal**: Make sure production survives non-happy-path conditions.
> **Duration**: 3 days

### 🟢 Parallel Work

| Step | Hamza | Habiba |
|---|---|---|
| **8-A** | **H8.1**: Upgrade `bench/load_test.py` beyond mint-only. Add: full session join burst, worker dispatch saturation, refresh-under-load scenario | **B8.1**: Dashboard + SDK soak test: multiple tenant agents, concurrent dashboard sessions, long-running browser session (30+ min) |
| **8-B** | **H8.2**: Run failure-recovery drills: worker restart during active call, control-plane deploy during session churn, stale session cleanup with reconciliation script | **B8.2**: Assemble release candidate: tag SDK version, note staging dashboard URL, tag host-backend starter |
| **8-C** | Monitor `quota_state.concurrent_now` during and after load tests — confirm it returns to 0 after all sessions end | Confirm dashboard remains usable under concurrent load |

---

### 🔴 SYNC POINT 8 — Before Phase 9 Begins

**Hamza confirms:**
- [ ] No unreconciled quota drift after load test — `concurrent_now` returns to 0
- [ ] Worker restart during active call: SDK reconnects or emits clear error
- [ ] Stale session repair: reconciliation script corrects quota correctly after simulated crash
- [ ] Refresh-under-load: long-running sessions (4+ min) stay alive

**Habiba confirms:**
- [ ] SDK release candidate version tagged and staged
- [ ] Dashboard soak: no UI hangs or auth session drops after 30 min
- [ ] Host-backend starter tag confirmed working against staging control plane

---

---

## PHASE 9 — Launch Gate
> **Goal**: Ship only when the whole package is coherent.
> **This is a joint phase — no parallel tracks. Both sign off together.**

### Joint Launch Checklist

Walk through this list together on a WhatsApp call. Neither person proceeds to flipping the production deploy hook until **all boxes are checked**.

**Infrastructure**
- [ ] Control plane healthy on **prod** Render
- [ ] Worker healthy on **prod** Render (registered with correct `LIVEKIT_AGENT_NAME`)
- [ ] Admin healthy on **prod** Render
- [ ] Staging mirrors prod topology
- [ ] CI/CD drives deploys — no more manual `curl` to deploy hooks

**Runtime Correctness**
- [ ] Session start increments concurrency
- [ ] Session end decrements concurrency (tested in prod with a real call)
- [ ] Reconciliation script runs cleanly against prod DB
- [ ] Dispatch failure rolls back session/quota cleanly
- [ ] Refresh works for calls longer than 2 minutes

**Security**
- [ ] CORS is `CP_ALLOWED_ORIGINS`-driven in production (not `["*"]`)
- [ ] New tenant onboarding does not require editing `CP_TENANT_SECRETS`
- [ ] Secret rotation only accessible via admin backend — not via session token
- [ ] Raw HMAC secret never re-displayed after initial issuance

**SDK & Client Package**
- [ ] `@uva/voice` published on npm
- [ ] `examples/basic-web-client/` works against production
- [ ] `examples/host-backend-node/` works against production
- [ ] `docs/CLIENT_QUICKSTART.md` sufficient for external integration (proven by certification)
- [ ] Package version and docs reference the same API surface

**Tenant Product**
- [ ] Tenant can sign in
- [ ] Tenant can create agent, pick voice, set prompt
- [ ] Tenant can retrieve integration credentials safely
- [ ] Tenant can see recent sessions and usage

**Billing & Telemetry**
- [ ] Stripe test billing matches DB usage totals
- [ ] Turn metrics flow end-to-end in production
- [ ] Admin sees blocker and usage visibility

**Human Signoff**
- [ ] **Hamza signs off**: runtime correctness, security, worker, infrastructure
- [ ] **Habiba signs off**: SDK package, dashboard, client onboarding, docs

---

---

## Complete Blocker Map — Quick Reference

This table shows every point where **Habiba must wait for Hamza** or vice versa.

| Blocker | What Habiba is waiting for | What Hamza is waiting for |
|---|---|---|
| **Start of Ph 2+3** | `docs/HOST_BACKEND_CONTRACT.md` draft (WhatsApp OK) — needed to build host-backend starter | Habiba's example app to test the contract integration |
| **During Ph 2+3** | H2.3 masked credentials model — needed to build credential display UX in dashboard | — |
| **Start of Ph 4 backend** | H4.1 API route schema (WhatsApp OK before routes are live) — needed to wire real data | B4.1 dashboard pages so there is a UI to test the API against |
| **During Ph 5+6** | H5.2 billing aggregation SQL — needed to wire billing daemon | — |
| **During Ph 5+6** | H6.2 admin query endpoint — needed to build dashboard metrics panels | — |
| **During Ph 5+6** | H6.1 worker metrics emission — needed to show latency in example app | — |
| **Ph 7 certification** | Neither person proceeds until both agree all 8 certification steps pass | Same — joint gate |
| **Ph 9 signoff** | Hamza runtime/security signoff | Habiba SDK/dashboard/docs signoff |

---

## Shared File Conflict Rules

These files must never be edited by both developers in the same phase. If you need to touch one, send a WhatsApp message first.

| File | Current owner | Rule |
|---|---|---|
| `control_plane/app.py` | Hamza (Ph 0, 2, 3) | One owner per phase. Habiba must not touch this file without explicit handoff. |
| `worker/main.py` | Hamza (Ph 0, 6) | Hamza-only. Habiba consumes worker output via SDK events. |
| `supabase/migrations/*` | Hamza authors odd numbers, Habiba authors even numbers | New migration = WhatsApp message first. Never commit the same number. |
| `sdk/src/index.ts` | Habiba leads | Hamza reviews only. No direct edits without Habiba's green light. |
| `admin/queries.py` | Hamza leads | Habiba only consumes via API layer. No direct edits. |
| `.github/workflows/*` | Habiba authors | Hamza reviews PRs. No direct CI edits without Habiba's green light. |
| `docker/control-plane.Dockerfile`, `docker/worker.Dockerfile` | Hamza | Habiba must not edit runtime images. |

---

## Branch Naming Convention

```
Hamza:
  feature/hamza-runtime-hardening    (Ph 0)
  feature/hamza-render-prod          (Ph 1)
  feature/hamza-secret-provider      (Ph 2)
  feature/hamza-host-contract        (Ph 3)
  feature/hamza-tenant-api           (Ph 4)
  feature/hamza-billing-truth        (Ph 5)
  feature/hamza-telemetry            (Ph 6)
  feature/hamza-api-docs             (Ph 7)
  feature/hamza-load-testing         (Ph 8)

Habiba:
  feature/habiba-sdk-starter         (Ph 0 + 3)
  feature/habiba-cicd                (Ph 1)
  feature/habiba-credential-ux       (Ph 2)
  feature/habiba-sdk-publish         (Ph 3)
  feature/habiba-tenant-dashboard    (Ph 4)
  feature/habiba-billing             (Ph 5)
  feature/habiba-metrics-ui          (Ph 6)
  feature/habiba-client-docs         (Ph 7)
  feature/habiba-soak-testing        (Ph 8)
```

**Flow:** Feature branch → `dev` (staging) → tested → `main` (production via Phase 9 deploy hook)

---

## First Actions Right Now

Open two branches in the next 10 minutes:

```
git checkout -b feature/hamza-runtime-hardening    # Hamza
git checkout -b feature/habiba-sdk-starter          # Habiba
```

**Hamza starts:** H0.1 (healthz) → H0.2 (worker closeout) → H0.3 (reconciliation script) → H0.4 (CORS)

**Habiba starts:** B0.1 (SDK contract audit) → B0.2 (example app scaffold) → jump ahead to B3.1 (host-backend starter scaffold, since you'll need it in Phase 3 and it unblocks a major integration test)

When Hamza finishes H0.4, send the `CP_ALLOWED_ORIGINS` env var name and format over WhatsApp so Habiba can configure it in the example app.

---

*Guide authored: 2026-07-21 | Based on VaaS Master Plan V2*
