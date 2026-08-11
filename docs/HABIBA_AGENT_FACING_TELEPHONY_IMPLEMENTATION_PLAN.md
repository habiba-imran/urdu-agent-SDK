# Habiba Agent-Facing Telephony Implementation Plan

Status: final.

Source of truth:

- `docs/.codexrules`
- `docs/HABIBA_TELEPHONY_IMPLEMENTATION_WORKFLOW.md`
- `docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md`
- `docs/TELEPHONY_WORKLOAD_AND_RESPONSIBILITY_DIVISION.md`
- `docs/TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md`
- `docs/HAMZA_TELEPHONY_IMPLEMENTATION_WORKFLOW.md`
- `docs/UKASHA_MULTIPLE_PROVIDERS_GUIDE.md`

This plan is for a coding agent implementing Habiba's telephony work. It converts Habiba's workflow into implementation phases with subphases, tests, human tasks, manual verification gates, and a scope audit. If this plan conflicts with `docs/.codexrules` or the frozen telephony contract, stop and ask Habiba before writing code.

## Agent Rules

- Re-read `docs/.codexrules` before implementation and every 5 to 10 messages.
- Inspect current code, migrations, manifests, tests, branch, and dirty worktree before edits.
- For any task touching more than two files, present the exact file plan and wait for Habiba approval.
- Make the smallest scoped change for the current phase.
- Do not modify dashboard files in this workflow.
- Do not implement Hamza-owned backend runtime work.
- Do not add dependencies without verifying existing manifests and getting approval.
- Do not hardcode secrets, API keys, provider payloads, phone numbers, Supabase credentials, HMAC secrets, or LiveKit secrets.
- Keep `@awaazlabs-uva/telephony` backend-only and out of browser/dashboard bundles.
- Prefer precise TypeScript types over `any`; validate external API responses where practical.
- Run verification after each phase and fix failures before moving forward.

## Phase 0 - Recon, Branch Safety, And Approval Gate

Purpose: verify current repo state before implementation.

Subphases:

1. Read source docs and confirm `docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md` is the shared contract Hamza is following.
2. Inspect current branch, `git status -sb`, migration sequence, package manifests, SDK layout, and test files.
3. Inspect HMAC references in `tenant_portal_api/machine_auth.py` and `sdk-server/src/index.ts`.
4. Inspect existing migration/RLS tests: `tests/test_schema.py`, `tests/test_isolation.py`, `tests/test_cross_tenant_read_live.py`, `tests/test_machine_agent_api.py`, and `tests/test_host_backend_contract.py`.

Tests/checks:

- No implementation tests yet.
- `rg` checks for dashboard out-of-scope wording, table names, route paths, action strings, and SDK method names.

Human tasks:

- Habiba approves this implementation plan.
- Habiba confirms work happens on `habiba` branch or an approved child branch.
- Hamza confirms he follows the same contract and will provide fixtures/API details.
- Ukasha confirms migration-number coordination process.

Manual verification:

- Human checks no live Supabase change is planned yet.
- Human checks no dashboard file or Hamza runtime file is in the first edit plan.

Exit criteria:

- Plan approved.
- Contract acknowledged.
- No implementation edits made before approval.

## Phase 1 - Contract Freeze And Open Decisions

Purpose: remove ambiguity before schema and SDK code depend on shared surfaces.

Subphases:

1. Verify table names, columns, constraints, indexes, RLS expectations, statuses, error codes, routes, methods, and machine HMAC action strings against the contract doc.
2. If both developers approve and Habiba asks for the edit, change contract status from `proposed freeze` to `frozen`.
3. Resolve or explicitly block Habiba-owned decisions: encryption mechanism, retention/export/offboarding policy, restricted payload access, DB-vs-app status enforcement, and deliverable packaging format.

Tests/checks:

- Markdown consistency checks for all expected table names and SDK methods.
- Contract checklist before migrations are created.

Human tasks:

- Habiba signs off schema, SDK method names, signing behavior, fixture requirements, and deliverable format.
- Hamza signs off route list, request/response fields, error/status table, row locks, fake fixtures, and backend compatibility.
- Ukasha confirms provider/language migrations will not collide with telephony migration numbers.

Manual verification:

- Human compares Hamza plan and shared contract for mismatches.
- Human confirms unresolved provider details do not block Habiba's schema/SDK scaffold.

Exit criteria:

- Contract is frozen or explicitly approved as the implementation contract.
- Migration-affecting decisions are resolved or recorded as blockers.

## Phase 2 - Migration Numbering And Schema Design

Purpose: design the Supabase migration slices safely.

Subphases:

1. Reserve migration numbers after the current local sequence. Current observed sequence ends at `supabase/migrations/0011_session_transcript.sql`.
2. Propose small migration slices: core tables, constraints/indexes/status/idempotency, RLS/grants, and data-governance/audit fields.
3. Finalize table model for `tenant_telnyx_connections`, `telnyx_sip_connections`, `telnyx_outbound_voice_profiles`, `telephony_phone_numbers`, `livekit_inbound_trunks`, `livekit_outbound_trunks`, `livekit_sip_dispatch_rules`, `telephony_number_orders`, `telephony_calls`, `telephony_call_events`, `telephony_idempotency_keys`, and `telephony_audit_log`.
4. Link only to agreed existing tables: `tenants`, `agents`, `sessions`, `usage_events`, `quota_state`, and `used_nonces` where required.
5. Do not extend `usage_events.kind` in the first telephony contract; store telephony duration/status on `telephony_calls` first.
6. Treat `external_customer_ref` and `external_workflow_ref` as opaque strings, not structured JSON or P2F-specific data.
7. Do not design tenant-scoped `telephony_calls` rows for failed inbound calls where no tenant can be resolved; those belong only in restricted backend/admin diagnostics.

Tests/checks:

- Migration ordering check.
- Schema contract checklist.
- Static check that every table has `tenant_id` where tenant-owned.

Human tasks:

- Ukasha reserves migration numbers.
- Hamza reviews field names, nullable fields, FK paths, lock needs, query indexes, and restricted payload storage requirements.
- Habiba approves migration slicing.

Manual verification:

- Human confirms no duplicate migration number.
- Human confirms no P2F-specific schema assumptions.
- Human confirms LiveKit trunk/rule provider IDs live only on owning resource tables, not duplicated into `telephony_calls`.

Exit criteria:

- Migration numbers and schema design are approved.

## Phase 3 - Core Telephony Schema Migrations

Purpose: create normalized telephony tables and base relationships.

Subphases:

1. Create reviewed migration files under `supabase/migrations/*` using reserved numbers.
2. Add the core telephony tables from Phase 2 with explicit names, tenant IDs, provider IDs, timestamps, internal references, and sensitive/restricted fields.
3. Add FKs to existing tenant, agent, and session tables only where the contract requires.
4. Do not edit old migrations unless Habiba explicitly approves a compatibility migration.

Tests/checks:

- Fresh database schema test.
- Table existence tests.
- Required column tests.
- FK constraint tests.
- Provider-ID ownership tests proving `telephony_calls` stores internal trunk/rule references and call-correlation IDs only.
- Status-column existence tests.

Human tasks:

- Habiba reviews SQL before any live application.
- Hamza reviews schema compatibility for backend repositories.

Manual verification:

- Human reads SQL for missing `tenant_id`, accidental secret values, broad grants, P2F-specific fields, and ambiguous provider ID columns.

Exit criteria:

- Core schema migrations are ready and schema tests cover every telephony table.

## Phase 4 - Constraints, Indexes, Status Rules, And Idempotency

Purpose: make the database enforce production invariants.

Subphases:

1. Add tenant-scoped uniqueness and FK validation so cross-tenant assignment cannot happen even if API validation regresses.
2. Add partial unique constraints/indexes for one active Telnyx connection per tenant, one active SIP connection per active Telnyx connection, one active inbound trunk/rule per number, one active outbound trunk per tenant connection, and one active `(tenant_id, e164_number)`.
3. Add indexes for `tenant_id`, E.164 number, assigned agent, LiveKit provider IDs, `room_name`, `livekit_sip_call_id`, `livekit_sip_call_id_full`, status, timestamps, provider event dedupe, idempotency, and stale reconciliation scans.
4. Add status checks/enums from the frozen contract.
5. Add `telephony_idempotency_keys` support with unique `(tenant_id, idempotency_key, action)`, `request_hash`, `response_body`, `platform_status`, `created_at`, and `completed_at`.
6. Do not implement Hamza's runtime idempotency handler; only provide schema, constraints, and tests.

Tests/checks:

- Duplicate active connection rejection.
- Duplicate active number rejection.
- Cross-tenant assignment rejection.
- Duplicate idempotency behavior.
- `idempotency_payload_mismatch` behavior where DB/test-fixture enforceable.
- Provider event dedupe constraints.
- Direction-specific call status transition tests where DB-enforced.
- Critical index existence tests.

Human tasks:

- Hamza confirms idempotency key scope, canonical request hash expectations, row-lock needs, and high-frequency query paths.
- Habiba confirms DB-enforced versus app-enforced transition strategy.

Manual verification:

- Human checks all constraints are tenant-scoped and all index names are readable.

Exit criteria:

- Database invariants support Hamza's backend repository work without ad hoc duplicate protection for every path.

## Phase 5 - RLS, Grants, And Tenant Isolation Verification

Purpose: prevent telephony data leakage across tenants.

Subphases:

1. Enable RLS on every tenant-owned telephony table.
2. Add tenant-scoped `USING` and `WITH CHECK` policies following existing repo patterns.
3. Avoid broad `TO authenticated` access without row ownership checks.
4. Avoid exposing encrypted credential columns, raw provider payloads, restricted diagnostics, stack traces, or secrets.
5. If views/functions are introduced, keep them RLS-safe and reviewed.
6. Extend `tests/test_isolation.py`, `tests/test_cross_tenant_read_live.py`, or add `tests/test_telephony_rls.py` according to repo style.

Tests/checks:

- RLS enabled for every tenant-owned telephony table.
- Tenant A cannot select Tenant B telephony rows.
- Tenant A cannot assign Tenant B agent or number.
- Tenant A cannot read restricted provider payloads.
- Update policies include both visibility and ownership checks where applicable.
- Unknown/unauthorized tenant behavior is stable and does not reveal ownership.

Human tasks:

- Habiba confirms whether direct Data API access is needed or backend-service-only access is enough.
- Hamza confirms which tables are written by trusted service code versus tenant-scoped role.
- Habiba provides live/staging test tenants only if live RLS checks are approved.

Manual verification:

- Human reviews Supabase policy behavior locally or in staging before production use.
- Human confirms live RLS tests do not touch production data.

Exit criteria:

- RLS, grants, and tenant isolation are verified for all telephony tables.

## Phase 6 - Data Governance, Audit, Retention, And Deletion

Purpose: model telephony data as sensitive data from the first release.

Subphases:

1. Add data-governance fields for retention, deletion/offboarding, export/access, redaction, and restricted diagnostics.
2. Implement `telephony_audit_log` for credential changes, number purchases/imports, assignment changes, SIP changes, outbound calls, number disconnections, transcript access, call-record access, exports, and restricted-payload access.
3. Keep raw provider payloads restricted to diagnostic fields/tables.
4. Prevent secrets from entering transcripts, prompts, summaries, call context, docs, fixtures, or logs.
5. Add `tests/test_telephony_data_governance.py` or extend existing tests.

Tests/checks:

- Retention/deletion field behavior.
- Tenant offboarding behavior where schema-supported.
- Export access-control behavior if exposed.
- Restricted provider payload access denied for tenant-facing paths.
- Transcript/call-record access audit tests where available.
- Redaction tests where testable.

Human tasks:

- Habiba confirms retention periods, export permissions, tenant-offboarding behavior, and restricted payload policy.
- Hamza confirms which raw provider payloads and operational metadata are needed for debugging/reconciliation.

Manual verification:

- Human reviews fixtures, migrations, and docs for accidental real provider data or phone numbers.

Exit criteria:

- Schema and contracts can support retention, deletion, export, audit, and restricted diagnostics without later table redesign.

## Phase 7 - Migration Application, Verification, And Rollback Safety

Purpose: apply migrations safely and keep a recovery path.

Subphases:

1. Apply migrations only in local or staging-safe environments first.
2. Verify migration history, table creation, constraints, RLS, grants, indexes, and advisors/security output where available.
3. Add optional `docs/TELEPHONY_MIGRATION_RUNBOOK.md` only if Habiba wants a runbook artifact.
4. Do not apply live Supabase migrations without explicit Habiba approval.
5. If live application is approved, run only reviewed commands and capture verification evidence.

Tests/checks:

- Fresh schema migration test.
- Migration list/history verification.
- RLS isolation checks.
- Constraint violation tests.
- Rollback or forward-fix drill where practical.
- Existing schema/isolation regressions.

Human tasks:

- Habiba supplies local/staging Supabase access and approves every live migration.
- Habiba chooses rollback strategy: rollback SQL, forward-fix migration, or restore plan.
- Hamza confirms backend compatibility against applied schema.

Manual verification:

- Human checks Supabase migration history and security/advisor output.
- Human confirms no secrets were printed, committed, or pasted into docs.
- Human confirms telephony remains disabled/degraded until backend runtime is ready.

Exit criteria:

- Migrations are applied and verified in the approved environment with rollback/recovery notes.

## Phase 8 - Backend-Only `@awaazlabs-uva/telephony` SDK

Purpose: create a portable Node backend SDK that calls Hamza's machine telephony API.

Subphases:

1. Scaffold `telephony/package.json`, `telephony/tsconfig.json`, `telephony/README.md`, `telephony/src/index.ts`, `telephony/src/signing.ts`, `telephony/src/types.ts`, optional `telephony/src/errors.ts`, and optional tests following repo practice.
2. Match `sdk-server` package conventions unless a reviewed reason exists.
3. Implement canonical JSON hashing compatible with `tenant_portal_api/machine_auth.py`.
4. Add HMAC headers: `X-Tenant-Id`, `X-Timestamp`, `X-Nonce`, and `X-Signature`.
5. Keep action strings fixed per method and never caller-controlled.
6. Ensure `extraHeaders` cannot override auth headers.
7. Serialize camelCase TypeScript params to snake_case JSON wire bodies.
8. Implement stable typed errors with `status`, `code`, redacted `message`, and optional redacted `detail`.
9. Accept Telnyx API keys only as method params during connect/rotate; never persist, cache, log, return, or store them on the client instance.
10. Do not modify `@awaazlabs-uva/voice`. Avoid changing `sdk-server/src/index.ts` unless Habiba approves extracting a shared signing helper.

SDK methods to implement:

- `connectTelnyxAccount`
- `rotateTelnyxAccountKey`
- `reverifyTelnyxAccount`
- `disconnectTelnyxAccount`
- `getConnectionStatus`
- `listTelnyxOwnedNumbers`
- `listManagedPhoneNumbers`
- `importTelnyxNumber`
- `syncTelnyxOwnedNumbers`
- `getTelnyxNumberDrift`
- `searchAvailableNumbers`
- `reserveNumber`
- `purchaseNumber`
- `getNumberOrderStatus`
- `assignAgentToNumber`
- `unassignAgentFromNumber`
- `upsertTelnyxSipConnection`
- `verifyTelnyxSipConnection`
- `upsertTelnyxOutboundVoiceProfile`
- `verifyTelnyxOutboundVoiceProfile`
- `configureNumberRouting`
- `configureOutboundTrunk`
- `getOutboundReadiness`
- `createOutboundCall`
- `getCallStatus`
- `listCallRecords`
- `disableNumber`

Tests/checks:

- `npm run build` in `telephony`.
- `npm run lint` or `tsc --noEmit` if script exists.
- Canonical JSON hashing parity tests.
- HMAC header construction tests.
- Fixed action string tests.
- `extraHeaders` auth override protection tests.
- Telnyx API key non-retention tests.
- Error mapping tests.
- Method serialization tests.
- Type/build tests for public interfaces.

Human tasks:

- Habiba approves package location and error type shape.
- Hamza confirms final machine route paths, action strings, request/response payloads, stable error format, and idempotency key placement.

Manual verification:

- Human reviews SDK code for retained secrets, browser APIs, logs, raw provider payloads, and `any` usage.

Exit criteria:

- `@awaazlabs-uva/telephony` builds independently, is backend-only, and calls only `/machine/telephony/*`.

## Phase 9 - SDK Contract Tests And Mocked API Integration

Purpose: finish SDK behavior before Hamza's real endpoints are complete.

Subphases:

1. Add SDK-local or `tests/fixtures/telephony/` fixtures using Hamza-provided fake responses.
2. Cover success, not connected, action required, degraded, failed, auth failure, outbound not ready, idempotency mismatch, and permission failure states.
3. Test every SDK method against mocked HTTP responses.
4. Verify GET requests sign `{}` and list/filter/search methods bind filters in signed JSON bodies where the contract requires.
5. Keep mocks isolated and removable.

Tests/checks:

- SDK method contract tests.
- SDK mocked integration suite.
- Fixture redaction checks using `rg` for obvious secret patterns.
- Build/typecheck after fixtures and tests.
- Existing agents SDK and browser voice SDK remain unchanged unless docs/package references are intentionally updated.

Human tasks:

- Hamza provides fake response examples and endpoint availability matrix.
- Habiba approves fixture location and safe sample values.

Manual verification:

- Human reviews fixtures for real secrets, real provider payloads, and unapproved phone numbers.
- Human confirms any contract mismatch is escalated to Hamza before shared names are changed.

Exit criteria:

- SDK is complete against mocked contract and mocks are not production paths.

## Phase 10 - Client Deliverable Package And Documentation

Purpose: make the SDK usable by client backend developers without exposing secrets.

Subphases:

1. If approved, create `client-submission_v2/sdk/@awaazlabs-uva/telephony/`.
2. Include source, README, package files, `dist`, and/or tarball according to Habiba's deliverable decision.
3. Update approved docs only: `README.md`, `docs/MACHINE_AGENT_API_CONTRACT.md` or a new telephony machine API doc, `client-submission_v2/README.md`, `client-submission_v2/sdk/README.md`, `telephony/README.md`, and deliverable README if present.
4. Optionally create `docs/TELEPHONY_CLIENT_INTEGRATION_GUIDE.md` and/or `docs/TELEPHONY_API_REFERENCE.md` if Habiba approves.
5. Explain the three-package model: `@awaazlabs-uva/voice` is browser/WebRTC, `@awaazlabs-uva/agents` is backend-only agent management, and `@awaazlabs-uva/telephony` is backend-only telephony management.
6. Use environment variable placeholders only and never real values.
7. Include stable error-handling examples for not connected, action required, outbound not ready, idempotency mismatch, number unavailable, optional reservation unsupported/action required, and permission failure.

Tests/checks:

- Telephony SDK build and lint/typecheck.
- Clean install from local package path or tarball.
- Node backend import smoke test.
- Documentation example syntax checks where practical.
- Secret scan over changed docs/package files.
- Verify no browser bundle imports telephony SDK.

Human tasks:

- Habiba confirms deliverable format.
- Hamza provides final route behavior, error-code table, staging examples, and operational caveats.
- Habiba performs client-developer documentation review.

Manual verification:

- Human opens deliverable docs and verifies a client backend developer can follow them without putting secrets in browser code.

Exit criteria:

- Client deliverable is buildable, installable, documented, and backend-only.

## Phase 11 - Staging Integration With Hamza Backend

Purpose: replace mocks with Hamza's real backend endpoints and prove SDK/backend/schema compatibility.

Subphases:

1. Confirm Hamza backend endpoints are available locally or in staging.
2. Confirm applied Supabase migrations, test tenant setup, machine API base URL, tenant ID, and tenant secret are available as environment variables.
3. Confirm explicit approval before any live Telnyx/LiveKit provider test.
4. Run real SDK smoke tests through the same SDK paths used by mocks.
5. Keep mocks isolated from staging/production paths.
6. Record any mismatch as a contract issue instead of silently renaming fields.

Tests/checks:

- SDK staging smoke: connection status, managed numbers list, search mock/live-safe path, order status, assignment, outbound readiness, and call records.
- Auth failure smoke.
- Tenant isolation verification.
- API-key non-retention and secret non-return.
- Retention/deletion behavior where implemented.
- Regression tests for existing `/machine/agents`, browser voice SDK, sessions, usage, WebRTC, and Urdu pipeline behavior.

Human tasks:

- Hamza provides staging backend URL, endpoint readiness matrix, known limitations, test tenant setup needs, and provider test approval notes.
- Habiba supplies/approves test credentials through environment variables only.
- Human explicitly approves any real Telnyx/LiveKit staging test.

Manual verification:

- Human confirms no paid/live provider call runs in default CI.
- Human approves mock isolation/removal before staging signoff.

Exit criteria:

- SDK works against Hamza backend using the frozen telephony contract.

## Phase 12 - Regression, PR Readiness, And Merge Gate

Purpose: prove Habiba's branch is ready for reviewed merge to `staging`.

Subphases:

1. Run final targeted Python schema, RLS, isolation, machine auth, host backend contract, and regression tests.
2. Run telephony SDK build, typecheck/lint, mocked contract tests, package import smoke, and staging smoke where backend is ready.
3. Run documentation and secret checks.
4. Confirm dashboard files were not modified.
5. Confirm no Hamza-owned runtime implementation was added.
6. Compare final implementation against Habiba's Definition of Completion.
7. Prepare concise PR notes with test evidence and explicit blockers, if any.

Tests/checks:

- `tests/test_schema.py` only if the legacy CER/TechZone harness is intentionally revived; otherwise record it as non-telephony retired-harness debt per `state/HANDOFF.md` and `docs/40-ADR.md` ADR-030.
- `tests/test_isolation.py`
- `tests/test_cross_tenant_read_live.py` when live credentials are configured and approved
- `tests/test_machine_agent_api.py`
- `tests/test_host_backend_contract.py`
- New telephony schema/RLS/constraint/governance tests
- Telephony SDK `npm run build`
- Telephony SDK `npm run lint` or `tsc --noEmit`
- Telephony SDK mocked contract tests
- Staging SDK smoke after Hamza backend is ready

Human tasks:

- Habiba reviews final diff.
- Hamza reviews migration/API compatibility.
- Ukasha confirms provider/language regressions are not introduced.
- Habiba approves PR creation and merge into `staging`.

Manual verification:

- Human checks Supabase migration evidence, SDK package output, docs, staging smoke evidence, and no-secret evidence.
- Human confirms final E2E dependencies are either passed or listed as explicit blockers.

Exit criteria:

- Habiba branch is ready for reviewed PR into `staging`.
- `main` remains untouched until integration, regression, staging, and production-readiness testing are complete.

## Human-Only Tasks Summary

- Approve this plan before implementation starts.
- Confirm shared contract freeze with Hamza.
- Reserve migration numbers with Ukasha.
- Decide Telnyx API key and SIP secret encryption mechanism.
- Decide retention periods, export permissions, tenant offboarding, and restricted payload access policy.
- Confirm whether status transitions are DB-enforced, app-enforced, or both.
- Confirm whether telephony deliverables include source, `dist`, tarball, or all three.
- Provide Supabase access and approve every live migration application.
- Review migration SQL before live application.
- Ask Hamza for final query/lock requirements, fake fixtures, endpoint matrix, staging URL, and error examples.
- Approve any real Telnyx/LiveKit provider test explicitly.
- Perform final client-developer documentation walkthrough.
- Approve PR into `staging` after Hamza compatibility review.

## Manual Verification Checklist

- Contract document is frozen or explicitly approved for implementation as proposed.
- Migration numbers do not collide with Ukasha's provider/language work.
- Every tenant-owned telephony table has `tenant_id`, RLS, tenant-scoped constraints, and indexes.
- Cross-tenant assignment is blocked at database level.
- Raw provider payloads and encrypted credential columns are not exposed to tenant-facing responses.
- Telnyx API key is accepted only transiently during connect/rotate and never retained by SDK state.
- `extraHeaders` cannot override HMAC/auth headers.
- SDK wire format uses snake_case and signs the exact body.
- Number reservation is optional by provider/market; unsupported cases return a stable unsupported/action-required response.
- Mocks contain no real secrets, real provider payloads, or unapproved phone numbers.
- Dashboard files remain unchanged.
- `worker/*`, `tenant_portal_api/*` runtime routes/services, Telnyx adapter, LiveKit SIP orchestration, webhooks, reconciliation, and outbound/inbound call runtime remain Hamza-owned.
- Existing agents, sessions, usage, WebRTC voice SDK, and Urdu pipeline regressions pass or have explicit blockers.
- `usage_events.kind` is not extended in the first telephony contract; telephony duration/status lives on `telephony_calls`.
- Failed inbound calls with no tenant do not create tenant-scoped `telephony_calls` rows.

## Scope Exclusions For Habiba

Habiba must not implement:

- Telnyx API adapter.
- Telnyx account verification runtime and credential lifecycle service beyond SDK/API contract and schema support.
- Number inventory/import/sync/drift/search/reservation/purchase backend service logic.
- Telnyx SIP/FQDN provider runtime.
- Telnyx Outbound Voice Profile provider runtime.
- LiveKit SIP adapter, inbound/outbound trunks, or SIP dispatch-rule orchestration.
- Portal and machine telephony backend routes/runtime owned by Hamza.
- Telephony session/quota lifecycle runtime.
- Inbound SIP resolver or failed-call cleanup runtime.
- Outbound call orchestration runtime.
- Webhook handling runtime.
- Polling/reconciliation schedulers.
- Backend logs/metrics/health/readiness runtime.
- Provider/language registry work owned by Ukasha.
- Dashboard routes, UI components, navigation, SWR keys, or dashboard-specific mocks.

Habiba may implement database structures, SDK methods, SDK tests, fixtures, documentation, client deliverable packaging, and integration validation that depend on Hamza's backend contracts.

## Self-Audit Against Habiba Workflow

Coverage check:

- Non-Negotiable Boundaries: covered in Agent Rules, Phase 0, Scope Exclusions, and Manual Verification Checklist.
- Shared Contract Freeze: covered in Phase 1.
- Migration Numbering And Supabase Workflow: covered in Phase 2 and Phase 7.
- Core Telephony Schema Migrations: covered in Phase 3.
- Constraints, Indexes, Status Rules, And Idempotency: covered in Phase 4.
- RLS, Grants, And Tenant Isolation Verification: covered in Phase 5.
- Data Governance, Audit, Retention, And Deletion: covered in Phase 6.
- Migration Application, Verification, And Rollback Safety: covered in Phase 7.
- Backend-Only `@awaazlabs-uva/telephony` SDK Structure: covered in Phase 8.
- Telephony SDK Contract Tests And Client Deliverable Package: covered in Phase 9 and Phase 10.
- Dashboard Implementation Out Of Scope: covered in Agent Rules, Scope Exclusions, and Manual Verification Checklist.
- SDK Integration With Mocked Then Real APIs: covered in Phase 9 and Phase 11.
- Client-Facing Documentation And Usage Examples: covered in Phase 10.
- Final Staging Integration With Hamza Backend: covered in Phase 11.
- Dependencies On Hamza: covered in Phase 1, Phase 2, Phase 8, Phase 9, Phase 10, and Phase 11 human tasks.
- Dependencies On Ukasha: covered in Phase 0 and Phase 2.
- Open Technical Decisions Relevant To Habiba: covered in Phase 1 and Human-Only Tasks Summary.
- Expected Migration, SDK, And Documentation Deliverables: covered in Phases 2 through 12.
- Definition Of Completion For Habiba: covered in Phase 12.
- First-release guardrails from the shared contract are covered: no `usage_events.kind` extension, opaque external refs, optional reservation behavior, and no tenant-scoped call rows for unresolved inbound calls.

Overlap audit:

- This plan does not assign Hamza-owned backend runtime implementation to Habiba.
- This plan does not assign Telnyx or LiveKit provider adapter work to Habiba.
- This plan does not assign inbound/outbound call orchestration, webhook handling, reconciliation, health, or metrics runtime to Habiba.
- This plan does not assign dashboard implementation to Habiba.
- This plan keeps provider/language work with Ukasha and only requires migration-number and regression coordination.
- Habiba's only backend-facing work is database/schema support, SDK calls to `/machine/telephony/*`, mocked/staging integration validation, and documentation.

Result: final and ready to use as the agent-facing plan after Habiba approves it and the contract/migration-number gates are satisfied.
