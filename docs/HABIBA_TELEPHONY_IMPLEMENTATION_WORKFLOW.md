# Habiba Telephony Implementation Workflow

This document is Habiba's implementation workflow for the production telephony layer. It uses `TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md` and `TELEPHONY_WORKLOAD_AND_RESPONSIBILITY_DIVISION.md` as the authoritative sources.

This is not a phase plan, sprint plan, week plan, timeline, or day-by-day task list. It is the dependency-ordered workflow for Habiba's database, backend-only SDK, integration, and documentation responsibilities. Work should be performed on the `habiba` branch and later merged through a reviewed pull request into `staging`. `main` should receive telephony changes only after integration, regression, staging, and production-readiness testing.

## Non-Negotiable Boundaries

- Habiba is the only telephony developer with Supabase project access.
- Habiba owns creating, reviewing, applying, and verifying all telephony migrations.
- Habiba owns RLS policies, tenant-scoped constraints, indexes, database functions, schema verification, rollback planning, and live Supabase migration deployment.
- Hamza provides backend query, transaction, row-locking, status-transition, and repository requirements, and reviews schema compatibility.
- Do not invent database requirements that conflict with the agreed schema/API contract.
- Coordinate migration numbers with Ukasha before creating migration files because Ukasha is working on provider/language migrations in `ukasha`.
- The telephony SDK must remain backend-only.
- The SDK may accept a Telnyx API key only transiently during `connectTelnyxAccount`; it must never persist, cache, log, or return it.
- Dashboard implementation is out of scope for this workflow. Keep telephony portal response contracts safe for a future dashboard, but do not modify dashboard files.
- `@awaazlabs-uva/telephony` must use Hamza's backend telephony service and must not bypass it.
- Use mocked machine API responses while Hamza's endpoints are incomplete, then replace mocks during staging integration.
- Do not implement Telnyx provider adapters, LiveKit SIP orchestration, webhook runtime, reconciliation runtime, inbound worker resolution, outbound call execution, or backend call runtime owned by Hamza.
- Keep the system production-ready, multi-tenant, and reusable for P2F and future clients without P2F-specific assumptions.

## Shared Contract Freeze

Purpose:

Freeze the schema, API, SDK, status, error, and idempotency contracts with Hamza before dependent implementation starts. This prevents duplicate field names, incompatible route shapes, and migration churn.

Exact existing files to modify:

- None required at first.
- Later documentation may update `docs/MACHINE_AGENT_API_CONTRACT.md`, `README.md`, `client-submission_v2/sdk/README.md`, or a new shared telephony contract document if the team agrees to create one.

New files/modules to create:

- `docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md` as the shared frozen contract artifact.

Inputs and outputs:

- Inputs: Hamza's backend query/transaction requirements, Document 1 resource model, Document 2 ownership split, Ukasha's provider/language migration plan, existing API and SDK patterns.
- Outputs: frozen entity names, field names, migration order, route list, SDK method names, request/response payloads, status enums, internal event stages, error codes, idempotency rules, tenant-isolation rules, and naming rules.

Dependencies:

- `TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md`.
- `TELEPHONY_WORKLOAD_AND_RESPONSIBILITY_DIVISION.md`.
- Hamza's backend route and repository contract.
- Ukasha's provider/language migration numbering and agent runtime fields.

Database objects involved:

- `tenant_telnyx_connections`.
- `telnyx_sip_connections`.
- `telnyx_outbound_voice_profiles`.
- `telephony_phone_numbers`.
- `livekit_inbound_trunks`.
- `livekit_outbound_trunks`.
- `livekit_sip_dispatch_rules`.
- `telephony_number_orders`.
- `telephony_calls`.
- `telephony_call_events`.
- `telephony_idempotency_keys`.
- `telephony_audit_log`.
- Existing `tenants`, `agents`, `sessions`, `usage_events`, `quota_state`, and `used_nonces`.

API or SDK contracts involved:

- `/portal/telephony/*` tenant portal routes for Hamza's backend contract and future UI consumers.
- `/machine/telephony/*` backend-only SDK routes.
- Machine HMAC action strings.
- `@awaazlabs-uva/telephony` method names and TypeScript types.
- Error shape and status shape consumed by the SDK and future portal consumers.

Security requirements:

- All tenant-owned rows must be tenant-isolated with RLS and tenant-scoped constraints.
- Browser code must not receive provider secrets, HMAC secrets, LiveKit secrets, Supabase service credentials, or raw provider payloads.
- Raw provider payloads and sensitive call data need restricted storage and redacted user-facing responses.

User-facing states and errors where applicable:

- Not connected, verifying, active, degraded, action required, failed, disabled, disconnected.
- User-facing messages must be stable and clear, not raw Telnyx or LiveKit payloads.

Required tests:

- Contract tests for route payloads.
- SDK type/serialization tests.
- SDK and API contract tests.
- Schema-contract review checklist before migrations are applied.

Completion condition:

- Hamza and Habiba agree on names, payloads, statuses, errors, idempotency rules, migration sequence, and ownership boundaries.
- No dependent SDK or migration work relies on unstated assumptions.

Information or work required from Hamza:

- Final backend query/transaction contract.
- Final portal and machine route list.
- Final error-code and status mapping.
- Required row locks and unique constraints.
- Fake response examples for SDK contract tests.

## Migration Numbering And Supabase Workflow

Purpose:

Create migration files safely in the existing repository sequence without colliding with Ukasha's provider/language migrations or Hamza's backend assumptions.

Exact existing files to modify:

- `supabase/migrations/*`: add new telephony migration files only after numbers are coordinated.
- `tests/test_schema.py`: extend schema assertions after migrations exist.
- `tests/test_isolation.py` and/or `tests/test_cross_tenant_read_live.py`: extend tenant-isolation tests after schema exists.

New files/modules to create:

- New migration files under `supabase/migrations/`, using the repo's existing numbering convention after coordination. The current local sequence observed ends at `supabase/migrations/0011_session_transcript.sql`.
- Optional verification scripts if needed, for example `scripts/verify_telephony_schema.py`, but only if the team wants script-based checks.

Inputs and outputs:

- Inputs: coordinated migration numbers, agreed schema contract, Hamza's transaction/locking requirements, Ukasha's provider migration plan.
- Outputs: ordered, reviewable, reversible migration files and a clear migration application plan.

Dependencies:

- Existing schema from `supabase/migrations/0001_schema.sql`.
- Existing RLS pattern from `supabase/migrations/0002_rls.sql`.
- Existing nonce/replay table from `supabase/migrations/0004_nonces.sql`.
- Existing admin/audit and session transcript changes from later migrations.
- Supabase project access held by Habiba.

Database objects involved:

- All new telephony tables, indexes, constraints, RLS policies, optional functions, grants, and comments.

API or SDK contracts involved:

- Backend route work depends on the resulting table/field names.
- SDK types depend on the final public response fields.

Security requirements:

- Follow Supabase migration safety: verify CLI/MCP command syntax before use, avoid untracked live schema edits, and run advisors/security checks where available.
- Do not use `service_role` or secret keys in frontend code.
- Enable RLS on every tenant-owned table before granting direct access to exposed roles.
- Prefer tenant-scoped RLS policies using tenant identity, not broad `TO authenticated` without row ownership checks.
- If views are created, make them RLS-safe, for example with `security_invoker` where supported or by keeping them out of exposed schemas.
- Avoid public `SECURITY DEFINER` functions unless explicitly required and reviewed.

User-facing states and errors where applicable:

- Migration failures should not be hidden. If a migration is partial or fails verification, telephony should remain disabled/degraded until repaired.

Required tests:

- Migration ordering check.
- Fresh database schema test.
- RLS enabled test for every tenant-owned telephony table.
- Constraint/index existence tests.
- Rollback or repair-plan review.

Completion condition:

- Migration numbers are reserved with Ukasha.
- Migration files are created, reviewed by Hamza for backend compatibility, and ready to apply.
- No live Supabase change is applied without a verification and rollback plan.

Information or work required from Hamza:

- Confirmation of the final required table names and query fields.
- Confirmation of lock and transaction needs.
- Confirmation of whether any DB functions are required for atomic operations.

## Core Telephony Schema Migrations

Purpose:

Create the normalized production telephony resource model without circular relationships, duplicated LiveKit provider identifiers, or P2F-specific assumptions.

Exact existing files to modify:

- New files under `supabase/migrations/*`.
- Do not modify existing migrations unless a reviewed compatibility migration requires it.

New files/modules to create:

- One or more telephony schema migration files after numbering is coordinated.
- Optional schema comments inside migration SQL to document sensitive columns and provider-ID ownership.

Inputs and outputs:

- Inputs: frozen schema contract and Hamza's repository requirements.
- Outputs: normalized tables, foreign keys, constraints, indexes, status checks, and tenant isolation foundations.

Dependencies:

- Existing `tenants`, `agents`, `sessions`, and `quota_state`.
- Hamza's backend repository contract.
- Ukasha's migration numbering plan.

Database objects involved:

- `tenant_telnyx_connections`: tenant Telnyx API account connection and encrypted credential reference/ciphertext.
- `telnyx_sip_connections`: reusable Telnyx SIP/FQDN connection.
- `telnyx_outbound_voice_profiles`: outbound SIP readiness profile.
- `telephony_phone_numbers`: AwaazLabs-managed number inventory and nullable `assigned_agent_id`.
- `livekit_inbound_trunks`: LiveKit inbound trunk provider IDs.
- `livekit_outbound_trunks`: LiveKit outbound trunk provider IDs.
- `livekit_sip_dispatch_rules`: LiveKit SIP dispatch-rule provider IDs.
- `telephony_number_orders`: exact-number purchase/order tracking.
- `telephony_calls`: call records linked to `sessions`.
- `telephony_call_events`: internal stages, raw provider events, and restricted diagnostics.
- `telephony_idempotency_keys`: idempotent number purchase and outbound call creation.
- `telephony_audit_log`: credential, number, assignment, SIP, outbound call, and disconnection audit events.

API or SDK contracts involved:

- SDK list/read/update methods depend on these fields.
- Hamza's portal and machine routes depend on table names and FK relationships.

Security requirements:

- `tenant_id` on every tenant-owned table.
- Tenant-scoped uniqueness and FK validation.
- No cross-tenant agent or number assignment possible even if API validation regresses.
- Encrypted credential fields for Telnyx API keys and SIP secrets.
- Restricted raw payload columns for provider diagnostics.
- Data-governance fields for retention and deletion/offboarding.

User-facing states and errors where applicable:

- Phone number state must split `provisioning_status` from `routing_status`.
- Assignment is nullable `assigned_agent_id`, not a status.
- Provider and platform statuses must remain separate where provider state exists.

Required tests:

- Table existence tests.
- Required column existence tests.
- FK constraint tests.
- Tenant-scoped uniqueness tests.
- Provider-ID ownership tests proving LiveKit IDs are not duplicated into `telephony_calls`.
- Status check tests.

Completion condition:

- The schema represents each resource once: tenant Telnyx connection, Telnyx SIP connection, Outbound Voice Profile, phone number, LiveKit trunks, dispatch rule, call, and session.
- LiveKit trunk/rule provider IDs exist only on the owning resource tables.
- `telephony_calls` stores internal record references plus call-specific IDs only.

Information or work required from Hamza:

- Exact required columns for service queries.
- Required nullable vs non-nullable fields.
- Required provider-ID lookup paths.
- Confirmation of which raw provider payloads need restricted storage.

## Constraints, Indexes, Status Rules, And Idempotency

Purpose:

Make the database enforce the core production invariants: tenant isolation, one active Telnyx connection initially, reusable SIP/trunk/rule resources, idempotent provider side effects, valid statuses, and efficient routing/call lookup.

Exact existing files to modify:

- New migration files under `supabase/migrations/*`.
- `tests/test_schema.py` and telephony schema tests after migrations exist.

New files/modules to create:

- Constraint/index migration SQL.
- Optional DB helper functions only if agreed with Hamza and reviewed for RLS/security behavior.

Inputs and outputs:

- Inputs: Hamza's uniqueness, lookup, idempotency, transition, and row-lock requirements.
- Outputs: constraints and indexes that protect production behavior.

Dependencies:

- Core telephony tables.
- Status enum/check-contract.
- Hamza's repository contract.

Database objects involved:

- Partial unique index on one active `tenant_telnyx_connections` row per tenant.
- Active uniqueness for one tenant SIP connection per active Telnyx connection.
- Active uniqueness for one inbound trunk and one SIP dispatch rule per phone number.
- Active uniqueness for one outbound trunk per tenant Telnyx connection.
- Unique active `(tenant_id, e164_number)` for phone numbers.
- Unique idempotency key constraints scoped by tenant and action.
- Provider event dedupe constraints for webhook events.
- Indexes for `tenant_id`, provider IDs, `e164_number`, `assigned_agent_id`, status, timestamps, `room_name`, `livekit_sip_call_id`, and stale reconciliation scans.

API or SDK contracts involved:

- Idempotency for number purchase and outbound call creation.
- Number assignment and reassignment.
- Call list/get and order list/get.
- Webhook dedupe and reconciliation.

Security requirements:

- Constraints must prevent cross-tenant assignment even if a backend bug passes another tenant's ID.
- Public client status values should be check-constrained where practical.
- Restricted provider payload columns should not be accidentally exposed by broad tenant-facing queries.

User-facing states and errors where applicable:

- Invalid assignments become stable errors, not silent no-ops.
- Duplicate idempotency keys with matching payload return existing result; mismatched payload returns `idempotency_payload_mismatch`.
- Invalid or stale call status updates should be rejected or recorded as ignored internal events.

Required tests:

- Duplicate active connection rejection.
- Duplicate active number rejection.
- Cross-tenant assignment rejection.
- Duplicate idempotency behavior.
- Provider event dedupe behavior.
- Direction-specific public call status transition tests where DB-enforced.
- Index existence tests for critical SDK/backend queries.

Completion condition:

- The database protects the invariants the backend relies on.
- Hamza can implement repository operations without adding defensive ad hoc checks for every invariant.

Information or work required from Hamza:

- Exact idempotency key scope.
- Canonical request hash storage expectations.
- Status transition enforcement preference: DB check/function, app layer only, or both.
- Query plan needs for high-frequency routing and call lookups.

## RLS, Grants, And Tenant Isolation Verification

Purpose:

Ensure every tenant-owned telephony table is protected by RLS and cannot leak data across tenants through Supabase/Postgres access paths.

Exact existing files to modify:

- New RLS migration files under `supabase/migrations/*`.
- `tests/test_isolation.py`.
- `tests/test_cross_tenant_read_live.py` if live verification is maintained for telephony.
- `tests/test_schema.py`.

New files/modules to create:

- Telephony RLS verification tests, for example `tests/test_telephony_rls.py`.
- Optional verification script if the team wants a manual Supabase smoke check.

Inputs and outputs:

- Inputs: final table list, tenant identity model, current `auth.jwt() ->> 'tenant_id'` pattern, and tenant-facing API access shape.
- Outputs: RLS policies, grants, and verification evidence.

Dependencies:

- Core schema migrations.
- Supabase project access.
- Existing RLS policy model from `supabase/migrations/0002_rls.sql`.

Database objects involved:

- Every telephony table listed above.
- Existing `tenants`, `agents`, `sessions`, and `quota_state` FK paths.
- Any views/functions if introduced.

API or SDK contracts involved:

- Future portal consumers read via `/portal/telephony/*`.
- Machine SDK reads/writes via `/machine/telephony/*`.
- Backend trusted service writes through Hamza-owned route/service code.

Security requirements:

- Enable RLS on every tenant-owned telephony table.
- Use tenant-scoped `USING` and `WITH CHECK` policies where direct inserts/updates are ever granted.
- Do not rely on `TO authenticated` alone.
- Avoid user-editable JWT metadata for authorization decisions.
- Do not expose raw provider payloads or encrypted credential columns through tenant-facing policies.
- If direct Data API access is not needed, avoid grants beyond what the backend deployment requires.

User-facing states and errors where applicable:

- Cross-tenant access must look like not found or unauthorized without revealing ownership by another tenant.

Required tests:

- Tenant A cannot select Tenant B rows from every telephony table.
- Tenant A cannot assign Tenant B agent or number.
- Tenant A cannot read restricted provider payloads.
- Update policies include both visibility and ownership checks where applicable.
- Unknown tenant/unauthorized tenant behavior remains stable.

Completion condition:

- RLS is enabled and verified on every tenant-owned telephony table.
- No tenant-facing query leaks another tenant's connection, number, order, SIP resource, call, event, or audit record.

Information or work required from Hamza:

- Which tables the backend writes as trusted service vs tenant-scoped role.
- Which fields are returned by portal/machine APIs so RLS and grants do not overexpose sensitive columns.

## Data Governance, Audit, Retention, And Deletion

Purpose:

Model telephony data as sensitive data. Phone numbers, recipient details, call context, transcripts, summaries, provider payloads, and error data need retention, deletion, export, redaction, and audit controls from the start.

Exact existing files to modify:

- New migration files under `supabase/migrations/*`.
- Existing session export behavior only if telephony call exports later reuse the same data-governance pattern.
- Documentation files after contracts stabilize.

New files/modules to create:

- Data-governance columns in telephony migrations.
- `telephony_audit_log` table.
- Optional tests such as `tests/test_telephony_data_governance.py`.

Inputs and outputs:

- Inputs: retention policy decision, tenant-offboarding policy, export permissions, restricted-payload access policy.
- Outputs: fields and constraints that support safe retention/deletion/export/access audit.

Dependencies:

- Product/architecture decisions for retention and export.
- Hamza's restricted provider payload storage requirements.
- Future portal call-record and transcript display requirements.

Database objects involved:

- `telephony_calls`: recipient, call context, transcript link/session link, retention/deletion metadata.
- `telephony_call_events`: restricted provider payloads.
- `telephony_number_orders`: restricted provider error payloads.
- `telephony_audit_log`: access and mutation audit events.
- `sessions`: linked transcript/summary data.

API or SDK contracts involved:

- Call record list/get.
- Transcript/summary access.
- Export operations if exposed.
- Number/credential/audit views.

Security requirements:

- Separate operational metadata from client-visible call data.
- Encrypt sensitive records at rest where supported by the chosen design.
- Restrict raw provider payload access to trusted backend/admin diagnostics.
- Redact phone numbers, recipient details, secrets, prompts, call context, provider payloads, and transcripts in logs and user-facing errors where policy requires.
- Audit credential changes, number purchases/imports, assignment changes, SIP changes, outbound calls, number disconnections, transcript access, call-record access, exports, and restricted-payload access.
- Prevent secrets from entering transcripts, prompts, summaries, or call context.
- Avoid indefinite retention by default.

User-facing states and errors where applicable:

- `retention_policy_violation`.
- `export_not_authorized`.
- `restricted_payload_access_denied`.
- Deleted or redacted call records should remain understandable without exposing removed sensitive data.

Required tests:

- Retention/deletion field behavior.
- Tenant offboarding behavior.
- Export access-control tests.
- Restricted provider payload access denied for tenant-facing routes.
- Transcript/call-record access audit tests.
- Log and user-facing redaction tests where testable.

Completion condition:

- The schema and API contracts can support retention, deletion, export, audit, and restricted diagnostics without later table redesign.

Information or work required from Hamza:

- Which raw provider payloads need to be stored for debugging.
- Which backend routes expose transcripts, summaries, events, and diagnostics.
- Operational metadata needed for reconciliation and support.

## Migration Application, Verification, And Rollback Safety

Purpose:

Apply the migrations to Supabase safely, prove they work, and keep a rollback/recovery path if anything fails.

Exact existing files to modify:

- `supabase/migrations/*`.
- Verification tests under `tests/`.
- Optional migration runbook documentation.

New files/modules to create:

- Optional `docs/TELEPHONY_MIGRATION_RUNBOOK.md`.
- Optional verification script if the team wants repeatable checks.

Inputs and outputs:

- Inputs: reviewed migration files, Supabase project access, environment-specific credentials, test tenants, rollback plan.
- Outputs: applied migrations, verified schema, verified RLS, verified indexes/constraints, rollback notes.

Dependencies:

- Hamza review of migration compatibility.
- Ukasha migration-number coordination.
- Supabase CLI/MCP availability and current command verification.

Database objects involved:

- All new telephony objects plus existing tables linked by FK.

API or SDK contracts involved:

- Backend can only switch from mocks/local fixtures to real repository integration after schema is available.

Security requirements:

- Do not commit or paste Supabase secrets into docs or code.
- Verify migrations in an isolated/local or staging-safe path before production application.
- Run Supabase advisors/security checks where available.
- Review any grants, RLS policies, views, functions, triggers, and indexes before live deployment.

User-facing states and errors where applicable:

- Until verification passes, telephony APIs should report disabled/unavailable state rather than enabling partial operations.

Required tests:

- Fresh schema migration test.
- Migration list/history verification.
- RLS isolation checks.
- Constraint violation tests.
- Rollback or forward-fix drill where practical.

Completion condition:

- Supabase migrations are applied and verified by Habiba.
- Hamza confirms backend compatibility against the applied schema.
- Migration rollback or recovery notes are documented.

Information or work required from Hamza:

- Confirmation that repository tests pass against the applied schema.
- Any query performance/index feedback after backend integration.

## Backend-Only `@awaazlabs-uva/telephony` SDK Structure

Purpose:

Create the backend-only telephony SDK package that lets client backends call AwaazLabs telephony APIs without embedding browser secrets or Telnyx credentials.

Exact existing files to modify:

- None in `@awaazlabs-uva/voice`.
- Avoid changing `sdk-server/src/index.ts` unless a shared signing helper is intentionally extracted later.
- `client-submission_v2/sdk/README.md` should be updated when the telephony package is included in deliverables.

New files/modules to create:

- `telephony/package.json`.
- `telephony/tsconfig.json`.
- `telephony/README.md`.
- `telephony/src/index.ts`.
- `telephony/src/signing.ts`.
- `telephony/src/types.ts`.
- Optional `telephony/src/errors.ts`.
- Optional `telephony/src/__tests__/...` or separate SDK test path, matching repo practice.
- `client-submission_v2/sdk/@awaazlabs-uva/telephony/` if this package is included in client deliverables.

Inputs and outputs:

- Inputs: `tenantId`, `tenantSecret`, `baseUrl`, optional non-auth `extraHeaders`, method params, idempotency keys, transient Telnyx API key during connection.
- Outputs: typed SDK responses, stable SDK errors, signed machine API requests.

Dependencies:

- Existing HMAC signing pattern in `sdk-server/src/index.ts`.
- `docs/MACHINE_AGENT_API_CONTRACT.md` canonical JSON/action binding model.
- Hamza's final `/machine/telephony/*` route contract and action strings.

Database objects involved:

- None directly. The SDK must never connect to Supabase.

API or SDK contracts involved:

- `connectTelnyxAccount`.
- `rotateTelnyxAccountKey`.
- `reverifyTelnyxAccount`.
- `disconnectTelnyxAccount`.
- `getConnectionStatus`.
- `listTelnyxOwnedNumbers`.
- `listManagedPhoneNumbers`.
- `importTelnyxNumber`.
- `syncTelnyxOwnedNumbers`.
- `getTelnyxNumberDrift`.
- `searchAvailableNumbers`.
- `reserveNumber`.
- `purchaseNumber`.
- `getNumberOrderStatus`.
- `assignAgentToNumber`.
- `unassignAgentFromNumber`.
- `upsertTelnyxSipConnection`.
- `verifyTelnyxSipConnection`.
- `upsertTelnyxOutboundVoiceProfile`.
- `verifyTelnyxOutboundVoiceProfile`.
- `configureNumberRouting`.
- `configureOutboundTrunk`.
- `getOutboundReadiness`.
- `createOutboundCall`.
- `getCallStatus`.
- `listCallRecords`.
- `disableNumber`.

Security requirements:

- Package must be Node/backend-only.
- It must use Node crypto/HMAC signing and must not ship browser-oriented code.
- `tenantSecret` is used locally to compute signatures and is never sent.
- Telnyx API key is accepted only as a method parameter during account connection/rotation and must not be persisted in SDK instance state, logs, caches, or error objects.
- Auth headers cannot be overridden by `extraHeaders`.
- Errors must not include secrets, signatures, raw Telnyx payloads, or raw provider credentials.

User-facing states and errors where applicable:

- SDK errors should expose stable `status`, `code`, and redacted `message`.
- Idempotency mismatch, not connected, outbound not ready, restricted destination, and action-required states should be typed.

Required tests:

- Canonical JSON hashing matches backend expectations.
- HMAC headers include tenant ID, timestamp, nonce, and signature.
- Action strings are fixed per method.
- `extraHeaders` cannot override auth headers.
- Telnyx API key is not retained on the client instance after request construction.
- Error mapping returns stable SDK errors.
- Type tests or build tests for public interfaces.

Completion condition:

- `@awaazlabs-uva/telephony` can build independently like `@awaazlabs-uva/agents`.
- It has no browser-secret path and calls only `/machine/telephony/*`.
- Mocked route contract tests pass before Hamza endpoints are complete.

Information or work required from Hamza:

- Final machine route paths.
- Final machine action strings.
- Final request/response payloads.
- Stable error format.
- Idempotency-key placement: body field, header, or agreed convention.

## Telephony SDK Contract Tests And Client Deliverable Package

Purpose:

Make the telephony SDK portable for client handoff and prove it can be installed, built, and used from a backend project.

Exact existing files to modify:

- `client-submission_v2/sdk/README.md`.
- `client-submission_v2/README.md` if the higher-level bundle explains all packages.
- Existing package docs only where package relationship wording needs an update.

New files/modules to create:

- `client-submission_v2/sdk/@awaazlabs-uva/telephony/`.
- `client-submission_v2/sdk/@awaazlabs-uva/telephony/package.json`.
- `client-submission_v2/sdk/@awaazlabs-uva/telephony/README.md`.
- `client-submission_v2/sdk/@awaazlabs-uva/telephony/src/index.ts`.
- `client-submission_v2/sdk/@awaazlabs-uva/telephony/dist/` after build, if deliverable includes compiled artifacts.
- Package tarball if the existing deliverable pattern continues.

Inputs and outputs:

- Inputs: built telephony package, README examples, local package path, backend-only usage sample.
- Outputs: clean client-deliverable package and install/build evidence.

Dependencies:

- Telephony SDK source package.
- Hamza's final API contract.
- Existing deliverable structure under `client-submission_v2/sdk/`.

Database objects involved:

- None directly.

API or SDK contracts involved:

- All backend-only SDK methods listed above.
- Existing relationship with `@awaazlabs-uva/voice` and `@awaazlabs-uva/agents`.

Security requirements:

- Deliverable docs must say `@awaazlabs-uva/telephony` is backend-only.
- Telnyx API key and tenant HMAC secret must never enter browser code.
- Examples must keep secrets in server environment variables only.

User-facing states and errors where applicable:

- Documentation should show stable error-code handling rather than provider payload logging.

Required tests:

- `npm run build` for the telephony package.
- `npm run lint` or `tsc --noEmit` if provided.
- Clean install from local tarball/package path.
- Import smoke test from Node backend context.
- No browser bundle example imports the telephony SDK.

Completion condition:

- Client deliverable includes the telephony SDK only if it is buildable, documented, and backend-only.
- Package docs explain how it relates to `@awaazlabs-uva/voice` and `@awaazlabs-uva/agents`.

Information or work required from Hamza:

- Final API examples.
- Final error codes.
- Final staging base URL guidance.
- Confirmation that SDK method calls match backend action strings.

## Dashboard Implementation Out Of Scope

Purpose:

Keep Habiba's current workflow aligned with `TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md`: dashboard changes are deferred. Habiba should not create telephony dashboard routes, UI components, navigation, SWR keys, or dashboard-specific mocks in this implementation pass.

Exact existing files to modify:

- None under `dashboard/*`.

New files/modules to create:

- None under `dashboard/*`.

Inputs and outputs:

- Inputs: final portal response contracts only when needed for API documentation or future handoff notes.
- Outputs: no dashboard code changes.

Dependencies:

- Hamza's portal route contract may be documented for future consumers, but it does not unblock Habiba's current database or SDK work.

Database objects involved:

- None directly.

API or SDK contracts involved:

- `/portal/telephony/*` remains Hamza's tenant-portal API surface and a future UI contract.
- `/machine/telephony/*` remains the active backend-only SDK surface for Habiba's current implementation.

Security requirements:

- Future dashboard work must keep Telnyx API keys, HMAC secrets, LiveKit secrets, Supabase service credentials, raw provider payloads, and encrypted credential fields out of browser code and storage.
- This workflow should not introduce dashboard code paths that handle provider credentials.

Required tests:

- No new dashboard telephony tests are required in this workflow.
- Existing dashboard tests/builds should remain unchanged unless unrelated work touches them.

Completion condition:

- Habiba's branch contains no telephony dashboard implementation.
- Dashboard work remains a deferred future phase that must use the same backend telephony service when it is eventually implemented.

Information or work required from Hamza:

- None for dashboard implementation in this workflow.

## SDK Integration With Mocked Then Real APIs

Purpose:

Let Habiba build the backend-only SDK while Hamza's backend endpoints are incomplete, then replace mocks with real staging API integration without rewriting the SDK surface.

Exact existing files to modify:

- Telephony SDK tests.
- Mock fixture files.

New files/modules to create:

- `telephony/src/__tests__/` or equivalent SDK test files.
- `tests/fixtures/telephony/` or an SDK-local fixture path if fixtures are useful.
- Optional `docs/TELEPHONY_STAGING_VALIDATION_CHECKLIST.md`.

Inputs and outputs:

- Inputs: Hamza fake response examples, final staging endpoints, test tenant credentials, test phone numbers where approved.
- Outputs: SDK passing against mocks, then passing against staging machine endpoints.

Dependencies:

- Hamza's route contract.
- Applied Supabase migrations.
- Backend staging deployment.
- Explicit approval for real Telnyx/LiveKit staging tests.

Database objects involved:

- All telephony objects indirectly through backend integration.

API or SDK contracts involved:

- Every machine telephony route used by the SDK. Portal route shapes may be documented for future consumers but are not implemented by Habiba.

Security requirements:

- Mocks must not contain real Telnyx API keys, HMAC secrets, LiveKit secrets, Supabase credentials, real phone numbers unless approved, or raw provider payloads copied from production.
- Staging tests with live providers must be explicitly gated and kept out of default CI.

User-facing states and errors where applicable:

- Tests should cover successful, not connected, action-required, degraded, failed, auth failure, and idempotency states.

Required tests:

- SDK method contract tests.
- Staging SDK smoke: connection status, managed numbers list, search mock/live-safe path, order status, assignment, readiness, and call records.
- Regression: existing agent SDK and browser voice SDK behavior remains unchanged.

Completion condition:

- Mocks are isolated and removable.
- Real staging integration uses the same SDK code paths.
- No temporary mock-only architecture remains.

Information or work required from Hamza:

- Fake response fixtures for SDK contract tests.
- Endpoint availability matrix.
- Staging API base URL.
- Test tenant and approved test resources.
- Confirmation when mocks should be replaced.

## Client-Facing Documentation And Usage Examples

Purpose:

Explain how clients use the three-package model without leaking secrets or confusing browser and backend responsibilities.

Exact existing files to modify:

- `README.md`.
- `docs/MACHINE_AGENT_API_CONTRACT.md` or a new telephony machine API contract doc.
- `client-submission_v2/README.md`.
- `client-submission_v2/sdk/README.md`.
- `telephony/README.md`.
- `client-submission_v2/sdk/@awaazlabs-uva/telephony/README.md` if deliverable copy exists.

New files/modules to create:

- Optional `docs/TELEPHONY_CLIENT_INTEGRATION_GUIDE.md`.
- Optional `docs/TELEPHONY_API_REFERENCE.md`.
- Optional backend-only example under client deliverables if agreed.

Inputs and outputs:

- Inputs: final SDK methods, API routes, error codes, backend-only security rules, and staging validation result.
- Outputs: client-ready docs and examples.

Dependencies:

- SDK implementation.
- Hamza's final backend API behavior.
- Security and data-governance decisions.

Database objects involved:

- None directly.

API or SDK contracts involved:

- `@awaazlabs-uva/voice`: browser WebRTC session SDK.
- `@awaazlabs-uva/agents`: backend-only agent management SDK.
- `@awaazlabs-uva/telephony`: backend-only telephony SDK.
- `/machine/telephony/*` backend API routes.

Security requirements:

- Docs must state that `@awaazlabs-uva/telephony` and `@awaazlabs-uva/agents` are backend-only.
- Telnyx API keys, tenant HMAC secrets, LiveKit secrets, and Supabase secrets must never enter frontend bundles.
- Telnyx API key is only submitted transiently during connection/rotation and is not needed for later SDK calls.
- Examples should use environment variable placeholders only, never real values.

User-facing states and errors where applicable:

- Include examples for not connected, action required, outbound not ready, idempotency mismatch, number unavailable, and permission failure.

Required tests:

- Documentation example compile/syntax checks where practical.
- Clean install and import smoke for SDK package.
- Review for accidental real secrets.
- Client-developer walkthrough after staging integration.

Completion condition:

- A client backend developer can understand which SDK to use where and can call telephony APIs without exposing secrets.

Information or work required from Hamza:

- Final backend route behavior.
- Final error-code table.
- Staging examples and approved workflow examples.
- Operational caveats for real Telnyx/LiveKit usage.

## Final Staging Integration With Hamza Backend

Purpose:

Replace mocks with Hamza's real backend endpoints, verify the database-backed flow, and confirm the SDK uses the same telephony service contract as the backend.

Exact existing files to modify:

- Telephony SDK tests/config examples.
- Client-facing docs.
- No backend runtime code owned by Hamza.

New files/modules to create:

- Optional staging validation checklist.
- Optional final integration notes document.

Inputs and outputs:

- Inputs: applied Supabase migrations, Hamza backend deployment, machine API base URL, test tenant, approved Telnyx/LiveKit staging resources.
- Outputs: staging validation evidence and resolved contract mismatches.

Dependencies:

- Hamza backend routes deployed or running in staging/local integration mode.
- Habiba migrations applied and verified.
- Ukasha provider registry integration not broken.
- Explicit approval for real provider tests.

Database objects involved:

- All telephony tables and existing `sessions` linkage.

API or SDK contracts involved:

- All SDK machine routes.
- Existing `/machine/agents` and browser voice-session regressions.

Security requirements:

- No real provider credentials in logs, fixtures, docs, or SDK state.
- Tenant isolation must be rechecked against staging data.
- Live provider tests must use approved staging resources and be kept separate from default CI.

User-facing states and errors where applicable:

- Validate connection, inventory, search, purchase/order status where approved, assignment, SIP/routing readiness, outbound readiness, call records, failures, degraded states, and auth failure.

Required tests:

- SDK integration smoke against staging backend.
- Tenant isolation verification.
- API-key non-retention and secret non-return.
- Retention/deletion behavior where implemented.
- Regression tests proving existing WebRTC and Urdu agent behavior remains unchanged.

Completion condition:

- Mocks are removed or clearly isolated from production/staging paths.
- SDK works against Hamza's backend using the same telephony service.
- Staging validation issues are either fixed or recorded as explicit blockers.

Information or work required from Hamza:

- Endpoint readiness.
- Backend deployment URL.
- Test tenant setup.
- Known backend limitations.
- Provider staging test approval and expected results.

## Dependencies On Hamza

- Final backend query, transaction, row-locking, and status-transition requirements.
- Final portal and machine API route list.
- Final request/response payloads.
- Final machine HMAC action strings.
- Stable platform error codes and redacted message format.
- Fake response fixtures for SDK mocks.
- Backend route availability for staging integration.
- Confirmation of which call events and provider payloads are tenant-visible, admin-only, or restricted.
- Outbound readiness behavior for SIP, Outbound Voice Profile, destination policies, limits, and verification restrictions.
- Staging backend URL, test tenant details, and approved provider test workflow.

Habiba should not implement Hamza's Telnyx adapter, LiveKit SIP orchestration, backend call runtime, inbound worker resolver, outbound execution, webhook runtime, or reconciliation runtime.

## Dependencies On Ukasha

- Migration-number coordination for provider/language changes in `ukasha`.
- Final provider/language fields that may touch `agents`, `worker/config.py`, `tenant_portal_api/app.py`, `tenant_portal_api/queries.py`, and SDK types.
- Final `AgentRuntimeConfig` shape and provider registry contract.
- Confirmation that telephony should only consume the final agent runtime config and must not choose STT/LLM/TTS providers.
- Regression proof that existing Urdu Gladia/Gemini/Uplift WebRTC behavior remains intact.

## Open Technical Decisions Relevant To Habiba

- Final secret encryption mechanism for Telnyx API keys and SIP secrets.
- Whether telephony call minutes extend `usage_events.kind` or use dedicated telephony billing/usage tables.
- Whether telephony routes remain inside `tenant_portal_api` or move to a separate deployed FastAPI service.
- Final first-release countries, number types, features, and destination policy labels exposed through stable API/SDK responses.
- Whether Telnyx number reservation is supported for the selected markets.
- Final Outbound Voice Profile policy summary fields safe for SDK responses.
- Final Telnyx webhook coverage and which raw payloads must be retained as restricted diagnostics.
- Retention periods, export permissions, tenant-offboarding behavior, and restricted provider-payload access policy.
- Whether failed inbound calls with no tenant resolution live in a restricted platform table or only in backend logs/admin diagnostics.
- Whether DB status transitions are enforced by constraints/functions, app layer only, or both.
- Whether client deliverables include `@awaazlabs-uva/telephony` source, compiled `dist`, tarball, or all three.

## Expected Migration, SDK, And Documentation Deliverables

- Coordinated telephony migration files under `supabase/migrations/*`.
- RLS policies for every tenant-owned telephony table.
- Tenant-scoped FKs, uniqueness constraints, status checks, idempotency constraints, audit-log table, data-governance fields, and indexes.
- Migration application and verification evidence from Supabase.
- Rollback or forward-fix migration safety notes.
- Backend-only `@awaazlabs-uva/telephony` package with types, methods, HMAC signing, errors, tests, and README.
- Client-deliverable telephony SDK package copy if approved.
- SDK integration tests and staging validation notes.
- Client-facing integration guide and examples.

## Definition Of Completion For Habiba

Habiba's implementation is complete when:

- Work is implemented on the `habiba` branch and is ready for reviewed PR into `staging`.
- Migration numbers were coordinated with Ukasha before files were created.
- All telephony Supabase migrations are created, applied by Habiba, verified, and reviewed by Hamza for backend compatibility.
- Every tenant-owned telephony table has RLS, tenant-scoped constraints, required indexes, and verified isolation.
- Idempotency, audit, data-governance, retention, deletion/offboarding, export/access, and restricted-payload fields are in place according to the agreed contract.
- `@awaazlabs-uva/telephony` is implemented as a backend-only SDK with HMAC signing, typed methods, stable errors, tests, and docs.
- The SDK never persists, caches, logs, or returns Telnyx API keys.
- Mocked API responses are replaced or isolated before staging signoff.
- SDK staging integration passes against Hamza's backend.
- Existing agents, credentials, usage, sessions, WebRTC, and Urdu pipeline behavior remains unchanged.
- Client-facing docs explain the three-package model and keep all secrets backend-only.
- No Hamza-owned backend runtime, provider adapter, LiveKit SIP orchestration, webhook runtime, or reconciliation runtime was reassigned to Habiba.
