# Hamza Agent-Facing Telephony Implementation Plan

Status: final.

Source of truth:

- `docs/.codexrules`
- `docs/HAMZA_TELEPHONY_IMPLEMENTATION_WORKFLOW.md`
- `docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md`
- `docs/TELEPHONY_WORKLOAD_AND_RESPONSIBILITY_DIVISION.md`
- `docs/TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md`
- `docs/HABIBA_TELEPHONY_IMPLEMENTATION_WORKFLOW.md`
- `docs/UKASHA_MULTIPLE_PROVIDERS_GUIDE.md`

This plan is for a coding agent implementing Hamza's telephony backend work. It converts Hamza's workflow into implementation phases with subphases, tests, human tasks, manual verification gates, and a scope audit. If this plan conflicts with `docs/.codexrules` or the frozen telephony contract, stop and ask before writing code.

## Agent Rules

- Re-read `docs/.codexrules` before implementation and every 5 to 10 messages.
- Inspect current code, migrations, manifests, tests, branch, and dirty worktree before edits.
- For any task touching more than two files, present the exact file plan and wait for Hamza or project-owner approval.
- Make the smallest scoped backend change for the current phase.
- Do not apply Supabase migrations or change the live Supabase project.
- Do not implement `@awaazlabs-uva/telephony`; that is Habiba-owned.
- Do not modify dashboard files in this workflow.
- Keep `worker/main.py` changes minimal and do not fork the STT/LLM/TTS pipeline.
- Do not choose STT, LLM, TTS, language, model, or voice independently; consume Ukasha's final provider runtime config.
- Do not create LiveKit trunks or SIP dispatch rules per call.
- Do not trust caller-controlled metadata for tenant, client, agent, routing, or authorization decisions.
- Do not expose Telnyx API keys, HMAC secrets, LiveKit secrets, Supabase credentials, raw provider payloads, stack traces, or unrestricted errors to clients.
- Use fake Telnyx/LiveKit adapters by default; real provider tests require explicit human approval.
- Do not add dependencies without verifying existing manifests and getting approval. Prefer existing `httpx==0.28.1` unless a Telnyx SDK is deliberately chosen.
Do not modify `control_plane/app.py` except for an approved shared LiveKit dispatch helper extraction; telephony must not call or depend on browser `/v1/session`.
- Run verification after each phase and fix failures before moving forward.

## Phase 0 - Recon, Branch Safety, And Approval Gate

Purpose: verify current repo state and contract readiness before backend implementation.

Subphases:

1. Read the source docs listed above.
2. Confirm `docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md` is the shared contract Habiba is following.
3. Inspect current branch, `git status -sb`, package manifests, test layout, tenant portal API modules, worker modules, and existing HMAC/auth patterns.
4. Inspect current backend references: `tenant_portal_api/app.py`, `tenant_portal_api/auth.py`, `tenant_portal_api/machine_auth.py`, `tenant_portal_api/queries.py`, `control_plane/app.py`, `worker/main.py`, `worker/config.py`, and `worker/usage.py`.
5. Inspect existing tests: `tests/test_machine_agent_api.py`, `tests/test_host_backend_contract.py`, `tests/test_phase4_portal_api.py`, `tests/test_mint.py`, `tests/test_worker.py`, and `tests/conftest.py`.

Tests/checks:

- No implementation tests yet.
- `rg` checks for dashboard out-of-scope wording, backend route paths, action strings, table names, and Hamza/Habiba ownership boundaries.

Human tasks:

- Hamza approves this implementation plan.
- Hamza confirms work happens on `hamza` branch or an approved child branch.
- Habiba confirms she owns migrations/RLS/SDK and will provide applied-schema availability when ready.
- Ukasha confirms provider/language work boundary and worker-runtime config expectations.

Manual verification:

- Human checks no live Supabase operation is planned.
- Human checks no dashboard files or SDK package files are in the first edit plan.
- Human confirms real Telnyx/LiveKit tests are disabled by default.

Exit criteria:

- Plan approved.
- Contract acknowledged.
- No implementation edits made before approval.

## Phase 1 - Contract Freeze And Backend Decisions

Purpose: remove ambiguity before provider adapters, routes, repositories, and worker hooks depend on shared surfaces.

Subphases:

1. Verify table names, required fields, row locks, status values, error codes, route paths, request/response shapes, and machine HMAC action strings against the contract doc.
2. If both developers approve and the team asks for the edit, change contract status from `proposed freeze` to `frozen`.
3. Confirm Hamza-owned live-provider blockers:
   - exact LiveKit SIP APIs and whether `livekit-api==1.2.0` is sufficient
   - exact LiveKit SIP participant attributes: `sip.callID`, `sip.callIDFull`, `sip.trunkPhoneNumber`, `sip.trunkID`, `sip.ruleID`
   - exact Telnyx APIs for key verification, inventory, exact search, optional reservation, exact orders, order status, pricing, SIP/FQDN connection, Outbound Voice Profile, and webhooks
   - first-release countries, number types, features, and destination policies
   - SIP verification test required before marking routing active
4. Record unresolved items as blockers or fake-provider-only assumptions.

Tests/checks:

- Contract checklist for route/action/status/error/table coverage.
- No live provider tests.

Human tasks:

- Hamza signs off route list, request/response fields, statuses, errors, repository/query functions, row locks, provider verification notes, and fake fixtures.
- Habiba signs off DB/SDK compatibility and migration/SDK fixture needs.
- Ukasha signs off that telephony consumes runtime config and does not own provider selection.

Manual verification:

- Human compares Hamza plan, Habiba plan, and shared contract for mismatches.
- Human confirms unresolved provider details do not block fake-provider backend scaffolding.

Exit criteria:

- Contract is frozen or explicitly approved as the implementation contract.
- Live-provider unknowns are documented as gated items.

## Phase 2 - Backend Module Scaffold, Statuses, And Errors

Purpose: create the backend telephony structure with no provider side effects during import.

Subphases:

1. Create backend module plan for:
   - `tenant_portal_api/telephony_models.py`
   - `tenant_portal_api/telephony_status.py`
   - `tenant_portal_api/telephony_errors.py`
   - `tenant_portal_api/telephony_queries.py`
   - `tenant_portal_api/telephony_service.py`
   - `tenant_portal_api/telnyx_client.py`
   - `tenant_portal_api/livekit_sip.py`
   - `tenant_portal_api/telephony_routes.py`
   - `tenant_portal_api/telephony_webhooks.py`
   - `tenant_portal_api/telephony_reconcile.py`
   - `tenant_portal_api/telephony_health.py`
   - `worker/telephony_runtime.py`
   - `scripts/reconcile_telephony.py`
2. Add status enum and transition utilities for public call statuses, resource platform statuses, provider statuses, and internal stages.
3. Add stable platform error types and HTTP mapping with redacted client responses.
4. Keep internal stages in `telephony_call_events.internal_stage`, not public call status.
5. Do not register routes until import and model tests pass.

Tests/checks:

- Import smoke tests for all new modules.
- Error-code serialization tests.
- Status transition tests for inbound and outbound calls.
- Stale update rejection tests.
- Redaction tests proving raw provider payloads and secrets are not in public errors.
- Regression smoke for existing `tenant_portal_api.app` import.

Human tasks:

- Hamza approves module boundaries and any dependency change.
- Habiba reviews status/error names for SDK mapping compatibility.

Manual verification:

- Human checks modules have no network/provider side effects during import.
- Human confirms no dashboard, SDK, or migration file is touched.

Exit criteria:

- Backend scaffold is importable, testable, and aligned with the frozen contract.

## Phase 3 - Database Contract And Repository Layer

Purpose: define and implement Hamza's backend query/repository contract while leaving migrations, RLS, indexes, and live Supabase deployment to Habiba.

Subphases:

1. Define repository functions in `tenant_portal_api/telephony_queries.py` for Telnyx connections, numbers, orders, SIP resources, LiveKit resources, call records, idempotency keys, call events, quota, and reconciliation scans.
2. Build against fake repository fixtures first if Habiba's migrations are not available.
3. Use parameterized SQL only; no string-interpolated SQL.
4. Use DB transactions and row locks for idempotency rows, phone-number assignment/reassignment, inbound SIP resolution, outbound call creation, quota reservation, call status transitions, exactly-once quota release, and exactly-once usage recording.
5. Do not apply migrations, alter live schema, or bypass Habiba's Supabase ownership.
6. Respect first-release guardrails: do not extend `usage_events.kind`; store telephony call duration/status on `telephony_calls`; treat `external_customer_ref` and `external_workflow_ref` as opaque strings; do not create tenant-scoped `telephony_calls` when inbound tenant resolution fails.
7. Cover the exact repository/query function checklist from Hamza's workflow:
   - `get_active_telnyx_connection(tenant_id)`
   - `upsert_telnyx_connection_verifying(...)`
   - `mark_telnyx_connection_active(...)`
   - `rotate_telnyx_connection_key(...)`
   - `disconnect_telnyx_connection(...)`
   - `list_telnyx_owned_number_snapshots(tenant_id)`
   - `list_managed_numbers(tenant_id, filters)`
   - `import_owned_number(...)`
   - `record_number_sync_result(...)`
   - `record_number_drift(...)`
   - `create_number_order_idempotently(...)`
   - `update_number_order_status(...)`
   - `sync_purchased_number(...)`
   - `get_or_create_tenant_sip_connection(...)`
   - `update_sip_connection_status(...)`
   - `get_or_create_outbound_voice_profile(...)`
   - `update_outbound_voice_profile_status(...)`
   - `get_or_create_inbound_trunk_record(...)`
   - `get_or_create_outbound_trunk_record(...)`
   - `get_or_create_sip_dispatch_rule_record(...)`
   - `configure_number_routing_transaction(...)`
   - `assign_number_to_agent(...)`
   - `resolve_inbound_call_by_sip_attributes(...)`
   - `create_or_link_inbound_call_and_session(...)`
   - `create_outbound_call_idempotently(...)`
   - `reserve_call_quota(...)`
   - `release_call_quota_once(...)`
   - `record_call_usage_once(...)`
   - `transition_call_status(...)`
   - `insert_call_event(...)`
   - `dedupe_webhook_event(...)`
   - `reconcile_stale_calls(...)`.

Tests/checks:

- Repository contract tests with fake DB fixtures before migrations land.
- Real local/staging schema tests only after Habiba migrations are applied.
- Row-lock/race tests for assignment, inbound resolution, outbound creation, quota reservation, and idempotency.
- Cross-tenant mismatch tests that return stable not-found/unauthorized behavior without leaking ownership.
- Status transition tests at repository layer.

Human tasks:

- Hamza provides Habiba the exact required fields, indexes, tenant-scoped FKs, partial unique constraints, row locks, and transaction expectations.
- Habiba confirms schema availability and whether transitions are DB-enforced, app-enforced, or both.

Manual verification:

- Human checks no migration file was created or applied by Hamza.
- Human checks repository SQL does not use `SELECT *` or string interpolation.

Exit criteria:

- Hamza can run fake repository tests before migrations exist.
- Once Habiba migrations exist, repository tests pass against the agreed schema without Hamza needing Supabase project access.

## Phase 4 - Telnyx API Adapter And Credential Lifecycle

Purpose: build backend-only Telnyx integration for tenant account verification and credential lifecycle.

Subphases:

1. Implement `tenant_portal_api/telnyx_client.py` with typed functions and fake HTTP/provider support by default.
2. Verify tenant Telnyx API keys, account readiness, permissions, owned inventory, exact search, optional reservation, exact order purchase/status, SIP/FQDN connection, and Outbound Voice Profile APIs according to confirmed Telnyx docs/API behavior.
3. Implement credential lifecycle in the service layer: connect, rotate, reverify, disconnect, disabled, compromised, permission failed, and active states.
4. Raw Telnyx API keys may enter only trusted backend routes or backend-only SDK calls during connect/rotate.
5. Never log, return, cache, store in fixtures, store in SDK state, or place raw Telnyx API keys in browser/dashboard code.
6. Persist only encrypted secret reference/ciphertext through Habiba's agreed schema and encryption mechanism.
7. Adapter must not write DB rows directly; service/repository layer persists typed results.

Tests/checks:

- Fake HTTP success/failure tests.
- Key verification success, invalid key, unauthorized key, permission failure, compromised key, timeout, rate limit, and malformed provider response tests.
- Credential rotation and disconnect service tests.
- Redaction tests for logs, errors, fixtures, and public responses.
- No-network default test guard.

Human tasks:

- Hamza confirms whether existing `httpx==0.28.1` is sufficient or a pinned Telnyx SDK is required.
- Habiba confirms encryption storage fields or secret-store reference.
- Human approves any real Telnyx account verification test.

Manual verification:

- Human confirms no real Telnyx key appears in logs, docs, fixtures, env examples, or commits.
- Human confirms real provider test files are skipped unless explicitly enabled.

Exit criteria:

- Telnyx adapter and credential lifecycle work with fake providers and redacted responses.

## Phase 5 - Number Inventory, Search, Reservation, Purchase, And Orders

Purpose: implement number inventory and exact-number acquisition flows through the backend service.

Subphases:

1. Implement Telnyx-owned inventory listing and AwaazLabs-managed inventory listing.
2. Implement import, sync, drift detection, exact available-number search, optional reservation, exact selected-number purchase, order status, and assignment/disable service paths.
3. Purchase only the exact selected E.164 number returned by search or verified by the backend; never purchase from broad country/area-code criteria alone.
4. Treat number reservation as optional by provider/market; unsupported cases return stable unsupported/action-required behavior.
5. Separate `provider_status`, `platform_status`, raw provider status, restricted provider error payload, stable `error_code`, and redacted `error_message`.
6. Enforce idempotency for number purchases before provider side effects.

Tests/checks:

- Inventory list/import/sync/drift tests with fake Telnyx responses.
- Exact search result tests and broad purchase rejection tests.
- Optional reservation supported/unsupported tests.
- Exact purchase idempotency tests.
- Number-order status normalization tests.
- Stale provider events must not move order/platform status backward.
- Assignment/unassignment validation tests.
- Cross-tenant number/agent assignment rejection tests.
- Partial purchase success plus routing setup failure recovery tests.

Human tasks:

- Hamza confirms first-release countries, number types, features, pricing fields, regulatory handling, and reservation support.
- Habiba confirms number/order schema supports backend state needs.

Manual verification:

- Human checks fake fixtures do not contain real phone numbers unless explicitly approved.
- Human approves any live Telnyx number search/order test because it may touch paid/provider resources.

Exit criteria:

- Number flows work with fake providers, stable statuses, and safe idempotency behavior.

## Phase 6 - Telnyx SIP/FQDN Connection And Outbound Voice Profile

Purpose: implement tenant SIP readiness and outbound readiness without exposing unnecessary raw Telnyx configuration.

Subphases:

1. Implement Telnyx SIP/FQDN upsert, verification/test, status normalization, and degraded/failed states.
2. Implement Telnyx Outbound Voice Profile upsert/select/associate/reverify/readiness behavior.
3. Require active tenant Telnyx connection before SIP/Profile operations.
4. Require active SIP connection and active Outbound Voice Profile before outbound readiness.
5. Store only SDK/future-portal-safe policy summaries and restricted diagnostics.
6. Do not mark routing ready solely because a database row exists; readiness must reflect provider checks and required LiveKit resources.

Tests/checks:

- SIP creation/update/verification fake-provider tests.
- SIP verification failure and action-required tests.
- Outbound Voice Profile create/select/reverify tests.
- Destination restriction, limit reached, verification required, and failed/degraded tests.
- Readiness response redaction tests.

Human tasks:

- Hamza confirms exact Telnyx SIP/FQDN and Outbound Voice Profile APIs, limits, destination policies, and SIP/Profile association behavior.
- Habiba confirms schema fields for SIP secrets, provider IDs, policy summaries, and statuses.

Manual verification:

- Human approves any real SIP or Outbound Voice Profile provider test.
- Human verifies SIP secrets and policy details are not returned to clients.

Exit criteria:

- SIP and outbound readiness services are fake-provider covered and SDK-safe.

## Phase 7 - LiveKit SIP Adapter, Trunks, And Dispatch Rules

Purpose: implement long-lived LiveKit SIP resources and routing orchestration using reusable resources.

Subphases:

1. Implement `tenant_portal_api/livekit_sip.py` with fake adapter support by default.
2. Confirm installed/deployed LiveKit SIP APIs for inbound trunks, outbound trunks, dispatch rules, SIP participants/calls, and agent dispatch.
3. Configure/repair one long-lived inbound trunk and one SIP dispatch rule per phone number where deterministic routing is required.
4. Configure/repair one reusable outbound trunk per active Telnyx connection/Profile path.
5. Do not create LiveKit trunks or SIP dispatch rules per call.
6. Store LiveKit provider IDs only on `livekit_inbound_trunks`, `livekit_outbound_trunks`, and `livekit_sip_dispatch_rules`; `telephony_calls` stores internal references and call-correlation IDs.
7. Do not trust LiveKit or caller metadata for tenant identity without resolving through AwaazLabs-owned DB records.

Tests/checks:

- Fake LiveKit trunk/rule create/update/list/get tests.
- Trunk/rule reuse tests proving no per-call resource creation.
- Provider-ID ownership tests.
- Routing repair tests.
- LiveKit API failure, timeout, and malformed response tests.
- Readiness/degraded response tests.

Human tasks:

- Hamza confirms exact LiveKit SIP API behavior and participant attributes.
- Habiba confirms LiveKit resource schema and indexes.
- Human approves any real LiveKit SIP test.

Manual verification:

- Human checks route/service code never creates trunks/rules inside call-creation code paths.

Exit criteria:

- Long-lived LiveKit SIP resource management is fake-adapter covered and contract-aligned.

## Phase 8 - Portal And Machine Telephony API Routes

Purpose: expose telephony through the existing tenant portal API deployment so portal consumers and `@awaazlabs-uva/telephony` use the same backend service.

Subphases:

1. Implement `tenant_portal_api/telephony_routes.py` with thin route handlers that delegate to service functions.
2. Register routes in `tenant_portal_api/app.py` only after route/model tests pass.
3. Add portal JWT routes under `/portal/telephony/*` and machine HMAC routes under `/machine/telephony/*` according to the frozen contract.
4. Machine action strings must be fixed per route and never client-supplied.
5. For machine routes, GET requests with no parameters sign `{}`; filtered/list/search operations must use signed JSON bodies or explicitly body-bound routes, not unsigned query params.
6. Add webhook route only after signature behavior and public URL decisions are confirmed.
7. If `DELETE` is used, update CORS method support only as needed.

Tests/checks:

- Route registration smoke tests.
- Portal JWT auth tests for tenant-scoped access.
- Machine HMAC tests for every `/machine/telephony/*` action, including bad signature, nonce replay, timestamp skew, wrong action, and tampered body.
- Response shape tests matching Habiba SDK contract fixtures.
- Existing `/portal/agents`, `/machine/agents`, and `/v1/session` regressions.

Human tasks:

- Hamza confirms final route/action mapping.
- Habiba confirms machine route behavior for SDK implementation.

Manual verification:

- Human checks route handlers do not contain provider/business logic directly.
- Human checks public responses are redacted and stable.

Exit criteria:

- Portal and machine routes share the same service/query layer and remain compatible with Habiba's SDK.

## Phase 9 - Telephony Session, Quota, Idempotency, And Concurrency Lifecycle

Purpose: make telephony call/session orchestration independent of browser `/v1/session` and safe under retries/concurrency.

Subphases:

1. Implement service-level idempotency for number purchase, outbound call creation, and retryable provider side effects.
2. Use row locks before provider side effects and store request hashes/responses according to `telephony_idempotency_keys` contract.
3. Implement atomic quota reservation and exactly-once quota release for telephony calls.
4. Implement exactly-once usage recording where required without extending `usage_events.kind` in the first telephony contract.
5. Keep telephony room/session/call orchestration independent of browser `/v1/session`.
6. Add direction-specific status transition guards.
7. Protect active calls from unsafe number reassignment/disable behavior.

Tests/checks:

- Idempotency same-key/same-payload replay tests.
- `idempotency_payload_mismatch` tests.
- Concurrent outbound call creation tests.
- Quota reservation/release race tests.
- Exactly-once release and usage recording tests.
- Stale status update rejection tests.
- Active-call reassignment/disable protection tests.

Human tasks:

- Habiba confirms DB constraint availability for idempotency and quota/call fields.
- Hamza confirms status transition enforcement split between app and DB.

Manual verification:

- Human checks quota release cannot happen twice and failures remain visible.
- Human checks telephony does not call `/v1/session` for call orchestration.

Exit criteria:

- Telephony session/quota/idempotency behavior is deterministic under retries and concurrent calls.

## Phase 10 - Inbound SIP Call Resolution And Failed-Call Cleanup

Purpose: resolve inbound SIP calls from trusted LiveKit SIP attributes and AwaazLabs-owned DB records before any agent session starts.

Subphases:

1. Implement minimal worker-side or pre-worker resolver according to the chosen architecture.
2. Read trusted LiveKit SIP attributes: `sip.callID`, `sip.callIDFull`, `sip.trunkPhoneNumber`, `sip.trunkID`, and `sip.ruleID` after they are confirmed.
3. Resolve tenant, number, assigned agent, inbound trunk, and dispatch rule through stored DB records.
4. Validate tenant status, number routing, assignment, quota, and provider runtime readiness before `AgentSession` starts.
5. Prevent multiple workers from handling the same SIP call.
6. For unknown/unresolved tenant inbound calls, do not create tenant-scoped `telephony_calls`; record restricted backend/admin diagnostics only.
7. For resolved-tenant failures, record idempotent failed call/events where contract allows and release quota only if reserved.
8. Add minimal worker-side telephony call close/update hooks where required for call status, quota release, and usage recording.
9. Keep `worker/main.py` changes minimal and do not fork STT/LLM/TTS construction.

Tests/checks:

- Inbound resolver tests for valid number/agent/trunk/rule.
- Unknown number, unassigned number, suspended tenant, routing mismatch, quota failure, assigned-agent load failure, provider pipeline start failure, and worker metadata missing tests.
- Duplicate worker handling/race tests.
- No-tenant diagnostic-only tests.
- Existing worker and Urdu pipeline regression tests.

Human tasks:

- Hamza confirms whether session rows are created by worker resolver or pre-worker orchestrator.
- Ukasha confirms provider registry runtime config contract for telephony-created rooms.
- Habiba confirms fields/indexes required for inbound resolution.

Manual verification:

- Human confirms no caller-controlled metadata is trusted for tenant/agent/routing.
- Human verifies worker changes are minimal and do not introduce a second STT/LLM/TTS pipeline.

Exit criteria:

- Inbound SIP calls resolve safely or fail cleanly before starting agent runtime.

## Phase 11 - Outbound Call Orchestration

Purpose: create outbound calls through reusable LiveKit outbound trunk resources with full readiness, policy, idempotency, and quota checks.

Subphases:

1. Validate tenant, agent, source number, number ownership, routing readiness, SIP readiness, Outbound Voice Profile readiness, destination policy, spending/concurrency limits, verification restrictions, and idempotency before provider side effects.
2. Create room/session/call records independently of browser `/v1/session`.
3. Dispatch the LiveKit agent and record `livekit_agent_dispatch_id`.
4. Create outbound SIP participant/call through reusable outbound trunk.
5. Track `livekit_sip_call_id`, `livekit_sip_call_id_full`, raw participant status, public status, errors, and call events.
6. Handle failure cleanup, quota release, status transitions, and usage recording exactly once.
7. Return stable SDK-safe responses.

Tests/checks:

- Outbound validation failure tests for every readiness/policy condition.
- Idempotent outbound creation tests.
- Fake LiveKit agent dispatch and outbound SIP participant tests.
- Failure cleanup and quota release tests.
- Direction-specific public status transition tests.
- Stable response/error shape tests.

Human tasks:

- Hamza confirms destination policy labels, limits, and verification restrictions.
- Habiba confirms SDK request/response fields and call schema support.
- Human approves any real outbound PSTN call test.

Manual verification:

- Human checks no outbound call test can run against paid/live providers by default.
- Human confirms failed outbound calls do not leak secrets or raw provider payloads.

Exit criteria:

- Outbound calls are orchestrated through reusable resources with safe retries and cleanup.

## Phase 12 - Webhooks, Polling, And Reconciliation

Purpose: keep orders, calls, trunks, dispatch rules, profiles, and quota consistent despite missed events, retries, and partial failures.

Subphases:

1. Implement Telnyx webhook signature verification, dedupe, provider-ID mapping, event validation, redaction, and event application.
2. Add optional LiveKit webhook handling only after the deployed event surface is confirmed useful.
3. Do not assume `telnyx_call_control_id` or Telnyx Voice API call webhooks for SIP-trunked calls unless confirmed.
4. Implement bounded reconciliation service functions for stale orders, calls, trunks, dispatch rules, Outbound Voice Profiles, drift reports, and quota leaks.
5. Add `scripts/reconcile_telephony.py` as a CLI wrapper with dry-run and apply modes.
6. Use bounded retries/backoff and move unrecoverable cases to visible `action_required`, `degraded`, or `failed` states.
7. Do not loop forever.

Tests/checks:

- Webhook valid signature, invalid signature, duplicate, unmapped provider ID, stale event, malformed event, and replay tests.
- Order reconciliation tests.
- Stale call and quota leak repair tests.
- Trunk/rule/Profile drift detection tests.
- Partial purchase success plus routing failure recovery tests.
- Reconciliation idempotency tests.
- Dry-run/apply CLI tests.

Human tasks:

- Hamza confirms Telnyx webhook event types and LiveKit webhook usefulness.
- Habiba confirms event/deduplication schema support and stale-scan index needs.
- Human approves public webhook URL and provider webhook configuration.

Manual verification:

- Human checks webhook routes never trust tenant IDs from provider payloads.
- Human checks reconciliation cannot run unbounded or hide failures.

Exit criteria:

- Webhooks and reconciliation repair or flag drift safely with fake providers and gated live validation.

## Phase 13 - Logs, Metrics, Tenant Health, Readiness, And Env Config

Purpose: add production visibility and backend config without leaking secrets or making one tenant's provider issue a global outage.

Subphases:

1. Implement `tenant_portal_api/telephony_health.py` and optional metrics helpers.
2. Add global readiness checks only for core platform dependencies; tenant-specific Telnyx/SIP/Profile failures must be tenant/resource health, not global service failure.
3. Add redacted structured logs for credential changes, provider failures, routing failures, call setup/cleanup, webhooks, reconciliation, and health diagnostics.
4. Add backend-only env var names to `.env.example` and docs only after final architecture decision.
5. Do not edit `.env.local` or commit real values.
6. Add config validation for encryption reference, webhook signing secret, provider timeout, reconciliation settings, and live-provider-test gating.
7. Define these backend-only env var names subject to final architecture decision:
   - `TELEPHONY_CREDENTIAL_ENCRYPTION_KEY` or a secret-store/KMS reference
   - `TELNYX_WEBHOOK_SIGNING_SECRET`
   - `TELEPHONY_WEBHOOK_PUBLIC_BASE_URL` if provider configuration needs callback URLs
   - `TELEPHONY_PROVIDER_HTTP_TIMEOUT_SEC`
   - `TELEPHONY_RECONCILE_INTERVAL_SEC`
   - `TELEPHONY_RECONCILE_MAX_ATTEMPTS`
   - `TELEPHONY_ENABLE_REAL_PROVIDER_TESTS`
   - existing `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `SUPABASE_DB_URL`, and tenant portal auth envs stay backend-only where already required.

Tests/checks:

- Tenant health isolation tests.
- Global readiness remains healthy during one tenant provider failure.
- Redaction tests for phone numbers where policy requires, recipient details, raw provider payloads, provider credentials, HMAC signatures, access tokens, transcripts, prompts, and call context secrets.
- Config loading tests with no value exposure.
- Missing required global config returns safe startup/readiness errors.

Human tasks:

- Hamza confirms env var names and deployment shape.
- Habiba confirms which readiness states must be SDK/future-portal visible.
- Human confirms no real env values are committed.

Manual verification:

- Human reviews logs and health responses for separation of global platform health and per-tenant provider health.

Exit criteria:

- Operators can distinguish platform health, provider availability, tenant connection health, routing health, and restricted diagnostics.

## Phase 14 - Controlled Provider Tests And Backend Integration Tests

Purpose: prove backend behavior with fake providers by default and live providers only through explicit staging gates.

Subphases:

1. Add focused backend tests for Telnyx adapter, connection API, inventory, number orders, SIP connection, Outbound Voice Profile, LiveKit SIP, routes, machine API, inbound worker, failed inbound calls, outbound calls, quota/idempotency, webhooks, reconciliation, health, and config.
2. Update `tests/conftest.py` only if needed to keep telephony live-provider tests skipped by default.
3. Keep existing regression tests green: `tests/test_mint.py`, `tests/test_host_backend_contract.py`, `tests/test_machine_agent_api.py`, `tests/test_worker.py`, `tests/test_tools.py`, `tests/test_phase4_portal_api.py`, and relevant health/admin tests.
4. Add optional live staging tests under a clearly named file such as `tests/test_telephony_staging_live.py`, skipped unless explicitly enabled.
5. Do not modify Habiba's SDK tests and do not add dashboard tests in this workflow.

Tests/checks:

- Fake-provider backend suite.
- Portal/machine route contract tests.
- Multi-tenant isolation tests once Habiba migrations land.
- Concurrency/race/idempotency tests.
- Duplicate webhook and stale reconciliation tests.
- Partial-failure recovery tests.
- Trunk/rule reuse tests.
- Urdu WebRTC and worker regression tests.
- Controlled real Telnyx/LiveKit staging tests only with explicit credentials and approval.

Human tasks:

- Hamza approves test coverage and live test gating.
- Habiba supplies applied-schema/staging DB confirmation when integration tests need it.
- Ukasha confirms provider registry regressions pass.
- Human explicitly approves any paid/live provider test.

Manual verification:

- Human checks default CI cannot call paid/live Telnyx, LiveKit PSTN, STT, LLM, or TTS providers.
- Human reviews staging checklist before live validation.

Exit criteria:

- Fake-provider suite passes, existing regressions pass, and live staging checklist is gated and documented.

## Phase 15 - Habiba Handoff, Staging Integration, And PR Readiness

Purpose: keep Habiba unblocked and prepare Hamza's backend branch for reviewed merge into `staging`.

Subphases:

1. Provide Habiba route list with auth type, machine action strings, request/response JSON examples, error-code list, status enum list, transition rules, required DB fields/indexes/constraints/RLS expectations, transaction locks, fake-provider fixtures, and staging validation checklist.
2. Review Habiba's migration designs for backend compatibility without applying migrations.
3. Confirm Habiba's SDK method calls match backend route/action/response behavior.
4. Run staging integration after Habiba migrations and SDK are ready.
5. Prepare PR notes with module map, test evidence, live-provider gating, known limitations, and handoff materials.
6. Confirm no direct development on `main`.

Tests/checks:

- Shared contract tests proving route responses match SDK and future portal expectations.
- Fixture parity tests if JSON fixtures are shared.
- Backend integration smoke against applied schema.
- Staging SDK/backend smoke with Habiba after endpoints are available.
- Final regression suite and fake-provider suite.

Human tasks:

- Habiba reviews final DB/API/SDK compatibility.
- Hamza approves final backend diff.
- Ukasha confirms provider/language regressions are not introduced.
- Human approves PR creation and merge into `staging`.

Manual verification:

- Human checks final handoff package gives Habiba enough detail to complete migrations, SDK, and docs without guessing.
- Human confirms all live-provider or E2E gaps are listed as explicit blockers.

Exit criteria:

- Hamza branch is ready for reviewed PR into `staging`.
- `main` remains untouched until integration, regression, staging, and production-readiness testing are complete.

## Human-Only Tasks Summary

- Approve this plan before implementation starts.
- Confirm shared contract freeze with Habiba.
- Confirm Hamza works on `hamza` branch or approved child branch.
- Confirm exact LiveKit SIP APIs and SIP participant attributes.
- Confirm exact Telnyx APIs, webhook event types, SIP verification method, countries, number types, features, destination policies, and reservation support.
- Decide whether existing `httpx==0.28.1` is enough or a pinned Telnyx SDK is required.
- Approve any new dependency before it is added.
- Confirm credential encryption/retrieval mechanism with Habiba.
- Approve any real Telnyx/LiveKit provider test explicitly.
- Confirm public webhook URL and provider webhook configuration.
- Confirm deployment env var names; never commit real values.
- Review Habiba migration designs for backend compatibility without applying them.
- Provide Habiba fake fixtures, route/action strings, response examples, errors, statuses, and transaction/lock requirements.
- Approve PR into `staging` after Habiba and Ukasha compatibility review.

## Manual Verification Checklist

- Contract document is frozen or explicitly approved for implementation as proposed.
- Hamza did not create, apply, or edit Supabase migrations.
- Dashboard files remain unchanged.
- `@awaazlabs-uva/telephony` SDK files remain Habiba-owned.
- Provider/language registry work remains Ukasha-owned.
- `worker/main.py` changes are minimal and do not fork STT/LLM/TTS.
- `control_plane/app.py` is modified only for approved shared LiveKit dispatch helper extraction, never to make telephony depend on browser `/v1/session`.
- Worker-side telephony close/update hooks are limited to call status, quota release, and usage recording needs.
- No LiveKit trunks or SIP dispatch rules are created per call.
- No caller-controlled metadata is trusted for tenant, agent, routing, or authorization.
- Telnyx API keys, SIP secrets, LiveKit secrets, Supabase credentials, HMAC secrets, raw provider payloads, stack traces, and unrestricted errors are not exposed to clients.
- Machine HMAC action strings are fixed server-side and never client-supplied.
- Filtered/list/search machine operations use signed bodies or body-bound routes, not unsigned query params.
- `usage_events.kind` is not extended in the first telephony contract.
- `external_customer_ref` and `external_workflow_ref` remain opaque strings.
- Failed inbound calls with no tenant do not create tenant-scoped `telephony_calls` rows.
- Number reservation is optional by provider/market and unsupported cases return stable unsupported/action-required responses.
- Default CI cannot call paid/live Telnyx, LiveKit PSTN, STT, LLM, or TTS providers.
- Existing `/portal/agents`, `/machine/agents`, `/v1/session`, worker, usage, WebRTC, and Urdu pipeline regressions pass or have explicit blockers.

## Scope Exclusions For Hamza

Hamza must not implement:

- Supabase migration files, RLS policies, indexes, tenant-scoped constraints, database functions, live Supabase deployment, schema verification, or rollback planning owned by Habiba.
- `@awaazlabs-uva/telephony` SDK source, SDK package tests, SDK README, or client-deliverable package implementation owned by Habiba.
- Dashboard routes, UI components, navigation, SWR keys, portal client code, dashboard-specific mocks, or dashboard telephony pages.
- Provider/language registry work owned by Ukasha.
- A separate STT/LLM/TTS pipeline or telephony-specific provider selection.
- Per-call LiveKit trunk or SIP dispatch-rule creation.
- P2F-specific billing, payment, or end-client workflows.
- Direct browser `/v1/session` dependency for telephony call orchestration.

Hamza may implement backend telephony service modules, provider adapters, portal/machine backend routes, worker resolver hooks, inbound/outbound orchestration, idempotency runtime, quota runtime, webhooks, reconciliation, health/readiness, fake-provider tests, gated provider tests, and handoff docs/fixtures.

## Self-Audit Against Hamza Workflow

Coverage check:

- Non-Negotiable Boundaries: covered in Agent Rules, Phase 0, Manual Verification Checklist, and Scope Exclusions.
- Backend Module Structure: covered in Phase 2.
- Database Requirements And Repository Contracts: covered in Phase 3.
- Stable Platform Errors And Status Transitions: covered in Phase 2.
- Telnyx API Adapter: covered in Phase 4.
- Telnyx Account Verification And Credential Lifecycle: covered in Phase 4.
- Number Inventory, Import, Sync, Drift, Search, Reservation, And Purchase: covered in Phase 5.
- Number-Order Status Tracking: covered in Phase 5.
- Telnyx SIP/FQDN Connection: covered in Phase 6.
- Telnyx Outbound Voice Profile: covered in Phase 6.
- LiveKit SIP Adapter, Trunks, And Dispatch Rules: covered in Phase 7.
- Portal And Machine Telephony API Routes: covered in Phase 8.
- Telephony Session And Quota Lifecycle: covered in Phase 9.
- Inbound SIP Call Resolution And Failed-Call Cleanup: covered in Phase 10.
- Outbound Call Orchestration: covered in Phase 11.
- Idempotency And Concurrency Handling: covered in Phase 9 and Phase 11.
- Telnyx And LiveKit Webhook Handling: covered in Phase 12.
- Polling And Reconciliation Schedulers: covered in Phase 12.
- Logs, Metrics, Tenant Health, And Readiness: covered in Phase 13.
- Backend Deployment Configuration And Environment Variables: covered in Phase 13.
- Controlled Provider Tests And Backend Integration Tests: covered in Phase 14.
- Habiba Handoff Requirements During Implementation: covered in Phase 15.
- Dependencies On Habiba: covered in Phase 1, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7, Phase 9, Phase 10, Phase 11, Phase 12, and Phase 15.
- Dependencies On Ukasha: covered in Phase 0, Phase 1, Phase 10, Phase 14, and Scope Exclusions.
- Open Technical Decisions Relevant To Hamza: covered in Phase 1 and Human-Only Tasks Summary.
- Expected Handoff Deliverables: covered in Phase 15 and Human-Only Tasks Summary.
- Definition Of Completion For Hamza: covered in Phase 15 and Manual Verification Checklist.

Overlap audit:

- This plan does not assign Supabase migration/RLS/live deployment work to Hamza.
- This plan does not assign `@awaazlabs-uva/telephony` SDK implementation to Hamza.
- This plan does not assign dashboard implementation to Hamza.
- This plan does not assign provider/language registry ownership to Hamza.
- This plan keeps Hamza focused on backend service/runtime, Telnyx/LiveKit adapters, portal/machine routes, inbound/outbound orchestration, idempotency/concurrency, webhooks, reconciliation, health, and backend tests.
- This plan includes Habiba handoff requirements without making Hamza responsible for Habiba-owned implementation.

Result: final, audited, and ready to use as the agent-facing plan after Hamza approves it and the contract/schema-availability gates are satisfied.
