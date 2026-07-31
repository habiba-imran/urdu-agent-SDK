# Telephony API And Schema Contract

Status: proposed freeze for Hamza + Habiba review.

This document turns the telephony architecture documents into a shared build contract. After Hamza and Habiba approve it, treat the names, route shapes, SDK methods, statuses, error codes, idempotency rules, and ownership boundaries here as frozen unless both agree to a contract change.

## What Contract Freeze Means

A contract freeze means both developers agree on the surfaces where their work meets:

- database table names, columns, constraints, and row-lock expectations
- backend route paths, HTTP methods, request bodies, response shapes, and machine HMAC action strings
- SDK method names, parameters, return objects, and error shape
- public statuses, internal stages, stable error codes, and idempotency behavior
- security boundaries, especially provider secrets and browser/backend separation

After this document is frozen:

- Hamza can implement backend service code against these table/API contracts.
- Habiba can implement migrations and the backend-only SDK against these same contracts.
- Neither side should rename fields, actions, statuses, or methods without updating this document and telling the other developer.

## Scope Decisions

| Decision | Frozen value |
|---|---|
| Current dashboard work | Out of scope. Do not create dashboard pages, navigation, SWR keys, UI components, or dashboard mocks in this workflow. |
| Telephony SDK | Backend-only Node SDK named `@awaazlabs-uva/telephony`. |
| Browser package | `@awaazlabs-uva/voice` remains browser/WebRTC only and must not contain HMAC, Telnyx, LiveKit, Supabase, or provider secrets. |
| Backend API home | Use `tenant_portal_api` route modules for portal and machine telephony APIs. |
| Provider/runtime ownership | Hamza owns Telnyx, LiveKit SIP, inbound/outbound orchestration, webhooks, reconciliation, health. |
| DB/SDK ownership | Habiba owns Supabase migrations/RLS/constraints/indexes and the backend-only telephony SDK. |
| Provider/language ownership | Ukasha owns STT/LLM/TTS provider registry and language selection. Telephony consumes agent runtime config but does not choose STT/LLM/TTS. |
| First Telnyx model | One active Telnyx account connection per tenant. Keep historical disconnected/disabled rows. |
| Trunks and dispatch rules | Long-lived reusable resources. Never create LiveKit trunks or SIP dispatch rules per call. |
| Inbound trust model | Do not trust caller-controlled metadata. Resolve tenant/number/agent from LiveKit SIP attributes plus AwaazLabs-owned DB rows. |
| Browser `/v1/session` | Telephony does not depend on browser `/v1/session`. It uses its own call/session/quota orchestration. |
| Number purchase | Purchase only one exact selected E.164 number. Do not purchase from broad country/area-code criteria alone. |
| Number reservation | Supported as an optional operation. If Telnyx does not support it for the selected number type/market, backend returns a stable unsupported/action-required response. |
| Outbound call idempotency | Required for every outbound call creation request. |
| Number purchase idempotency | Required for every number purchase request. |
| Existing `sessions` table | Keep `sessions`; link telephony through `telephony_calls.session_id`. Do not replace `sessions`. |
| Existing `usage_events` table | Do not extend `usage_events.kind` in the first telephony contract. Store telephony call duration/status on `telephony_calls`; add billing-specific tables later only if productized. |
| External refs | `external_customer_ref` and `external_workflow_ref` are opaque strings. No JSON structure required in first release. |
| Failed inbound call with no tenant | Do not create a tenant-scoped `telephony_calls` row if no tenant can be resolved. Record restricted backend/admin diagnostics only. |

## Items Hamza Must Confirm Before Live Provider Work

These do not block Habiba's schema/SDK scaffold, but they do block live Telnyx/LiveKit enablement.

- Exact LiveKit SIP APIs available in the installed/deployed LiveKit SDK and whether `livekit-api==1.2.0` is sufficient.
- Exact LiveKit SIP participant attributes: `sip.callID`, `sip.callIDFull`, `sip.trunkPhoneNumber`, `sip.trunkID`, `sip.ruleID`.
- Exact Telnyx APIs for key verification, owned-number inventory, exact search, optional reservation, exact number order, order status, pricing, SIP/FQDN connection, and Outbound Voice Profile.
- Exact Telnyx webhook event types confirmed for the APIs actually used.
- Whether LiveKit SIP webhooks are available and useful in the deployed plan.
- Which first-release countries, number types, features, and outbound destination policies are enabled.
- Which SIP verification test is required before marking SIP connection/routing active.
- Final encryption mechanism: secret-store reference preferred; app-level encrypted ciphertext allowed only if reviewed.

## Database Contract

Create new migration files under `supabase/migrations/*` after migration numbers are coordinated with Ukasha. Enable RLS on every tenant-owned table. Use tenant-scoped foreign keys and uniqueness constraints so cross-tenant assignment cannot happen even if API validation regresses.

### Tables

`tenant_telnyx_connections`

- Fields: `id`, `tenant_id`, `label`, `platform_status`, `provider_status`, `encrypted_api_key_ref` or `encrypted_api_key_ciphertext`, `key_fingerprint`, `telnyx_account_id`, `last_verified_at`, `permission_last_checked_at`, `created_at`, `updated_at`, `disabled_at`, `disconnected_at`, `compromised_at`.
- Constraint: one active connection per tenant where `platform_status in ('verifying', 'active', 'rotation_required')`.
- Rule: keep historical disconnected/disabled rows.

`telnyx_sip_connections`

- Fields: `id`, `tenant_id`, `telnyx_connection_id`, `provider_sip_connection_id`, `sip_fqdn`, `sip_username`, `encrypted_sip_secret_ref`, `platform_status`, `provider_status`, `last_verified_at`, `created_at`, `updated_at`, `disabled_at`.
- Constraint: one active SIP connection per active `telnyx_connection_id`.
- Rule: do not store LiveKit trunk or dispatch rule IDs here.

`telnyx_outbound_voice_profiles`

- Fields: `id`, `tenant_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `provider_outbound_voice_profile_id`, `platform_status`, `provider_status`, `allowed_destinations`, `concurrency_limit`, `channel_limit`, `daily_spending_limit`, `last_verified_at`, `created_at`, `updated_at`, `disabled_at`.
- Rule: active Outbound Voice Profile associated with the tenant SIP connection is required before outbound calls are ready.

`telephony_phone_numbers`

- Fields: `id`, `tenant_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `provider_number_id`, `e164_number`, `country`, `number_type`, `features`, `provisioning_status`, `routing_status`, `provider_status`, `assigned_agent_id`, `external_customer_ref`, `last_synced_at`, `created_at`, `updated_at`, `disabled_at`.
- Constraint: unique active `(tenant_id, e164_number)`.
- Constraint: `assigned_agent_id` must belong to the same tenant when non-null.
- Rule: assignment is nullable `assigned_agent_id`; do not encode assignment as a number status.
- Rule: do not store LiveKit trunk or dispatch rule IDs here.

`livekit_inbound_trunks`

- Fields: `id`, `tenant_id`, `phone_number_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `livekit_inbound_trunk_id`, `platform_status`, `provider_status`, `last_reconciled_at`, `created_at`, `updated_at`, `disabled_at`.
- Constraint: unique active `(tenant_id, phone_number_id)`.

`livekit_outbound_trunks`

- Fields: `id`, `tenant_id`, `telnyx_connection_id`, `telnyx_sip_connection_id`, `outbound_voice_profile_record_id`, `livekit_outbound_trunk_id`, `platform_status`, `provider_status`, `last_reconciled_at`, `created_at`, `updated_at`, `disabled_at`.
- Constraint: unique active `(tenant_id, telnyx_connection_id)`.

`livekit_sip_dispatch_rules`

- Fields: `id`, `tenant_id`, `phone_number_id`, `livekit_inbound_trunk_id`, `livekit_sip_dispatch_rule_id`, `platform_status`, `provider_status`, `last_reconciled_at`, `created_at`, `updated_at`, `disabled_at`.
- Constraint: unique active `(tenant_id, phone_number_id)`.

`telephony_number_orders`

- Fields: `id`, `tenant_id`, `telnyx_connection_id`, `idempotency_key`, `provider_order_id`, `selected_e164_number`, `country`, `area_code`, `number_type`, `features`, `price_amount`, `price_currency`, `provider_status`, `platform_status`, `raw_provider_status`, `provider_error_payload`, `error_code`, `error_message`, `created_at`, `updated_at`.
- Constraint: unique `(tenant_id, idempotency_key)`.

`telephony_calls`

- Fields: `id`, `tenant_id`, `session_id`, `agent_id`, `phone_number_id`, `direction`, `room_name`, `from_number`, `to_number`, `recipient`, `call_context`, `external_customer_ref`, `external_workflow_ref`, `inbound_trunk_record_id`, `outbound_trunk_record_id`, `sip_dispatch_rule_record_id`, `livekit_agent_dispatch_id`, `livekit_sip_call_id`, `livekit_sip_call_id_full`, `sip_trunk_phone_number`, `raw_livekit_sip_participant_status`, `platform_status`, `provider_status`, `outcome`, `error_code`, `error_message`, `quota_reserved_at`, `quota_released_at`, `usage_recorded_at`, `started_at`, `answered_at`, `ended_at`, `duration_sec`, `created_at`, `updated_at`.
- Rule: `session_id` references existing `sessions(id)`.
- Rule: LiveKit SIP identifiers are canonical call-correlation fields for SIP-trunked calls.
- Rule: `inbound_trunk_record_id`, `outbound_trunk_record_id`, and `sip_dispatch_rule_record_id` are internal FK references to owner tables.
- Rule: LiveKit trunk/rule provider IDs stay only on `livekit_inbound_trunks`, `livekit_outbound_trunks`, and `livekit_sip_dispatch_rules`.

`telephony_call_events`

- Fields: `id`, `tenant_id`, `telephony_call_id`, `source`, `event_type`, `provider_event_id`, `internal_stage`, `payload`, `created_at`.
- Constraint: provider event dedupe uniqueness, for example `(source, provider_event_id)` where provider event ID exists.
- Rule: raw provider payloads go here only as restricted diagnostics.

`telephony_idempotency_keys`

- Fields: `tenant_id`, `idempotency_key`, `action`, `request_hash`, `response_body`, `platform_status`, `created_at`, `completed_at`.
- Constraint: unique `(tenant_id, idempotency_key, action)`.
- Rule: same key + same request hash returns original response.
- Rule: same key + different request hash returns `idempotency_payload_mismatch`.

`telephony_audit_log`

- Fields: `id`, `tenant_id`, `actor_type`, `actor_id`, `action`, `target_type`, `target_id`, `detail`, `created_at`.
- Rule: audit credential changes, number purchases/imports, assignments, SIP changes, outbound calls, and disconnections.

### Required Row Locks

Hamza's repository/service layer must use DB transactions and row locks for:

- idempotency rows before number purchase or outbound call side effects
- phone-number assignment/reassignment
- inbound SIP resolution and call/session creation
- outbound call creation and quota reservation
- call status transitions
- exactly-once quota release
- exactly-once usage recording

### Index Requirements

Create indexes for:

- `tenant_id` on every tenant-owned table
- `telephony_phone_numbers.e164_number`
- `telephony_phone_numbers.assigned_agent_id`
- LiveKit provider IDs on trunk/rule tables
- `telephony_calls.room_name`
- `telephony_calls.livekit_sip_call_id`
- `telephony_calls.livekit_sip_call_id_full`
- `telephony_calls.platform_status`
- `telephony_calls.created_at`
- `telephony_call_events.provider_event_id`
- `telephony_idempotency_keys (tenant_id, idempotency_key, action)`
- stale reconciliation scans by status/timestamp

## Status Contract

Use separate `provider_status` and normalized `platform_status` where provider state exists. Preserve raw provider status for restricted diagnostics only.

`telnyx_connection_platform_status`

- `not_connected`
- `verifying`
- `active`
- `verification_failed`
- `rotation_required`
- `permission_failed`
- `compromised`
- `disabled`
- `disconnected`

`phone_number_provisioning_status`

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

`phone_number_routing_status`

- `not_configured`
- `configuring`
- `ready`
- `degraded`
- `failed`
- `disabled`

`number_order_provider_status`

- `pending`
- `success`
- `failure`
- `cancelled`
- `deleted`

`number_order_platform_status`

- `pending`
- `purchased`
- `configuring_routing`
- `ready`
- `action_required`
- `failed`
- `cancelled`
- `deleted`

`telnyx_sip_connection_platform_status` and LiveKit trunk/rule platform statuses

- `draft`
- `pending_verification`
- `testing`
- `active`
- `failed`
- `disabled`

`telnyx_outbound_voice_profile_platform_status`

- `not_configured`
- `configuring`
- `active`
- `destination_restricted`
- `limit_reached`
- `verification_required`
- `failed`
- `disabled`

`call_direction`

- `inbound`
- `outbound`

Public `call_status`

- `queued`
- `dialing`
- `ringing`
- `in_progress`
- `completed`
- `busy`
- `no_answer`
- `failed`
- `cancelled`

Outbound transitions:

- `queued` -> `dialing`, `failed`, `cancelled`
- `dialing` -> `ringing`, `in_progress`, `busy`, `no_answer`, `failed`, `cancelled`
- `ringing` -> `in_progress`, `busy`, `no_answer`, `failed`, `cancelled`
- `in_progress` -> `completed`, `failed`, `cancelled`
- terminal: `completed`, `busy`, `no_answer`, `failed`, `cancelled`

Inbound transitions:

- `ringing` -> `in_progress`, `failed`, `cancelled`
- `in_progress` -> `completed`, `failed`, `cancelled`
- terminal: `completed`, `failed`, `cancelled`

Internal stages belong in `telephony_call_events.internal_stage`, not in public call status. Examples: `validating`, `quota_reserved`, `session_created`, `room_created`, `livekit_agent_dispatch_created`, `sip_participant_created`, `cleanup_started`, `quota_released`, `usage_recorded`.

## Error Contract

Stable platform errors:

- Auth and tenant state: `telephony_auth_failed`, `tenant_not_active`, `tenant_not_found`.
- Credentials: `telnyx_connection_missing`, `telnyx_key_invalid`, `telnyx_key_unauthorized`, `telnyx_key_permission_failed`, `telnyx_key_compromised`, `provider_credentials_missing`.
- Validation: `agent_not_found`, `number_not_found`, `number_not_owned_by_tenant`, `number_not_assigned`, `number_not_routing_ready`, `outbound_voice_profile_missing`, `outbound_destination_disabled`, `outbound_spending_limit_reached`, `outbound_concurrency_limit_reached`, `outbound_verification_required`, `invalid_to_number`, `unsupported_number_feature`, `outbound_not_ready`.
- Idempotency: `duplicate_idempotency_key`, `idempotency_payload_mismatch`.
- Provider/API: `telnyx_api_error`, `telnyx_rate_limited`, `number_not_available`, `insufficient_telnyx_balance`, `number_order_action_required`, `regulatory_action_required`, `provider_timeout`.
- LiveKit/SIP: `livekit_inbound_trunk_failed`, `livekit_outbound_trunk_failed`, `livekit_sip_dispatch_rule_failed`, `livekit_agent_dispatch_failed`, `sip_verification_failed`, `sip_media_failed`.
- Runtime: `call_setup_failed`, `call_state_conflict`, `quota_reservation_failed`, `quota_release_failed`, `unknown_inbound_number`, `routing_identifier_mismatch`, `assigned_agent_load_failed`, `provider_pipeline_start_failed`, `worker_metadata_missing`, `worker_session_failed`.
- Webhooks: `webhook_signature_invalid`, `webhook_duplicate`, `webhook_unmapped_provider_id`.
- Data governance: `retention_policy_violation`, `export_not_authorized`, `restricted_payload_access_denied`.

Public API error shape:

```json
{
  "error": {
    "code": "idempotency_payload_mismatch",
    "message": "This idempotency key was already used with a different request.",
    "status": 409
  }
}
```

Do not return raw Telnyx/LiveKit payloads, stack traces, secrets, signatures, or provider credentials in public errors.

## Backend Route Contract

Portal routes are backend API contracts and future UI contracts. Dashboard implementation is out of scope now.

Machine routes are the active SDK surface. Machine requests use the existing HMAC pattern:

- headers: `X-Tenant-Id`, `X-Timestamp`, `X-Nonce`, `X-Signature`
- signed message: `tenant_id.timestamp.nonce.action.payload_hash`
- payload hash: canonical JSON body, sorted keys, no whitespace, UTF-8
- GET requests with no parameters sign `{}`
- filtered/list/search machine operations must put filters in a signed JSON body or use an explicitly signed body route; do not rely on unsigned query params for SDK operations

### Portal Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/portal/telephony/telnyx/connection` | Connection status without secrets |
| POST | `/portal/telephony/telnyx/connect` | Verify and store Telnyx API key encrypted |
| POST | `/portal/telephony/telnyx/rotate` | Rotate and reverify Telnyx API key |
| POST | `/portal/telephony/telnyx/reverify` | Recheck permissions/account readiness |
| DELETE | `/portal/telephony/telnyx/connection` | Disconnect/disable active connection |
| GET | `/portal/telephony/telnyx/owned-numbers` | Telnyx-owned inventory |
| GET | `/portal/telephony/numbers` | AwaazLabs-managed numbers |
| POST | `/portal/telephony/numbers/import` | Import existing Telnyx-owned number |
| POST | `/portal/telephony/numbers/sync` | Sync owned numbers/drift |
| GET | `/portal/telephony/numbers/drift` | Drift report |
| POST | `/portal/telephony/available-numbers/search` | Exact available-number search |
| POST | `/portal/telephony/number-reservations` | Optional reservation |
| POST | `/portal/telephony/number-orders` | Exact selected-number purchase |
| GET | `/portal/telephony/number-orders/{order_id}` | Order status |
| PATCH | `/portal/telephony/numbers/{number_id}/assignment` | Assign/reassign/unassign agent |
| POST | `/portal/telephony/telnyx/sip-connection` | Upsert SIP/FQDN connection |
| POST | `/portal/telephony/telnyx/sip-connection/test` | Verify/test SIP |
| POST | `/portal/telephony/telnyx/outbound-voice-profile` | Upsert Outbound Voice Profile |
| POST | `/portal/telephony/telnyx/outbound-voice-profile/reverify` | Reverify outbound policy/readiness |
| POST | `/portal/telephony/numbers/{number_id}/routing/configure` | Configure/repair inbound trunk/rule |
| POST | `/portal/telephony/telnyx/outbound-trunk/configure` | Configure/repair outbound trunk |
| GET | `/portal/telephony/outbound-readiness` | Outbound readiness |
| POST | `/portal/telephony/outbound-calls` | Create outbound call |
| GET | `/portal/telephony/calls` | List call records |
| GET | `/portal/telephony/calls/{telephony_call_id}` | Call detail/status |
| POST | `/portal/telephony/numbers/{number_id}/disable` | Disable/disconnect number |

### Machine Routes And Action Strings

| SDK method | Method | Path | Action |
|---|---|---|---|
| `connectTelnyxAccount` | POST | `/machine/telephony/telnyx/connect` | `telephony.telnyx_connection.connect` |
| `rotateTelnyxAccountKey` | POST | `/machine/telephony/telnyx/rotate` | `telephony.telnyx_connection.rotate` |
| `reverifyTelnyxAccount` | POST | `/machine/telephony/telnyx/reverify` | `telephony.telnyx_connection.reverify` |
| `disconnectTelnyxAccount` | DELETE | `/machine/telephony/telnyx/connection` | `telephony.telnyx_connection.disconnect` |
| `getConnectionStatus` | GET | `/machine/telephony/telnyx/connection` | `telephony.telnyx_connection.status` |
| `listTelnyxOwnedNumbers` | POST | `/machine/telephony/telnyx/owned-numbers/list` | `telephony.telnyx_owned_numbers.list` |
| `listManagedPhoneNumbers` | POST | `/machine/telephony/numbers/list` | `telephony.managed_numbers.list` |
| `importTelnyxNumber` | POST | `/machine/telephony/numbers/import` | `telephony.managed_numbers.import` |
| `syncTelnyxOwnedNumbers` | POST | `/machine/telephony/numbers/sync` | `telephony.managed_numbers.sync` |
| `getTelnyxNumberDrift` | POST | `/machine/telephony/numbers/drift` | `telephony.managed_numbers.drift` |
| `searchAvailableNumbers` | POST | `/machine/telephony/available-numbers/search` | `telephony.available_numbers.search` |
| `reserveNumber` | POST | `/machine/telephony/number-reservations` | `telephony.number_reservations.create` |
| `purchaseNumber` | POST | `/machine/telephony/number-orders` | `telephony.number_orders.create` |
| `getNumberOrderStatus` | POST | `/machine/telephony/number-orders/get` | `telephony.number_orders.get` |
| `assignAgentToNumber` | PATCH | `/machine/telephony/numbers/{number_id}/assignment` | `telephony.numbers.assign_agent` |
| `unassignAgentFromNumber` | PATCH | `/machine/telephony/numbers/{number_id}/assignment` | `telephony.numbers.assign_agent` |
| `upsertTelnyxSipConnection` | POST | `/machine/telephony/telnyx/sip-connection` | `telephony.telnyx_sip_connection.upsert` |
| `verifyTelnyxSipConnection` | POST | `/machine/telephony/telnyx/sip-connection/test` | `telephony.telnyx_sip_connection.test` |
| `upsertTelnyxOutboundVoiceProfile` | POST | `/machine/telephony/telnyx/outbound-voice-profile` | `telephony.telnyx_outbound_voice_profile.upsert` |
| `verifyTelnyxOutboundVoiceProfile` | POST | `/machine/telephony/telnyx/outbound-voice-profile/reverify` | `telephony.telnyx_outbound_voice_profile.reverify` |
| `configureNumberRouting` | POST | `/machine/telephony/numbers/{number_id}/routing/configure` | `telephony.number_routing.configure` |
| `configureOutboundTrunk` | POST | `/machine/telephony/telnyx/outbound-trunk/configure` | `telephony.outbound_trunk.configure` |
| `getOutboundReadiness` | GET | `/machine/telephony/outbound-readiness` | `telephony.outbound_readiness.get` |
| `createOutboundCall` | POST | `/machine/telephony/outbound-calls` | `telephony.outbound_calls.create` |
| `getCallStatus` | POST | `/machine/telephony/calls/get` | `telephony.calls.get` |
| `listCallRecords` | POST | `/machine/telephony/calls/list` | `telephony.calls.list` |
| `disableNumber` | POST | `/machine/telephony/numbers/{number_id}/disable` | `telephony.numbers.disable` |

For `unassignAgentFromNumber`, the request body uses `agent_id: null`.

For `getNumberOrderStatus` and `getCallStatus`, the request body includes the target ID even when the route is not path-based. This keeps machine request payloads fully HMAC-bound.

## SDK Method Contract

Package name: `@awaazlabs-uva/telephony`.

Constructor options:

```ts
{
  tenantId: string;
  tenantSecret: string;
  baseUrl: string;
  extraHeaders?: Record<string, string>;
}
```

Methods:

- `connectTelnyxAccount({ apiKey, label? })`
- `rotateTelnyxAccountKey({ apiKey })`
- `reverifyTelnyxAccount()`
- `disconnectTelnyxAccount()`
- `getConnectionStatus()`
- `listTelnyxOwnedNumbers(filters?)`
- `listManagedPhoneNumbers(filters?)`
- `importTelnyxNumber({ e164Number, externalCustomerRef? })`
- `syncTelnyxOwnedNumbers()`
- `getTelnyxNumberDrift()`
- `searchAvailableNumbers({ country, areaCode?, numberType?, features? })`
- `reserveNumber({ e164Number, idempotencyKey })`
- `purchaseNumber({ e164Number, externalCustomerRef?, idempotencyKey })`
- `getNumberOrderStatus(orderId)`
- `assignAgentToNumber(numberId, agentId)`
- `unassignAgentFromNumber(numberId)`
- `upsertTelnyxSipConnection(params)`
- `verifyTelnyxSipConnection()`
- `upsertTelnyxOutboundVoiceProfile(params)`
- `verifyTelnyxOutboundVoiceProfile()`
- `getOutboundReadiness()`
- `configureNumberRouting(numberId)`
- `configureOutboundTrunk()`
- `createOutboundCall({ agentId, fromNumberId, toNumber, recipient?, context?, externalCustomerRef?, externalWorkflowRef?, idempotencyKey })`
- `getCallStatus(telephonyCallId)`
- `listCallRecords(filters?)`
- `disableNumber(numberId)`

SDK errors:

```ts
class AwaazLabsUvaTelephonyError extends Error {
  status: number;
  code: string;
  detail?: unknown;
}
```

SDK security requirements:

- `tenantSecret` is used locally only for HMAC signing and is never sent.
- `apiKey` for Telnyx connect/rotate is accepted only as a method parameter and must not be stored on the client instance.
- `extraHeaders` must not override auth headers.
- SDK must never log request bodies containing Telnyx keys.

## Request Body Contract

Use snake_case JSON fields on the wire, matching existing backend style. SDK methods may expose camelCase TypeScript parameters but must serialize to snake_case.

Examples:

`connectTelnyxAccount`

```json
{
  "api_key": "REDACTED",
  "label": "Primary Telnyx account"
}
```

`purchaseNumber`

```json
{
  "e164_number": "+15551234567",
  "external_customer_ref": "customer_123",
  "idempotency_key": "purchase_2026_01_01_abc"
}
```

`assignAgentToNumber`

```json
{
  "number_id": "uuid",
  "agent_id": "uuid"
}
```

`unassignAgentFromNumber`

```json
{
  "number_id": "uuid",
  "agent_id": null
}
```

`createOutboundCall`

```json
{
  "agent_id": "uuid",
  "from_number_id": "uuid",
  "to_number": "+15557654321",
  "recipient": "Optional display name",
  "context": {},
  "external_customer_ref": "customer_123",
  "external_workflow_ref": "workflow_456",
  "idempotency_key": "call_2026_01_01_abc"
}
```

## Response Shape Contract

Every successful response should return stable AwaazLabs fields, not raw provider payloads.

Common object conventions:

- IDs are strings.
- Timestamps are ISO-8601 strings or `null`.
- Phone numbers are E.164 strings.
- Provider payloads are absent from public responses unless explicitly redacted.
- `provider_status` may be returned when normalized and non-sensitive.
- Raw provider status/payload belongs in restricted diagnostics only.

Connection response minimum:

```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "label": "Primary Telnyx account",
  "platform_status": "active",
  "provider_status": "active",
  "key_fingerprint": "abcd1234",
  "telnyx_account_id": "provider-account-id",
  "last_verified_at": "2026-01-01T00:00:00Z",
  "permission_last_checked_at": "2026-01-01T00:00:00Z"
}
```

Outbound call response minimum:

```json
{
  "telephony_call_id": "uuid",
  "session_id": "uuid",
  "room_name": "tenant-call-room",
  "platform_status": "queued",
  "direction": "outbound",
  "error_code": null,
  "error_message": null
}
```

## Security Contract

- Telnyx API keys and SIP secrets are tenant-specific secrets.
- Raw Telnyx API keys may enter only trusted backend routes or backend-only SDK calls during connect/rotate.
- Raw Telnyx API keys must never be persisted in SDK state, browser storage, logs, prompts, transcripts, summaries, fixtures, or docs.
- Store secrets using a reviewed encrypted mechanism: secret-store reference preferred, encrypted ciphertext acceptable only with reviewed key management.
- Webhooks must map provider IDs to stored tenant-owned records; never trust tenant IDs from webhook payloads.
- RLS must be enabled on every tenant-owned telephony table.
- Tenant-scoped constraints must prevent cross-tenant agent, number, trunk, dispatch-rule, profile, and call assignment.
- Public responses must be redacted and stable.

## Handoff Checklist

Hamza signs off when he confirms:

- route list and machine action strings
- request/response fields
- status and error-code list
- repository/query functions and row locks
- LiveKit/Telnyx provider verification notes
- fake provider fixtures for SDK tests

Habiba signs off when she confirms:

- migration numbers with Ukasha
- schema fields, constraints, indexes, and RLS policy shape
- SDK method names and signing behavior
- SDK test fixture requirements
- docs and client-deliverable packaging path

After both sign off, change `Status: proposed freeze` to `Status: frozen`.
