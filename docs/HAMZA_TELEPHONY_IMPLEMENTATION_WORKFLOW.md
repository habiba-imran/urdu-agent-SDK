# Hamza Telephony Implementation Workflow

This document is Hamza's backend implementation workflow for the production telephony layer. It uses `TELEPHONY_CODEBASE_ANALYSIS_AND_INTEGRATION_PLAN.md` and `TELEPHONY_WORKLOAD_AND_RESPONSIBILITY_DIVISION.md` as the authoritative sources.

This is not a phase plan, sprint plan, timeline, or P2F-specific plan. It is the dependency-ordered backend workflow Hamza should follow on the `hamza` branch. Completed work should enter `staging` through reviewed pull requests. `main` should receive telephony changes only after integration, regression, and production-readiness testing.

## Non-Negotiable Boundaries

- Hamza does not have Supabase project access.
- Habiba owns migration files, RLS, indexes, tenant-scoped constraints, database functions, schema verification, rollback planning, and live Supabase deployment.
- Hamza may define required tables, fields, queries, transactions, locks, status constraints, and repository contracts.
- Hamza must build against agreed contracts, mocks, fake adapters, local fixtures, or temporary repository interfaces until Habiba's migrations are available.
- Do not create a separate STT/LLM/TTS pipeline.
- Keep `worker/main.py` changes minimal.
- Provider and language selection remains owned by Ukasha's provider registry work.
- Telephony consumes the final agent runtime configuration and must not choose STT, LLM, TTS, language, model, or voice independently.
- Do not create LiveKit trunks or SIP dispatch rules per call.
- Do not trust caller-controlled metadata for tenant, client, agent, routing, or authorization decisions.
- Do not expose Telnyx API keys, HMAC secrets, LiveKit secrets, Supabase credentials, raw provider payloads, or unrestricted error details to clients.
- Dashboard implementation is out of scope for the current workflow. Hamza should produce future-safe portal API contracts, but should not assign dashboard implementation or dashboard-specific mocks to Habiba.

## Backend Module Structure

Purpose:

Create a backend telephony layer inside the existing tenant portal API deployment so tenant-portal routes and `@awaazlabs-uva/telephony` use the same service, query layer, error mapping, status rules, and provider adapters.

Exact existing files to modify:

- `tenant_portal_api/app.py`: register telephony routes and, if needed, allow `DELETE` in CORS methods for disconnect/disable endpoints.
- `requirements.txt`: modify only if Hamza confirms a new pinned dependency is required. The default should use existing `httpx==0.28.1` for Telnyx HTTP calls unless a Telnyx SDK is intentionally selected.
- `control_plane/app.py`: modify only if extracting shared LiveKit dispatch helpers from the current private `_dispatch_agent` pattern. Telephony must not call or depend on `/v1/session`.
- `docs/MACHINE_AGENT_API_CONTRACT.md`, `README.md`, or a new telephony API contract doc: update later only for backend contract documentation, not for SDK or dashboard implementation.

New files/modules to create:

- `tenant_portal_api/telephony_models.py`: Pydantic request/response models for portal and machine APIs.
- `tenant_portal_api/telephony_status.py`: platform status enums, provider status normalization, valid transition maps.
- `tenant_portal_api/telephony_errors.py`: stable platform error codes and HTTP mapping.
- `tenant_portal_api/telephony_queries.py`: repository/query functions for telephony tables.
- `tenant_portal_api/telephony_service.py`: orchestration, validation, idempotency, quota lifecycle, status transitions.
- `tenant_portal_api/telnyx_client.py`: Telnyx API adapter.
- `tenant_portal_api/livekit_sip.py`: LiveKit SIP, trunk, dispatch-rule, room, participant, and agent-dispatch adapter.
- `tenant_portal_api/telephony_routes.py`: portal and machine route registration.
- `tenant_portal_api/telephony_webhooks.py`: provider webhook verification, dedupe, event application.
- `tenant_portal_api/telephony_reconcile.py`: bounded polling and reconciliation service functions.
- `tenant_portal_api/telephony_health.py`: provider availability, tenant Telnyx health, SIP routing health, diagnostics models.
- `worker/telephony_runtime.py`: minimal worker-side inbound SIP resolution and telephony call close/update hooks.
- `scripts/reconcile_telephony.py`: CLI wrapper for telephony reconciliation, separate from `scripts/reconcile_sessions.py` unless a shared wrapper is agreed.

Inputs and outputs:

- Inputs: tenant JWT claims for portal routes, machine HMAC headers for SDK routes, Telnyx API key during connection, Telnyx and LiveKit provider responses, LiveKit SIP participant attributes, agent IDs, phone-number IDs, idempotency keys.
- Outputs: stable AwaazLabs platform responses, masked Telnyx connection metadata, managed number records, order records, routing readiness, outbound readiness, telephony call records, call events, tenant/provider health data, redacted errors.

Dependencies:

- Existing tenant portal auth in `tenant_portal_api/auth.py`.
- Existing machine auth in `tenant_portal_api/machine_auth.py`.
- Existing DB connection helper in `scripts/dbconn.py`.
- Existing LiveKit credentials loading pattern in `control_plane/app.py`.
- Habiba's database contract and migrations.
- Ukasha's final `AgentRuntimeConfig` and provider registry boundary.

Required database fields or operations:

- Hamza must provide Habiba with the exact backend query/transaction contract for all telephony tables listed in the source plan.
- Every tenant-owned table needs `tenant_id`, RLS, tenant-scoped foreign keys, tenant-scoped uniqueness, indexes, auditability, and restricted raw-payload handling.
- Use DB operations that can be executed atomically for idempotency, quota reservation, call creation, call status transitions, and exactly-once quota release.

API routes or service contracts involved:

- `/portal/telephony/*` for tenant portal and future UI consumers.
- `/machine/telephony/*` for backend-only SDK use.
- `/telephony/webhooks/telnyx` or `/webhooks/telnyx` for Telnyx events.
- Optional LiveKit webhook route only after the deployed LiveKit SIP event surface is confirmed.

Error and status handling:

- All modules should raise or return stable `telephony_*`, `telnyx_*`, `livekit_*`, `quota_*`, `webhook_*`, and data-governance error codes defined in `telephony_errors.py`.
- Public call statuses must remain limited to `queued`, `dialing`, `ringing`, `in_progress`, `completed`, `busy`, `no_answer`, `failed`, and `cancelled`.
- Internal stages belong in `telephony_call_events`, not public status.

Required tests:

- Import and route-registration smoke tests.
- Error-code serialization tests.
- Status transition map tests.
- No-network fake-provider tests by default.
- Regression tests proving existing `/portal/agents`, `/machine/agents`, `/v1/session`, and worker tests still pass.

Completion condition:

- New backend modules exist with clear public functions and no provider side effects during import.
- `tenant_portal_api/app.py` can register telephony routes without breaking existing routes.
- Fake adapters allow Hamza to develop and test before live migrations/provider credentials exist.

Information to hand to Habiba:

- Final module map.
- Route contract draft.
- Required DB repository function list.
- Required request/response models.
- Any confirmed dependency additions.

## Database Requirements And Repository Contracts

Purpose:

Define the exact database contract Hamza needs while leaving migration creation, application, RLS, indexes, and Supabase verification to Habiba.

Exact existing files to modify:

- None for live database changes by Hamza.
- `tenant_portal_api/telephony_queries.py`: new repository functions that target the agreed schema.
- Test fixtures under new telephony test files can simulate rows before migrations are available.

New files/modules to create:

- `tenant_portal_api/telephony_queries.py`.
- `tests/fakes/telephony_db.py` or equivalent local fixture helpers if needed.
- `docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md` as the shared frozen contract artifact.

Inputs and outputs:

- Inputs: required entity names, field names, query shapes, transaction boundaries, lock requirements, idempotency keys, provider identifiers, tenant IDs.
- Outputs: a database contract Habiba can implement and Hamza can code against.

Dependencies:

- `supabase/migrations/0001_schema.sql` for current `tenants`, `agents`, `sessions`, `usage_events`, and `quota_state`.
- `supabase/migrations/0002_rls.sql` for existing tenant-isolation patterns.
- `supabase/migrations/0004_nonces.sql` for nonce/replay model.
- `supabase/migrations/0007_admin.sql`, `0008_tools.sql`, `0009_tenant_secrets.sql`, and `0011_session_transcript.sql` for current audit/session/transcript surfaces.

Required database fields or operations to communicate to Habiba:

- Tables: `tenant_telnyx_connections`, `telnyx_sip_connections`, `telnyx_outbound_voice_profiles`, `telephony_phone_numbers`, `livekit_inbound_trunks`, `livekit_outbound_trunks`, `livekit_sip_dispatch_rules`, `telephony_number_orders`, `telephony_calls`, `telephony_call_events`, `telephony_idempotency_keys`, and `telephony_audit_log`.
- Existing table linkage: `telephony_calls.session_id` should reference `sessions(id)`. Prefer linking rather than replacing `sessions`.
- `telephony_calls` should store internal foreign-key references `inbound_trunk_record_id`, `outbound_trunk_record_id`, and `sip_dispatch_rule_record_id`, not duplicate LiveKit provider IDs.
- LiveKit provider IDs belong only to `livekit_inbound_trunks`, `livekit_outbound_trunks`, and `livekit_sip_dispatch_rules`.
- Call-specific identifiers stored directly on `telephony_calls`: `livekit_sip_call_id`, `livekit_sip_call_id_full`, `livekit_agent_dispatch_id`, and `room_name`.
- One active Telnyx account connection per tenant initially, with historical disconnected records and future-safe support for multiple provider connections later.
- One reusable Telnyx SIP/FQDN connection per active tenant Telnyx connection.
- One active Telnyx Outbound Voice Profile associated with the tenant SIP connection before outbound readiness.
- One long-lived LiveKit inbound trunk and SIP dispatch rule per phone number where deterministic routing is required.
- One reusable LiveKit outbound trunk per active Telnyx connection and Outbound Voice Profile.
- Row locks required for number assignment, inbound call resolution, outbound call creation, idempotency rows, quota reservation, quota release, and status transitions.
- Tenant-scoped constraints must prevent cross-tenant agent assignment, number assignment, trunk/rule association, and call creation.
- Data-governance fields are required for retention, deletion/offboarding, restricted raw provider payload access, export/access audit, disabled states, and timestamps.

Repository/query contracts Hamza should define:

- `get_active_telnyx_connection(tenant_id)`.
- `upsert_telnyx_connection_verifying(...)`.
- `mark_telnyx_connection_active(...)`.
- `rotate_telnyx_connection_key(...)`.
- `disconnect_telnyx_connection(...)`.
- `list_telnyx_owned_number_snapshots(tenant_id)`.
- `list_managed_numbers(tenant_id, filters)`.
- `import_owned_number(...)`.
- `record_number_sync_result(...)`.
- `record_number_drift(...)`.
- `create_number_order_idempotently(...)`.
- `update_number_order_status(...)`.
- `sync_purchased_number(...)`.
- `get_or_create_tenant_sip_connection(...)`.
- `update_sip_connection_status(...)`.
- `get_or_create_outbound_voice_profile(...)`.
- `update_outbound_voice_profile_status(...)`.
- `get_or_create_inbound_trunk_record(...)`.
- `get_or_create_outbound_trunk_record(...)`.
- `get_or_create_sip_dispatch_rule_record(...)`.
- `configure_number_routing_transaction(...)`.
- `assign_number_to_agent(...)`.
- `resolve_inbound_call_by_sip_attributes(...)`.
- `create_or_link_inbound_call_and_session(...)`.
- `create_outbound_call_idempotently(...)`.
- `reserve_call_quota(...)`.
- `release_call_quota_once(...)`.
- `record_call_usage_once(...)`.
- `transition_call_status(...)`.
- `insert_call_event(...)`.
- `dedupe_webhook_event(...)`.
- `reconcile_stale_calls(...)`.

API routes or service contracts involved:

- All portal and machine telephony routes rely on this query layer.
- Worker inbound resolver relies on the same status and query contract.
- Reconciliation jobs rely on stable query functions rather than ad hoc SQL.

Error and status handling:

- Repository functions should return typed results or raise stable platform exceptions, not raw SQL strings.
- Stale updates must not move calls backwards.
- Idempotency mismatches must return `idempotency_payload_mismatch`.
- Cross-tenant mismatches must return stable authorization/validation errors without leaking whether another tenant owns the resource.

Required tests:

- Repository contract tests using local fixtures/mocks until migrations are available.
- Tenant isolation tests after Habiba's RLS and constraints land.
- Row-lock and race-condition tests for assignment, inbound resolution, outbound creation, quota reservation, and idempotency.
- Status transition tests at repository and service layers.

Completion condition:

- Habiba has a precise schema/query contract to implement.
- Hamza can run fake repository tests before live migrations exist.
- Once migrations exist, the repository layer passes against real local/staging schema without Hamza needing Supabase project access.

Information to hand to Habiba:

- Required table fields and indexes.
- Required partial unique constraints.
- Required tenant-scoped foreign keys.
- Required DB-enforced transition constraints, if chosen.
- Required transactional behavior and row-lock points.
- Sample seed rows for backend tests.

## Stable Platform Errors And Status Transitions

Purpose:

Centralize public statuses, provider statuses, normalized platform statuses, internal stages, and stable error codes before any provider adapter or route returns responses.

Exact existing files to modify:

- None initially.
- Later `tenant_portal_api/app.py` imports route modules that use the status/error layer.

New files/modules to create:

- `tenant_portal_api/telephony_status.py`.
- `tenant_portal_api/telephony_errors.py`.
- Tests such as `tests/test_telephony_status.py` and `tests/test_telephony_errors.py`.

Inputs and outputs:

- Inputs: raw Telnyx statuses, raw LiveKit SIP participant statuses, backend validation failures, quota failures, provider exceptions.
- Outputs: stable AwaazLabs status strings, error codes, redacted client messages, restricted diagnostic payloads.

Dependencies:

- Source plan status model.
- Habiba's DB enum/check-constraint decisions.

Required database fields or operations:

- `provider_status` and `platform_status` where provider resources have raw state.
- `raw_provider_status` and restricted `provider_error_payload` on records/events where debugging needs it.
- `raw_livekit_sip_participant_status` separate from `platform_status`.
- `telephony_call_events.internal_stage` for internal lifecycle details.

API routes or service contracts involved:

- All `/portal/telephony/*` and `/machine/telephony/*` routes.
- Webhook handlers.
- Reconciliation jobs.
- Worker telephony status hooks.

Error and status handling:

- Public outbound transitions:
  - `queued` -> `dialing`, `failed`, `cancelled`
  - `dialing` -> `ringing`, `in_progress`, `busy`, `no_answer`, `failed`, `cancelled`
  - `ringing` -> `in_progress`, `busy`, `no_answer`, `failed`, `cancelled`
  - `in_progress` -> `completed`, `failed`, `cancelled`
  - terminal: `completed`, `busy`, `no_answer`, `failed`, `cancelled`
- Public inbound transitions:
  - `ringing` -> `in_progress`, `failed`, `cancelled`
  - `in_progress` -> `completed`, `failed`, `cancelled`
  - terminal: `completed`, `failed`, `cancelled`
- Inbound calls must not be forced through outbound-only `dialing`.
- No silent provider fallback.
- Raw provider details are restricted; clients get stable error codes and redacted messages.

Required tests:

- Direction-specific status transition tests.
- Stale update rejection tests.
- Provider-to-platform error mapping tests.
- Redaction tests.
- Restricted payload access tests where backend surfaces diagnostics.

Completion condition:

- No telephony route or service returns raw provider errors directly.
- Status transition guards are used consistently by service, webhook, reconciliation, and worker update paths.

Information to hand to Habiba:

- Final status enum lists.
- DB constraints desired for statuses and transitions.
- Stable error-code list for SDK and future portal mapping.

## Telnyx API Adapter

Purpose:

Build a backend-only Telnyx adapter that verifies tenant Telnyx accounts, lists inventory, searches exact available numbers, optionally reserves numbers, purchases exact selected numbers, manages SIP/FQDN connections, manages Outbound Voice Profiles, and translates provider errors.

Exact existing files to modify:

- `requirements.txt` only if a pinned Telnyx SDK is selected. Otherwise use existing `httpx`.
- No SDK package, dashboard, or Supabase migration files.

New files/modules to create:

- `tenant_portal_api/telnyx_client.py`.
- `tests/test_telephony_telnyx_client.py`.
- Fake provider helpers under `tests/fakes/` if useful.

Inputs and outputs:

- Inputs: decrypted tenant Telnyx API key from trusted backend credential service, selected exact E.164 number, search filters, SIP connection payloads, Outbound Voice Profile payloads, provider IDs.
- Outputs: typed provider result objects, normalized provider status, raw provider status for restricted storage, stable provider error categories.

Dependencies:

- Confirmed Telnyx APIs for account/key verification, owned-number inventory, exact number search, optional reservation, exact number order, order status, SIP/FQDN connection, Outbound Voice Profile, and applicable webhooks.
- Credential encryption/retrieval service.
- Telephony error/status modules.

Required database fields or operations:

- None directly in adapter. The adapter must not write DB rows.
- Service layer persists adapter results through `telephony_queries.py`.

API routes or service contracts involved:

- Telnyx connection routes.
- Owned-number inventory routes.
- Available-number search/reservation/purchase routes.
- SIP/FQDN connection routes.
- Outbound Voice Profile routes.
- Reconciliation service.

Error and status handling:

- Map timeouts to `provider_timeout`.
- Map rate limits to `telnyx_rate_limited`.
- Map bad or unauthorized keys to `telnyx_key_invalid`, `telnyx_key_unauthorized`, or `telnyx_key_permission_failed`.
- Map unavailable searched numbers to `number_not_available`.
- Map balance failures to `insufficient_telnyx_balance`.
- Map regulatory states to `regulatory_action_required` or `number_order_action_required`.
- Preserve raw provider status and payload only for restricted storage.

Required tests:

- Adapter uses fake HTTP responses by default.
- Verification success and permission failure.
- Search returns exact available numbers with pricing where available.
- Reservation unsupported or unavailable handling.
- Exact purchase request never purchases from broad country/area criteria alone.
- Order status normalization.
- SIP/FQDN and Outbound Voice Profile response normalization.
- Timeout, rate-limit, malformed response, and provider error mapping.

Completion condition:

- Telnyx adapter exposes typed functions with no direct DB writes and no raw key logging.
- Fake-provider tests cover all adapter operations required by service layer.

Information to hand to Habiba:

- Provider IDs and raw statuses that must be persisted.
- Fields required for connection, SIP, Outbound Voice Profile, number, order, drift, and restricted event records.
- Redacted shape of provider metadata safe for SDK and future portal consumers.

## Telnyx Account Verification And Credential Lifecycle

Purpose:

Allow each tenant to connect one active Telnyx account initially, verify permissions, encrypt credentials at rest, rotate/reverify/disconnect safely, and isolate failures to the affected tenant.

Exact existing files to modify:

- `tenant_portal_api/app.py`: register the telephony route module.
- `tenant_portal_api/machine_auth.py`: no direct change expected; reuse `verify_machine_request` with fixed telephony action strings.
- `control_plane/secrets.py` and `control_plane/secrets_db.py`: do not reuse tenant HMAC secret providers for Telnyx keys. Modify only if a shared secret-provider abstraction is deliberately extracted.

New files/modules to create:

- `tenant_portal_api/telephony_service.py`: credential lifecycle orchestration.
- `tenant_portal_api/telephony_queries.py`: connection row operations.
- `tenant_portal_api/telephony_routes.py`: portal and machine endpoints.
- Optional `tenant_portal_api/telephony_crypto.py` if encryption is implemented in app code rather than via an external secret store.

Inputs and outputs:

- Inputs: tenant ID from portal JWT or machine HMAC, raw Telnyx API key submitted once over TLS, rotation key, disconnect/reverify requests.
- Outputs: masked connection metadata, `platform_status`, `provider_status`, `key_fingerprint`, `last_verified_at`, permission/readiness summary.

Dependencies:

- Secret encryption mechanism decision.
- Habiba's `tenant_telnyx_connections` schema.
- Telnyx adapter verification function.

Required database fields or operations:

- `tenant_telnyx_connections.id`.
- `tenant_telnyx_connections.tenant_id`.
- `label`.
- `platform_status`.
- `provider_status`.
- `encrypted_api_key_ref` or `encrypted_api_key_ciphertext`.
- `key_fingerprint`.
- `telnyx_account_id`.
- `last_verified_at`.
- `permission_last_checked_at`.
- `created_at`, `updated_at`, `disabled_at`, `disconnected_at`, `compromised_at`.
- Partial unique constraint for one active connection per tenant.
- Audit log row for connect, rotate, reverify, disconnect, permission failure, and compromised key.

API routes or service contracts involved:

- `GET /portal/telephony/telnyx/connection`.
- `POST /portal/telephony/telnyx/connect`.
- `POST /portal/telephony/telnyx/rotate`.
- `POST /portal/telephony/telnyx/reverify`.
- `DELETE /portal/telephony/telnyx/connection`.
- Mirrored `/machine/telephony/*` routes with fixed action strings.

Error and status handling:

- `not_connected`, `verifying`, `active`, `verification_failed`, `rotation_required`, `permission_failed`, `compromised`, `disabled`, `disconnected`.
- Raw Telnyx key must never be returned, logged, cached, or stored outside the chosen encrypted-at-rest mechanism.
- Future dashboard key entry may temporarily enter browser memory during submission, but backend responses must return only masked metadata.
- After successful connection, other operations must select the stored encrypted tenant credential and must not require the raw key again.

Required tests:

- Successful connection stores only encrypted secret material or secret reference.
- API response returns masked metadata only.
- Invalid key, unauthorized key, permission failure, compromised-key path.
- Rotation replaces credential and preserves audit trail.
- Reverification updates status without exposing secret.
- Disconnection disables future operations but preserves historical records.
- Multi-tenant credential isolation.

Completion condition:

- A tenant can connect, rotate, reverify, disconnect, and view masked connection status through portal and machine routes using fake Telnyx responses.
- Provider failure for one tenant does not affect global readiness or other tenants.

Information to hand to Habiba:

- Encryption-field requirement.
- Audit-log event names.
- SDK-safe and future portal-safe response shape.
- SDK method names and action strings for Habiba's `@awaazlabs-uva/telephony` implementation.

## Number Inventory, Import, Sync, Drift, Search, Reservation, And Purchase

Purpose:

Separate Telnyx-owned inventory from AwaazLabs-managed inventory, support importing existing Telnyx numbers, synchronize and detect drift, search exact available numbers, optionally reserve, and purchase only an exact selected number idempotently.

Exact existing files to modify:

- `tenant_portal_api/app.py`: route registration only.
- No changes to existing agent CRUD in `tenant_portal_api/queries.py`; telephony number assignment belongs in new telephony query/service modules.

New files/modules to create:

- `tenant_portal_api/telephony_service.py`: inventory, import, sync, drift, search, reservation, purchase orchestration.
- `tenant_portal_api/telephony_queries.py`: phone-number, order, idempotency, and drift operations.
- `tenant_portal_api/telnyx_client.py`: provider operations.
- Tests: `tests/test_telephony_inventory.py`, `tests/test_telephony_number_orders.py`, `tests/test_telephony_number_assignment.py`.

Inputs and outputs:

- Inputs: tenant ID, Telnyx connection, filters for country/area code/type/features, selected exact `e164Number`, optional reservation ID, idempotency key, optional `externalCustomerRef`, target `agentId`.
- Outputs: Telnyx-owned inventory snapshots, AwaazLabs-managed numbers, drift reports, exact available numbers, reservation result, number order result, routing configuration request, assignment result.

Dependencies:

- Active Telnyx connection.
- Telnyx adapter.
- `telephony_idempotency_keys` contract.
- `telephony_phone_numbers` and `telephony_number_orders` schemas.
- Agent ownership validation against current `agents`.

Required database fields or operations:

- `telephony_phone_numbers`: `id`, `tenant_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `provider_number_id`, `e164_number`, `country`, `number_type`, `features`, `provisioning_status`, `routing_status`, `provider_status`, `assigned_agent_id`, `external_customer_ref`, `last_synced_at`, timestamps, `disabled_at`.
- `telephony_number_orders`: `id`, `tenant_id`, `telnyx_connection_id`, `idempotency_key`, `provider_order_id`, `selected_e164_number`, filters, price, `provider_status`, `platform_status`, raw provider status, restricted provider error payload, stable error fields, timestamps.
- `telephony_idempotency_keys`: `(tenant_id, idempotency_key, action, request_hash, response_body, platform_status, created_at, completed_at)`.
- Unique active `(tenant_id, e164_number)`.
- Unique `(tenant_id, idempotency_key)` for purchase.
- Same-tenant FK/check for `assigned_agent_id`.
- Lock number row during assignment/reassignment and during inbound call start.

API routes or service contracts involved:

- `GET /portal/telephony/telnyx/owned-numbers`.
- `GET /portal/telephony/numbers`.
- `POST /portal/telephony/numbers/import`.
- `POST /portal/telephony/numbers/sync`.
- `GET /portal/telephony/numbers/drift`.
- `POST /portal/telephony/available-numbers/search`.
- `POST /portal/telephony/number-reservations`.
- `POST /portal/telephony/number-orders`.
- `GET /portal/telephony/number-orders/{order_id}`.
- `PATCH /portal/telephony/numbers/{number_id}/assignment`.
- `POST /portal/telephony/numbers/{number_id}/disable`.
- Mirrored machine routes with fixed action strings from the source plan.

Error and status handling:

- Do not purchase from broad criteria. Purchase only the exact selected number returned by search or a verified selected number.
- Handle `number_not_available`, `insufficient_telnyx_balance`, `regulatory_action_required`, `number_order_action_required`, `provider_timeout`, and `telnyx_rate_limited`.
- Use provider order statuses `pending`, `success`, `failure`, `cancelled`, `deleted`.
- Use platform order statuses `pending`, `purchased`, `configuring_routing`, `ready`, `action_required`, `failed`, `cancelled`, `deleted`.
- Phone-number assignment is represented by nullable `assigned_agent_id`, not by `assigned` or `unassigned` statuses.
- Split phone-number state into `provisioning_status` and `routing_status`.
- Partial setup after successful purchase must leave the number owned and set routing to `failed` or `degraded` with retryable configure-routing workflows.

Required tests:

- Telnyx-owned vs AwaazLabs-managed inventory separation.
- Import existing Telnyx-owned number.
- Sync detects new, changed, removed, suspended, or feature-changed numbers.
- Drift detection does not silently rewrite assignments.
- Exact search returns exact numbers and pricing where available.
- Optional reservation unsupported/supported paths.
- Idempotent exact purchase and duplicate-click behavior.
- Same idempotency key with different payload returns `idempotency_payload_mismatch`.
- Number unavailable after search.
- Insufficient balance and regulatory action required.
- Assignment validates same tenant and active-call protection.

Completion condition:

- Number inventory and purchase operations work end to end with fake Telnyx and fake DB/repository fixtures.
- All provider side effects are idempotency-gated before calls to Telnyx.
- Assignment never crosses tenants and never races active inbound call startup.

Information to hand to Habiba:

- Exact number/order/idempotency fields.
- Required indexes for number lookup by `tenant_id`, `e164_number`, `provider_number_id`, `assigned_agent_id`, and `idempotency_key`.
- SDK and future portal response shapes for owned inventory, managed inventory, drift, search, reservation, order, and assignment.
- SDK method contract for listing, importing, syncing, searching, reserving, purchasing, assigning, and disabling numbers.

## Number-Order Status Tracking

Purpose:

Track Telnyx number orders through provider and platform statuses, handle webhook delays, and reconcile orders without blocking the request process indefinitely.

Exact existing files to modify:

- None beyond route registration in `tenant_portal_api/app.py`.

New files/modules to create:

- `tenant_portal_api/telephony_service.py`: order lifecycle orchestration.
- `tenant_portal_api/telephony_reconcile.py`: order polling and reconciliation.
- `tenant_portal_api/telephony_webhooks.py`: webhook-driven order updates.
- `tests/test_telephony_number_orders.py`.
- `tests/test_telephony_reconciliation.py`.

Inputs and outputs:

- Inputs: `telephony_number_order_id`, provider order ID, provider webhook event ID, provider order status, bounded polling trigger.
- Outputs: normalized order status, call-to-action status, configured phone number when successful, failed/degraded routing state when setup partially fails.

Dependencies:

- Number purchase service.
- Telnyx adapter order status function.
- Webhook signature verification.
- Idempotency contract.

Required database fields or operations:

- Update `provider_status`, `platform_status`, `raw_provider_status`, `provider_error_payload`, `error_code`, `error_message`, and timestamps.
- Dedupe provider events.
- Preserve raw provider payloads in restricted records.
- Link successful orders to `telephony_phone_numbers`.

API routes or service contracts involved:

- `GET /portal/telephony/number-orders/{order_id}`.
- Machine `telephony.number_orders.get`.
- Telnyx webhook route.
- Reconciliation scheduler.

Error and status handling:

- `action_required` is an AwaazLabs platform status, not a raw Telnyx status.
- Pending orders must survive process restarts.
- Stale provider events must not move platform status backward.
- Unknown provider order IDs must become restricted failed/unmapped events, not tenant-scoped mutations unless mapping is proven.

Required tests:

- Provider status normalization.
- Webhook delay plus polling fallback.
- Duplicate webhook dedupe.
- Stale webhook ignored event.
- Partial setup failure after successful purchase.
- Reconciliation repairs or flags drift.

Completion condition:

- Orders can be created, queried, updated from webhook, and reconciled with deterministic platform statuses and redacted client responses.

Information to hand to Habiba:

- Order status enum mappings.
- SDK-safe and future portal-safe order details.
- Restricted provider payload fields and audit expectations.

## Telnyx SIP/FQDN Connection

Purpose:

Create or select one reusable Telnyx SIP/FQDN connection per tenant Telnyx account, verify it, and keep it separate from phone numbers, LiveKit trunks, dispatch rules, and calls.

Exact existing files to modify:

- `tenant_portal_api/app.py`: route registration only.
- `requirements.txt`: only if new provider SDK dependency is selected.

New files/modules to create:

- `tenant_portal_api/telnyx_client.py`: SIP/FQDN provider calls.
- `tenant_portal_api/telephony_service.py`: SIP connection orchestration.
- `tenant_portal_api/telephony_queries.py`: SIP connection persistence.
- `tests/test_telephony_sip_connection.py`.

Inputs and outputs:

- Inputs: active Telnyx connection, desired SIP/FQDN connection settings, optional SIP test request.
- Outputs: `telnyx_sip_connection_id` DB row, provider SIP connection ID, SIP FQDN, status, verification result.

Dependencies:

- Active Telnyx connection and decrypted provider credential.
- Habiba's `telnyx_sip_connections` schema.
- Confirmed Telnyx SIP/FQDN APIs.

Required database fields or operations:

- `id`, `tenant_id`, `telnyx_connection_id`, `provider_sip_connection_id`, `sip_fqdn`, `sip_username`, `encrypted_sip_secret_ref`, `platform_status`, `provider_status`, `last_verified_at`, timestamps, `disabled_at`.
- Unique active SIP connection per active Telnyx connection.
- No LiveKit trunk or dispatch-rule IDs in this table.

API routes or service contracts involved:

- `POST /portal/telephony/telnyx/sip-connection`.
- `POST /portal/telephony/telnyx/sip-connection/test`.
- Machine `telephony.telnyx_sip_connection.upsert`.
- Machine `telephony.telnyx_sip_connection.test`.

Error and status handling:

- Platform statuses: `draft`, `pending_verification`, `testing`, `active`, `failed`, `disabled`.
- Failed SIP verification maps to `sip_verification_failed`.
- Provider/API failures map to stable Telnyx error codes.
- Do not mark routing ready solely because the SIP row exists.

Required tests:

- Create/update SIP connection.
- Verify/test success and failure.
- Provider error mapping.
- Tenant isolation.
- Disabled connection blocks routing/outbound readiness.

Completion condition:

- Tenant SIP connection can be created or selected, tested, stored, disabled, and reconciled through backend service functions using fake Telnyx.

Information to hand to Habiba:

- Required SIP fields and status constraints.
- Redacted SDK and future portal response shape.
- SIP test result fields.

## Telnyx Outbound Voice Profile

Purpose:

Add production support for the Telnyx Outbound Voice Profile required before outbound SIP calling is ready.

Exact existing files to modify:

- `tenant_portal_api/app.py`: route registration only.

New files/modules to create:

- `tenant_portal_api/telnyx_client.py`: Outbound Voice Profile calls.
- `tenant_portal_api/telephony_service.py`: profile create/select/associate/reverify/reconcile orchestration.
- `tenant_portal_api/telephony_queries.py`: profile persistence and readiness queries.
- `tests/test_telephony_outbound_voice_profile.py`.

Inputs and outputs:

- Inputs: active Telnyx connection, active Telnyx SIP connection, selected or newly created provider Outbound Voice Profile, destination/limit policy.
- Outputs: `outbound_voice_profile_record_id`, `provider_outbound_voice_profile_id`, outbound readiness state, redacted policy summary.

Dependencies:

- Active Telnyx connection.
- Active or testable Telnyx SIP/FQDN connection.
- Confirmed Telnyx APIs for Outbound Voice Profiles and SIP association.

Required database fields or operations:

- `telnyx_outbound_voice_profiles.id`.
- `tenant_id`.
- `telnyx_connection_id`.
- `telnyx_sip_connection_id`.
- `provider_outbound_voice_profile_id`.
- `platform_status`.
- `provider_status`.
- `allowed_destinations`.
- `concurrency_limit`.
- `channel_limit`.
- `daily_spending_limit`.
- `last_verified_at`.
- timestamps and `disabled_at`.

API routes or service contracts involved:

- `POST /portal/telephony/telnyx/outbound-voice-profile`.
- `POST /portal/telephony/telnyx/outbound-voice-profile/reverify`.
- `GET /portal/telephony/outbound-readiness`.
- Machine `telephony.telnyx_outbound_voice_profile.upsert`.
- Machine `telephony.telnyx_outbound_voice_profile.reverify`.
- Machine `telephony.outbound_readiness.get`.

Error and status handling:

- Platform statuses: `not_configured`, `configuring`, `active`, `destination_restricted`, `limit_reached`, `verification_required`, `failed`, `disabled`.
- Outbound calls must fail clearly with `outbound_voice_profile_missing`, `outbound_destination_disabled`, `outbound_spending_limit_reached`, `outbound_concurrency_limit_reached`, `outbound_verification_required`, or `outbound_not_ready` as applicable.
- Do not expose unnecessary raw Telnyx configuration to SDK or future portal consumers.

Required tests:

- Create/select profile.
- Associate with SIP connection.
- Outbound readiness success.
- Disabled destination, spending limit, concurrency/channel limit, and verification restriction failures.
- Reconciliation detects provider-side changes.
- Multi-tenant isolation.

Completion condition:

- Outbound readiness cannot become ready unless the tenant SIP connection is associated with an active Outbound Voice Profile and required limits/destination checks pass.

Information to hand to Habiba:

- Profile fields and readiness response shape.
- SDK-safe and future portal-safe policy summary.
- SDK method contract for create/select/reverify/readiness.

## LiveKit SIP Adapter, Trunks, And Dispatch Rules

Purpose:

Manage LiveKit SIP resources as long-lived tenant/number resources, not per-call resources.

Exact existing files to modify:

- `requirements.txt` only if the current `livekit-api==1.2.0` lacks required SIP APIs and a pinned upgrade is confirmed.
- `control_plane/app.py` only if a shared agent dispatch helper is extracted from `_dispatch_agent`.

New files/modules to create:

- `tenant_portal_api/livekit_sip.py`.
- Optional shared `control_plane/livekit_dispatch.py` if LiveKit agent dispatch is reused by both browser minting and telephony without importing the FastAPI app.
- `tests/test_telephony_livekit_sip.py`.

Inputs and outputs:

- Inputs: LiveKit URL/API key/API secret from backend environment, tenant Telnyx SIP/FQDN connection, phone number record, Outbound Voice Profile readiness.
- Outputs: LiveKit inbound trunk record, outbound trunk record, SIP dispatch-rule record, LiveKit agent dispatch ID, outbound SIP participant result.

Dependencies:

- Confirmed LiveKit SIP APIs and package support.
- Active Telnyx SIP/FQDN connection.
- Outbound Voice Profile readiness for outbound trunk readiness.
- Habiba's `livekit_inbound_trunks`, `livekit_outbound_trunks`, and `livekit_sip_dispatch_rules` schema.

Required database fields or operations:

- `livekit_inbound_trunks`: `id`, `tenant_id`, `phone_number_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `livekit_inbound_trunk_id`, statuses, `last_reconciled_at`, timestamps, `disabled_at`.
- `livekit_outbound_trunks`: `id`, `tenant_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `outbound_voice_profile_record_id`, `livekit_outbound_trunk_id`, statuses, `last_reconciled_at`, timestamps, `disabled_at`.
- `livekit_sip_dispatch_rules`: `id`, `tenant_id`, `phone_number_id`, `livekit_inbound_trunk_id`, `livekit_sip_dispatch_rule_id`, statuses, `last_reconciled_at`, timestamps, `disabled_at`.
- Active uniqueness for `(tenant_id, phone_number_id)` inbound trunk and dispatch rule.
- Active uniqueness for `(tenant_id, telnyx_connection_id)` outbound trunk.

API routes or service contracts involved:

- `POST /portal/telephony/numbers/{number_id}/routing/configure`.
- `POST /portal/telephony/telnyx/outbound-trunk/configure`.
- `GET /portal/telephony/outbound-readiness`.
- Machine `telephony.number_routing.configure`.
- Machine `telephony.outbound_trunk.configure`.

Error and status handling:

- LiveKit failures map to `livekit_inbound_trunk_failed`, `livekit_outbound_trunk_failed`, `livekit_sip_dispatch_rule_failed`, or `livekit_agent_dispatch_failed`.
- Trunk and dispatch-rule provider IDs belong only to their resource tables.
- Call records use internal record references, not duplicated provider IDs.
- Provider-ID snapshots may go into restricted call events only for debugging.

Required tests:

- Inbound trunk creation/update/reuse.
- Outbound trunk creation/update/reuse.
- Dispatch-rule creation/update/reuse.
- No per-call trunk/rule creation.
- No duplicated provider-ID ownership in call record writes.
- Reconciliation detects missing, disabled, or changed LiveKit resources.

Completion condition:

- Routing configuration can create or repair long-lived resources and mark readiness without creating resources per call.

Information to hand to Habiba:

- Required LiveKit resource fields.
- Readiness and degraded status shape.
- SDK-safe and future portal-safe trunk/rule metadata.

## Portal And Machine Telephony API Routes

Purpose:

Expose all telephony operations through the existing tenant portal API deployment, with portal JWT auth for tenant portal/future UI consumers and machine HMAC auth for backend-only SDK calls.

Exact existing files to modify:

- `tenant_portal_api/app.py`: import and register the telephony router; add CORS method support for `DELETE` if implementing `DELETE /portal/telephony/telnyx/connection`.
- `tenant_portal_api/machine_auth.py`: no direct change expected unless a reusable header extraction helper is agreed.

New files/modules to create:

- `tenant_portal_api/telephony_routes.py`.
- `tenant_portal_api/telephony_models.py`.
- `tests/test_telephony_routes.py`.
- `tests/test_machine_telephony_api.py`.

Inputs and outputs:

- Inputs: portal bearer token, machine HMAC headers, route payloads, path parameters, idempotency keys.
- Outputs: stable JSON responses suitable for tenant portal/future UI consumers and `@awaazlabs-uva/telephony`.

Dependencies:

- Telephony service functions.
- Machine action strings agreed with Habiba's SDK work.
- Stable error/status modules.

Required database fields or operations:

- Route handlers should not contain direct SQL beyond opening the connection and passing it to service/query layers.
- Machine routes should burn nonce and execute side effect atomically where possible, following the style in `tenant_portal_api/app.py`.

API routes or service contracts involved:

- Portal connection, inventory, search, reservation, order, assignment, SIP, Outbound Voice Profile, routing, outbound readiness, outbound calls, calls list/get, number disable routes listed in the source plan.
- Machine routes mirror those responsibilities with fixed action strings such as `telephony.telnyx_connection.connect`, `telephony.number_orders.create`, and `telephony.outbound_calls.create`.

Error and status handling:

- Portal and machine routes should use the same service functions and error mapper.
- Authentication failures stay `401` or `403`.
- Provider failures should not leak raw provider payloads.
- Client-visible errors must be stable and redacted.

Required tests:

- Portal JWT required for portal routes.
- Machine HMAC required for machine routes.
- Payload tampering and nonce replay rejected.
- Cross-tenant path IDs rejected.
- Error mapper response format.
- Existing `tests/test_machine_agent_api.py` remains green.

Completion condition:

- Every backend telephony operation has one service implementation and two auth surfaces where needed: portal and machine.
- SDK and future portal consumers can use the same backend contracts.

Information to hand to Habiba:

- Final route list.
- Request/response JSON.
- Machine action strings.
- Error response format.
- Idempotency header/body convention.

## Telephony Session And Quota Lifecycle

Purpose:

Create a production-safe session and quota lifecycle for inbound and outbound calls that is independent of browser `/v1/session`.

Exact existing files to modify:

- `control_plane/mint.py`: do not route telephony through this browser/WebRTC mint path.
- `control_plane/app.py`: do not reuse `/v1/session` for telephony calls.
- `worker/main.py`: later add minimal hooks to consume telephony-created sessions/calls.
- `worker/usage.py`: no change unless the team decides to add telephony-specific usage kinds to `usage_events`; default should keep model usage as-is and store phone/SIP usage separately.

New files/modules to create:

- `tenant_portal_api/telephony_service.py`: session/quota orchestration.
- `tenant_portal_api/telephony_queries.py`: transactional quota/call/session operations.
- `worker/telephony_runtime.py`: worker status close/update hooks.
- `tests/test_telephony_quota_idempotency.py`.
- `tests/test_telephony_worker_runtime.py`.

Inputs and outputs:

- Inputs: tenant ID, agent ID, phone-number record, call direction, routing records, idempotency key for outbound, LiveKit SIP attributes for inbound.
- Outputs: `session_id`, `telephony_call_id`, `room_name`, quota reservation timestamp, call event records, exactly-once release and usage record.

Dependencies:

- Existing `sessions` and `quota_state` semantics in `control_plane/mint.py`.
- Worker closeout behavior in `worker/main.py`.
- Habiba's `telephony_calls` and event schema.
- Status transition module.

Required database fields or operations:

- In one transaction: validate tenant active, validate agent ownership, validate number ownership/readiness, validate routing/trunk/rule/profile records, lock relevant rows, check quota, insert `sessions`, insert or link `telephony_calls`, increment `quota_state.concurrent_now`, set `quota_reserved_at`.
- Release quota with a conditional guard such as `quota_released_at is null`.
- Record usage with a conditional guard such as `usage_recorded_at is null`.
- Reconcile stale calls and quota mismatches.

API routes or service contracts involved:

- Outbound call creation route.
- Inbound worker resolver.
- Reconciliation scheduler.
- Call status routes.

Error and status handling:

- Prevent quota leaks, double releases, duplicate outbound calls, duplicate worker handling, calls after tenant suspension, stale status updates, and race conditions during reassignment.
- Use `quota_reservation_failed`, `quota_release_failed`, `call_state_conflict`, and `worker_session_failed` where appropriate.

Required tests:

- Atomic reservation success.
- Quota cap rejection.
- Monthly cap behavior or telephony-specific billing decision.
- Release exactly once.
- Usage recorded once.
- Stale-call reconciliation repairs leaked quota.
- Existing WebRTC mint tests continue passing.

Completion condition:

- Telephony can create/link sessions and calls without `/v1/session`.
- Quota is reserved and released exactly once in setup failure, active call, normal close, and stale reconciliation paths.

Information to hand to Habiba:

- Transaction requirements.
- Required locks and conditional updates.
- Usage/billing table decision needed.
- SDK and future portal call lifecycle fields.

## Inbound SIP Call Resolution And Failed-Call Cleanup

Purpose:

Resolve inbound LiveKit SIP participants to tenant, phone number, assigned agent, call, and session using trusted AwaazLabs-owned DB rows.

Exact existing files to modify:

- `worker/main.py`: minimal change to detect SIP participants and call `worker/telephony_runtime.py`; keep existing WebRTC metadata path working.
- `worker/config.py`: modify only as needed to consume Ukasha's final runtime config; do not add provider selection logic owned by telephony.
- `worker/tools.py`: avoid changes unless the agreed runtime context needs `telephony_call_id` in `AgentUserdata`.
- `worker/usage.py`: avoid changes unless a confirmed usage schema decision requires it.

New files/modules to create:

- `worker/telephony_runtime.py`.
- `tenant_portal_api/telephony_queries.py` functions callable by the worker or mirrored in a worker-safe repository.
- `tests/test_telephony_inbound_worker.py`.
- `tests/test_telephony_failed_inbound.py`.

Inputs and outputs:

- Inputs: LiveKit SIP participant attributes `sip.callID`, `sip.callIDFull`, `sip.trunkPhoneNumber`, `sip.trunkID`, `sip.ruleID`; room name; worker job context.
- Outputs: trusted `tenant_id`, `agent_id`, `telephony_call_id`, `session_id`, final agent runtime config, call status/event updates, clean participant termination on failure.

Dependencies:

- LiveKit SIP attributes confirmed.
- Long-lived inbound trunk and SIP dispatch rule records.
- Number assignment and routing readiness.
- Telephony quota lifecycle.
- Ukasha provider registry runtime config.

Required database fields or operations:

- Resolve `sip.trunkPhoneNumber` to `telephony_phone_numbers.e164_number`.
- Validate `sip.trunkID` against `livekit_inbound_trunks.livekit_inbound_trunk_id`.
- Validate `sip.ruleID` against `livekit_sip_dispatch_rules.livekit_sip_dispatch_rule_id`.
- Lock phone-number/routing rows during resolution.
- Create or link `telephony_calls` and `sessions` idempotently by `livekit_sip_call_id` and `livekit_sip_call_id_full`.
- Store `inbound_trunk_record_id`, `sip_dispatch_rule_record_id`, `livekit_sip_call_id`, `livekit_sip_call_id_full`, `sip_trunk_phone_number`, `room_name`, and initial `ringing` status.

API routes or service contracts involved:

- Worker internal call resolver, not browser `/v1/session`.
- Call list/get routes should show failed inbound attempts where tenant resolution is possible.
- Admin diagnostics may show restricted platform events where no tenant can be resolved.

Error and status handling:

- Unknown number: terminate cleanly; tenant-scoped failed call only if tenant can be inferred from trunk/rule, otherwise restricted platform event.
- No agent assigned: `number_not_assigned`; no `AgentSession`.
- Tenant suspended: `tenant_not_active`; no quota reservation.
- Routing mismatch: `routing_identifier_mismatch`; no trusted start.
- Quota failure: `quota_reservation_failed`; no `AgentSession`.
- Agent load failure: `assigned_agent_load_failed`; release quota only if reserved.
- Provider pipeline start failure: `provider_pipeline_start_failed`; release quota only if reserved.
- Multiple workers seeing the same SIP call must converge on one call record and one handler.

Required tests:

- Correct tenant/agent resolution from SIP attributes.
- Unknown number failure.
- Unassigned number failure.
- Suspended tenant failure.
- Trunk/rule mismatch failure.
- Quota failure cleanup.
- Agent load failure cleanup.
- Provider pipeline start failure cleanup.
- Duplicate inbound SIP participant handling.
- Existing WebRTC worker metadata path still passes `tests/test_worker.py`.

Completion condition:

- Inbound SIP can start the same `AgentSession` pipeline from trusted DB resolution, or fail closed with an idempotent event/call record and clean quota behavior.

Information to hand to Habiba:

- Fields SDK and future portal consumers need for inbound failed calls.
- Failure codes and end reasons.
- DB lock/idempotency details for inbound call records.

## Outbound Call Orchestration

Purpose:

Create outbound calls from trusted backend requests through AwaazLabs validation, LiveKit room/agent dispatch, reusable outbound SIP trunk, Telnyx PSTN, and normalized call status storage.

Exact existing files to modify:

- `tenant_portal_api/app.py`: route registration.
- `control_plane/app.py`: avoid using `/v1/session`; extract shared LiveKit dispatch helper only if chosen.
- `worker/main.py`: minimal hook to recognize telephony-created rooms/calls and update close status.

New files/modules to create:

- `tenant_portal_api/telephony_service.py`: outbound orchestration.
- `tenant_portal_api/livekit_sip.py`: room, agent dispatch, outbound SIP participant creation.
- `tenant_portal_api/telephony_queries.py`: outbound transaction and status updates.
- `tests/test_telephony_outbound_calls.py`.

Inputs and outputs:

- Inputs: `agentId`, `fromNumberId`, `toNumber`, `recipient`, call `variables` or `context`, optional `externalCustomerRef`, optional `externalWorkflowRef`, `idempotencyKey`.
- Outputs: `telephony_call_id`, `session_id`, `room_name`, public call status, redacted errors, call events, `livekit_agent_dispatch_id`, LiveKit SIP call identifiers when available.

Dependencies:

- Active tenant.
- Agent belongs to tenant.
- From number belongs to tenant.
- Number is provisioned, routing-ready, outbound-ready, and not disabled.
- Active Telnyx SIP connection.
- Active Outbound Voice Profile.
- Reusable LiveKit outbound trunk.
- Idempotency contract.
- Telephony quota lifecycle.

Required database fields or operations:

- Lock idempotency row before provider side effects.
- Validate and lock `telephony_phone_numbers` row.
- Validate outbound trunk record and Outbound Voice Profile record.
- Insert `sessions` and `telephony_calls` in same reservation transaction.
- Store `outbound_trunk_record_id`, `livekit_agent_dispatch_id`, `room_name`, `from_number`, `to_number`, redacted recipient/context, `external_customer_ref`, and `external_workflow_ref`.
- Store internal stages in `telephony_call_events`.

API routes or service contracts involved:

- `POST /portal/telephony/outbound-calls`.
- `GET /portal/telephony/calls`.
- `GET /portal/telephony/calls/{telephony_call_id}`.
- Machine `telephony.outbound_calls.create`.
- Machine `telephony.calls.get`.
- Machine `telephony.calls.list`.

Error and status handling:

- Validate destination number and policy before LiveKit/Telnyx operations.
- Failure codes: `agent_not_found`, `number_not_found`, `number_not_owned_by_tenant`, `number_not_routing_ready`, `outbound_voice_profile_missing`, `outbound_destination_disabled`, `outbound_spending_limit_reached`, `outbound_concurrency_limit_reached`, `outbound_verification_required`, `invalid_to_number`, `outbound_not_ready`, `livekit_agent_dispatch_failed`, `call_setup_failed`.
- Public outbound status starts at `queued`, then `dialing`, then `ringing` or `in_progress`, then terminal.
- Raw LiveKit SIP participant status stored separately.

Required tests:

- Valid outbound request creates one call per idempotency key.
- Same key/same payload returns original response.
- Same key/different payload returns `idempotency_payload_mismatch`.
- Cross-tenant agent/number rejected.
- Outbound readiness failures.
- Destination/spending/concurrency/verification restriction failures.
- LiveKit agent dispatch failure releases quota.
- SIP participant creation failure releases quota.
- Duplicate outbound requests do not create duplicate calls.

Completion condition:

- Outbound call creation works with fake LiveKit and fake Telnyx without relying on browser session minting.
- All setup failure paths release quota exactly once and produce stable call status/events.

Information to hand to Habiba:

- SDK request/response contract.
- SDK and future portal outbound call create/status fields.
- Failure codes and user-safe messages.
- Required idempotency convention.

## Idempotency And Concurrency Handling

Purpose:

Make provider side effects safe under retries, duplicate clicks, duplicate webhooks, worker races, and concurrent assignment/call operations.

Exact existing files to modify:

- None outside route registration.

New files/modules to create:

- `tenant_portal_api/telephony_service.py`: idempotency enforcement.
- `tenant_portal_api/telephony_queries.py`: idempotency row operations and row locks.
- `tests/test_telephony_quota_idempotency.py`.
- `tests/test_telephony_race_conditions.py`.

Inputs and outputs:

- Inputs: `tenant_id`, `idempotencyKey`, action string, canonical request hash, existing response body, row lock results.
- Outputs: original response on retry, mismatch error on changed payload, one provider side effect, one call/order row.

Dependencies:

- Habiba's `telephony_idempotency_keys` table and constraints.
- Stable action strings for number purchase and outbound call create.
- Transaction boundaries from service layer.

Required database fields or operations:

- Unique `(tenant_id, idempotency_key, action)` or agreed equivalent.
- Store canonical request hash.
- Store final response body.
- Lock idempotency row before making provider side effects.
- Lock number and routing rows during reassignment and inbound/outbound start.
- Lock call rows during status transitions and quota release.

API routes or service contracts involved:

- Number order creation.
- Outbound call creation.
- Any retryable provider-side operation that can create external resources.
- Webhook event dedupe.

Error and status handling:

- `duplicate_idempotency_key` only when the chosen contract needs it.
- `idempotency_payload_mismatch` for same key and different payload.
- `call_state_conflict` for stale or invalid concurrent updates.
- No silent fallback after provider failure.

Required tests:

- Duplicate purchase.
- Duplicate outbound call.
- Concurrent duplicate requests.
- Same key different payload.
- Reassignment during active inbound start.
- Duplicate webhook event.
- Multiple workers handling same inbound call.

Completion condition:

- Tests prove retries and races do not duplicate Telnyx orders, LiveKit resources, outbound calls, quota reservations, or quota releases.

Information to hand to Habiba:

- Exact unique constraints.
- Row-locking requirements.
- Canonical request-hash rules.
- Response-body retention/redaction rules for idempotency rows.

## Telnyx And LiveKit Webhook Handling

Purpose:

Process provider events idempotently, verify signatures, map provider IDs to tenant-owned records, and avoid assuming unavailable Voice API webhooks for SIP-trunked calls.

Exact existing files to modify:

- `tenant_portal_api/app.py`: register webhook route if hosted in same FastAPI app.
- Deployment routing config outside the repo may need a public webhook URL, but that is an operational setup item, not code in this document.

New files/modules to create:

- `tenant_portal_api/telephony_webhooks.py`.
- `tenant_portal_api/telephony_queries.py` webhook dedupe functions.
- `tests/test_telephony_webhooks.py`.

Inputs and outputs:

- Inputs: Telnyx webhook headers/body, optional LiveKit webhook headers/body after event surface is confirmed, provider event IDs, provider resource IDs.
- Outputs: deduped event record, normalized order/number/call state update, ignored duplicate/stale event, restricted failed-event record.

Dependencies:

- Confirmed Telnyx webhook event types for APIs actually used.
- Confirmed LiveKit SIP webhook/event availability if used.
- Webhook signing secret environment variable.
- Provider ID mapping tables.

Required database fields or operations:

- `telephony_call_events.provider_event_id` uniqueness where available.
- Store source, event type, internal stage, restricted payload, and timestamp.
- Map provider identifiers to tenant-owned connection/order/number/trunk/call records.
- Failed or unmapped events must be persisted for diagnostics without unsafe tenant mutation.

API routes or service contracts involved:

- `POST /telephony/webhooks/telnyx` or `POST /webhooks/telnyx`.
- Optional LiveKit webhook route only after confirmation.

Error and status handling:

- `webhook_signature_invalid`.
- `webhook_duplicate`.
- `webhook_unmapped_provider_id`.
- Stale events are recorded as ignored events, not applied backwards.
- Do not assume `telnyx_call_control_id` or Telnyx Voice API call webhooks for SIP-trunked calls.
- Use `livekit_sip_call_id` and `livekit_sip_call_id_full` as canonical SIP call-correlation fields.

Required tests:

- Signature verification.
- Duplicate event dedupe.
- Unmapped provider ID.
- Stale event ignored.
- Restricted payload redaction.
- Number-order webhook update.
- LiveKit webhook tests only for confirmed events.

Completion condition:

- Webhooks are safe to expose publicly, idempotent, tenant-mapped through DB records, and unable to leak raw provider payloads to clients.

Information to hand to Habiba:

- Required webhook event storage fields.
- Event IDs used for dedupe.
- Restricted diagnostic payload shape.
- Future portal/admin display fields for webhook failures.

## Polling And Reconciliation Schedulers

Purpose:

Repair eventual consistency, missed webhooks, partial setup failures, stale calls, stuck orders, missing trunks, stale dispatch rules, Outbound Voice Profile drift, and quota leaks.

Exact existing files to modify:

- `scripts/reconcile_sessions.py`: do not overload unless the team explicitly wants a single CLI entrypoint.
- `scripts/simulate_worker_crash.py`: no direct change required unless adding a telephony crash simulation.
- `requirements.txt`: no change expected unless scheduler infrastructure is added.

New files/modules to create:

- `tenant_portal_api/telephony_reconcile.py`.
- `scripts/reconcile_telephony.py`.
- Optional `scripts/simulate_telephony_worker_crash.py`.
- `tests/test_telephony_reconciliation.py`.

Inputs and outputs:

- Inputs: stale pending orders, stale calls, unreleased quota, missing/changed provider resources, disabled profiles/destinations, drift reports.
- Outputs: repaired records, failed/degraded/action-required statuses, call events, metrics, and operational summary.

Dependencies:

- Telnyx adapter status/list functions.
- LiveKit SIP adapter list/get functions.
- Repository locks and transition guards.
- Confirmed polling limits and intervals.

Required database fields or operations:

- Query pending/stuck orders by age/status.
- Query stale calls by status and timestamps.
- Query resources not reconciled since threshold.
- Conditional quota release.
- Conditional usage recording.
- Insert reconciliation call events.
- Record `last_reconciled_at` or `last_synced_at`.

API routes or service contracts involved:

- Internal scheduler/CLI.
- Optional admin diagnostics endpoint.
- Future degraded-state views consume results through portal APIs.

Error and status handling:

- Use bounded retries and exponential backoff with hard limits.
- Do not loop forever.
- Move to visible `action_required`, `degraded`, or `failed` when repair cannot complete.
- Provider outage should degrade affected tenant/resource health, not global readiness.

Required tests:

- Stale order reconciliation.
- Stale call reconciliation.
- Quota leak repair.
- Trunk/rule drift detection.
- Outbound Voice Profile drift detection.
- Partial purchase success plus routing failure recovery.
- Reconciliation idempotency.

Completion condition:

- A dry-run and apply mode can report and repair telephony drift safely with fake providers.
- Stuck calls and quota leaks are not left invisible.

Information to hand to Habiba:

- Reconciliation result fields for future portal/admin consumers.
- Index needs for stale scans.
- Retention of failed-event payloads.

## Logs, Metrics, Tenant Health, And Readiness

Purpose:

Add production visibility without making the whole AwaazLabs service globally unhealthy because one tenant's Telnyx account, SIP connection, balance, destination policy, or provider state fails.

Exact existing files to modify:

- `tenant_portal_api/app.py`: register health/diagnostics routes if exposed through tenant portal API.
- `control_plane/app.py`: modify only for global readiness if telephony core dependencies become part of the same deployment; do not include tenant-specific provider failures in global readiness.

New files/modules to create:

- `tenant_portal_api/telephony_health.py`.
- Optional `tenant_portal_api/telephony_metrics.py`.
- `tests/test_telephony_health.py`.

Inputs and outputs:

- Inputs: DB connectivity, LiveKit API config, Telnyx adapter availability, tenant credential status, SIP routing status, Outbound Voice Profile readiness, recent failure counts.
- Outputs: global health, provider availability metrics, per-tenant Telnyx health, SIP routing health, degraded-state reports, redacted diagnostics.

Dependencies:

- Existing `/healthz` in `tenant_portal_api/app.py`.
- Existing `/healthz/deep` pattern in `control_plane/app.py`.
- Telephony connection/resource status tables.
- Logging/metrics destination decision.

Required database fields or operations:

- Read connection/profile/trunk/rule/call health states tenant-scoped.
- Insert audit or diagnostic events for sensitive operations.
- Store restricted raw payloads only where authorized.

API routes or service contracts involved:

- `GET /portal/telephony/outbound-readiness`.
- Call and number status routes.
- Optional admin diagnostics route if admin integration is approved separately.
- Global health route should cover core AwaazLabs dependencies only.

Error and status handling:

- A revoked key affects only that tenant's Telnyx health.
- Insufficient balance affects only that tenant's outbound readiness.
- Broken SIP routing affects only the number/tenant.
- External Telnyx outage should surface provider degradation without making unrelated tenant data inaccessible.
- Logs must redact phone numbers where policy requires, recipient details, raw provider payloads, provider credentials, HMAC signatures, access tokens, transcripts, prompts, and call context secrets.

Required tests:

- Tenant health isolation.
- Global readiness remains healthy during one tenant provider failure.
- Redaction tests.
- Metrics event emission tests where testable.
- Restricted diagnostics access tests.

Completion condition:

- Operators can distinguish platform health, provider availability, tenant connection health, and per-number routing health.

Information to hand to Habiba:

- Future portal degraded-state response shape.
- User-facing explanations and error codes.
- Restricted diagnostics fields for admin/future portal display decisions.

## Backend Deployment Configuration And Environment Variables

Purpose:

Define backend runtime configuration for telephony without putting secrets in browser code, SDK source, future dashboard env vars, or logs.

Exact existing files to modify:

- `.env.example`: add variable names only, no real values.
- `README.md` or deployment docs: document backend-only telephony env vars after implementation contract is stable.
- `requirements.txt`: only for confirmed pinned dependency changes.
- Do not edit `.env.local` in implementation docs or commits.

New files/modules to create:

- Optional `docs/TELEPHONY_DEPLOYMENT_ENV.md` if env guidance is too large for README.
- Tests for config loading can live in `tests/test_telephony_config.py`.

Inputs and outputs:

- Inputs: process environment variables, secret store config, LiveKit credentials, Telnyx API v2 webhook public key, encryption key/reference.
- Outputs: validated backend config object or startup/runtime error with redacted details.

Dependencies:

- Secret encryption mechanism decision.
- Deployment shape decision for telephony routes and webhook public URL.
- LiveKit SIP API package decision.

Required environment variable names to define, subject to final architecture decision:

- `TELEPHONY_CREDENTIAL_ENCRYPTION_KEY` or secret-store/KMS reference.
- `TELNYX_PUBLIC_KEY`.
- `TELEPHONY_WEBHOOK_PUBLIC_BASE_URL` if provider configuration needs callback URLs.
- `TELEPHONY_PROVIDER_HTTP_TIMEOUT_SEC`.
- `TELEPHONY_RECONCILE_INTERVAL_SEC`.
- `TELEPHONY_RECONCILE_MAX_ATTEMPTS`.
- `TELEPHONY_ENABLE_REAL_PROVIDER_TESTS` for controlled staging tests only.
- Existing `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `SUPABASE_DB_URL`, and tenant portal auth envs remain backend-only where already required.

API routes or service contracts involved:

- Config is consumed by Telnyx adapter, webhook handler, LiveKit SIP adapter, health checks, and reconciliation jobs.

Error and status handling:

- Missing global core config can make the telephony backend unready.
- Tenant-specific Telnyx credential failures must not make global health fail.
- Never log env var values.

Required tests:

- Config loads from environment variable names without exposing values.
- Missing required global config returns a safe startup/readiness error.
- Tenant-specific failures are health data, not global config failures.
- No secret values appear in logs or API responses.

Completion condition:

- Required env var names are documented with no real secret values.
- Backend config is validated in tests.

Information to hand to Habiba:

- Env var names that affect SDK and future portal behavior indirectly.
- Public webhook URL requirement.
- Which readiness failures should be visible to SDK and future portal consumers.

## Controlled Provider Tests And Backend Integration Tests

Purpose:

Build backend confidence using fake providers by default, with controlled real Telnyx/LiveKit staging tests that never run in default CI without explicit credentials and approval.

Exact existing files to modify:

- `tests/conftest.py`: update only if the offline guard needs to recognize telephony tests and prevent accidental provider calls.
- Existing regression tests should remain unchanged unless the implementation requires explicit new fixtures.
- Do not modify SDK tests owned by Habiba, and do not add dashboard tests in this workflow.

New files/modules to create:

- `tests/test_telephony_telnyx_client.py`.
- `tests/test_telephony_connection_api.py`.
- `tests/test_telephony_inventory.py`.
- `tests/test_telephony_number_orders.py`.
- `tests/test_telephony_sip_connection.py`.
- `tests/test_telephony_outbound_voice_profile.py`.
- `tests/test_telephony_livekit_sip.py`.
- `tests/test_telephony_routes.py`.
- `tests/test_machine_telephony_api.py`.
- `tests/test_telephony_inbound_worker.py`.
- `tests/test_telephony_failed_inbound.py`.
- `tests/test_telephony_outbound_calls.py`.
- `tests/test_telephony_quota_idempotency.py`.
- `tests/test_telephony_webhooks.py`.
- `tests/test_telephony_reconciliation.py`.
- `tests/test_telephony_health.py`.
- Optional human-approved staging tests under a clearly named file such as `tests/test_telephony_staging_live.py`, skipped unless explicitly enabled.

Inputs and outputs:

- Inputs: fake provider responses, fake repository fixtures, local/staging DB contract, optional real staging credentials.
- Outputs: passing fake-provider suite, preserved existing regression suite, explicit manual staging checklist.

Dependencies:

- Telephony modules and adapters.
- Habiba's migrations for DB-backed integration tests.
- Ukasha's provider registry for full worker runtime tests.

Required database fields or operations:

- Tests must cover RLS/tenant isolation once Habiba migrations land.
- Tests must cover row locks, idempotency, status transitions, and quota release guards.

API routes or service contracts involved:

- All portal/machine telephony routes.
- Webhook routes.
- Inbound worker resolver.
- Outbound orchestration.
- Reconciliation CLI/service.

Error and status handling:

- Tests should assert stable platform error codes, not raw provider messages.
- Default CI must not call paid/live Telnyx, LiveKit PSTN, STT, LLM, or TTS providers unintentionally.

Required tests:

- Keep existing regression tests: `tests/test_mint.py`, `tests/test_host_backend_contract.py`, `tests/test_machine_agent_api.py`, `tests/test_worker.py`, `tests/test_tools.py`, `tests/test_phase4_portal_api.py`, and relevant health/admin tests.
- Add multi-tenant isolation, concurrency/race, idempotency, duplicate webhook, stale-call reconciliation, partial-failure recovery, trunk/rule reuse, number reassignment active-call protection, high-concurrency inbound/outbound, and Urdu WebRTC regression tests.
- Controlled real Telnyx/LiveKit staging tests must be separate from default CI.

Completion condition:

- Fake-provider backend suite passes.
- Existing WebRTC/Urdu worker behavior remains unchanged.
- Live staging checklist is documented and gated behind explicit approval.

Information to hand to Habiba:

- Contract-test expectations for SDK and future portal consumers.
- Fake response fixtures she can reuse for client-facing tests.
- Error/status examples for user-facing UI handling.

## Habiba Handoff Requirements During Implementation

Purpose:

Keep Habiba unblocked for database, SDK, and client-facing documentation without assigning her implementation work to Hamza.

Exact existing files to modify:

- None specifically for handoff unless the team chooses a shared contract doc.

New files/modules to create:

- `docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md`.
- Optional example JSON fixtures under `tests/fixtures/telephony/`.

Inputs and outputs:

- Inputs: final backend contracts, fake provider fixtures, DB query requirements, route payloads, status/error codes.
- Outputs: concise implementation handoff material for Habiba.

Dependencies:

- Agreement on API/schema contract.
- Backend service signatures.
- Stable status and error modules.

Required database fields or operations:

- All DB requirements listed above must be delivered as requirements, not applied by Hamza.
- Hamza should review Habiba's migration designs for backend compatibility.

API routes or service contracts involved:

- All portal routes as future tenant-portal contracts.
- All machine routes for `@awaazlabs-uva/telephony`.

Error and status handling:

- Habiba needs stable error codes and user-safe messages.
- Unsupported/degraded states must have clear explanations for SDK and future portal consumers.
- SDK errors should map to the same platform codes.

Required tests:

- Shared contract tests that prove route responses match SDK and future portal expectations.
- Fixture parity tests if JSON fixtures are used.

Completion condition:

- Habiba has enough backend contract detail to implement migrations, SDK methods, and client docs without guessing.

Information to hand to Habiba:

- Route list with auth type.
- Machine action strings.
- Request/response JSON examples.
- Error-code list and messages.
- Status enum list and transition rules.
- Required DB fields, indexes, constraints, RLS expectations, and transaction locks.
- Fake-provider fixtures.
- Staging validation checklist.

## Dependencies On Habiba

- Final telephony migrations under `supabase/migrations/*`.
- RLS policies for every tenant-owned telephony table.
- Tenant-scoped foreign keys and uniqueness constraints.
- Indexes for routing lookup, provider ID lookup, idempotency, call listing, stale reconciliation, event dedupe, and API reads.
- Database status constraints or approved app-layer-only transition rules.
- Audit-log tables and data-governance fields.
- Secret encryption storage fields or secret-store references.
- Database verification and rollback planning.
- Migration numbering coordination with Ukasha's provider migrations.
- Final SDK method names and future portal response needs for route contract polishing.

Hamza should not apply migrations, change the live Supabase project, take over SDK implementation, or introduce dashboard implementation.

## Dependencies On Ukasha

- Final provider registry and `AgentRuntimeConfig` shape.
- Final per-agent provider/language/model/voice fields.
- Worker factory changes that preserve the existing Urdu Gladia/Gemini/Uplift pipeline.
- Agreement that every STT and TTS adapter receives `agent_language` from runtime config.
- Worker boundary for telephony-created rooms: telephony supplies trusted tenant/agent/session/call routing; provider registry supplies STT/LLM/TTS construction.
- Regression proof that Urdu WebRTC sessions still transcribe, generate LLM output, synthesize TTS audio, interrupt correctly, close, and record usage.

Hamza must not add telephony-specific provider selection or a second provider pipeline.

## Open Technical Decisions Relevant To Hamza

- Exact LiveKit SIP APIs and whether `livekit-api==1.2.0` is sufficient.
- Exact shape and availability of LiveKit SIP participant attributes: `sip.callID`, `sip.callIDFull`, `sip.trunkPhoneNumber`, `sip.trunkID`, and `sip.ruleID`.
- Whether inbound `sessions` rows are created by worker-side resolver or by a pre-worker telephony orchestrator. Either way, quota reservation must be atomic and independent of browser `/v1/session`.
- Whether telephony phone/SIP usage extends `usage_events.kind` or uses dedicated telephony billing tables.
- Secret encryption mechanism for Telnyx API keys and SIP secrets.
- Whether telephony routes remain inside `tenant_portal_api` or move to a separate deployed FastAPI service. The source plan recommends adding telephony route modules to the tenant portal API deployment.
- First-release Telnyx countries, number types, features, and destination policies.
- Whether Telnyx number reservation is available and worthwhile for supported number types/countries.
- Exact Telnyx Outbound Voice Profile APIs, limits, destination configuration, verification restrictions, and SIP association behavior.
- Confirmed Telnyx webhook event types for account/number/order APIs actually used.
- Confirmed LiveKit SIP webhook/event surface.
- SIP verification test required before marking a connection active.
- Whether external customer/workflow references remain opaque strings or need indexed/searchable structure.
- Retention periods, export permissions, tenant-offboarding behavior, and restricted provider-payload access policy.
- How to store failed inbound calls when no tenant can be resolved.
- Hosting model for reconciliation schedulers and any queue/dead-letter mechanism.

## Expected Handoff Deliverables

- Backend module map and implemented service boundaries.
- Telephony API route contract for portal and machine routes.
- Machine HMAC action strings.
- Stable status enum and transition contract.
- Stable platform error-code contract.
- Database schema/query/transaction/locking requirements for Habiba.
- Telnyx adapter contract and fake-provider fixtures.
- LiveKit SIP adapter contract and fake-provider fixtures.
- Webhook verification and dedupe contract.
- Reconciliation command/service contract.
- Tenant health and readiness response contract.
- Backend deployment env var names with no real secret values.
- Backend tests and staging validation instructions.
- Notes for Habiba's SDK and public integration documentation.

## Definition Of Completion For Hamza

Hamza's implementation is complete when:

- The backend telephony modules are implemented on the `hamza` branch.
- Portal and machine telephony routes call the same service layer and return stable redacted responses.
- Telnyx account verification, rotation, reverification, disconnection, inventory, exact search, optional reservation, exact purchase, order tracking, SIP/FQDN connection, and Outbound Voice Profile readiness are implemented with fake-provider coverage.
- LiveKit inbound trunk, outbound trunk, and SIP dispatch-rule management uses long-lived reusable resources and never creates trunks/rules per call.
- Inbound SIP resolution uses trusted LiveKit SIP attributes and AwaazLabs-owned DB records, not caller-controlled metadata.
- Failed inbound calls terminate cleanly, avoid starting `AgentSession`, record idempotent failures where tenant resolution is possible, and release quota only if reserved.
- Outbound call orchestration validates tenant, agent, number, routing readiness, Outbound Voice Profile, destination, limits, idempotency, and quota before provider side effects.
- Telephony session and quota lifecycle is independent of browser `/v1/session` and releases quota exactly once.
- Webhooks verify signatures, dedupe events, map provider IDs through tenant-owned records, and avoid unsupported Telnyx Voice API assumptions.
- Polling and reconciliation can repair or flag stuck orders, calls, trunks, rules, Outbound Voice Profiles, drift, and quota leaks.
- Logs, metrics, tenant health, and readiness separate global platform health from per-tenant provider failures.
- Existing WebRTC, agent-management, worker, usage, and Urdu pipeline tests remain green.
- New backend telephony tests pass with fake providers by default.
- Controlled real Telnyx/LiveKit staging tests are documented, gated, and separate from default CI.
- Habiba has the final database, SDK, and documentation handoff materials.
- Work is ready for reviewed PR into `staging`, with no direct development on `main`.
