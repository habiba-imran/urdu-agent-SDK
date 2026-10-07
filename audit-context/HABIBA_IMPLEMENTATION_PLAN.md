# Habiba implementation plan — backend gatekeepers audit + hardening

**Status:** FINAL  
**Owner:** Habiba only  
**Source of truth for scope:** `audit-context/AUDIT_SPLIT_PLAN (4).md`  
**Goal:** A gap-free **backend foundation** (auth, tenancy, telephony control plane, quotas, RLS, Render resilience, server-side secrets/PII, portal enforcement) so Ehsan can start worker/SDK/dashboard work later with a clean contract surface—not a half-audited API.

**Out of this plan:** worker runtime, npm SDKs, dashboard UI, CI/release, host-tools runtime, Ehsan’s script set. Habiba may **read** those files for contract checks; Habiba must **not wait** for Ehsan to start, approve, or co-edit.

---

## 0. Strategy decision (audit vs fix)

### Decision: **Audit-then-fix in waves** (not “fix while discovering”)

| Approach | Verdict |
|---|---|
| Fix every issue the moment you see it | Rejected — contaminates severity ranking, skips systemic patterns, breaks retest trail |
| Audit everything Habiba owns, then one giant fix dump | Rejected — P0 money/auth bugs sit open too long |
| **Wave audit → wave remediate Critical/High → retest → next wave** | **Selected** |

This matches common practice (OWASP ASVS verification + reporting, then remediation and **retest** with fixed / partial / open status; PTES/NIST-style engagements treat reporting and retest as first-class, not optional).

### How waves map to priority

1. **Wave A — P0 audit complete** (M1 server, M5, M4, M2 server) → findings file frozen for P0  
2. **Wave B — P0 remediate** Critical + High only → retest each closed finding  
3. **Wave C — P1 audit** (M8 server, M11 enforcement, M7 server, M6 save-time) → findings frozen  
4. **Wave D — P1 remediate** Critical + High → retest  
5. **Wave E — P2 / packaging for Ehsan** (M12 Python inventory + Habiba exit package)  
6. **Wave F — Medium/Low backlog** (optional before Ehsan; never blocks Ehsan start if Crit/High closed)

Medium/Low can be deferred to a backlog unless they block a Critical fix.

### What “gap-free final SDK” means for Habiba

Habiba does **not** ship the npm packages. Habiba ships a **final backend contract** that a production SDK depends on:

| Gate | Habiba exit criterion |
|---|---|
| Auth | HMAC mint + machine auth: constant-time compare, replay/nonce rules proven, secrets not logged |
| Tenancy | No cross-tenant read/write via portal JWT or machine HMAC; RLS posture documented; privileged DB role use justified |
| Money / telephony | Webhooks verify signatures; mock mode cannot be on in hosted; outbound destination policy enforced; idempotency durable in DB |
| Quotas | Mint/rollback/refresh rules coherent; slot leak paths documented with server-side mitigations Habiba owns |
| Secrets / PII | Encryption keys, retention, recording URLs, admin rotate, portal credential flags reviewed server-side |
| Resilience | In-memory loss on Render restart understood; hosted fail-closed for secrets/CORS/docs; health/runbook notes |
| Observability | Minimum audit fields for mint/machine/admin/telephony denials; Python test map for M1–M5 |

Ehsan later covers client signers, worker release, SDK timeouts, dashboard UI. Habiba leaves **HANDOFF_TO_EHSAN.md** with contracts and open counterparts—not joint work sessions.

---

## 1. Operating rules (strict)

1. Findings go only in `audit-context/FINDINGS_HABIBA.md` using the Section 9 template from the split plan.  
2. Every finding cites `path:line` **you opened**. Never copy pack citations as proof.  
3. Every Check item ends as one of: **PASS** / **FAIL** (finding ID) / **N/A** (why) / **DEFERRED-EHSAN** (handoff note only).  
4. **No Dashboard product changes** until M11 product decision is written (Section 8 Q5). Habiba may still audit enforcement and record current state.  
5. **No edits to Ehsan-owned paths** (`.github/workflows/**`, `docker/**`, `Makefile`, `requirements*.txt`, root lockfiles, `sdk/`, `sdk-server/`, `telephony/`, `worker/` code, `dashboard/` UI) unless Habiba owns the file under the split plan (migrations, Habiba scripts, portal/CP/admin).  
6. Fixes for Habiba code: branch per wave or per Critical finding; one finding ID in the commit/PR body.  
7. After each fix: **retest** the original reproduction; mark Status `fixed` only with evidence (test name, command, or manual steps).  
8. Stop a phase if a Critical finding is open with no mitigation and a public/hosted path is implicated—finish remediation before expanding scope.

### Artifacts Habiba maintains

| Artifact | Purpose |
|---|---|
| `audit-context/FINDINGS_HABIBA.md` | All findings |
| `audit-context/HABIBA_CHECKLIST.md` | Pass/fail per Check item (copy from modules below) |
| `audit-context/HABIBA_EVIDENCE/` | Screenshots, script outputs, SQL extracts (no secrets) |
| `audit-context/HANDOFF_TO_EHSAN.md` | Counterpart items + contracts Ehsan must verify later |
| `audit-context/HABIBA_GATE_LOG.md` | Phase exit signatures (date, PASS/FAIL) |

---

## 2. Habiba scope map (no Ehsan blockers)

### In scope (Habiba executes end-to-end)

| Module | Habiba slice | Priority |
|---|---|---|
| **M1** | Server: mint HMAC, machine auth, secrets providers, secret crypto, nonce purge script/migrations | P0 |
| **M5** | Portal tenancy, RLS/migrations, admin auth, membership | P0 |
| **M4** | Portal telephony service/routes/webhooks/clients/credentials/reconcile + telephony migrations + Habiba Telnyx scripts | P0 |
| **M2** | CP mint/quota/rollback/refresh; portal session/`test_studio`; `reconcile_sessions.py`; quota SQL | P0 |
| **M8** | CP / portal / admin cold-start & in-memory loss; hosted fail-closed | P1 |
| **M11** | Portal + RLS enforcement of read-only (not UI) | P1 |
| **M7** | Server secrets/PII/recordings/URLs/Sentry/admin rotate/portal credential flags | P1 |
| **M6** | **Only** `tenant_portal_api/tools_webhook.py` + tools migrations (save-time) | P1 |
| **M12** | Python `tests/**` inventory + gaps for Habiba modules | P2 |

### Explicitly out of Habiba execution (handoff only)

| Topic | Why |
|---|---|
| Client HMAC signers (`sdk-server`, `telephony` signing, starter signing) | Ehsan M1 counterpart |
| Worker quota release / stale jobs / crash scripts | Ehsan M2 |
| Telephony npm SDK | Ehsan M4 |
| Worker SSRF request-time / host-tools | Ehsan M6 |
| Worker laptop secrets / transcript dumps | Ehsan M7 |
| SDK/demo timeouts | Ehsan M8 |
| Dashboard UI visibility | Ehsan M11 |
| npm tests / CI release | Ehsan M10/M12 |

**Allowed without Ehsan:** open those files read-only to confirm server expectations; write “Ehsan must verify X” in `HANDOFF_TO_EHSAN.md`. That is not a blocker.

### Habiba scripts (run/read as listed in split plan)

`migrate.py`, `db_inspect.py`, `db_reset.py`, `dbconn.py`, `rls_check.py`, `encrypt_tenant_secrets.py`, `purge_used_nonces.py`, `purge_expired_session_media.py`, `reconcile_sessions.py`, `reconcile_telephony.py`, `usage_guard.py`, `verify_admin_boundary_live.py`, `verify_rate_limit_live.py`, `provision_admin.py`, `provision_demo_tenant.py`, `create_new_client.py`, `mint_demo_token.py`, Telnyx `scripts/*.mjs` helpers.

---

## 3. Phase plan

---

### PHASE 0 — Kickoff & environment (½–1 day)

#### 0.1 Sub-phase: Freeze product answers Habiba can answer alone

| ID | Action | Verification |
|---|---|---|
| 0.1.1 | Write M11 interim decision in `HABIBA_GATE_LOG.md`: either “enforcement audit assumes **create-agent forbidden**; edits/reveal/telephony/Test Studio **undecided—record current state only**” or a full decision if product owner confirms | File exists; Q5 status recorded |
| 0.1.2 | List Render services Habiba owns (CP, portal, admin) and confirm `UVA_ENV`/`RENDER`/`TELEPHONY_PROVIDER_MODE` from dashboard/env (no code change) | Table in gate log: service → env vars present/absent |
| 0.1.3 | Confirm DB is Supabase (or not); note which role `SUPABASE_DB_URL` uses | Gate log entry |

#### 0.2 Sub-phase: Tooling & baselines

| ID | Action | Verification |
|---|---|---|
| 0.2.1 | Create empty `FINDINGS_HABIBA.md`, `HABIBA_CHECKLIST.md`, `HANDOFF_TO_EHSAN.md`, `HABIBA_EVIDENCE/` | Paths exist |
| 0.2.2 | Run `scripts/rls_check.py` (dry or documented mode); save stdout to evidence | Evidence file; note coverage gaps |
| 0.2.3 | Inventory Python tests touching `control_plane`, `tenant_portal_api`, `admin` (`pytest --collect-only` or name grep) | List pasted into checklist under M12 draft |

#### Phase 0 exit gate

- [ ] Artifacts created  
- [ ] M11 interim stance written  
- [ ] RLS script run once  
- [ ] No code changes required to pass Phase 0  

---

### PHASE 1 — Wave A: P0 audit (no fixes except emergency Critical live exploit)

**Order (matches split plan):** M1 → M5 → M4 → M2  

**Rule:** Do not land intentional hardening PRs in Phase 1 unless a Critical issue is actively exploitable on a hosted deployment you control; if so, emergency fix + finding still filed first.

---

#### PHASE 1A — M1 Request signing, replay, tenant secrets (server)

**Unread first (mandatory):** `control_plane/secrets_db.py`, `control_plane/secret_crypto.py`, slices of `control_plane/app.py` for rate limit + secret wiring; migrations `0004_nonces.sql`, `0009_tenant_secrets.sql`, `0033_tenant_secret_encryption.sql`; `scripts/encrypt_tenant_secrets.py`, `scripts/purge_used_nonces.py`.

| Sub-phase | Audit steps | Verification (must produce evidence) |
|---|---|---|
| **1A.1 Message & compare** | Trace mint `expected_signature` and verify path; confirm compare is constant-time or FAIL. Trace machine `expected_signature` + `payload_hash` + `compare_digest`. | Checklist items for mint compare + machine compare; finding if mint uses `==` |
| **1A.2 Replay & nonce** | Prove insert uniqueness; measure purge age vs `REPLAY_WINDOW_SEC`; confirm reconcile workflow invokes purge (read workflow; note if prod schedule unknown → open Q4 in gate log) | SQL/migration cite; purge script age vs 60s; handoff if schedule unknown |
| **1A.3 Rate limits** | Confirm tenant 120/min and IP 240/min (mint) and machine 30/120 applied **after/before** auth as intended; document in-memory reset | `verify_rate_limit_live.py` run **or** FAIL with “cannot run” + code-only PASS/FAIL |
| **1A.4 Secrets** | Env vs DB provider; cache TTL; rotation window; encryption algorithm/key location; which hosts need decrypt key | Findings for weak crypto / key in logs / hosted using env map |
| **1A.5 Contract snapshot for Ehsan** | Read client signers **read-only**; document expected message/header/body-hash rules in handoff—do not wait for Ehsan to “approve” | `HANDOFF_TO_EHSAN.md` M1 section |

**M1 Check → checklist rows:** all M1 Checks from split plan except client-only signing tests (mark client test gap DEFERRED-EHSAN; still verify **server** accepts/rejects correctly via existing Python tests if present).

**1A exit:** Every M1 Check classified; Critical/High filed if any; gate log `1A PASS`.

---

#### PHASE 1B — M5 Tenant isolation, RLS, admin

**Unread first:** `supabase/migrations/**` (start `0002_rls.sql`, `0015_telephony_rls_grants.sql`, `0030`, `0031`, `0032`, `0034`, `0035`), `queries.py`, `membership.py`, most `app.py`, `admin/queries.py`; run `scripts/rls_check.py`, `scripts/verify_admin_boundary_live.py`.

| Sub-phase | Audit steps | Verification |
|---|---|---|
| **1B.1 Role & RLS map** | For each tenant table: RLS on? FORCE? policies USING/WITH CHECK? Which DB role do CP/portal/admin/worker use? | Table in evidence: table → RLS → force → roles |
| **1B.2 Portal query scoping** | Sample every query helper: tenant id from verified token vs body | At least N high-risk routes: agents, sessions, credentials, telephony list; FAIL on IDOR |
| **1B.3 Machine vs portal limits** | Confirm max agents/prompt/greeting/page limits apply on HMAC routes too | Code cites both paths or finding |
| **1B.4 Hosted secrets** | `jwt_secret`, `PORTAL_ALLOW_*`, admin JWT generation vs hosted | Env matrix |
| **1B.5 Admin** | PBKDF2 iterations, TOTP window/replay (0031), disable/revocation (0032), audit log on rotate | `verify_admin_boundary_live.py` evidence or documented blocker |
| **1B.6 Membership** | Roles/permissions matrix for tenant members | Written matrix |

**Aligned with OWASP multi-tenant guidance:** treat privileged/`BYPASSRLS` connections as **not** protected by RLS; require app-layer tenant filters + justify service-role use.

**1B exit:** RLS map complete; all M5 Checks classified; gate `1B PASS`.

---

#### PHASE 1C — M4 Telephony control plane

**Unread first:** `telephony_service.py` (2,477), `telnyx_client.py`, `livekit_sip.py`, `telephony_queries.py`, `telephony_credentials.py`, routes/reconcile/errors/health/destinations; migrations `0012`–`0015` + `20260801*`; `scripts/reconcile_telephony.py` + Telnyx `*.mjs`.

| Sub-phase | Audit steps | Verification |
|---|---|---|
| **1C.1 Webhook trust** | Ed25519 over raw body; 256 KiB; 300s window; IP rate; mock accept path; hosted never mock | Prove mock cannot return True when hosted; finding if it can |
| **1C.2 Durable idempotency** | Read `0013`/`0014_*idempotency*`; prove DB unique keys for event/signature; LRU is secondary | SQL cites; concurrent double-delivery thought experiment documented |
| **1C.3 Spend controls** | Where `TELNYX_OUTBOUND_DESTINATIONS` enforced; bypass via any of 28 machine ops; per-tenant caps | Matrix: operation → gated Y/N |
| **1C.4 Credentials** | Encryption alg, key env, rotation, never returned in API/logs | Redaction check on error paths |
| **1C.5 Isolation & state machine** | SIP/LiveKit resources per tenant; status mapping; reconcile repairs | Call lifecycle diagram in evidence (Habiba-drawn) |
| **1C.6 Client timeouts** | Telnyx/LiveKit HTTP client timeouts/retries | Code cites |
| **1C.7 Handoff** | Note telephony SDK has no timeout—Ehsan M4/M8 | Handoff only |

**1C exit:** All M4 Checks classified; gate `1C PASS`.

---

#### PHASE 1D — M2 Sessions, quotas (server)

**Unread first:** remaining `control_plane/app.py` handlers, quota SQL in migrations, `test_studio.py`, `scripts/reconcile_sessions.py`.

| Sub-phase | Audit steps | Verification |
|---|---|---|
| **1D.1 Quota truth** | Concurrent + monthly gates; DB defaults; user-visible errors | Cite migration defaults + mint error paths |
| **1D.2 Slot lifecycle (server)** | Mint increment, dispatch rollback, refresh gates, absence of session-end route | Sequence diagram; read `worker/session_close.py` **read-only** → handoff “Ehsan must prove release on crash” |
| **1D.3 Refresh cap** | `MAX_REFRESHES` via JWT `refresh_count`; hosted DB fail-closed on refresh gates | Prove count survives process restart |
| **1D.4 Reconcile** | Does `reconcile_sessions.py` repair `concurrent_now`? | Script behavior summarized; finding if no |
| **1D.5 Dispatch failure** | What “worker not ready / full” means in CP | Code path + HTTP mapping |

**Do not run Ehsan scripts** (`concurrency_test.py`, `simulate_worker_crash.py`) as a Phase 1D requirement. Optional local run is allowed; results go to handoff if they need worker ownership.

**1D exit:** All Habiba M2 Checks classified; gate `1D PASS`.

---

#### PHASE 1 exit (Wave A complete)

- [ ] `FINDINGS_HABIBA.md` has all P0 findings with severity  
- [ ] `HABIBA_CHECKLIST.md` M1/M5/M4/M2 complete  
- [ ] `HANDOFF_TO_EHSAN.md` has M1/M2/M4 counterpart stubs  
- [ ] Gate log: `WAVE_A_AUDIT PASS`  
- [ ] **No Wave B until Wave A exit signed**

---

### PHASE 2 — Wave B: P0 remediation + retest

#### 2.1 Triage

| Severity | Action in Wave B |
|---|---|
| Critical | Must fix before Wave C |
| High | Must fix before Wave C |
| Medium | Backlog or fix if ≤½ day and unblocks High |
| Low / Info | Backlog |

#### 2.2 Fix loop (per finding)

1. Reproduce → evidence  
2. Implement minimal fix in Habiba-owned code  
3. Add/adjust **Python** test under `tests/` when feasible  
4. Retest original steps → Status `fixed`  
5. Note any Ehsan follow-up in handoff (e.g. “client must send new header”)

#### 2.3 Verification gate

| ID | Gate |
|---|---|
| 2.3.1 | Zero open Critical in M1/M4/M5/M2 Habiba scope |
| 2.3.2 | Zero open High **or** written risk acceptance with expiry date in gate log |
| 2.3.3 | `pytest` subset for touched modules green locally (list commands in gate log) |
| 2.3.4 | Re-run `rls_check.py` / rate-limit / admin-boundary scripts if those areas changed |

**Phase 2 exit:** `WAVE_B_REMEDIATE PASS`.

---

### PHASE 3 — Wave C: P1 audit

Order: **M8 (server) → M11 (enforcement) → M7 (server) → M6 (save-time only)**.

---

#### PHASE 3A — M8 Resilience (server)

| Sub-phase | Steps | Verification |
|---|---|---|
| **3A.1 Inventory volatile state** | Rate buckets, webhook LRU, any portal in-memory caches Habiba owns | Table: structure → lost on restart → DB backup? |
| **3A.2 Cold start UX (server)** | Document what CP/portal/admin return when waking; health endpoints | Curl/evidence against staging if available; else code-only |
| **3A.3 Hosted fail-closed** | Secrets, CORS, docs, mock telephony | Env matrix |
| **3A.4 DB pool under restart** | Timeouts, pool sizes in portal/CP/admin | Code cites |
| **3A.5 Handoff** | SDK 15s timeout / agents no timeout → Ehsan | Handoff |

**3A exit:** M8 Habiba Checks done.

---

#### PHASE 3B — M11 Dashboard read-only (enforcement only)

| Sub-phase | Steps | Verification |
|---|---|---|
| **3B.1 Route matrix** | Portal JWT routes that create/update agents, credentials, telephony, test studio | Matrix: route → method → allowed today → intended under decision |
| **3B.2 RLS bypass test** | Can anon/authenticated Supabase roles write agents? | SQL/`rls_check` evidence |
| **3B.3 Machine vs portal** | Machine create still allowed (by design); portal create blocked if required | Explicit PASS/FAIL vs decision |
| **3B.4 No UI work** | Do not change dashboard components | Confirm no `dashboard/` commits in Habiba PRs |

**3B exit:** Enforcement findings filed; UI items DEFERRED-EHSAN.

---

#### PHASE 3C — M7 Secrets / PII / recordings (server)

| Sub-phase | Steps | Verification |
|---|---|---|
| **3C.1 Env & logging** | Portal/CP/admin logs never print secrets; Sentry scrub posture | Grep + Sentry config cite |
| **3C.2 Recordings** | `recording_urls.py`, migrations 0027/0028, purge script | Retention actually deletes? |
| **3C.3 Telephony PII** | Call rows, numbers at rest | Schema + access paths |
| **3C.4 Credential reveal flags** | Server enforcement of reveal/rotate flags | Code + default hosted values |
| **3C.5 Handoff** | Worker laptop / `.env.local` → Ehsan | Handoff |

**3C exit:** M7 server Checks done.

---

#### PHASE 3D — M6 Save-time tools only

| Sub-phase | Steps | Verification |
|---|---|---|
| **3D.1 Read `tools_webhook.py` + migrations 0008/0026** | Validate `tools_base_url` / secret storage | Cite SSRF/save-time rules |
| **3D.2 Equivalence note** | Compare intended rules to worker guard **read-only** (`ssrf_guard.py`, `runtime_env.py`) | Written gap list for Ehsan if mismatch |
| **3D.3 No host-tools fixes** | Out of scope | Confirm |

**3D exit:** Save-time Checks done; request-time DEFERRED-EHSAN.

---

#### PHASE 3 exit

- [ ] Wave C checklist complete  
- [ ] Gate `WAVE_C_AUDIT PASS`

---

### PHASE 4 — Wave D: P1 remediation + retest

Same loop as Phase 2 for Critical/High from M8/M11/M7/M6-save-time.

**Phase 4 exit:** Zero open Critical; High closed or accepted; `WAVE_D_REMEDIATE PASS`.

---

### PHASE 5 — Wave E: M12 Python + Ehsan-ready package

| Sub-phase | Steps | Verification |
|---|---|---|
| **5.1 Test inventory** | Map `tests/**` → M1–M5/M8/M11/M7 coverage; list missing | Table in checklist |
| **5.2 Minimum new tests** | Only where Wave B/D left untested Critical paths | Named tests green |
| **5.3 Logging fields** | Decide mint/machine/admin/telephony denial log fields (tenant_id, reason, request_id if any) | Doc in handoff; implement if Critical gap |
| **5.4 Handoff package** | Finalize `HANDOFF_TO_EHSAN.md`: contracts, open counterpart Checks, known env requirements | Peer-readable without Habiba present |
| **5.5 Habiba Definition of Done** | Sign gate below | `HABIBA_BACKEND_FINAL PASS` |

---

### PHASE 6 — Optional Medium/Low cleanup

Only after Phase 5. Does not block Ehsan start.

---

## 4. End-to-end verification matrix (Habiba)

Use this as the recurring “are we done?” board. Each row needs evidence path.

| # | Capability | Primary modules | Proof type |
|---|---|---|---|
| V1 | Mint HMAC reject bad sig / replay / skew | M1 | test or script |
| V2 | Machine HMAC reject bad sig / replay | M1 | test |
| V3 | Cross-tenant agent mint blocked | M5/M1 | test or live |
| V4 | Cross-tenant portal list/read blocked | M5 | test or SQL |
| V5 | RLS cannot be relied on alone under service role — documented mitigations | M5 | written + code |
| V6 | Admin login throttle + rotate audited | M5 | script/test |
| V7 | Telnyx webhook rejects bad signature | M4 | test |
| V8 | Webhook duplicate event safe (DB) | M4 | test or SQL proof |
| V9 | Mock telephony disabled when hosted | M4/M8 | code+env |
| V10 | Outbound destination policy enforced | M4 | code path test |
| V11 | Quota increment + dispatch rollback | M2 | test |
| V12 | Refresh cap enforced via JWT metadata | M2 | test |
| V13 | Portal agent-create policy matches M11 decision | M11 | route matrix |
| V14 | Recording URL / retention / purge coherent | M7 | script+migration |
| V15 | tools_base_url rejected if private/metadata at save-time (hosted rules) | M6 | test |
| V16 | In-memory limiter loss documented; DB truth for money/auth | M8/M1/M4 | written |

---

## 5. Suggested calendar (solo Habiba)

| Phase | Duration (indicative) |
|---|---|
| Phase 0 | 0.5–1 day |
| Phase 1A–1D (P0 audit) | 5–8 days |
| Phase 2 (P0 fix+retest) | 3–6 days (depends on findings) |
| Phase 3 (P1 audit) | 3–5 days |
| Phase 4 (P1 fix+retest) | 2–4 days |
| Phase 5 (M12 + handoff) | 1–2 days |

Compress only by skipping Medium/Low, never by skipping retest on Critical.

---

## 6. Final Habiba gate (`HABIBA_BACKEND_FINAL`)

Sign only when all are true:

1. Wave A–D exits PASS in `HABIBA_GATE_LOG.md`  
2. No open Critical in Habiba scope  
3. No open High without dated risk acceptance  
4. V1–V16 matrix filled (PASS / N/A / DEFERRED-EHSAN only where justified)  
5. `HANDOFF_TO_EHSAN.md` complete for M1/M2/M4/M6/M7/M8/M11 counterparts  
6. Migrations Habiba changed (if any) have apply notes and rollback notes  
7. Secrets never committed; evidence redacted  

When this gate is signed, **Ehsan may start** his plan independently.

---

## 7. Anti-patterns (do not do)

- Waiting for Ehsan to “review client signers” before closing M1 server audit  
- Fixing dashboard UI under M11 before product decision  
- Editing `requirements.txt` / workflows / Docker without ownership (Ehsan owns build files)  
- Marking findings fixed without retest evidence  
- Treating pack `Known` lines as findings  
- Expanding into `worker/` feature work “while you’re there”

---

## 8. Immediate next actions (start tomorrow)

1. Create the four artifacts listed in §1.  
2. Execute Phase 0.1–0.2.  
3. Begin **1A.1** on `control_plane/mint.py` signature verify path (constant-time check).  
4. Do not open fix PRs until Wave A exit unless emergency Critical.

---

## 9. References used for methodology

- OWASP ASVS 5.0 — verification levels, evidence, report exceptions, hybrid source-led review  
- OWASP Multi-Tenant Security Cheat Sheet — RLS FORCE, non-BYPASSRLS roles, app-layer tenant context  
- Webhook security practice — raw-body signatures, timestamp windows, **DB** idempotency (not memory alone)  
- Production readiness / SDK release gates — auth, rotation, timeouts/idempotency, ops runbook, retest after remediation  
- Cold-start / free-tier reality — document wake latency and fail-closed hosted config (M8)

---

*This plan is Habiba-complete and intentionally non-blocking on Ehsan. Counterpart work is recorded as handoff, never as a wait state.*
