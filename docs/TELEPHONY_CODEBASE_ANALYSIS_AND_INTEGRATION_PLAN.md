# Telephony Codebase Analysis And Integration Plan

This document maps a reusable, production-ready, multi-tenant telephony layer onto the current AwaazLabs Voice-Agent SDK architecture. It is not P2F-specific. P2F is one tenant/platform use case where P2F can connect its own Telnyx account and bill its own customers outside AwaazLabs. The same architecture must support future AwaazLabs tenants without client-specific branches or temporary test-only shortcuts.

Initial production constraint: support one active Telnyx account connection per AwaazLabs tenant. Keep historical disconnected records, and keep the schema safely extendable to multiple active provider connections later.

No telephony implementation exists in the current codebase. `CLAUDE.md` explicitly marks telephony/SIP as out of scope today, and code search found no Telnyx, SIP trunk, phone-number, or PSTN runtime implementation.

## Current Codebase Findings

Current branch state:

- Local branch: `staging`.
- Local branches observed: `main`, `staging`, `backup-staging-before-ukasha-merge`.
- Remote branches observed: `origin/main`, `origin/staging`, `origin/ukasha`, `origin/hamza`, `origin/habiba`.

Existing backend/control-plane services:

- `control_plane/app.py`: FastAPI service for `/v1/session`, `/v1/session/refresh`, `/v1/session/dev-mint`, `/v1/voices`, `/healthz`, `/healthz/deep`. It mints short-lived LiveKit room tokens and dispatches the configured LiveKit agent.
- `control_plane/mint.py`: HMAC validation, tenant status checks, agent ownership check, origin allowlist, quota checks, nonce replay protection, LiveKit JWT creation, `sessions` insert, and `quota_state` increment.
- `tenant_portal_api/app.py`: Tenant dashboard API and server-to-server machine API. Current resources are agents, credentials, sessions, and usage summary.
- `tenant_portal_api/machine_auth.py`: Existing machine-to-machine HMAC scheme for backend-only SDK calls. It signs `tenant_id.timestamp.nonce.action.payload_hash` and reuses `used_nonces`.
- `admin/app.py`: Separate super-admin API with its own JWT/TOTP auth, tenant/session/usage views, credential rotation, and audit logging.
- `examples/host-backend/src/createApp.js`: Reference host backend that accepts browser session requests, signs `/v1/session`, and maps upstream errors.

Tenant authentication and credential handling:

- Browser flow: `sdk/src/index.ts` uses a public `publishableKey` and calls the host app's own `sessionEndpoint`. It does not hold tenant, provider, LiveKit, Supabase, or HMAC secrets.
- Host backend flow: `examples/host-backend/src/signing.js` signs control-plane session requests with the tenant HMAC secret.
- Backend SDK flow: `sdk-server/src/index.ts` implements `@awaazlabs-uva/agents`, a Node backend-only client that signs machine API requests with `tenantSecret`.
- Tenant portal human flow: `tenant_portal_api/auth.py` is used by `tenant_portal_api/app.py` to issue tenant portal JWTs after tenant login.
- Admin flow: `admin/auth.py` is used by `admin/app.py`; admin auth is separate from tenant auth.
- DB secret provider: `control_plane/secrets_db.py` reads `tenants.hmac_secret`; `control_plane/secrets.py` provides env fallback and hashing utilities.
- Environment variables: `.env.example` and `.env.local` contain LiveKit, Supabase, Gladia, Gemini/Google, Uplift, tenant portal, and HMAC-related variable names. Real values must never be copied into SDK/browser code or docs.

Database schema and migrations:

- `supabase/migrations/0001_schema.sql`: Creates `voices`, `tenants`, `agents`, `sessions`, `usage_events`, and `quota_state`.
- `supabase/migrations/0002_rls.sql`: Enables RLS and tenant-isolation select policies on core tenant tables. `voices` is a shared enabled catalogue.
- `supabase/migrations/0004_nonces.sql`: Creates `used_nonces` for replay protection.
- `supabase/migrations/0007_admin.sql`: Creates `admin_users`, `admin_audit_log`, and `mint_rejections`.
- `supabase/migrations/0008_tools.sql`: Adds `sessions.summary` and creates tenant-scoped `escalations`.
- `supabase/migrations/0009_tenant_secrets.sql`: Adds `tenants.hmac_secret`.
- `supabase/migrations/0011_session_transcript.sql`: Adds `sessions.transcript jsonb`.

Current agent and voice APIs:

- `tenant_portal_api/app.py`: `CreateAgentBody` and `UpdateAgentBody` expose `name`, `prompt`, `voice_id`, and `llm_model`.
- `tenant_portal_api/queries.py`: Agent CRUD persists only `name`, `prompt`, `voice_id`, and `llm_model`.
- `sdk-server/src/index.ts`: `@awaazlabs-uva/agents` exposes `createAgent`, `listAgents`, `updateAgent`; it maps JS `voiceId` and `llmModel` to API `voice_id` and `llm_model`.
- `client-submission_v2/sdk/@awaazlabs-uva/agents/src/index.ts`: Delivered copy of the backend agents SDK.
- `control_plane/app.py`: `/v1/voices` reads `voices` and returns enabled voice metadata, with a fallback catalogue if DB reads fail.
- `dashboard/src/lib/portalApi.ts`: Dashboard typed client for agents, credentials, sessions, and usage.
- `dashboard/src/lib/voicesApi.ts`: Dashboard voice catalogue client for control-plane `/v1/voices`.

Dashboard structure:

- `dashboard/src/components/Sidebar.tsx`: Current navigation has Overview, Agents, Usage, Credentials, and Call Sessions.
- `dashboard/src/app/agents/page.tsx` and `dashboard/src/app/agents/[id]/page.tsx`: Agent create/edit and voice selection.
- `dashboard/src/app/sessions/page.tsx`: Session history, transcript, summary, live/stale state.
- `dashboard/src/app/usage/page.tsx`: Quota and usage views.
- `dashboard/src/app/credentials/page.tsx`: Publishable key and HMAC credential display.

LiveKit session and worker architecture:

- `control_plane/mint.py` creates a LiveKit JWT with metadata containing `tenant_id` and `agent_id`.
- `control_plane/app.py` calls `agent_dispatch.create_dispatch(...)` through `_dispatch_agent`.
- `worker/main.py` connects to the LiveKit room, waits for the participant, reads the participant metadata, loads the tenant agent, and starts `AgentSession`.
- `worker/config.py` loads `AgentConfig` through an RLS-scoped read of `agents`.
- `worker/factories.py` instantiates the current STT/LLM/TTS components.
- `worker/tools.py` provides fixed domain-agnostic tools: end conversation with summary, and escalate to human.
- `worker/usage.py` writes `usage_events` for `stt_sec`, `tts_sec`, `llm_tokens`, and `agent_sec`.

Existing call/session logging, status handling, and tests:

- `sessions` is the current conversation/session record. It stores room name, started/ended timestamps, duration, end reason, summary, and transcript.
- `quota_state` tracks current concurrency and monthly minutes.
- `usage_events` is append-only usage accounting, but its `kind` check is limited to `stt_sec`, `tts_sec`, `llm_tokens`, and `agent_sec`.
- `mint_rejections` records control-plane rejections.
- `admin_audit_log` records admin actions.
- `escalations` records human escalation requests from worker tools.
- `scripts/reconcile_sessions.py` repairs stale open sessions and quota counters.
- Existing relevant tests include `tests/test_mint.py`, `tests/test_machine_agent_api.py`, `tests/test_worker.py`, `tests/test_tools.py`, `tests/test_phase4_portal_api.py`, `tests/test_host_backend_contract.py`, `tests/test_admin.py`, and the offline network guard in `tests/conftest.py`.

## What Can Be Reused

- Tenant identity and isolation: `tenants`, `agents`, RLS pattern in `supabase/migrations/0002_rls.sql`, and tenant-scoped queries.
- Backend-only HMAC auth: `tenant_portal_api/machine_auth.py` and the signing pattern in `sdk-server/src/index.ts`.
- Browser secret boundary: `sdk/src/index.ts` and `examples/host-backend/src/createApp.js` already keep secrets out of browser code.
- Agent loading and conversation runtime: `worker/config.py`, `worker/main.py`, `worker/tools.py`, and the current LiveKit worker.
- Session transcript/history: `sessions.summary`, `sessions.transcript`, and `dashboard/src/app/sessions/page.tsx`.
- Quota/concurrency concepts: `control_plane/mint.py`, `quota_state`, and `scripts/reconcile_sessions.py`, but telephony needs its own orchestrator independent of browser `/v1/session`.
- Dashboard auth/client shape: `dashboard/src/lib/portalApi.ts`, `tenant_portal_api/app.py`, and SWR patterns in `dashboard/src/lib/swr-keys.ts`.
- Test style: focused contract tests, tenant isolation tests, and provider network fakes by default.

## Missing Telephony Components

Must be created as production components:

- Encrypted per-tenant Telnyx credential storage, verification, rotation, reverification, disconnection, and compromised-key handling.
- Telnyx API adapter for owned-number inventory, exact available-number search, optional reservation, exact-number purchase, pricing, number orders, order status, and reconciliation.
- Telnyx SIP/FQDN connection management, separate from the tenant's Telnyx API account connection.
- Telnyx Outbound Voice Profile management for outbound SIP calling, associated with the tenant SIP connection.
- LiveKit SIP orchestration for long-lived inbound trunks, one reusable outbound trunk, SIP dispatch rules, SIP call correlation, reconciliation, and cleanup.
- Phone-number inventory, import, synchronization, assignment, routing state, drift detection, and idempotent purchase records.
- Existing Telnyx-number import flow.
- Future custom SIP connection flow for non-Telnyx carriers.
- Inbound call router that resolves LiveKit SIP attributes to tenant, number, and assigned agent from AwaazLabs-owned database records.
- Outbound call orchestration path from backend API request to LiveKit room/worker/SIP/PSTN.
- Telephony call records, call events, provider error mapping, public call status handling, internal stage logging, and outcome storage.
- Backend-only `@awaazlabs-uva/telephony` package.
- Dashboard telephony views that use the same backend telephony API as the SDK.
- Webhook handlers with provider signature verification, event deduplication, bounded retries, and failed-event handling.
- Reconciliation jobs for number orders, managed numbers, trunks, dispatch rules, calls, and quota release.
- Audit logs for credential changes, number purchases/imports, assignments, SIP changes, outbound calls, and disconnections.
- Tests for tenant isolation, concurrency, idempotency, webhooks, routing, SIP orchestration, failure recovery, and preservation of current WebRTC/Urdu behavior.

## Normalized Resource Model

Do not blend Telnyx account, Telnyx SIP connection, phone number, LiveKit trunk, LiveKit dispatch rule, call, and session records. Do not store the same LiveKit trunk or dispatch rule ID in multiple tables. Recommended ownership:

- `tenant_telnyx_connections`: owns the tenant Telnyx API account connection and encrypted API credential.
- `telnyx_sip_connections`: owns the reusable Telnyx SIP/FQDN connection for the tenant.
- `telnyx_outbound_voice_profiles`: owns the tenant outbound calling profile required for outbound SIP readiness.
- `telephony_phone_numbers`: owns AwaazLabs-managed phone-number inventory and agent assignment.
- `livekit_inbound_trunks`: owns LiveKit inbound trunk provider IDs.
- `livekit_outbound_trunks`: owns LiveKit outbound trunk provider IDs.
- `livekit_sip_dispatch_rules`: owns LiveKit SIP dispatch-rule provider IDs.
- `telephony_calls`: owns AwaazLabs call records and canonical LiveKit SIP call identifiers.
- `sessions`: remains the existing voice-agent session table and should be linked from `telephony_calls.session_id`.

Production resource rules:

- One active Telnyx account connection per tenant in the initial design.
- One reusable Telnyx SIP/FQDN connection per active Telnyx account connection.
- One active Telnyx Outbound Voice Profile associated with the tenant SIP connection before outbound calling is ready.
- One long-lived LiveKit inbound trunk and one long-lived LiveKit SIP dispatch rule per phone number where deterministic routing requires it.
- One reusable LiveKit outbound trunk per active Telnyx connection and verified Outbound Voice Profile.
- Trunks and dispatch rules must never be created per call.
- Every resource must support creation, update, failure recovery, disabling, reconciliation, and cleanup.

## Recommended Database Entities

Create new migrations under `supabase/migrations/`. Enable RLS on every tenant-facing table and add tenant-isolation policies matching `supabase/migrations/0002_rls.sql`. Use tenant-scoped uniqueness and foreign-key checks so cross-tenant assignment cannot happen even if API validation regresses.

Recommended entities:

- `tenant_telnyx_connections`
  - Fields: `id`, `tenant_id`, `label`, `platform_status`, `provider_status`, `encrypted_api_key_ref` or `encrypted_api_key_ciphertext`, `key_fingerprint`, `telnyx_account_id`, `last_verified_at`, `permission_last_checked_at`, `created_at`, `updated_at`, `disabled_at`, `disconnected_at`, `compromised_at`.
  - Initial constraint: one active connection per tenant, for example a partial unique index on `(tenant_id)` where `platform_status in ('verifying', 'active', 'rotation_required')`.
  - Keep historical disconnected/disabled rows for audit and troubleshooting.

- `telnyx_sip_connections`
  - Fields: `id`, `tenant_id`, `telnyx_connection_id`, `provider_sip_connection_id`, `sip_fqdn`, `sip_username`, `encrypted_sip_secret_ref`, `platform_status`, `provider_status`, `last_verified_at`, `created_at`, `updated_at`, `disabled_at`.
  - Initial constraint: one active `telnyx_sip_connection_id` per active `telnyx_connection_id`.
  - Do not store LiveKit trunk or dispatch rule IDs here.

- `telnyx_outbound_voice_profiles`
  - Fields: `id`, `tenant_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `provider_outbound_voice_profile_id`, `platform_status`, `provider_status`, `allowed_destinations`, `concurrency_limit`, `channel_limit`, `daily_spending_limit`, `last_verified_at`, `created_at`, `updated_at`, `disabled_at`.
  - The tenant Telnyx SIP connection must be associated with an active Outbound Voice Profile before outbound calls are considered ready.
  - Store only the configuration needed for readiness, policy enforcement, reconciliation, and diagnostics. Do not expose unnecessary raw Telnyx configuration to SDK consumers.
  - Reconcile provider-side changes such as disabled destinations, spending limits, concurrency/channel limits, verification restrictions, or disabled profiles.

- `telephony_phone_numbers`
  - Fields: `id`, `tenant_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `provider_number_id`, `e164_number`, `country`, `number_type`, `features`, `provisioning_status`, `routing_status`, `provider_status`, `assigned_agent_id`, `external_customer_ref`, `last_synced_at`, `created_at`, `updated_at`, `disabled_at`.
  - `assigned_agent_id` references `agents(id)` and is nullable. Assignment is not a phone-number status.
  - Do not store LiveKit trunk or dispatch rule IDs here.
  - Add uniqueness for active `(tenant_id, e164_number)` and validate that `assigned_agent_id` belongs to the same tenant.

- `livekit_inbound_trunks`
  - Fields: `id`, `tenant_id`, `phone_number_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `livekit_inbound_trunk_id`, `platform_status`, `provider_status`, `last_reconciled_at`, `created_at`, `updated_at`, `disabled_at`.
  - Add uniqueness for active `(tenant_id, phone_number_id)`.
  - Never create inbound trunks per call.

- `livekit_outbound_trunks`
  - Fields: `id`, `tenant_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `outbound_voice_profile_record_id`, `livekit_outbound_trunk_id`, `platform_status`, `provider_status`, `last_reconciled_at`, `created_at`, `updated_at`, `disabled_at`.
  - Add uniqueness for active `(tenant_id, telnyx_connection_id)`.
  - Never create outbound trunks per call.

- `livekit_sip_dispatch_rules`
  - Fields: `id`, `tenant_id`, `phone_number_id`, `livekit_inbound_trunk_id`, `livekit_sip_dispatch_rule_id`, `platform_status`, `provider_status`, `last_reconciled_at`, `created_at`, `updated_at`, `disabled_at`.
  - Add uniqueness for active `(tenant_id, phone_number_id)`.
  - Never create SIP dispatch rules per call.

- `telephony_number_orders`
  - Fields: `id`, `tenant_id`, `telnyx_connection_id`, `idempotency_key`, `provider_order_id`, `selected_e164_number`, `country`, `area_code`, `number_type`, `features`, `price_amount`, `price_currency`, `provider_status`, `platform_status`, `raw_provider_status`, `provider_error_payload`, `error_code`, `error_message`, `created_at`, `updated_at`.
  - Add a unique constraint on `(tenant_id, idempotency_key)`.
  - `provider_status` stores normalized Telnyx order state such as `pending`, `success`, `failure`, `cancelled`, or `deleted`.
  - `platform_status` stores AwaazLabs state such as `pending`, `purchased`, `configuring_routing`, `ready`, `action_required`, `failed`, `cancelled`, or `deleted`.

- `telephony_calls`
  - Fields: `id`, `tenant_id`, `session_id`, `agent_id`, `phone_number_id`, `direction`, `room_name`, `from_number`, `to_number`, `recipient`, `call_context`, `external_customer_ref`, `external_workflow_ref`, `inbound_trunk_record_id`, `outbound_trunk_record_id`, `sip_dispatch_rule_record_id`, `livekit_agent_dispatch_id`, `livekit_sip_call_id`, `livekit_sip_call_id_full`, `sip_trunk_phone_number`, `raw_livekit_sip_participant_status`, `platform_status`, `provider_status`, `outcome`, `error_code`, `error_message`, `quota_reserved_at`, `quota_released_at`, `usage_recorded_at`, `started_at`, `answered_at`, `ended_at`, `duration_sec`, `created_at`, `updated_at`.
  - Prefer `telephony_calls.session_id references sessions(id)` instead of replacing `sessions`.
  - LiveKit SIP identifiers are the canonical call-correlation fields for SIP-trunked calls.
  - `inbound_trunk_record_id`, `outbound_trunk_record_id`, and `sip_dispatch_rule_record_id` are internal foreign-key references to the owning resource tables. Keep each LiveKit provider ID only in its corresponding resource table.
  - Provider-ID snapshots may be included in restricted `telephony_call_events` payloads when useful for debugging, but they must not become competing sources of truth.
  - Telnyx Voice API fields such as `telnyx_voice_api_call_control_id` or `telnyx_voice_api_call_session_id` should be nullable and future-only if the Voice API is added later.

- `telephony_call_events`
  - Fields: `id`, `tenant_id`, `telephony_call_id`, `source`, `event_type`, `provider_event_id`, `internal_stage`, `payload`, `created_at`.
  - Add uniqueness for provider event dedupe, for example `(source, provider_event_id)` where applicable.
  - Internal stages belong here, for example `validating`, `quota_reserved`, `session_created`, `room_created`, `livekit_agent_dispatch_created`, `sip_participant_created`, `cleanup_started`, `quota_released`, and `usage_recorded`.

- `telephony_idempotency_keys`
  - Fields: `tenant_id`, `idempotency_key`, `action`, `request_hash`, `response_body`, `platform_status`, `created_at`, `completed_at`.
  - Use for number purchase, outbound call creation, and any retryable operation that could create provider-side side effects.

- `telephony_audit_log`
  - Fields: `id`, `tenant_id`, `actor_type`, `actor_id`, `action`, `target_type`, `target_id`, `detail`, `created_at`.
  - Audit credential changes, number purchases/imports, assignments, SIP changes, outbound calls, and number disconnections.

Existing tables likely to extend:

- `sessions`: either add `channel`/`source` such as `webrtc` or `telephony`, or keep `sessions` unchanged and join through `telephony_calls.session_id`. The second option is safer for backward compatibility.
- `usage_events`: either create separate telephony usage tables or migrate the `kind` check to include phone/SIP billing units. Do not silently insert unsupported kinds.
- `agents`: no telephony fields are required if number assignment lives in `telephony_phone_numbers`. Provider/language work may add agent runtime fields separately.

## Backend API Groups

Recommended approach: add telephony route modules to the tenant portal API deployment so dashboard and SDK use the same backend domain, auth patterns, and service/query layer. The dashboard can use `/portal/telephony/*` with tenant JWT auth; `@awaazlabs-uva/telephony` can use `/machine/telephony/*` with HMAC auth.

Proposed new server modules, not present today:

- `tenant_portal_api/telephony_routes.py`: FastAPI route registration.
- `tenant_portal_api/telephony_queries.py`: DB reads/writes.
- `tenant_portal_api/telephony_service.py`: orchestration, validation, idempotency, status transitions, quota lifecycle.
- `tenant_portal_api/telnyx_client.py`: Telnyx adapter.
- `tenant_portal_api/livekit_sip.py`: LiveKit SIP/trunk/dispatch adapter.
- `tenant_portal_api/telephony_webhooks.py`: provider webhook verification and event handling, or a separate webhook app if deployment needs a different public URL.

Portal/dashboard endpoints:

- `GET /portal/telephony/telnyx/connection`: return active Telnyx connection status without secrets.
- `POST /portal/telephony/telnyx/connect`: verify a Telnyx API key and store it encrypted.
- `POST /portal/telephony/telnyx/rotate`: rotate and reverify the Telnyx API key.
- `POST /portal/telephony/telnyx/reverify`: recheck permissions and account readiness.
- `DELETE /portal/telephony/telnyx/connection`: disconnect or disable a tenant Telnyx connection.
- `GET /portal/telephony/telnyx/owned-numbers`: list numbers currently owned in the connected Telnyx account.
- `GET /portal/telephony/numbers`: list phone numbers already managed by AwaazLabs.
- `POST /portal/telephony/numbers/import`: import an existing Telnyx-owned number into AwaazLabs management.
- `POST /portal/telephony/numbers/sync`: synchronize owned Telnyx numbers into AwaazLabs inventory or drift reports.
- `GET /portal/telephony/numbers/drift`: show numbers removed or changed directly in Telnyx.
- `POST /portal/telephony/available-numbers/search`: search exact available numbers by country, area code, type, and features.
- `POST /portal/telephony/number-reservations`: optionally reserve one selected exact number if Telnyx supports reservation for that number type.
- `POST /portal/telephony/number-orders`: purchase one exact selected number with idempotency.
- `GET /portal/telephony/number-orders/{order_id}`: get order status.
- `PATCH /portal/telephony/numbers/{number_id}/assignment`: assign, reassign, or unassign an agent.
- `POST /portal/telephony/telnyx/sip-connection`: create or update the reusable tenant Telnyx SIP/FQDN connection.
- `POST /portal/telephony/telnyx/sip-connection/test`: verify/test SIP configuration.
- `POST /portal/telephony/telnyx/outbound-voice-profile`: create, select, or update the tenant Outbound Voice Profile.
- `POST /portal/telephony/telnyx/outbound-voice-profile/reverify`: verify destinations, limits, and outbound eligibility.
- `POST /portal/telephony/numbers/{number_id}/routing/configure`: create or repair the long-lived LiveKit inbound trunk and SIP dispatch rule for that number.
- `POST /portal/telephony/telnyx/outbound-trunk/configure`: create or repair the reusable LiveKit outbound trunk for the active Telnyx connection.
- `GET /portal/telephony/outbound-readiness`: check tenant outbound readiness without exposing raw Telnyx configuration.
- `POST /portal/telephony/outbound-calls`: create outbound call.
- `GET /portal/telephony/calls`: list call records.
- `GET /portal/telephony/calls/{telephony_call_id}`: get call status, transcript link, events, and outcome.
- `POST /portal/telephony/numbers/{number_id}/disable`: disable or disconnect a number.

Machine SDK endpoints should mirror the same responsibilities under `/machine/telephony/*`, with fixed action strings such as:

- `telephony.telnyx_connection.connect`
- `telephony.telnyx_connection.rotate`
- `telephony.telnyx_connection.reverify`
- `telephony.telnyx_connection.disconnect`
- `telephony.telnyx_connection.status`
- `telephony.telnyx_owned_numbers.list`
- `telephony.managed_numbers.list`
- `telephony.managed_numbers.import`
- `telephony.managed_numbers.sync`
- `telephony.managed_numbers.drift`
- `telephony.available_numbers.search`
- `telephony.number_reservations.create`
- `telephony.number_orders.create`
- `telephony.number_orders.get`
- `telephony.numbers.assign_agent`
- `telephony.telnyx_sip_connection.upsert`
- `telephony.telnyx_sip_connection.test`
- `telephony.telnyx_outbound_voice_profile.upsert`
- `telephony.telnyx_outbound_voice_profile.reverify`
- `telephony.number_routing.configure`
- `telephony.outbound_trunk.configure`
- `telephony.outbound_readiness.get`
- `telephony.outbound_calls.create`
- `telephony.calls.get`
- `telephony.calls.list`
- `telephony.numbers.disable`

Outbound Voice Profile service responsibilities:

- Create or select an Outbound Voice Profile for the tenant's active Telnyx connection.
- Associate the profile with the tenant `telnyx_sip_connection_id`.
- Verify allowed destinations, daily spending limits, concurrency/channel limits, and Telnyx verification restrictions before outbound calls.
- Reconcile provider-side profile changes and mark outbound readiness degraded or failed when limits or destination policy block calls.
- Return only stable readiness state and redacted policy summaries to SDK/dashboard consumers.

Webhook endpoints:

- `POST /webhooks/telnyx` or `POST /telephony/webhooks/telnyx`: verify Telnyx signatures, map provider identifiers to tenant-owned rows, dedupe event IDs, and update order/number state only for event types confirmed for the Telnyx APIs actually used.
- `POST /webhooks/livekit` or equivalent if LiveKit SIP webhooks are available and enabled for trunks/calls in the deployed plan.
- Do not assume Telnyx Voice API call-control webhooks for SIP-trunked calls. Use LiveKit SIP call identifiers as the canonical call correlation fields.

## Runtime Flow Mapping

Inbound calls:

```text
Caller
-> Telnyx
-> SIP
-> LiveKit inbound trunk
-> Dispatch rule
-> LiveKit room
-> Assigned AwaazLabs agent
-> STT/LLM/TTS conversation
```

Production inbound routing strategy:

1. The worker receives or waits for the LiveKit SIP participant.
2. Read LiveKit SIP attributes from the participant, including `sip.callID`, `sip.callIDFull`, `sip.trunkPhoneNumber`, `sip.trunkID`, and `sip.ruleID`.
3. Resolve `sip.trunkPhoneNumber` to `telephony_phone_numbers.e164_number`.
4. Resolve the tenant and nullable `assigned_agent_id` from AwaazLabs-owned DB records.
5. Validate `sip.trunkID` against `livekit_inbound_trunks.livekit_inbound_trunk_id` for the resolved `phone_number_id`.
6. Validate `sip.ruleID` against `livekit_sip_dispatch_rules.livekit_sip_dispatch_rule_id` for the resolved `phone_number_id`.
7. Lock the phone-number/routing row during resolution so reassignment cannot race an active call start.
8. Create or link `telephony_calls` and `sessions` using `livekit_sip_call_id` and `livekit_sip_call_id_full` idempotently.
9. Reserve tenant concurrency/quota atomically before starting the voice session.
10. Load the assigned agent configuration through the existing tenant-safe worker path.
11. Start `AgentSession` with the same STT/LLM/TTS pipeline selected by the provider registry work.

Do not trust caller-controlled metadata for tenant, client, agent, routing, or authorization decisions. Phone-number and trunk/rule resolution must be based on AwaazLabs-owned database records.

Current architecture gap: `worker/main.py` currently reads `tenant_id` and `agent_id` from the joining participant metadata created by the browser `/v1/session` token. Inbound SIP calls must not depend on that browser `/v1/session` mint path. Telephony should add a minimal worker-side resolver that can build trusted runtime config from LiveKit SIP attributes and DB records.

Outbound calls:

```text
Client backend request
-> AwaazLabs validation
-> LiveKit room and agent dispatch
-> LiveKit outbound SIP trunk
-> Telnyx PSTN call
-> Recipient
-> Call status, transcript and outcome storage
```

Outbound request payload:

- `agentId`
- `fromNumberId`
- `toNumber`
- `recipient`
- `variables` or `context`
- Optional `externalCustomerRef`
- Optional `externalWorkflowRef`
- `idempotencyKey`

Outbound production flow:

1. Validate tenant HMAC/JWT and tenant status.
2. Validate `agentId` belongs to tenant.
3. Validate `fromNumberId` belongs to tenant, is provisioned, routing-ready, outbound-ready, and not disabled.
4. Validate the active `telnyx_outbound_voice_profiles` record for the tenant SIP connection.
5. Validate destination number format, allowed destination policy, spending limits, concurrency/channel limits, and Telnyx verification restrictions.
6. Validate the reusable `livekit_outbound_trunk_id` for the tenant's active `telnyx_connection_id`.
7. Enforce idempotency before making any LiveKit or provider call.
8. Reserve concurrency/quota, create `sessions`, and create `telephony_calls` in one transaction.
9. Create or dispatch the LiveKit agent for the room and store `livekit_agent_dispatch_id`.
10. Create the outbound SIP participant/call through the reusable LiveKit outbound trunk.
11. Track public `platform_status` and internal stages in `telephony_call_events`.
12. Release quota exactly once and record usage when the call ends or setup fails.

Current architecture gap: `control_plane/mint.py` is a browser/WebRTC token mint path. Inbound and outbound telephony must not depend on browser `/v1/session`. Create a telephony session orchestrator that reuses the same tenant/agent/quota semantics, but owns phone-call room creation, call IDs, trunk validation, and status updates.

## Telephony Quota Lifecycle

Telephony needs a production-safe quota lifecycle separate from browser token minting:

1. Start a DB transaction.
2. Validate tenant exists and is active.
3. Validate agent ownership and agent availability.
4. Validate phone-number ownership, provisioning status, routing status, and assignment.
5. Validate the expected `telnyx_connection_id`, `telnyx_sip_connection_id`, `outbound_voice_profile_record_id`, `inbound_trunk_record_id` or `outbound_trunk_record_id`, and `sip_dispatch_rule_record_id` where applicable.
6. Lock the relevant phone-number and call/idempotency rows with row-level locks.
7. Check concurrency and monthly quota.
8. Insert `sessions` and `telephony_calls`, or idempotently return the existing matching call.
9. Set `quota_reserved_at` and increment `quota_state.concurrent_now` in the same transaction.
10. Commit before starting external call execution.
11. Execute LiveKit/Telnyx operations with bounded retries and event logging.
12. On call end or setup failure, release quota with a conditional update such as `where quota_released_at is null`.
13. Record usage once with a guard such as `usage_recorded_at is null`.
14. Reconcile stale calls and leaked quota through a scheduled job.

This design must prevent quota leaks, double releases, duplicate outbound calls, multiple workers handling the same SIP call, calls proceeding after tenant suspension, cross-tenant assignment, race conditions during number reassignment, and stale webhooks moving calls backwards.

## Failed Inbound Calls

For inbound SIP calls where the participant reaches LiveKit but the platform cannot safely start the agent, the worker/orchestrator must fail closed:

- Unknown number: reject or terminate the SIP participant cleanly. If no tenant can be resolved, record a restricted platform-level event without tenant-scoped call data; if tenant can be inferred from trunk/rule, create an idempotent failed `telephony_calls` row.
- No agent assigned: create or update a tenant-scoped failed call/event record with `number_not_assigned`, do not start `AgentSession`, and terminate cleanly.
- Tenant suspended: create or update a failed call/event record where tenant resolution is possible, store `tenant_not_active`, do not reserve quota, and terminate cleanly.
- Routing identifiers do not match: store `routing_identifier_mismatch`, do not trust the call, do not start `AgentSession`, and terminate cleanly.
- Quota cannot be reserved: store `quota_reservation_failed` or quota-specific error, do not start `AgentSession`, and terminate cleanly.
- Assigned agent cannot load: store `assigned_agent_load_failed`, release quota only if it was reserved, and terminate cleanly.
- Provider pipeline cannot start: store `provider_pipeline_start_failed`, release quota only if it was reserved, avoid starting or continue draining `AgentSession` depending on failure timing, and terminate cleanly.

Rules:

- Use `livekit_sip_call_id`/`livekit_sip_call_id_full` plus trunk/rule records for idempotency so multiple workers cannot handle the same inbound call.
- Release quota only when `quota_reserved_at` is set and `quota_released_at` is null.
- Avoid exposing internal failure details to the caller.
- Support an optional future fallback message or fallback destination, but do not silently enable fallback behavior in the current design.

## `@awaazlabs-uva/telephony` Package

Recommended package: backend-only Node SDK, matching `@awaazlabs-uva/agents`.

Proposed new package root, not present today:

```text
telephony/
  package.json
  tsconfig.json
  README.md
  src/
    index.ts
    signing.ts
    types.ts
```

If included in client deliverables, mirror it under:

```text
client-submission_v2/sdk/@awaazlabs-uva/telephony/
```

Package rules:

- Backend-only. Never import in browser code.
- Holds only the tenant HMAC secret passed by the client backend at runtime.
- `connectTelnyxAccount` may accept a Telnyx API key transiently.
- The SDK sends that key to AwaazLabs over TLS and must never persist, cache, log, or return it.
- AwaazLabs encrypts the credential at rest and associates it with the verified tenant.
- After connection succeeds, other SDK operations must not require the raw Telnyx API key again.
- Reuse the canonical JSON and HMAC pattern from `sdk-server/src/index.ts`.
- Use typed methods for connection, numbers, SIP, outbound calls, call lookup, and disable/disconnect flows.
- Keep error shape similar to `AwaazLabsUvaAgentsError`, but with telephony-specific categories and codes.

Conceptual SDK methods:

- `connectTelnyxAccount({ apiKey, label? })`
- `rotateTelnyxAccountKey({ apiKey })`
- `reverifyTelnyxAccount()`
- `disconnectTelnyxAccount()`
- `getConnectionStatus()`
- `listTelnyxOwnedNumbers()`
- `listManagedPhoneNumbers()`
- `importTelnyxNumber({ e164Number, externalCustomerRef? })`
- `syncTelnyxOwnedNumbers()`
- `getTelnyxNumberDrift()`
- `searchAvailableNumbers({ country, areaCode?, numberType?, features? })`
- `reserveNumber({ e164Number, idempotencyKey })`
- `purchaseNumber({ e164Number, externalCustomerRef?, idempotencyKey })`
- `getNumberOrderStatus(orderId)`
- `assignAgentToNumber(numberId, agentId)`
- `unassignAgentFromNumber(numberId)`
- `upsertTelnyxSipConnection(...)`
- `verifyTelnyxSipConnection()`
- `upsertTelnyxOutboundVoiceProfile(...)`
- `verifyTelnyxOutboundVoiceProfile()`
- `getOutboundReadiness()`
- `configureNumberRouting(numberId)`
- `configureOutboundTrunk()`
- `createOutboundCall({ agentId, fromNumberId, toNumber, recipient?, context?, externalCustomerRef?, externalWorkflowRef?, idempotencyKey })`
- `getCallStatus(telephonyCallId)`
- `listCallRecords(filters?)`
- `disableNumber(numberId)`

Credential lifecycle requirements:

- Rotation must verify the new key before replacing the active encrypted credential.
- Reverification must detect permission loss, account suspension, insufficient permissions, and revoked keys.
- Disconnection must disable new number/call actions while preserving historical numbers, orders, calls, and audit logs.
- Compromised-key handling must immediately disable use of the credential, require rotation, and audit the event.

## Dashboard Integration Areas

Do not implement dashboard changes in this phase. Future dashboard work should add telephony views while reading the same telephony backend API used by the SDK.

Likely new dashboard areas:

- Telnyx connection status, connect/disconnect, credential rotation, reverification, permission failure, and compromised-key handling. The API-key form must clear the key after submission and must never persist, log, redisplay, or store it in browser storage.
- Separate Telnyx-owned number inventory and AwaazLabs-managed number inventory.
- Import and synchronize existing Telnyx numbers.
- Available-number exact search, optional reservation, and exact-number purchase.
- Number order status.
- Assign/reassign/unassign number to agent, with active-call protection.
- Telnyx SIP/FQDN connection setup and verification.
- Telnyx Outbound Voice Profile selection/setup, destination eligibility, limits, and verification status.
- LiveKit inbound trunk/dispatch-rule routing readiness per number.
- LiveKit outbound trunk readiness per Telnyx connection.
- Outbound readiness summary that reports disabled destinations, spending limits, concurrency/channel limits, and verification restrictions without showing unnecessary raw Telnyx configuration.
- Outbound call test/creation view.
- Telephony call records, statuses, transcripts, provider errors, internal events, and outcomes.
- Admin visibility for tenant connection health and repeated telephony failures.

Likely files to extend later:

- `dashboard/src/components/Sidebar.tsx`
- `dashboard/src/lib/portalApi.ts`
- `dashboard/src/lib/swr-keys.ts`
- `dashboard/src/app/sessions/page.tsx`
- New route group such as `dashboard/src/app/telephony/...`

## Telnyx And LiveKit Responsibility Boundaries

Telnyx account owner responsibilities:

- Business/KYC verification.
- Telnyx billing and regulatory obligations.
- Owning the Telnyx account, API key, purchased numbers, and PSTN usage.
- Maintaining sufficient Telnyx balance and required regulatory documents.
- P2F-specific billing of P2F's own customers, if P2F chooses to do that.

AwaazLabs responsibilities:

- Verify and store each tenant's Telnyx API key encrypted.
- Never embed Telnyx keys in frontend source, frontend environment variables, frontend SDKs, dashboard bundles, logs, transcripts, prompts, or call context.
- The dashboard connection form may hold a user-entered Telnyx API key only for the submission lifecycle. It must submit the key once over TLS directly to the trusted AwaazLabs backend, then clear the input and related state.
- Never persist Telnyx keys in local storage, session storage, IndexedDB, cookies, or long-lived frontend application state.
- Never log, cache, return, or redisplay a raw Telnyx key after connection.
- Use the correct tenant's Telnyx connection for every number/search/order/import/sync/call action.
- Store tenant numbers, optional external customer refs, assignments, order states, call states, transcripts, events, and errors.
- Import and synchronize Telnyx-owned numbers.
- Create and reconcile Telnyx SIP/FQDN connections, Telnyx Outbound Voice Profiles, LiveKit SIP trunks, and LiveKit SIP dispatch rules.
- Validate readiness before inbound routing and outbound calls.
- Translate Telnyx and LiveKit failures into clear platform errors.
- Keep P2F and future client billing workflows outside AwaazLabs unless separately productized.

LiveKit responsibilities:

- SIP media bridge, inbound/outbound trunks, room creation/participation, dispatch rules, and media flow into the existing worker.
- SIP participant attributes such as `sip.callID`, `sip.callIDFull`, `sip.trunkPhoneNumber`, `sip.trunkID`, and `sip.ruleID`.
- Exact SIP API methods and metadata behavior must be verified against the installed LiveKit SDK and deployed LiveKit plan before implementation.

Telnyx Voice API boundary:

- The current telephony design is SIP trunking based.
- Do not assume `telnyx_call_control_id`, `telnyx_call_session_id`, or Voice API call webhooks exist for SIP-trunked calls.
- Keep Telnyx Voice API-specific fields optional and future-only.
- Only recommend Telnyx webhooks for event types confirmed to exist for the Telnyx APIs actually used.
- Use bounded polling and reconciliation where webhook coverage is incomplete.

## Multi-Tenant Security And Credential Encryption

Requirements:

- Telnyx API keys are tenant-specific secrets. They may be entered into a secure dashboard connection form or passed transiently through the backend-only SDK during `connectTelnyxAccount`, but they must never be embedded in frontend code or persisted client-side.
- A tenant can only see and use its own Telnyx connection, SIP connection, Outbound Voice Profile, numbers, orders, trunks, dispatch rules, calls, and events.
- Webhook handlers must not trust tenant IDs from payloads. Map provider IDs to stored tenant-owned records.
- Secrets must be encrypted at rest with a deliberate mechanism such as Supabase Vault, KMS, or envelope encryption. Do not store raw Telnyx API keys in plaintext DB columns.
- Backend connection APIs must encrypt the key immediately and return only masked connection metadata.
- Frontend code must clear the key input and related transient state after submission.
- Store non-secret metadata such as `key_fingerprint`, `last_verified_at`, and masked status for display.
- Redact phone provider payloads before logging where they may contain secrets or personal data.
- Keep RLS enabled on all new tenant-visible tables.
- Use tenant-scoped uniqueness and foreign-key validation for every tenant-owned relation.
- Prevent cross-tenant agent, number, Outbound Voice Profile, trunk, dispatch-rule, and call assignment at both API and DB levels.
- Select the correct encrypted Telnyx credential for every operation by `tenant_id` and active `telnyx_connection_id`.
- Add per-tenant rate limits for connection changes, number search, purchases, imports, sync, SIP changes, outbound calls, and webhook-derived processing.
- Audit credential changes, number purchases, imports, assignments, SIP changes, outbound calls, and number disconnection.
- Isolate failures per tenant so one client's Telnyx, SIP, quota, or routing failure does not affect other tenants.
- Use DB owner/service connections only in trusted backend services, never from browser code.

## Data Governance

Telephony records may contain personal or sensitive information, including phone numbers, recipient details, call context, transcripts, summaries, provider events, and error payloads.

Requirements:

- Define configurable retention periods for call records, call events, transcripts, summaries, raw provider payloads, and audit logs.
- Avoid indefinite retention by default. Keep only what is needed for operations, support, billing, compliance, and tenant reporting.
- Separate operational metadata from client-visible call data. Clients should see stable statuses, summaries, transcript fields they are authorized to view, and redacted errors, not raw provider payloads by default.
- Encrypt sensitive records at rest where supported by the chosen storage layer and encryption design.
- Restrict raw provider payload access to trusted backend/admin diagnostics.
- Redact secrets, provider credentials, access tokens, and sensitive provider payload fields from logs and user-facing errors.
- Prevent secrets from entering transcripts, prompts, call context, summaries, or provider-visible metadata.
- Audit access to transcripts, summaries, call records, exports, and restricted provider payloads.
- Define tenant-offboarding behavior: disable new calls, disconnect or release resources according to contract, export tenant data if authorized, then delete or anonymize retained records according to retention policy.
- Exports must be tenant-scoped, access-controlled, audited, and redacted according to the recipient's authorization.

## Status Modelling

Use both `provider_status` and normalized `platform_status` where a provider has its own state. Preserve raw provider status and restricted provider error payloads for debugging, but return stable AwaazLabs statuses and error codes to clients.

Suggested `telnyx_connection_platform_status`:

- `not_connected`
- `verifying`
- `active`
- `verification_failed`
- `rotation_required`
- `permission_failed`
- `compromised`
- `disabled`
- `disconnected`

Suggested `phone_number_provisioning_status`:

- `discovered`
- `import_pending`
- `imported`
- `purchase_pending`
- `purchase_failed`
- `owned`
- `provider_removed`
- `suspended`
- `disabled`
- `released`
- `deleted`

Suggested `phone_number_routing_status`:

- `not_configured`
- `configuring`
- `ready`
- `degraded`
- `failed`
- `disabled`

Use nullable `assigned_agent_id` for assignment. Do not use `assigned` or `unassigned` as phone-number statuses.

Suggested Telnyx `number_order_provider_status`:

- `pending`
- `success`
- `failure`
- `cancelled`
- `deleted`

Suggested AwaazLabs `number_order_platform_status`:

- `pending`
- `purchased`
- `configuring_routing`
- `ready`
- `action_required`
- `failed`
- `cancelled`
- `deleted`

`action_required` is an AwaazLabs platform status, not a raw Telnyx order status.

Suggested `telnyx_sip_connection_platform_status` and LiveKit trunk/rule platform statuses:

- `draft`
- `pending_verification`
- `testing`
- `active`
- `failed`
- `disabled`

Suggested `telnyx_outbound_voice_profile_platform_status`:

- `not_configured`
- `configuring`
- `active`
- `destination_restricted`
- `limit_reached`
- `verification_required`
- `failed`
- `disabled`

Suggested `call_direction`:

- `inbound`
- `outbound`

Public `call_status` must stay limited to stable lifecycle states:

- `queued`
- `dialing`
- `ringing`
- `in_progress`
- `completed`
- `busy`
- `no_answer`
- `failed`
- `cancelled`

Internal stages such as `validating`, `quota_reserved`, `room_created`, `dispatching_agent`, `sip_participant_created`, and `cleanup_started` belong in `telephony_call_events`, not the public call status.

Store raw LiveKit SIP participant status separately, for example `raw_livekit_sip_participant_status` on `telephony_calls` or as restricted call events. Do not force inbound calls through outbound-only states such as `dialing`.

Suggested `call_end_reason`:

- `caller_hangup`
- `recipient_hangup`
- `agent_ended`
- `provider_error`
- `livekit_error`
- `validation_failed`
- `timeout`
- `cancelled`
- `unknown`

Valid public outbound call status transitions:

- `queued` -> `dialing`, `failed`, `cancelled`
- `dialing` -> `ringing`, `in_progress`, `busy`, `no_answer`, `failed`, `cancelled`
- `ringing` -> `in_progress`, `busy`, `no_answer`, `failed`, `cancelled`
- `in_progress` -> `completed`, `failed`, `cancelled`
- Terminal statuses: `completed`, `busy`, `no_answer`, `failed`, `cancelled`

Valid public inbound call status transitions:

- `ringing` -> `in_progress`, `failed`, `cancelled`
- `in_progress` -> `completed`, `failed`, `cancelled`
- Terminal statuses: `completed`, `failed`, `cancelled`

Reject invalid or stale status updates unless they are explicitly recorded as ignored events in `telephony_call_events`.

## Naming Rules

Use unambiguous names everywhere:

- `telnyx_connection_id`: AwaazLabs DB row for a tenant's Telnyx API account connection.
- `telnyx_sip_connection_id`: AwaazLabs DB row for the tenant's Telnyx SIP/FQDN connection.
- `outbound_voice_profile_record_id`: AwaazLabs DB row for the tenant's Telnyx Outbound Voice Profile.
- `provider_outbound_voice_profile_id`: Telnyx provider ID for the Outbound Voice Profile.
- `inbound_trunk_record_id`: AwaazLabs DB row for the inbound trunk used by a call.
- `outbound_trunk_record_id`: AwaazLabs DB row for the outbound trunk used by a call.
- `sip_dispatch_rule_record_id`: AwaazLabs DB row for the SIP dispatch rule used by an inbound call.
- `livekit_inbound_trunk_id`: LiveKit provider ID for an inbound SIP trunk.
- `livekit_outbound_trunk_id`: LiveKit provider ID for an outbound SIP trunk.
- `livekit_sip_dispatch_rule_id`: LiveKit SIP dispatch-rule provider ID.
- `livekit_agent_dispatch_id`: LiveKit agent dispatch ID created when assigning the worker to a room.
- `livekit_sip_call_id`: Value derived from LiveKit SIP attribute `sip.callID`.
- `livekit_sip_call_id_full`: Value derived from LiveKit SIP attribute `sip.callIDFull`.
- `telephony_call_id`: AwaazLabs DB ID for the telephony call row.
- `session_id`: AwaazLabs DB ID for the existing `sessions` row.

Avoid broad names such as `dispatch_id`, `connection_id`, `trunk_id`, or `call_id` in new APIs and DB columns where the owning system is ambiguous.

## Error-Code Categories

Use stable platform error codes instead of leaking raw provider errors directly.

- Auth and tenant state: `telephony_auth_failed`, `tenant_not_active`, `tenant_not_found`.
- Credentials: `telnyx_connection_missing`, `telnyx_key_invalid`, `telnyx_key_unauthorized`, `telnyx_key_permission_failed`, `telnyx_key_compromised`, `provider_credentials_missing`.
- Validation: `agent_not_found`, `number_not_found`, `number_not_owned_by_tenant`, `number_not_assigned`, `number_not_routing_ready`, `outbound_voice_profile_missing`, `outbound_destination_disabled`, `outbound_spending_limit_reached`, `outbound_concurrency_limit_reached`, `outbound_verification_required`, `invalid_to_number`, `unsupported_number_feature`, `outbound_not_ready`.
- Idempotency: `duplicate_idempotency_key`, `idempotency_payload_mismatch`.
- Provider/API: `telnyx_api_error`, `telnyx_rate_limited`, `number_not_available`, `insufficient_telnyx_balance`, `number_order_action_required`, `regulatory_action_required`, `provider_timeout`.
- LiveKit/SIP: `livekit_inbound_trunk_failed`, `livekit_outbound_trunk_failed`, `livekit_sip_dispatch_rule_failed`, `livekit_agent_dispatch_failed`, `sip_verification_failed`, `sip_media_failed`.
- Runtime: `call_setup_failed`, `call_state_conflict`, `quota_reservation_failed`, `quota_release_failed`, `unknown_inbound_number`, `routing_identifier_mismatch`, `assigned_agent_load_failed`, `provider_pipeline_start_failed`, `worker_metadata_missing`, `worker_session_failed`.
- Webhooks: `webhook_signature_invalid`, `webhook_duplicate`, `webhook_unmapped_provider_id`.
- Data governance: `retention_policy_violation`, `export_not_authorized`, `restricted_payload_access_denied`.

## Number Inventory And Purchase Flow

Separate Telnyx inventory from AwaazLabs-managed inventory:

- Telnyx-owned inventory: numbers currently visible in the connected tenant Telnyx account.
- AwaazLabs-managed inventory: numbers imported, purchased, configured, assigned, and tracked by AwaazLabs.
- Import operation: attaches an existing Telnyx-owned number to AwaazLabs management after ownership and capability verification.
- Sync operation: detects new, changed, removed, suspended, or feature-changed numbers in Telnyx.
- Drift operation: reports mismatches between Telnyx and AwaazLabs records without silently rewriting assignments or routing.

Production purchase flow:

1. Search exact available numbers.
2. Optionally reserve the selected number if the provider supports reservation.
3. Purchase the exact selected `e164Number`.
4. Track provider and platform order statuses.
5. Synchronize the purchased number into `telephony_phone_numbers`.
6. Configure the reusable Telnyx SIP connection if missing.
7. Create or associate an active Telnyx Outbound Voice Profile for the tenant SIP connection.
8. Configure long-lived LiveKit inbound trunk and SIP dispatch rule for the number.
9. Configure or verify the reusable LiveKit outbound trunk for the tenant Telnyx connection.
10. Assign the number to an agent.

Do not purchase directly from broad country or area-code criteria without an exact selected number.

Production purchase requirements:

- Idempotent purchase requests with duplicate-click protection.
- Clear handling when a number becomes unavailable after search.
- Clear handling for insufficient Telnyx balance.
- Regulatory action-required state.
- Pending order state that survives process restarts.
- Webhook delays handled by bounded polling fallback.
- Partial setup failure after successful purchase must leave the number owned but `routing_status = failed` or `degraded`, with retryable configure-routing and outbound-readiness workflows.
- Reconciliation must repair or flag drift across Telnyx order state, Telnyx owned-number inventory, Telnyx Outbound Voice Profiles, AwaazLabs phone-number rows, LiveKit trunks, and LiveKit SIP dispatch rules.

## Webhook, Polling, And Idempotency

Webhook requirements:

- Verify Telnyx webhook signatures before reading business fields.
- Dedupe by provider event ID.
- Store raw provider payloads only in restricted/event tables and redact before user-facing display.
- Update `telephony_number_orders`, `telephony_calls`, and `telephony_call_events` idempotently.
- Map provider identifiers to tenant-owned connection/order/call rows; never accept caller-supplied tenant IDs.
- Only use Telnyx webhooks for event types confirmed to exist for the Telnyx APIs actually used.
- Do not assume Telnyx Voice API call webhooks for SIP-trunked calls.

Polling requirements:

- Poll order status when webhook delivery is delayed or missed.
- Poll number inventory, routing readiness, and call state where LiveKit or Telnyx exposes eventual consistency or missing webhook coverage.
- Use bounded retries and visible `action_required` or `failed` statuses rather than infinite background loops.

Idempotency requirements:

- Require idempotency keys for number purchases and outbound call creation.
- Store request hash and final response for each idempotent action.
- Same key and same payload returns the original result.
- Same key with a different payload returns `idempotency_payload_mismatch`.
- Use provider idempotency headers/features where Telnyx supports them, but keep AwaazLabs DB idempotency as the first line of defense.

Reliability requirements:

- Retry transient provider failures with exponential backoff and hard limits.
- Persist failed events for later inspection or replay.
- Add reconciliation jobs for number orders, calls, trunks, dispatch rules, and quotas.
- Add timeout handling for call setup, ringing, SIP participant creation, and cleanup.
- Emit structured logs with tenant IDs, stable internal IDs, provider IDs, and redacted payloads.
- Add metrics and alerts for credential failures, purchase failures, trunk/rule drift, call setup failures, stuck calls, quota leaks, and webhook failure rates.
- Add global health/readiness checks for core AwaazLabs dependencies required to serve requests, such as database connectivity, tenant API process readiness, LiveKit API credential/configuration readiness, and worker dependency readiness.
- Track Telnyx API availability, LiveKit SIP behavior, tenant Telnyx connection health, and SIP routing health separately from global service readiness.
- Document operational recovery for partially configured numbers, stuck orders, stuck calls, missing trunks, stale dispatch rules, and unreleased quota.

## Readiness And Tenant Health

Do not make the entire AwaazLabs service globally unready because one tenant has a revoked Telnyx key, insufficient Telnyx balance, a broken SIP connection, disabled destinations, exhausted provider limits, or a temporary Telnyx outage.

Global health/readiness should cover core AwaazLabs dependencies required to serve requests:

- Database connectivity and migration compatibility.
- Tenant portal/control-plane process readiness.
- LiveKit API credential/configuration readiness.
- Worker dependency readiness.
- Required internal queues/schedulers if reconciliation workers are introduced.

Track separately:

- Provider availability metrics for Telnyx and LiveKit SIP operations.
- Per-tenant Telnyx connection health.
- Per-tenant Telnyx Outbound Voice Profile readiness.
- Per-number SIP routing health.
- Degraded-state reporting in dashboard/admin APIs.
- Alerts and admin diagnostics for tenant-specific failures.

Failures must remain isolated to the affected tenant wherever possible.

## Required Tests

Preserve existing tests:

- `tests/test_mint.py`: browser/WebRTC token mint behavior.
- `tests/test_host_backend_contract.py`: host backend/control-plane contract.
- `tests/test_machine_agent_api.py`: machine HMAC auth behavior.
- `tests/test_worker.py` and `tests/test_tools.py`: worker config, tools, and usage behavior.
- `tests/test_phase4_portal_api.py`: tenant portal sessions, credentials, usage, and agent routes.
- `tests/conftest.py`: offline guard should continue preventing accidental paid-provider calls.

Add telephony tests:

- Schema/RLS tests for every new telephony table.
- Telnyx credential verification stores only encrypted secret material and returns only masked status.
- Credential rotation, reverification, permission failure, disconnection, and compromised-key tests.
- Machine HMAC tests for every `/machine/telephony/*` action, including payload tampering and nonce replay.
- Portal JWT tests for every `/portal/telephony/*` route.
- Tenant isolation tests for connections, numbers, orders, SIP connections, calls, and call events.
- Multi-tenant isolation tests proving one tenant cannot use another tenant's Telnyx credential, number, agent, trunk, dispatch rule, or call.
- Number inventory tests for Telnyx-owned vs AwaazLabs-managed numbers, import, sync, and drift detection.
- Number exact-search, optional reservation, exact purchase, order-state, and routing-configuration tests with Telnyx fake responses.
- Outbound Voice Profile association and outbound readiness tests.
- Disabled destination, spending-limit, concurrency-limit, channel-limit, and verification-restriction tests.
- Idempotency tests for number orders and outbound calls.
- Duplicate webhook and stale webhook tests.
- Webhook signature, dedupe, unmapped-provider-ID, failed-event, and replay tests.
- Number assignment/reassignment validation tests, including active-call protection.
- Concurrency and race-condition tests for reassignment during call start, duplicate inbound SIP participants, and duplicate outbound requests.
- Direction-specific status transition tests for inbound and outbound calls.
- Inbound routing tests: number maps to the correct tenant and assigned agent from `sip.trunkPhoneNumber`, `sip.trunkID`, and `sip.ruleID`.
- Failed inbound-call cleanup tests for unknown number, no assigned agent, suspended tenant, routing mismatch, quota failure, agent load failure, and provider pipeline start failure.
- Outbound validation tests: agent belongs to tenant, from number belongs to tenant, number is ready, destination number is valid.
- LiveKit SIP adapter tests with fake trunk, SIP dispatch-rule, agent dispatch, and outbound participant responses.
- Trunk and dispatch-rule reuse tests proving trunks/rules are not created per call.
- No duplicated LiveKit provider-ID ownership tests proving `telephony_calls` uses internal record references for trunks/rules.
- Worker resolver tests for telephony-created rooms.
- Stale-call and quota reconciliation tests.
- Partial-failure recovery tests for purchase success plus routing setup failure, LiveKit trunk failure, dispatch-rule failure, and outbound SIP creation failure.
- High-concurrency inbound and outbound tests.
- Dashboard connection-form tests for API-key input clearing, no client persistence, and secret non-return from backend APIs.
- Retention, deletion, tenant-offboarding, export access-control, and restricted payload access tests.
- Per-tenant provider-health isolation tests proving one tenant's Telnyx/SIP failure does not make unrelated tenants or global readiness fail.
- End-to-end test call before marking a SIP connection active where necessary. Real PSTN calls should be human-approved and isolated from default CI.
- Regression test proving existing Urdu WebRTC sessions still mint, dispatch, transcribe, synthesize, interrupt, close, and record usage.
- Controlled real Telnyx/LiveKit staging tests must be separate from default CI and must not run without explicit credentials and approval.

## Files Likely To Be Reused Or Modified

Backend/control plane:

- `tenant_portal_api/app.py`
- `tenant_portal_api/machine_auth.py`
- `tenant_portal_api/queries.py`
- `control_plane/app.py`
- `control_plane/mint.py`
- `control_plane/secrets.py`
- `control_plane/secrets_db.py`

Worker:

- `worker/main.py`
- `worker/config.py`
- `worker/tools.py`
- `worker/usage.py`
- `worker/factories.py`

Database:

- `supabase/migrations/*`
- `scripts/reconcile_sessions.py`

SDKs and deliverables:

- `sdk-server/src/index.ts`
- `sdk-server/package.json`
- `sdk-server/README.md`
- `client-submission_v2/sdk/@awaazlabs-uva/agents/src/index.ts`
- `client-submission_v2/sdk/README.md`
- New backend-only `telephony/` package and delivered `client-submission_v2/sdk/@awaazlabs-uva/telephony/` copy if this package is included in handoff bundles.

Dashboard:

- `dashboard/src/lib/portalApi.ts`
- `dashboard/src/lib/swr-keys.ts`
- `dashboard/src/components/Sidebar.tsx`
- `dashboard/src/app/sessions/page.tsx`
- New `dashboard/src/app/telephony/...` route group.

Tests/docs/dependencies:

- `tests/test_mint.py`
- `tests/test_machine_agent_api.py`
- `tests/test_worker.py`
- `tests/test_phase4_portal_api.py`
- `tests/test_host_backend_contract.py`
- New telephony test files.
- `requirements.txt`
- `docs/MACHINE_AGENT_API_CONTRACT.md`
- `docs/HOST_BACKEND_CONTRACT.md`
- `README.md`
- `docs/UKASHA_MULTIPLE_PROVIDERS_GUIDE.md`

## Likely Overlap With Ukasha Provider Modularity

Ukasha's provider/language work overlaps with telephony in these areas:

- `supabase/migrations/*`: both efforts may add columns/tables and validation rules.
- `tenant_portal_api/app.py` and `tenant_portal_api/queries.py`: provider fields and telephony routes will both expand tenant-facing API models.
- `sdk-server/src/index.ts` and delivered SDK copies: provider fields and telephony package work may both touch SDK packaging/signing conventions.
- `worker/config.py`: provider work adds runtime provider/language fields; telephony needs call metadata and possibly `telephony_call_id` loading.
- `worker/main.py`: provider work wants registry-based STT/LLM/TTS construction; telephony needs SIP-created room resolution and call status updates.
- `worker/usage.py`: provider work may refine model usage; telephony may add phone/SIP usage or a separate billing table.
- `requirements.txt`: provider adapters and Telnyx/LiveKit SIP dependencies may both add packages.
- `dashboard/src/lib/portalApi.ts` and `dashboard/src/components/Sidebar.tsx`: future provider UI and telephony UI may both extend shared dashboard client/navigation.
- `docs/UKASHA_MULTIPLE_PROVIDERS_GUIDE.md` and this document: keep provider/language decisions separate from telephony, but align around a single agent runtime config.

Architecture boundary:

- Provider/language selection remains owned by Ukasha's provider registry work.
- Telephony owns number provisioning, SIP routing, call orchestration, telephony quota lifecycle, and telephony statuses.
- `worker/main.py` should stay minimally changed: add a trusted telephony runtime resolver and call/session status hooks, not a second pipeline.
- The dashboard and `@awaazlabs-uva/telephony` SDK must call the same telephony backend service.
- The telephony SDK remains backend-only.
- P2F or any future client may build its own billing or user-facing workflow, but AwaazLabs remains responsible for technical telephony execution through its API and SDK.
- Neither effort should rewrite the current working Urdu Gladia/Gemini/Uplift pipeline.

Recommended coordination rule: land schema migrations in small, numbered slices and keep `worker/main.py` changes minimal. Provider registry should own STT/LLM/TTS selection; telephony should consume the selected agent runtime config and own phone-call routing.

## Implementation Order

1. Confirm LiveKit SIP API behavior, especially SIP participant attributes, trunk creation, dispatch rules, outbound SIP participant/call creation, and event surfaces.
2. Confirm Telnyx API details for key verification, owned-number inventory, exact search, optional reservation, exact number orders, order statuses, pricing, webhooks, and idempotency.
3. Decide secret encryption mechanism for tenant Telnyx API keys.
4. Add normalized telephony DB migrations with RLS, tenant-scoped constraints, idempotency, audit logs, and indexes.
5. Add backend service layer and fake Telnyx/LiveKit adapters.
6. Add Telnyx connection, credential rotation, reverification, and disconnect APIs.
7. Add Telnyx-owned inventory, AwaazLabs-managed inventory, import, sync, drift, exact search, optional reservation, and exact purchase APIs.
8. Add Telnyx SIP/FQDN connection management.
9. Add Telnyx Outbound Voice Profile create/select/associate/reverify/reconcile operations.
10. Add long-lived LiveKit inbound trunk, outbound trunk, and SIP dispatch-rule orchestration with reconciliation.
11. Add portal and machine telephony API routes, sharing the same validation/service/query layer.
12. Add `@awaazlabs-uva/telephony` backend-only SDK with contract tests.
13. Implement telephony quota/session/call orchestrator independent of `/v1/session`.
14. Implement inbound routing and failed-inbound cleanup from LiveKit SIP attributes to DB-owned tenant/number/agent records.
15. Implement outbound call orchestration through the reusable LiveKit outbound trunk, gated by Outbound Voice Profile readiness.
16. Add data-governance controls for retention, deletion, exports, transcript/call-record access audit, and restricted provider payload access.
17. Add reconciliation jobs, metrics, alerts, global readiness checks, tenant/provider health diagnostics, and operational recovery runbooks.
18. Add dashboard telephony views after the backend API is stable.
19. Add controlled real-provider staging tests gated behind explicit human approval and keep default CI on fakes.
20. Update client deliverables and public docs.

## Blockers, Assumptions, And Decisions

Needs confirmation:

- Exact LiveKit SIP APIs and whether the current `livekit-api==1.2.0` package is sufficient.
- Exact shape and availability of LiveKit SIP participant attributes: `sip.callID`, `sip.callIDFull`, `sip.trunkPhoneNumber`, `sip.trunkID`, and `sip.ruleID`.
- Whether the worker or a pre-worker telephony orchestrator creates the initial `sessions` row for inbound calls. Either way, quota reservation must be atomic and independent of browser `/v1/session`.
- Whether telephony call minutes should extend `usage_events.kind` or use dedicated telephony billing tables.
- Which encryption mechanism will be used for Telnyx API keys.
- Whether telephony routes live inside `tenant_portal_api` or a separate deployed FastAPI service.
- Which Telnyx number types/features/countries are allowed in the first release.
- Whether Telnyx number reservation is available and worthwhile for the selected number types/countries.
- Exact Telnyx Outbound Voice Profile APIs, limits, destination configuration, verification restrictions, and how a SIP/FQDN connection is associated with the profile.
- Which Telnyx webhook event types are confirmed for number orders and inventory APIs actually used.
- Which SIP verification test is required before marking a connection active.
- Outbound call creation should require an idempotency key for every request. Recommended answer: yes.
- Whether external customer/workflow refs are opaque strings only, or need indexed/searchable structure.
- Whether one active Telnyx account connection per tenant remains sufficient for the first production release. Recommended answer: yes, with historical records and future-safe provider-connection schema.
- Retention periods, export permissions, tenant-offboarding behavior, and restricted provider-payload access policy.
- Whether failed inbound calls with no tenant resolution should be stored only as restricted platform events or in a separate non-tenant operational table.

Assumptions:

- AwaazLabs stays multi-tenant with one reusable worker architecture.
- P2F may connect one Telnyx account and manage/bill its own downstream customers externally.
- AwaazLabs does not implement P2F's customer payment module.
- Provider/language modularity remains separate from telephony, but both will share agent runtime configuration and worker startup paths.
- Trunks and dispatch rules are long-lived reusable resources, never per-call resources.
- Outbound SIP calls require an active Telnyx Outbound Voice Profile associated with the tenant SIP connection.

## Source Of Truth Summary

Already exists:

- Multi-tenant WebRTC voice sessions.
- Tenant HMAC auth and dashboard JWT auth.
- Backend-only agents SDK pattern.
- Agent/voice management.
- LiveKit dispatch to a single worker.
- STT/LLM/TTS worker pipeline.
- Session transcript, summary, usage, quota, and stale-session reconciliation.

Can be reused:

- Tenant portal API route structure.
- Machine HMAC SDK/auth pattern.
- `sessions` and dashboard session history.
- Worker metadata/userdata model.
- Admin audit and failure visibility.
- Existing test discipline.

Must be created:

- Production Telnyx credential connection, encryption, rotation, reverification, disconnection, and compromised-key handling.
- Separate Telnyx-owned inventory and AwaazLabs-managed phone-number inventory.
- Import, sync, drift detection, exact search, optional reservation, exact purchase, and order reconciliation.
- Reusable Telnyx SIP/FQDN connection per tenant.
- Telnyx Outbound Voice Profile association, readiness, and reconciliation.
- Long-lived LiveKit inbound trunks, outbound trunk, and SIP dispatch rules.
- Inbound and outbound telephony call orchestration.
- Telephony call/event tables.
- Webhook, polling, and reconciliation workers.
- Backend-only telephony SDK.
- Dashboard telephony areas.

Must be production-hardened:

- Tenant-scoped DB constraints, RLS, and audit logging.
- Credential encryption, rotation, and redacted logs.
- Idempotency for number purchase and outbound call creation.
- Status transition guards and stale update rejection.
- Exactly-once quota release and usage recording.
- Reconciliation for numbers, orders, calls, trunks, dispatch rules, and quota.
- Retention, deletion, tenant offboarding, export/access controls, and restricted raw-payload access.
- Direction-specific call transition guards and failed inbound-call cleanup.
- Metrics, alerts, readiness checks, failed-event handling, and recovery runbooks.

Requires decision:

- Secret encryption backend.
- LiveKit SIP attribute/routing and inbound session-creation strategy.
- Telephony usage/billing table strategy.
- Route deployment shape.
- First-release countries/features/providers.
- Outbound Voice Profile creation/selection and destination/limit policy.
- Telnyx webhook coverage for the APIs actually used.
- Real test-call approval and operational runbook.
