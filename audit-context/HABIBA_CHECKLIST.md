# Habiba checklist — pass / fail tracker

**Plan:** `HABIBA_IMPLEMENTATION_PLAN.md`  
**Result values:** `PASS` | `FAIL` (finding ID) | `N/A` (why) | `DEFERRED-EHSAN` (handoff) | `TODO`

Fill **Result**, **Evidence** (`path:line` or evidence file), **Date** as you go. Do not mark PASS without opening the code yourself.

---

## Phase 0 — Kickoff

| ID | Item | Result | Evidence | Date |
|---|---|---|---|---|
| 0.1.1 | M11 interim decision written in gate log | PASS | GATE_LOG interim create-ban | 2026-10-07 |
| 0.1.2 | Render services Habiba owns + env matrix (`UVA_ENV`/`RENDER`/`TELEPHONY_PROVIDER_MODE`) | PASS | HABIBA_EVIDENCE/2026-10-07_0_env_matrix.md (live Render UNKNOWN) | 2026-10-07 |
| 0.1.3 | DB location (Supabase vs other) + role used by `SUPABASE_DB_URL` | PASS | Supabase pooler user `postgres.*` — M5-F02 | 2026-10-07 |
| 0.2.1 | Artifacts exist: FINDINGS, CHECKLIST, GATE_LOG, HANDOFF, EVIDENCE/ | PASS | audit-context/* | 2026-10-07 |
| 0.2.2 | `scripts/rls_check.py` run; stdout saved | PASS | HABIBA_EVIDENCE/2026-10-07_0_rls_check.txt | 2026-10-07 |
| 0.2.3 | Python test inventory draft (CP/portal/admin) | PASS | HABIBA_EVIDENCE/2026-10-07_0_test_inventory_draft.md | 2026-10-07 |

---

## M1 — Signing, replay, secrets (P0) · Wave A · Phase 1A

| ID | Check | Result | Evidence | Date |
|---|---|---|---|---|
| M1-C1 | Server mint + machine message/body-hash/headers correct (empty body included). Client signer parity → DEFERRED-EHSAN after server verified | PASS (server) / DEFERRED-EHSAN (clients) | mint.py expected_signature; machine_auth body sha256 JSON | 2026-10-07 |
| M1-C2 | Mint-path signature compare is constant-time | PASS | mint.py:L111,L126; evidence 2026-10-07_1A_mint_compare_digest.md | 2026-10-07 |
| M1-C3 | Nonce insert atomic under concurrency; DB unreachable fails closed | PASS | UniqueViolation→401; mint_db connect fail→uncaught 500 (no token) | 2026-10-07 |
| M1-C4 | Purge age > replay window; prod schedule noted (Q4 if unknown) | PASS | purge min 5m > 60s window; prod cron UNKNOWN | 2026-10-07 |
| M1-C5 | Secret rotation / cache TTL; `CP_TENANT_SECRETS` not used on hosted | FAIL (M1-F02) | secrets_db TTL 60s + env fallback always wired | 2026-10-07 |
| M1-C6 | Secret encryption: algorithm, key location, rotation, who needs decrypt key | FAIL (M1-F01) | AES-GCM when keyed; optional plaintext path | 2026-10-07 |
| M1-C7 | Rate limits applied where intended (mint 120/240; machine 30/120); in-memory reset documented | PASS | app.py 120/240; machine_auth 30/120; process-local (restart clears) | 2026-10-07 |
| M1-H1 | Handoff: client signer contract written for Ehsan | PASS | HANDOFF_TO_EHSAN.md M1 section | 2026-10-07 |

**Unread done?** secrets_db / secret_crypto / mint rate / purge / encrypt scripts: done (Wave A)

---

## M5 — Tenant isolation, RLS, admin (P0) · Wave A · Phase 1B

| ID | Check | Result | Evidence | Date |
|---|---|---|---|---|
| M5-C1 | Portal queries scoped by verified token tenant, not body input | PASS | queries + routes use claims["sub"] / verified membership | 2026-10-07 |
| M5-C2 | RLS map: tables, FORCE, policies; DB role per service; BYPASSRLS justified | FAIL (M5-F02) | ENABLE OK 25 tables; no FORCE; postgres pooler role | 2026-10-07 |
| M5-C3 | Hosted detection; no auto-gen secrets in prod; `PORTAL_ALLOW_*` defaults | PASS | is_hosted; reveal default on / rotate off / bootstrap hosted off | 2026-10-07 |
| M5-C4 | Agent/prompt/greeting/page limits on machine HMAC routes too | FAIL (M5-F01) | machine create skips MAX_AGENTS | 2026-10-07 |
| M5-C5 | Admin: PBKDF2 iterations, TOTP window/replay (0031), disable (0032), audit on rotate | PASS | security.py 600k; auth TOTP consume; disable route; rotate_secret audits | 2026-10-07 |
| M5-C6 | Membership roles (0034/0035): who can see/do what | PASS | portal_access live role from DB; owner gates on mutate | 2026-10-07 |

**Scripts:** `rls_check.py` PASS · `verify_admin_boundary_live.py` not re-run this session (N/A deferred)

---

## M4 — Telephony control plane (P0) · Wave A · Phase 1C

| ID | Check | Result | Evidence | Date |
|---|---|---|---|---|
| M4-C1 | Webhook idempotent in **DB** (not only LRU); reconcile repairs documented | FAIL (M4-F02) | DB insert when call matched; unmatched skips durable row | 2026-10-07 |
| M4-C2 | Hosted never mock; never accept webhooks without public key | PASS (+ M4-F01 Medium residual) | assert_mock_switches_disabled; soft verify path remains | 2026-10-07 |
| M4-C3 | Webhook during Render sleep: what is lost / how recovers | FAIL (M4-F02) | in-memory signature/event sets lost; Telnyx retry + DB for matched | 2026-10-07 |
| M4-C4 | Outbound destination enforcement; 28-op bypass matrix; per-tenant caps | PASS (partial) | assert on create_outbound_call; sole dial entry; OVP allowlist | 2026-10-07 |
| M4-C5 | Credential encryption: alg, key, rotation; never logged/returned | PASS | telephony_credentials AES-GCM v2; key required | 2026-10-07 |
| M4-C6 | Per-tenant SIP/LiveKit isolation; call state machine | PASS (partial) | connections/lookups by tenant_id; deep FSM not fully enumerated | 2026-10-07 |
| M4-C7 | Telnyx/LiveKit HTTP client timeouts/retries | FAIL (M4-F03) | Telnyx timeout=10; LiveKit no explicit timeout | 2026-10-07 |
| M4-H1 | Handoff: telephony SDK no timeout → Ehsan | PASS | HANDOFF M4 note | 2026-10-07 |

**Unread done?** core telephony_service/webhooks/credentials/config sampled; full 28-op matrix not line-audited

---

## M2 — Sessions, quotas (server) (P0) · Wave A · Phase 1D

| ID | Check | Result | Evidence | Date |
|---|---|---|---|---|
| M2-C1 | Per-tenant/global concurrency limits (migrations/defaults) + user-visible errors | PASS (+ M2-F01 Info) | default max_concurrent=2; 429 concurrent cap; no global pool | 2026-10-07 |
| M2-C2 | Server slot lifecycle (mint/rollback/refresh/reconcile). Worker crash release → DEFERRED-EHSAN after read-only note | PASS / DEFERRED-EHSAN | mint +1; dispatch fail rollback; refresh no +1 | 2026-10-07 |
| M2-C3 | Dispatch failure detection when no worker / worker full | PASS | _watch_dispatch timeout → _rollback_dispatched_session | 2026-10-07 |
| M2-C4 | Refresh cap enforced every refresh; other duration bounds | PASS | MAX_REFRESHES=720; _enforce_refresh_gates hosted fail-closed | 2026-10-07 |
| M2-C5 | `reconcile_sessions.py` behavior on `concurrent_now` documented | PASS | closes stale; resets concurrent_now to true open count | 2026-10-07 |
| M2-H1 | Handoff: worker release / stale_jobs / crash scripts for Ehsan | PASS | HANDOFF M2 | 2026-10-07 |

---

## Wave A exit

| Gate | Result | Date |
|---|---|---|
| All M1/M5/M4/M2 Habiba checks classified (not TODO) | PASS | 2026-10-07 |
| P0 findings filed in FINDINGS_HABIBA.md | PASS | 2026-10-07 |
| `WAVE_A_AUDIT` signed in GATE_LOG | PASS | 2026-10-07 |

---

## Wave B — P0 remediate

| ID | Item | Result | Date |
|---|---|---|---|
| B-1 | All Critical M1/M4/M5/M2 fixed + retested | PASS (0 Critical) | 2026-10-07 |
| B-2 | All High fixed **or** dated risk acceptance in GATE_LOG | PASS (M5-F01/M11-F01 fixed; M5-F02 accepted) | 2026-10-07 |
| B-3 | pytest subset for touched modules green (commands logged) | PASS | 2026-10-07 |
| B-4 | Re-run rls/rate/admin scripts if those areas changed | N/A (no RLS/admin code change) | 2026-10-07 |
| B-5 | `WAVE_B_REMEDIATE` signed | PASS | 2026-10-07 |

---

## M8 — Resilience server (P1) · Wave C · Phase 3A

| ID | Check | Result | Evidence | Date |
|---|---|---|---|---|
| M8-C1 | Render services + plan limits listed (from dashboard) | FAIL (M8-F01 Info) | UNKNOWN — no Render UI; Docker UVA_ENV known | 2026-10-07 |
| M8-C2 | First request after idle: server response characterized (client UX → DEFERRED-EHSAN) | PASS / DEFERRED-EHSAN | pool warm + healthz; client timeouts → Ehsan | 2026-10-07 |
| M8-C3 | Every Habiba in-memory structure: break-on-restart + DB coverage | PASS | HABIBA_EVIDENCE/2026-10-07_C_volatile_state.md | 2026-10-07 |
| M8-C4 | Health endpoints; keep-alive hour burn risk noted | PASS | /healthz/warm can burn hours if polled always | 2026-10-07 |
| M8-C5 | DB pool/timeouts under restart (CP/portal/admin) | PASS | portal pool=4; mint_db singleton; connect_timeout 3–10s | 2026-10-07 |
| M8-H1 | Handoff: SDK/demo timeouts → Ehsan | PASS | HANDOFF M8 | 2026-10-07 |

---

## M11 — Dashboard read-only enforcement (P1) · Wave C · Phase 3B

| ID | Check | Result | Evidence | Date |
|---|---|---|---|---|
| M11-D0 | Product decision recorded (create forbidden; edits/reveal/telephony/studio ?) | PASS | GATE_LOG interim; edits undecided | 2026-10-07 |
| M11-C1 | Portal JWT routes that create/change agents (and related) vs decision | PASS | 2026-10-07_C_m11_route_matrix.md | 2026-10-07 |
| M11-C2 | Signed-in user cannot write agents via Supabase browser client (RLS) | PASS | 0002 SELECT-only; dashboard auth-only | 2026-10-07 |
| M11-C3 | Server rejects create even if API called directly (Habiba half) | PASS | M11-F01 fixed Wave B | 2026-10-07 |
| M11-C4 | Repeat for other actions once decision made | N/A | undecided → recorded allowed; M11-F02 Info | 2026-10-07 |
| M11-C5 | Server-side hygiene relevant to portal (not full UI XSS) | PASS | live membership enrich; owner gates | 2026-10-07 |
| M11-H1 | Visibility / UI / staleness → DEFERRED-EHSAN | DEFERRED-EHSAN | hide createAgent UI | 2026-10-07 |

---

## M7 — Secrets / PII / recordings server (P1) · Wave C · Phase 3C

| ID | Check | Result | Evidence | Date |
|---|---|---|---|---|
| M7-C1 | Server logs/errors never leak secrets/internal URLs; Sentry scrub posture | FAIL (M7-F01) | sentry init no before_send | 2026-10-07 |
| M7-C2 | Recording storage, signed URL lifetime, retention/purge (0028 + purge script) | FAIL (M7-F02) | TTL 1h OK; PURGE_APPLY dry-run default | 2026-10-07 |
| M7-C3 | PII at rest: telephony phones, transcripts (server paths) | PASS (partial) | tenant-scoped tables; purge clears transcript | 2026-10-07 |
| M7-C4 | Credential reveal/rotate flags enforced server-side | PASS | reveal default on; rotate default off | 2026-10-07 |
| M7-H1 | Laptop / worker `.env.local` / decrypt key on worker → DEFERRED-EHSAN | DEFERRED-EHSAN | HANDOFF | 2026-10-07 |

---

## M6 — Save-time tools only (P1) · Wave C · Phase 3D

| ID | Check | Result | Evidence | Date |
|---|---|---|---|---|
| M6-C1 | `runtime_env.is_hosted` behavior documented (Habiba file) | PASS | runtime_env.py UVA_ENV/RENDER/ENVIRONMENT | 2026-10-07 |
| M6-C2 | `tools_webhook.py` save-time validation of tools URL/secret | PASS | https hosted; block metadata/private | 2026-10-07 |
| M6-C3 | Gap list vs request-time guard (read-only) → handoff if mismatch | PASS | worker pins IP; save-time cannot defeat rebind | 2026-10-07 |
| M6-H1 | Worker SSRF / host-tools / injection / tool loops → DEFERRED-EHSAN | DEFERRED-EHSAN | HANDOFF | 2026-10-07 |

---

## Wave C / D exits

| Gate | Result | Date |
|---|---|---|
| `WAVE_C_AUDIT` signed | PASS | 2026-10-07 |
| Critical/High from Wave C fixed + retested (`WAVE_D_REMEDIATE`) | N/A (0 Crit/High from Wave C) | 2026-10-07 |

---

## M12 — Python tests & observability (P2) · Wave E

| ID | Check | Result | Evidence | Date |
|---|---|---|---|---|
| M12-C1 | Inventory Python tests for M1–M5 (and Habiba P1); gaps listed | PASS | HABIBA_EVIDENCE/2026-10-07_0_test_inventory_draft.md | 2026-10-07 |
| M12-C2 | Smallest useful tests added where Wave B/D left Critical holes | PASS | machine limit + portal create 403 + sentry_scrub | 2026-10-07 |
| M12-C3 | Minimum log fields decided (tenant_id, session/room, reason) | PASS | Prefer: tenant_id, room/agent_id, reason/status; never secrets | 2026-10-07 |

---

## End-to-end verification matrix (Habiba)

| # | Capability | Result | Evidence | Date |
|---|---|---|---|---|
| V1 | Mint HMAC reject bad sig / replay / skew | PASS | tests/test_mint.py (+ mint.py compare_digest) | 2026-10-07 |
| V2 | Machine HMAC reject bad sig / replay | PASS | tests/test_machine_agent_api.py | 2026-10-07 |
| V3 | Cross-tenant agent mint blocked | PASS | mint agent ownership check; machine cross-tenant test | 2026-10-07 |
| V4 | Cross-tenant portal list/read blocked | PASS | claims[sub] scoping; portal_access membership | 2026-10-07 |
| V5 | Privileged DB role + RLS limits documented | PASS | M5-F02 accepted; rls_check ENABLE | 2026-10-07 |
| V6 | Admin login throttle + rotate audited | PASS | admin auth TOTP + rotate_secret audit | 2026-10-07 |
| V7 | Telnyx webhook rejects bad signature | PASS | telephony_webhooks verify; real_provider tests | 2026-10-07 |
| V8 | Webhook duplicate event safe in DB | PARTIAL | matched path OK; unmatched = M4-F02 | 2026-10-07 |
| V9 | Mock telephony disabled when hosted | PASS | assert_mock_switches_disabled + M4-F01 fix | 2026-10-07 |
| V10 | Outbound destination policy enforced | PASS | assert_outbound_destination_allowed | 2026-10-07 |
| V11 | Quota increment + dispatch rollback | PASS | mint + _watch_dispatch rollback | 2026-10-07 |
| V12 | Refresh cap via JWT metadata | PASS | MAX_REFRESHES + refresh_count | 2026-10-07 |
| V13 | Portal agent-create matches M11 decision | PASS | 403 default; test_portal_create_agent_forbidden | 2026-10-07 |
| V14 | Recording URL / retention / purge coherent | PARTIAL | TTL 1h; purge script; PURGE_APPLY ops M7-F02 | 2026-10-07 |
| V15 | tools_base_url rejected if unsafe at save-time | PASS | tools_webhook.py hosted https/SSRF rules | 2026-10-07 |
| V16 | In-memory loss documented; DB truth for money/auth | PASS | 2026-10-07_C_volatile_state.md | 2026-10-07 |

---

## Final Habiba gate

| # | Criterion | Result | Date |
|---|---|---|---|
| F1 | Waves A–D PASS in GATE_LOG | PASS | 2026-10-07 |
| F2 | No open Critical | PASS | 2026-10-07 |
| F3 | No open High without dated acceptance | PASS (M5-F02 accepted → 2026-12-31) | 2026-10-07 |
| F4 | V1–V16 filled | PASS | 2026-10-07 |
| F5 | HANDOFF_TO_EHSAN.md complete | PASS | 2026-10-07 |
| F6 | Migration apply/rollback notes if any Habiba migrations | N/A (no new migrations this audit) | 2026-10-07 |
| F7 | No secrets in evidence/git | PASS (URL user only; no passwords) | 2026-10-07 |
| F8 | `HABIBA_BACKEND_FINAL` signed | PASS | 2026-10-07 |
