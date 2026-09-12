# Telephony Workload And Responsibility Division

This document divides the production telephony implementation between Hamza and Habiba. It uses `TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md` as the authoritative technical source and does not replace that architecture plan.

## 1. Purpose And Scope

The objective is to add a production-ready, reusable, multi-tenant telephony layer to the AwaazLabs Voice-Agent SDK architecture. The feature must support P2F and future AwaazLabs clients without P2F-specific assumptions, temporary shortcuts, or a test-only design.

The telephony layer covers tenant Telnyx account connection, secure credential handling, Telnyx number inventory, exact number search/reservation/purchase, Telnyx SIP/FQDN connection, Telnyx Outbound Voice Profile readiness, LiveKit SIP trunks and dispatch rules, inbound call routing, outbound call orchestration, call records, status handling, quotas, idempotency, reconciliation, security, audit, and data governance.

Existing and planned packages:

- `@awaazlabs-uva/voice`: existing browser voice-session SDK. It remains the frontend/browser WebRTC package and must not hold provider, HMAC, LiveKit, or database secrets.
- `@awaazlabs-uva/agents`: existing backend-only agent-management SDK. It manages agent create/list/update through the machine API and HMAC signing.
- `@awaazlabs-uva/telephony`: planned backend-only SDK. It will manage Telnyx connection, phone numbers, SIP readiness, outbound calls, call lookup, and related telephony operations through AwaazLabs telephony APIs.

`@awaazlabs-uva/telephony` must use the AwaazLabs telephony backend service and must not bypass it. Dashboard implementation is out of scope for the current telephony workflow; any future dashboard work must use the same backend service and must not implement separate telephony business logic.

## 2. Shared Decisions Required Before Implementation

Hamza and Habiba should freeze a shared API and schema contract before either person begins dependent implementation. Use `docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md` as the shared contract artifact derived from `TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md`, covering schema, API, SDK, status, error, and worker boundary rules.

Contracts to agree before coding:

- Database entity and field names, including `tenant_telnyx_connections`, `telnyx_sip_connections`, `telnyx_outbound_voice_profiles`, `telephony_phone_numbers`, `livekit_inbound_trunks`, `livekit_outbound_trunks`, `livekit_sip_dispatch_rules`, `telephony_number_orders`, `telephony_calls`, `telephony_call_events`, `telephony_idempotency_keys`, and `telephony_audit_log`.
- Migration sequence and migration-number allocation, coordinated with Ukasha's provider/language migrations under `supabase/migrations/*`.
- Portal API routes under `/portal/telephony/*`.
- Machine API routes under `/machine/telephony/*`.
- Request and response payloads for Telnyx connection, number inventory, number search, reservation, purchase, order status, SIP readiness, Outbound Voice Profile readiness, trunk/rule readiness, outbound calls, call records, and call events.
- SDK method names and TypeScript types for `@awaazlabs-uva/telephony`.
- Public status enums for calls, numbers, orders, SIP connections, Outbound Voice Profiles, trunks, and dispatch rules.
- Internal event stages stored in `telephony_call_events`.
- Stable platform error codes.
- Idempotency requirements for number purchase, outbound call creation, and retryable provider-side side effects.
- Tenant-isolation rules, including RLS, tenant-scoped foreign keys, uniqueness constraints, and cross-tenant assignment prevention.
- Naming rules for Telnyx, LiveKit, and AwaazLabs IDs, especially avoiding ambiguous names such as `connection_id`, `trunk_id`, or `dispatch_id`.
- API versioning and backward-compatibility rules.
- Worker integration boundary with Ukasha's provider registry work: provider/language selection remains Ukasha's responsibility; telephony owns number provisioning, SIP routing, call orchestration, and telephony statuses.

Access constraint:

- Habiba has Supabase project and database environment access.
- Hamza does not have Supabase project access.
- Habiba owns all database implementation, migration deployment, RLS, indexes, tenant-scoped constraints, database functions, schema verification, and rollback planning.
- Hamza provides database requirements, required fields, query patterns, and backend transaction needs.
- Hamza reviews migration designs for compatibility with backend services but must not apply migrations or change the live Supabase project.
- Hamza can build backend logic against the agreed database contract, mocks, local fixtures, and fake adapters while Habiba completes actual migrations.

## 3. Overall Workstreams

| Workstream | Primary owner | Supporting/reviewing owner | Main dependency | Expected high-level output |
|---|---|---|---|---|
| Architecture and contract finalization | Hamza + Habiba | Ukasha for provider boundary | `TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md` | Frozen schema/API/SDK/status/error contract |
| Database and Supabase implementation | Habiba | Hamza reviews backend compatibility | Final schema contract and migration numbering | Applied, verified, tenant-isolated Supabase schema |
| Telnyx account and credential management | Hamza | Habiba for DB fields and SDK contract | Encrypted credential schema | Backend connection, rotation, reverification, disconnect services |
| Telnyx number inventory, search, reservation and purchase | Hamza | Habiba for DB/API/SDK contract | Telnyx connection and number/order schema | Number inventory/import/sync/drift/search/purchase backend |
| Telnyx SIP/FQDN connection | Hamza | Habiba for schema and SDK contract | Telnyx connection schema | Tenant SIP connection service and readiness state |
| Telnyx Outbound Voice Profile | Hamza | Habiba for schema and SDK contract | Telnyx SIP connection contract | Outbound profile association and readiness service |
| LiveKit inbound trunks, outbound trunks and SIP dispatch rules | Hamza | Habiba for schema and status contract | Telnyx SIP/profile readiness | Long-lived trunk/rule orchestration and reconciliation |
| Telephony backend service and APIs | Hamza | Habiba for SDK/API contract | Shared API contract and DB availability | Portal and machine telephony backend routes |
| Inbound call routing | Hamza | Habiba for DB constraints and call records | LiveKit SIP attributes and phone-number routing schema | Inbound resolver, failed-call cleanup, session/call linking |
| Outbound call orchestration | Hamza | Habiba for SDK/API contract | Outbound profile and trunk readiness | Idempotent outbound call service and status handling |
| Quota, idempotency and reconciliation | Hamza | Habiba for DB constraints and verification | `quota_state`, `sessions`, telephony tables | Exactly-once release, retries, reconciliation jobs |
| Backend-only telephony SDK | Habiba | Hamza reviews API compatibility | Frozen machine API contract | `@awaazlabs-uva/telephony` package with types/tests/docs |
| Future dashboard telephony experience | Deferred | Hamza + Habiba provide future-safe API/schema contracts | Stable portal API contract | No dashboard implementation in this workflow |
| Logs, metrics, health and admin diagnostics | Hamza | Habiba for DB and restricted-data schema | Backend service and event schema | Structured logs, tenant health, provider metrics, diagnostics |
| Security, data governance and audit controls | Habiba + Hamza | Shared review | Schema/API contracts and retention policy | Encryption, redaction, retention, access audit, tenant offboarding |
| Tests, staging validation and documentation | Habiba + Hamza | Ukasha for provider regression overlap | Implemented backend/schema/SDK slices | Contract, integration, E2E, staging, and client-facing docs |

## 4. Habiba Responsibilities

Habiba is the primary owner for all database implementation, SDK packaging, and client-facing integration documentation.

### Database And Supabase

Habiba owns:

- All telephony migration files under `supabase/migrations/*`.
- Applying migrations to Supabase.
- RLS policies for every tenant-owned telephony table.
- Tenant-scoped foreign keys and uniqueness constraints.
- Indexes for routing, call lookup, event dedupe, idempotency, and API reads.
- Status and transition constraints where implemented in the database.
- Idempotency tables and constraints.
- Audit-log tables.
- Data-governance fields for retention, deletion/offboarding, export, transcript/call access audit, and restricted provider payload access.
- Database verification and rollback planning.
- Migration numbering coordination with Ukasha's provider/language migrations in `ukasha`.

Hamza should provide backend query needs, transaction boundaries, row-locking requirements, and required fields. Habiba owns the actual database workflow and live Supabase project changes.

### Backend-Only Telephony SDK

Habiba owns:

- Creating `@awaazlabs-uva/telephony`.
- SDK types and public method interfaces.
- HMAC request signing using the same backend-only pattern as `sdk-server/src/index.ts`.
- SDK error mapping to stable platform error codes.
- SDK contract tests.
- SDK README and usage examples.
- Client-deliverable package copy under `client-submission_v2/sdk/@awaazlabs-uva/telephony/` if required.

The SDK remains backend-only. It may submit a Telnyx API key transiently during account connection, but it must never persist, cache, log, or return raw provider credentials.

### Dashboard

Dashboard implementation is deferred and out of scope for this workflow.

Habiba does not own telephony dashboard routes, navigation, UI components, SWR keys, or dashboard-specific mocks in the current implementation pass. Any future dashboard work must use Hamza's backend telephony API and must keep provider credentials and raw provider payloads out of browser code and storage.

### Integration And Client-Facing Documentation

Habiba owns:

- SDK-to-machine-API integration.
- Public integration guides.
- Client examples.
- Final integration validation from a client-developer perspective.
- Documentation that explains the relationship between `@awaazlabs-uva/voice`, `@awaazlabs-uva/agents`, and `@awaazlabs-uva/telephony`.

Detailed Habiba implementation steps belong in a separate Habiba workflow document.

## 5. Hamza Responsibilities

Hamza is the primary owner for the telephony backend service, provider adapters, LiveKit SIP orchestration, call orchestration, and backend runtime behavior. Hamza does not own applying live Supabase migrations.

### Telephony Backend Service

Hamza owns:

- Telnyx API adapter.
- Telnyx connection verification and credential lifecycle service.
- Number inventory, import, sync, and drift service.
- Available-number search.
- Number reservation and purchase orchestration.
- Number-order status and reconciliation.
- Telnyx SIP/FQDN connection management.
- Telnyx Outbound Voice Profile management and outbound readiness.
- LiveKit SIP adapter.
- Long-lived inbound and outbound trunk management.
- LiveKit SIP dispatch-rule management.
- Portal and machine telephony backend routes in the agreed route structure.
- Stable provider-to-platform error mapping.

### Inbound Call Routing

Hamza owns:

- Reading LiveKit SIP attributes such as `sip.callID`, `sip.callIDFull`, `sip.trunkPhoneNumber`, `sip.trunkID`, and `sip.ruleID`.
- Resolving number, tenant, assigned agent, trunk records, and dispatch-rule records from AwaazLabs-owned database rows.
- Validating routing identifiers before any agent session starts.
- Creating or linking `telephony_calls` and `sessions` through the agreed DB contract.
- Preventing multiple workers from handling the same SIP call.
- Failed inbound-call cleanup for unknown numbers, unassigned numbers, suspended tenants, routing mismatches, quota failures, agent-load failures, and provider-pipeline start failures.
- Ensuring `worker/main.py` changes stay minimal and do not fork the STT/LLM/TTS pipeline.

### Outbound Call Orchestration

Hamza owns:

- Tenant, agent, phone-number, routing-readiness, Outbound Voice Profile, destination, spending, concurrency, and verification checks.
- Idempotent outbound call creation.
- LiveKit room/session orchestration independent of browser `/v1/session`.
- LiveKit agent dispatch and `livekit_agent_dispatch_id` handling.
- Outbound SIP participant/call creation through the reusable outbound trunk.
- Direction-specific status transitions and raw LiveKit SIP participant status handling.
- Failure handling, quota release, and usage-recording hooks.

### Quota, Idempotency, Reconciliation, Health And Diagnostics

Hamza owns backend runtime logic for:

- Atomic concurrency/quota reservation and exactly-once release.
- Idempotency handling for outbound calls and provider-side side effects.
- Reconciliation jobs for orders, calls, trunks, dispatch rules, Outbound Voice Profiles, and quota.
- Structured backend logs with redaction.
- Provider availability metrics.
- Tenant Telnyx connection health.
- SIP routing health.
- Global readiness checks that do not fail the whole service for one tenant's provider issue.
- Admin diagnostics data surfaced through backend APIs.

Habiba owns the database tables/constraints that support these flows and future restricted tenant/admin display requirements.

### Backend Tests And Technical Documentation

Hamza owns:

- Backend unit and integration tests using fake Telnyx and LiveKit adapters by default.
- Inbound routing tests.
- Outbound orchestration tests.
- Provider-to-platform error mapping tests.
- Quota/idempotency/reconciliation tests.
- Controlled real Telnyx/LiveKit staging validation plan, separate from default CI.
- Backend service documentation and operational notes needed by Habiba's SDK integration.

Detailed Hamza implementation steps belong in a separate Hamza workflow document.

## 6. Branch And Integration Rules

Current branches:

- `main`
- `staging`
- `ukasha`
- `hamza`
- `habiba`

Branch rules:

- Hamza performs telephony backend implementation work in `hamza`.
- Habiba performs database, SDK, and client-facing documentation work in `habiba`.
- Ukasha continues provider/language modularity work in `ukasha`.
- Completed work should enter `staging` through reviewed pull requests.
- `main` should receive telephony changes only after integration, regression, staging, and production-readiness testing.
- Neither Hamza nor Habiba should directly develop telephony work on `main`.
- Shared schema/API/SDK/status/error contracts should be agreed before both developers touch dependent code.
- Database migration PRs should be reviewed for backend compatibility before merge, but Habiba remains the owner of applying and verifying Supabase migrations.

## 7. Explicit Non-Goals

- Do not build P2F-specific payment or end-client billing workflows.
- Do not move provider/language selection out of Ukasha's provider registry work.
- Do not create per-call LiveKit trunks or SIP dispatch rules.
- Do not bypass the telephony backend service from `@awaazlabs-uva/telephony` or any future dashboard.
- Do not put Telnyx, HMAC, LiveKit, Supabase, or provider secrets in browser packages.
- Do not create the detailed Hamza or Habiba workflow documents in this file.
