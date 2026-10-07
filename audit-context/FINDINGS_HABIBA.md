# Findings — Habiba (backend gatekeepers)

**Owner:** Habiba (executed by audit agent)  
**Plan:** `HABIBA_IMPLEMENTATION_PLAN.md`  
**Date started:** 2026-10-07  

**Severity:** Critical · High · Medium · Low · Info  
**Status:** `open` | `in progress` | `fixed` | `won't fix` | `deferred-ehsan`

---

## Index

| ID | Module | Severity | Status | One-line |
|---|---|---|---|---|
| M5-F01 | M5 | High | fixed | Machine `POST /machine/agents` skips `MAX_AGENTS_PER_TENANT` |
| M5-F02 | M5 | High | won't fix (accepted) | Service DB role bypasses RLS; isolation is app-layer only (no FORCE RLS) |
| M11-F01 | M11 | High | fixed | `POST /portal/agents` still creates agents for owner JWT (conflicts with read-only create ban) |
| M4-F01 | M4 | Medium | fixed | Webhook verify still soft-accepts mock+no-key (hosted blocked at portal startup) |
| M1-F01 | M1 | Medium | fixed | Tenant secret encryption optional; plaintext column still usable when key unset |
| M1-F02 | M1 | Medium | fixed | On DB lookup failure, mint falls back to `CP_TENANT_SECRETS` env map (incl. hosted) |
| M4-F02 | M4 | Medium | fixed | Webhook with no matched call skips durable event insert; side effects may still run |
| M4-F03 | M4 | Low | fixed | LiveKit SIP client calls have no explicit HTTP timeout in wrapper |
| M2-F01 | M2 | Info | deferred-ops | Default `max_concurrent=2` per tenant (schema); no global pool constant |
| M7-F01 | M7 | Medium | fixed | Sentry init has no `before_send` scrub for secrets/headers |
| M7-F02 | M7 | Medium | fixed | Session-media purge GitHub Action defaults to dry-run (`PURGE_APPLY` opt-in) |
| M8-F01 | M8 | Info | deferred-ops | Render plan / idle sleep limits UNKNOWN (no dashboard access) |
| M11-F02 | M11 | Info | fixed | Telephony RLS allows authenticated INSERT/UPDATE — dashboard uses portal API only today |

---

## Findings

```
ID:           M5-F01
Module:       M5
Severity:     High
Where:        tenant_portal_api/app.py:L1107-L1158 vs L683-L699
What:         Portal create enforces MAX_AGENTS_PER_TENANT (default 100); machine HMAC create calls queries.create_agent with no count check.
Impact:       Authenticated host with HMAC can create unbounded agents (resource / cost / DoS against tenant row volume).
How verified: read code
Evidence:     audit-context/HABIBA_EVIDENCE/2026-10-07_1B_machine_agent_limit.md
Suggested fix: Apply the same count gate (and archive-aware count if required) inside machine_create_agent_route before insert.
Retest:       tests/test_machine_agent_api.py::test_create_agent_enforces_max_agents_per_tenant
Status:       fixed
Wave:         B
```

```
ID:           M4-F01
Module:       M4
Severity:     Medium
Where:        tenant_portal_api/telephony_webhooks.py:L159-L160; mitigated by telephony_routes.py:L68-L92
What:         verify_telnyx_webhook_signature returns True when mock mode and no TELNYX_PUBLIC_KEY. Hosted portal refuses start if TELEPHONY_PROVIDER_MODE != real (assert_mock_switches_disabled), so primary exploit path is blocked — residual is defense-in-depth / alternate entrypoints.
Impact:       Local/test and any process that mounts webhook router without the assert can accept unsigned webhooks.
How verified: read code; tests/test_wave2_gate1.py covers assert
Suggested fix: In verify_telnyx_webhook_signature, if is_hosted() return False unless real signature verifies; keep startup assert.
Retest:       verify path now returns False when is_hosted() + mock + no key
Status:       fixed
Wave:         B
```
```
ID:           M4-F03
Module:       M4
Severity:     Low
Where:        tenant_portal_api/livekit_sip.py (LiveKitAPI usages); contrast telnyx_client.py timeout=10.0
What:         LiveKit SIP wrapper constructs LiveKitAPI without an explicit request timeout; Telnyx client defaults to 10s.
Impact:       Hung LiveKit control-plane calls can stall telephony threads under provider outage.
How verified: read code
Suggested fix: Pass timeout to LiveKitAPI / wrap awaits with asyncio.wait_for.
Retest:       tests/test_livekit_sip_timeout.py; LiveKitSipClient._livekit_api timeout
Status:       fixed
Wave:         backlog
```

```
ID:           M5-F02
Module:       M5
Severity:     High
Where:        scripts/dbconn.py:L30-L50; supabase/migrations/0002_rls.sql:L1-L6; (no FORCE ROW LEVEL SECURITY in migrations/)
What:         CP/portal/admin connect via SUPABASE_DB_URL as DB user (default username postgres). RLS policies target authenticated JWT role. Table owner bypasses RLS; FORCE RLS not enabled. Isolation for service paths is application WHERE tenant_id only.
Impact:       Any bug that omits tenant_id in a service query is a cross-tenant read/write; RLS will not catch it. Meets neither OWASP multi-tenant “FORCE RLS + non-BYPASSRLS app role” ideal.
How verified: read code; rls_check.py PASS (ENABLE only); rg FORCE ROW LEVEL SECURITY → none
Suggested fix: Document as accepted architecture OR introduce least-privilege DB role + FORCE RLS for browser paths; keep mandatory tenant filters + tests for every service query.
Retest:       Risk accepted in HABIBA_GATE_LOG Wave B (expiry 2026-12-31)
Status:       won't fix (accepted)
Wave:         B
```

```
ID:           M11-F01
Module:       M11
Severity:     High
Where:        tenant_portal_api/app.py:L683-L726
What:         Under Habiba interim decision (dashboard must not create agents), portal still exposes POST /portal/agents for owner JWT and creates rows.
Impact:       Any client holding a portal owner session (dashboard or crafted request) can create agents server-side; UI hiding alone is insufficient.
How verified: read code; interim decision in HABIBA_GATE_LOG.md
Suggested fix: Disable or 403 portal create (and optionally update) per product decision; keep machine HMAC create for SDK path.
Retest:       tests/test_phase4_portal_api.py::test_portal_create_agent_forbidden_by_default
Status:       fixed
Wave:         B
```

```
ID:           M1-F01
Module:       M1
Severity:     Medium
Where:        control_plane/secret_crypto.py:L49-L55, L67-L71; secrets_db.py:L94-L101
What:         Encryption is inactive when TENANT_SECRET_ENCRYPTION_KEY unset; encrypt_tenant_secret returns None; DB may still store/use plaintext hmac_secret (warns if key present).
Impact:       Hosted deploy without key leaves signing secrets recoverable from DB dumps.
How verified: read code
Suggested fix: Hosted fail-closed: require encryption key + refuse plaintext when is_hosted(); ops run encrypt_tenant_secrets.py --finalize.
Retest:       CP + portal raise RuntimeError on hosted without TENANT_SECRET_ENCRYPTION_KEY
Status:       fixed
Wave:         backlog
```

```
ID:           M1-F02
Module:       M1
Severity:     Medium
Where:        control_plane/secrets_db.py:L105-L119; app.py:L330
What:         DbSecretProvider always constructed with EnvSecretProvider fallback. DB errors log warning then serve CP_TENANT_SECRETS.
Impact:       Hosted outage or ACL mistake can authenticate against a static env map that may be stale or broader than intended.
How verified: read code
Suggested fix: When is_hosted(), disable env fallback (or require empty CP_TENANT_SECRETS); fail closed on DB errors.
Retest:       secrets_db.py hosted DB-error path returns None (no env fallback)
Status:       fixed
Wave:         B
```

```
ID:           M4-F02
Module:       M4
Severity:     Medium
Where:        tenant_portal_api/telephony_webhooks.py:L299-L357, L425-L427
What:         Durable insert into telephony_call_events only when a telephony_calls row matches. If unmatched, code skips insert, still may apply side effects; in-memory event-id set is the only dedupe for that path until restart.
Impact:       After process restart, unmatched or racey events can be re-processed; incomplete DB idempotency vs plan goal.
How verified: read code; unique index idx_telephony_call_events_tenant_event_id exists (0014)
Suggested fix: Always persist provider_event_id (inbox table) before side effects; apply effects only after durable claim.
Retest:       migration 0038 + telephony_webhooks claim-before-effects
Status:       fixed
Wave:         backlog
```

```
ID:           M2-F01
Module:       M2
Severity:     Info
Where:        supabase/migrations/0001_schema.sql:L28; control_plane/mint.py:L190-L191
What:         Per-tenant default max_concurrent is 2; mint returns 429 concurrent cap reached. No separate global concurrency constant in CP.
Impact:       Capacity planning must use sum of tenant caps + worker limits (Ehsan); document for load tests.
How verified: read code
Suggested fix: Document in ops runbook; optional global gate later.
Retest:       Documented in HANDOFF / START_HERE (capacity = sum of tenant caps)
Status:       deferred-ops
Wave:         backlog
```

```
ID:           M7-F01
Module:       M7
Severity:     Medium
Where:        control_plane/app.py:L131-L137 (sentry_sdk.init); portal/admin similar if any
What:         Sentry initialized with DSN + traces_sample_rate only — no before_send / event scrubber for Authorization, hmac_secret, cookies, or raw bodies.
Impact:       Exception contexts or breadcrumbs can ship signing secrets / JWTs to Sentry.
How verified: read code
Suggested fix: Add deny-list scrubber (headers Authorization/Cookie/X-Signature; keys *secret*, *password*, *token*).
Retest:       tests/test_sentry_scrub.py
Status:       fixed
Wave:         D
```

```
ID:           M7-F02
Module:       M7
Severity:     Medium
Where:        .github/workflows/purge-session-media.yml; scripts/purge_expired_session_media.py
What:         Scheduled purge exists (daily 03:30 UTC) but defaults to dry-run unless repo variable PURGE_APPLY=true.
Impact:       Retention columns may be set while Storage objects and transcripts remain forever in production if ops never flipped the flag.
How verified: read workflow comments + script
Suggested fix: Confirm hosted PURGE_APPLY; document in runbook; alert if dry-run-only for >N days.
Retest:       --fail-if-pending on scheduled dry-run; ops still sets PURGE_APPLY to delete
Status:       fixed
Wave:         backlog
```

```
ID:           M8-F01
Module:       M8
Severity:     Info
Where:        Render dashboard (not accessible this session); healthz/warm in CP
What:         Cannot list Render instance type / spin-down idle minutes from code alone.
Impact:       Cold-start SLO and keep-alive cost unknown.
How verified: code-only; Docker UVA_ENV known
Suggested fix: Paste plan limits into GATE_LOG when dashboard available.
Retest:       Needs Render UI access — leave for ops
Status:       deferred-ops
Wave:         backlog
```

```
ID:           M11-F02
Module:       M11
Severity:     Info
Where:        supabase/migrations/0015_telephony_rls_grants.sql
What:         authenticated role has INSERT/UPDATE policies on telephony tables (tenant-scoped). agents remain SELECT-only.
Impact:       A future browser PostgREST client could mutate telephony without portal audit/authz layers. Current dashboard uses auth + portal API only.
How verified: read migrations; dashboard grep (auth only)
Suggested fix: Prefer revoke write grants from authenticated for telephony; keep portal service path. Ehsan: never add .from() writes.
Retest:       migration 0037 drops write policies + revoke insert/update/delete
Status:       fixed
Wave:         backlog
```

---

## PASS notes (not findings)

| Check | Result | Evidence |
|---|---|---|
| M1 mint signature compare constant-time | PASS | `control_plane/mint.py:L109-L111`, `L126` `hmac.compare_digest` |
| M1 machine compare_digest | PASS | `tenant_portal_api/machine_auth.py:L160` |
| M1 purge age ≥ 5 min > 60s replay | PASS | `scripts/purge_used_nonces.py:L95-L97` |
| M1 AES-GCM + HKDF for tenant secrets when keyed | PASS | `control_plane/secret_crypto.py:L58-L77` |
| RLS ENABLE on public tables (live DB) | PASS | `HABIBA_EVIDENCE/2026-10-07_0_rls_check.txt` — 25 tables OK |
| Admin PBKDF2 iterations | PASS | `admin/security.py:L24` = 600_000 (OWASP 2023 floor) |
| Outbound dial checks destinations | PASS (partial) | `telephony_service.py:L1111` `assert_outbound_destination_allowed` on create outbound path |
| Docker UVA_ENV=production | PASS (CP/portal/admin) | `docker/control-plane.Dockerfile:L30`, `tenant-portal-api.Dockerfile:L24`, `admin.Dockerfile:L35` |
| M11 portal create forbidden | PASS | `POST /portal/agents` 403; evidence `2026-10-07_C_m11_route_matrix.md` |
| M11 agents RLS no write | PASS | `0002_rls.sql` SELECT-only policy + grants |
| M6 save-time tools URL | PASS | `tools_webhook.py` https + private/metadata deny when hosted |
| M6 request-time SSRF (worker) | PASS (read-only) | `worker/ssrf_guard.py` pin; handoff DNS rebind residual |
| M7 recording signed URLs | PASS | `recording_urls.py` TTL 1h; path not returned to clients |
| M8 health endpoints | PASS | CP `/healthz`, `/healthz/deep`, `/healthz/warm`; portal `/healthz` |
