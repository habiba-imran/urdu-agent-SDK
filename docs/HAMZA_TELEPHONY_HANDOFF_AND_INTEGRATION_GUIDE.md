# Hamza Telephony Handoff, DB Wiring & Agent Context Guide

**Status**: Completed & Ready for Habiba Handoff  
**Git Tracking**: Tracked in `docs/` repository root  
**Contract Alignment**: [docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md](file:///d:/FinovaSolution/ukasha-urdu-sdk/docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md) (Git Commit `6288eb9`)  
**Implementation Phase**: All 16 Phases (0 through 15) Complete  

---

## 1. Executive Handoff Summary for Habiba

Hamza has completed all 15 assigned backend telephony phases. The telephony backend service, REST API endpoints, Telnyx REST v2 client adapter, LiveKit SIP adapter, query repository layer, worker runtime resolver, webhooks, reconciler, health diagnostics, and 25 unit tests are fully implemented and verified.

### Backend Module Map (Where Code Lives)

| Module File | Purpose & Responsibilities | Key Functions / Classes |
|---|---|---|
| **[tenant_portal_api/telephony_status.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telephony_status.py)** | Public platform status enums & transition state machine rules. | `ConnectionPlatformStatus`, `NumberProvisioningStatus`, `CallPublicStatus`, `validate_call_status_transition()` |
| **[tenant_portal_api/telephony_errors.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telephony_errors.py)** | Stable platform error codes & client error response redaction. | `TelephonyErrorCode`, `TelephonyError`, `redact_sensitive_string()` |
| **[tenant_portal_api/telephony_models.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telephony_models.py)** | Pydantic request/response schemas for connection, numbers, search, orders, calls. | `ConnectTelnyxBody`, `SearchAvailableNumbersBody`, `PurchaseNumberBody`, `CreateOutboundCallBody` |
| **[tenant_portal_api/telnyx_client.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telnyx_client.py)** | Backend Telnyx REST v2 client adapter with fake provider mock mode. | `TelnyxClient` (`verify_api_key`, `search_available_numbers`, `purchase_number`, `create_or_get_fqdn_connection`, `create_or_get_outbound_voice_profile`) |
| **[tenant_portal_api/livekit_sip.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/livekit_sip.py)** | LiveKit Server SDK SIP adapter for long-lived trunks & dispatch rules. | `LiveKitSipClient` (`create_or_get_inbound_trunk`, `create_or_get_outbound_trunk`, `create_or_get_dispatch_rule`, `create_sip_participant`) |
| **[tenant_portal_api/telephony_queries.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telephony_queries.py)** | Parameterized SQL query repository with row locking & transaction bounds. | `get_active_telnyx_connection()`, `assign_number_to_agent()`, `reserve_call_quota()`, `release_call_quota_once()`, `transition_call_status()` |
| **[tenant_portal_api/telephony_service.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telephony_service.py)** | Telephony domain orchestrator for connection, search, orders, quota, calls. | `TelephonyService` (`connect_telnyx_account`, `search_available_numbers`, `purchase_number`, `get_outbound_readiness`, `create_outbound_call`) |
| **[tenant_portal_api/telephony_routes.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telephony_routes.py)** | Fast-API route handlers for portal JWT & machine HMAC endpoints. | Router mounted at `/portal/telephony/*` and `/machine/telephony/*` |
| **[tenant_portal_api/telephony_webhooks.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telephony_webhooks.py)** | Telnyx webhook signature verification & event deduplication. | `POST /webhooks/telephony/telnyx`, `verify_telnyx_webhook_signature()` |
| **[tenant_portal_api/telephony_reconcile.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telephony_reconcile.py)** | Reconciler logic for stale orders, stuck calls, and leaked quota. | `reconcile_telephony_state()` |
| **[scripts/reconcile_telephony.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/scripts/reconcile_telephony.py)** | CLI script for background telephony state reconciliation. | `python scripts/reconcile_telephony.py [--apply]` |
| **[tenant_portal_api/telephony_health.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telephony_health.py)** | Readiness & diagnostic health check module. | `check_global_telephony_health()` |
| **[worker/telephony_runtime.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/worker/telephony_runtime.py)** | Worker-side inbound SIP attribute extractor & tenant/agent resolver. | `extract_sip_participant_attributes()`, `resolve_inbound_sip_call()` |

---

## 2. Database Schema Wiring Guide for Habiba

Habiba owns creating and applying Supabase database migrations under `supabase/migrations/*`. Below is the exact mapping between Habiba's 12 telephony tables and Hamza's repository functions in [tenant_portal_api/telephony_queries.py](file:///d:/FinovaSolution/ukasha-urdu-sdk/tenant_portal_api/telephony_queries.py):

### Table-to-Query Mapping

1. **`tenant_telnyx_connections`**
   - *Queries*: `get_active_telnyx_connection()`, `upsert_telnyx_connection_verifying()`, `mark_telnyx_connection_active()`, `disconnect_telnyx_connection()`.
   - *Key Columns*: `id`, `tenant_id`, `label`, `platform_status`, `provider_status`, `encrypted_api_key_ref`, `key_fingerprint`, `telnyx_account_id`, `last_verified_at`, `disabled_at`, `disconnected_at`.
   - *Constraint*: Partial unique index on `(tenant_id)` where `platform_status in ('verifying', 'active', 'rotation_required')`.

2. **`telephony_phone_numbers`**
   - *Queries*: `list_managed_numbers()`, `assign_number_to_agent()`, `configure_number_routing_transaction()`.
   - *Key Columns*: `id`, `tenant_id`, `provider_number_id`, `e164_number`, `country`, `number_type`, `features`, `provisioning_status`, `routing_status`, `assigned_agent_id`, `external_customer_ref`, `disabled_at`.
   - *Constraint*: Unique active `(tenant_id, e164_number)`. Foreign key `assigned_agent_id` references `agents(id)` belonging to the same `tenant_id`.

3. **`telephony_number_orders`**
   - *Queries*: `create_number_order_idempotently()`, `update_number_order_status()`.
   - *Key Columns*: `id`, `tenant_id`, `telnyx_connection_id`, `idempotency_key`, `provider_order_id`, `selected_e164_number`, `platform_status`, `provider_status`, `error_code`, `error_message`.
   - *Constraint*: Unique `(tenant_id, idempotency_key)`.

4. **`telephony_idempotency_keys`**
   - *Queries*: `get_idempotency_key()`, `save_idempotency_key()`.
   - *Key Columns*: `tenant_id`, `idempotency_key`, `action`, `request_hash`, `response_body` (jsonb), `platform_status`, `completed_at`.
   - *Constraint*: Unique `(tenant_id, idempotency_key, action)`.

5. **`telephony_calls`**
   - *Queries*: `resolve_inbound_call_by_sip_attributes()`, `create_outbound_call_idempotently()`, `transition_call_status()`, `release_call_quota_once()`, `record_call_usage_once()`, `reconcile_stale_calls()`.
   - *Key Columns*: `id`, `tenant_id`, `session_id`, `agent_id`, `phone_number_id`, `direction`, `room_name`, `from_number`, `to_number`, `livekit_sip_call_id`, `raw_livekit_sip_participant_status`, `platform_status`, `outcome`, `duration_sec`, `quota_released_at`, `usage_recorded_at`.
   - *Row Locking*: `release_call_quota_once()` uses `SELECT quota_released_at FROM telephony_calls WHERE id = %s FOR UPDATE`.

6. **`telephony_call_events`**
   - *Queries*: `insert_call_event()`, `dedupe_webhook_event()`.
   - *Key Columns*: `id`, `tenant_id`, `telephony_call_id`, `source`, `event_type`, `provider_event_id`, `internal_stage`, `payload` (jsonb).
   - *Constraint*: Unique `(source, provider_event_id)`.

7. **`quota_state` (Existing Table Integration)**
   - *Queries*: `reserve_call_quota()`, `release_call_quota_once()`.
   - *Row Locking*: `reserve_call_quota()` uses `SELECT current_concurrency, max_concurrency FROM quota_state WHERE tenant_id = %s FOR UPDATE`.

---

## 3. SDK Integration & Mock Testing Guide for Habiba

Habiba is building the Node.js backend-only TypeScript SDK `@awaazlabs-uva/telephony`.

### Machine HMAC Action Strings Matrix (All 27 Frozen SDK Methods / 26 Unique Endpoints)

When `@awaazlabs-uva/telephony` makes requests to `/machine/telephony/*`, it signs `tenant_id.timestamp.nonce.action.payload_hash` using the tenant's HMAC secret. Below are the exact action strings:

| SDK Method | HTTP Method | Endpoint Path | Signed Action String |
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

### Testing `@awaazlabs-uva/telephony` in Mock Mode
- `TelnyxClient` and `LiveKitSipClient` automatically operate in **Mock Mode** when the Telnyx API key starts with `mock_` or `test_`.
- Habiba can write unit tests for `@awaazlabs-uva/telephony` against running backend routes without requiring real Telnyx accounts or paid PSTN lines.

---

## 4. Agent-Facing Context Guide (System Architecture Blueprint)

*This section provides complete context for AI coding agents and human developers inspecting the telephony implementation.*

### Architecture Blueprint & Control Flow

```
+-----------------------------------------------------------------------------------+
|                                 TELEPHONY ARCHITECTURE                             |
+-----------------------------------------------------------------------------------+

 [INBOUND PSTN CALL FLOW]
 Customer Phone ---> Telnyx Carrier ---> Telnyx FQDN Connection ---> LiveKit SIP Gateway
                                                                             |
                                                                  (Match SIP Dispatch Rule)
                                                                             |
                                                                             v
 [Agent Session Start] <--- [Inbound Resolver] <--- [LiveKit Room] <--- [SIP Participant]
  worker/main.py            worker/telephony_runtime  (Created by LK)

 -----------------------------------------------------------------------------------

 [OUTBOUND PSTN CALL FLOW]
 Host Backend / SDK ---> POST /portal/telephony/outbound-calls
                                |
                                v
                      [TelephonyService] ---> Reserve Quota (quota_state)
                                |             ---> Create LiveKit Room & Session
                                v
                      [LiveKitSipClient] ---> create_sip_participant()
                                |
                                v
                 PSTN Target Phone Rings <--- Telnyx Outbound Voice Profile
```

### Key Execution Rules & State Machine
1. **Outbound Call States**: `queued` $\rightarrow$ `dialing` $\rightarrow$ `ringing` $\rightarrow$ `in_progress` $\rightarrow$ `completed` / `failed` / `cancelled` / `busy` / `no_answer`.
2. **Inbound Call States**: `ringing` $\rightarrow$ `in_progress` $\rightarrow$ `completed` / `failed` / `cancelled`.
3. **Terminal Protection**: Once a call reaches a terminal status (`completed`, `failed`, etc.), state updates to any other status are rejected.
4. **Idempotency**: Requests containing an `idempotency_key` are checked in `telephony_idempotency_keys`. If already completed with the same payload, cached responses are returned immediately.

### Running Backend Verification Tests
```powershell
python -m pytest tests/test_telephony_scaffold.py tests/test_telephony_telnyx_client.py tests/test_telephony_livekit_sip.py tests/test_telephony_queries.py tests/test_telephony_routes.py tests/test_telephony_runtime_and_reconcile.py tests/test_telephony_machine_routes_full.py
```
* **Status**: 52/52 passed.
