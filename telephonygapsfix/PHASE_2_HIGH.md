# Phase 2: High Severity Routing, Webhook & State Security Fixes

## Executive Overview
Phase 2 resolves 6 high-severity anomalies spanning provider status mapping (`TEL-HIGH-01`), LiveKit resource propagation (`TEL-HIGH-02`), worker job metadata security (`TEL-HIGH-03`), disabled status preservation (`TEL-HIGH-04`), multi-tenant webhook deduplication (`TEL-HIGH-05`), and active-call guardrails (`TEL-HIGH-06`).

---

## Gap 2.1: Accurate Provider Outcome Mapping (`TEL-HIGH-01`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telephony_service.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_service.py) (`purchase_number`).
- **Anomaly**: Non-purchased order outcomes (e.g., Telnyx `cancelled`, `failed`, or `expired`) are mapped to `purchase_pending` instead of terminal error statuses.
- **Impact**: Failed purchases display misleading status in administrative UI, suppressing error reporting and blocking retry attempts.

### Detailed Architectural Fix Specification
1. **Explicit Status Converter**:
   Create status mapping helper in `tenant_portal_api/telephony_status.py`:
   ```python
   def map_telnyx_order_status(telnyx_status: str) -> tuple[NumberOrderPlatformStatus, NumberProvisioningStatus]:
       mapping = {
           "pending": (NumberOrderPlatformStatus.PENDING, NumberProvisioningStatus.PURCHASE_PENDING),
           "in_progress": (NumberOrderPlatformStatus.PENDING, NumberProvisioningStatus.PURCHASE_PENDING),
           "complete": (NumberOrderPlatformStatus.PURCHASED, NumberProvisioningStatus.OWNED),
           "failed": (NumberOrderPlatformStatus.FAILED, NumberProvisioningStatus.PURCHASE_FAILED),
           "cancelled": (NumberOrderPlatformStatus.CANCELLED, NumberProvisioningStatus.PURCHASE_FAILED),
           "expired": (NumberOrderPlatformStatus.FAILED, NumberProvisioningStatus.PURCHASE_FAILED),
       }
       return mapping.get(telnyx_status.lower(), (NumberOrderPlatformStatus.FAILED, NumberProvisioningStatus.PURCHASE_FAILED))
   ```
2. **Atomic Order & Inventory Update**:
   Apply mapped status synchronously to both `telephony_number_orders` and `telephony_phone_numbers` tables upon receiving order status webhooks or poll responses.

### Verification & Test Specifications
- **Test 2.1a (Failed Order Mapping)**:
  - Mock Telnyx API returning order status `"failed"`.
  - Process purchase outcome.
  - **Assert**: `telephony_number_orders.status` is `'failed'`; `telephony_phone_numbers.provisioning_status` is `'purchase_failed'`.

---

## Gap 2.2: Disable/Unassign Propagation to LiveKit (`TEL-HIGH-02`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telephony_service.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_service.py) (`disable_number`, `unassign_number`), [`tenant_portal_api/livekit_sip.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/livekit_sip.py).
- **Anomaly**: When a number is disabled or unassigned in the database, `telephony_phone_numbers` status is updated, but active LiveKit SIP dispatch rules and trunks remain registered in LiveKit cloud services.
- **Impact**: Inbound calls to disabled numbers continue executing LiveKit dispatch rules, launching agent instances for disabled routes.

### Detailed Architectural Fix Specification
1. **LiveKit Dispatch Deactivation Flow**:
   In `disable_number` and `unassign_number`:
   ```python
   # 1. Fetch active LiveKit dispatch rules for number from DB
   dispatch_rules = queries.get_livekit_dispatch_rules_for_number(conn, number_id)
   
   # 2. Issue LiveKit API deletion / disable call
   livekit_client = self._get_livekit_sip_client()
   for rule in dispatch_rules:
       livekit_client.delete_sip_dispatch_rule(rule_id=rule["livekit_dispatch_rule_id"])
       queries.mark_dispatch_rule_disabled(conn, rule["id"])

   # 3. Update number routing status to 'disabled'
   queries.update_number_status(conn, number_id, provisioning_status="disabled", routing_status="disabled")
   ```
2. **Reconciliation Consistency Check**:
   Add `check_livekit_drift(conn)` task in `telephony_reconcile.py` that queries LiveKit SIP dispatch rules and verifies whether corresponding database numbers are active. If number is disabled, delete orphaned dispatch rule.

### Verification & Test Specifications
- **Test 2.2a (LiveKit Rule Cleanup on Disable)**:
  - Disable number with active dispatch rule `"rule-123"`.
  - **Assert**: `livekit_client.delete_sip_dispatch_rule("rule-123")` is called.
  - **Assert**: Database dispatch rule record marked `is_active=False`.

---

## Gap 2.3: Worker Metadata Revalidation (`TEL-HIGH-03`)

### Problem Statement & Root Cause
- **Location**: [`worker/telephony_runtime.py`](file:///d:/FinovaSolution/habiba-sdk-agent/worker/telephony_runtime.py) (`parse_job_telephony_metadata`, `resolve_session_metadata`).
- **Anomaly**: Worker runtime trusts inbound telephony job metadata payloads without validating current DB assignment and routing status.
- **Impact**: If a number is reassigned or disabled between job enqueue and execution, stale metadata can cause misrouting, agent impersonation, or unauthorized access.

### Detailed Architectural Fix Specification
1. **Mandatory DB Revalidation Step**:
   Before initiating session execution in `resolve_session_metadata`:
   ```python
   # Query database for authoritative number assignment
   db_number = db_queries.get_active_phone_number(conn, phone_number=job_phone_number)
   if not db_number or db_number["provisioning_status"] != "owned" or db_number["routing_status"] != "ready":
       logger.error("Job metadata rejected: phone number %s is not active/ready", job_phone_number)
       raise SecurityValidationError("Phone number is not active or ready in DB")
       
   if db_number["tenant_id"] != job_tenant_id or db_number["assigned_agent_id"] != job_agent_id:
       logger.warning("Job metadata divergence detected: enqueued (%s, %s) vs DB (%s, %s)",
                      job_tenant_id, job_agent_id, db_number["tenant_id"], db_number["assigned_agent_id"])
       # Re-resolve session metadata using authoritative DB values
       return resolve_from_db_record(db_number)
   ```

### Verification & Test Specifications
- **Test 2.3a (Stale Metadata Rejection)**:
  - Enqueue worker job with `agent_id="agent-old"`. Update DB assignment to `"agent-new"`.
  - Execute `resolve_session_metadata`.
  - **Assert**: Worker re-resolves metadata to `"agent-new"` and logs divergence warning.

---

## Gap 2.4: Preserve Disabled Semantics in Sync (`TEL-HIGH-04`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telephony_service.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_service.py) (`_materialize_managed_number`).
- **Anomaly**: Passive inventory synchronization upserts rows without checking whether existing records have `disabled_at IS NOT NULL` or `provisioning_status = 'disabled'`.
- **Impact**: Syncing provider inventory automatically clears `disabled_at` and restores disabled numbers to `owned` status without admin intent.

### Detailed Architectural Fix Specification
1. **Sync Upsert Predicate Protection**:
   In `_materialize_managed_number` / `upsert_managed_number`:
   ```sql
   UPDATE telephony_phone_numbers
   SET
       provider_raw_data = EXCLUDED.provider_raw_data,
       updated_at = NOW()
       -- DO NOT update provisioning_status if currently 'disabled'
       -- DO NOT clear disabled_at
   WHERE id = EXCLUDED.id
     AND provisioning_status != 'disabled'
     AND disabled_at IS NULL;
   ```

### Verification & Test Specifications
- **Test 2.4a (Disabled State Immunity During Sync)**:
  - Disable a phone number (`disabled_at = NOW()`).
  - Execute `sync_telnyx_owned_numbers()`.
  - **Assert**: Number remains `provisioning_status = 'disabled'` and `disabled_at` is preserved intact.

---

## Gap 2.5: Tenant-Scoped Webhook Event Dedupe (`TEL-HIGH-05`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telephony_webhooks.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_webhooks.py) (`_persist_telnyx_webhook_event`), [`supabase/migrations/0013_telephony_constraints_indexes_status_idempotency.sql`](file:///d:/FinovaSolution/habiba-sdk-agent/supabase/migrations/0013_telephony_constraints_indexes_status_idempotency.sql).
- **Anomaly**: Unique constraint `uq_telephony_webhook_events_provider_event` is scoped to `(source, provider_event_id)` without including `tenant_id`.
- **Impact**: Collisions in provider event IDs or shared webhook targets across tenants cause valid events for Tenant B to be rejected if Tenant A already processed the same event ID.

### Detailed Architectural Fix Specification
1. **Migration File `0014_telephony_idempotency_webhook_tenant_scope.sql`**:
   ```sql
   -- Drop existing global constraint
   ALTER TABLE telephony_webhook_events DROP CONSTRAINT IF EXISTS uq_telephony_webhook_events_provider_event;
   
   -- Add tenant-scoped composite unique constraint
   ALTER TABLE telephony_webhook_events
       ADD CONSTRAINT uq_telephony_webhook_events_tenant_provider_event
       UNIQUE (tenant_id, source, provider_event_id);
   ```
2. **Webhook Query Update**:
   Update `_persist_telnyx_webhook_event` SQL insert query to include `tenant_id` in conflict target list: `ON CONFLICT (tenant_id, source, provider_event_id) DO NOTHING`.

### Verification & Test Specifications
- **Test 2.5a (Cross-Tenant Same Event ID Insertion)**:
  - Persist webhook event with `provider_event_id="evt-100"` for `tenant_id="tenant-A"`.
  - Persist webhook event with `provider_event_id="evt-100"` for `tenant_id="tenant-B"`.
  - **Assert**: Both rows persist successfully in `telephony_webhook_events`.

---

## Gap 2.6: Active-Call Safeguards for Destructive Actions (`TEL-HIGH-06`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telephony_service.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_service.py) (`disable_number`, `disconnect_telnyx_account`).
- **Anomaly**: No preflight check or drain procedure exists when disabling a number or disconnecting a provider account while calls are actively in progress.
- **Impact**: Destructive API calls abruptly drop ongoing active phone calls without warning.

### Detailed Architectural Fix Specification
1. **Pre-flight Active Call Audit**:
   ```python
   active_calls = queries.get_active_calls_for_number(conn, number_id)
   if active_calls and not force:
       raise TelephonyError(
           status=409,
           message=f"Cannot perform operation: {len(active_calls)} active calls in progress.",
           details={"active_call_ids": [c["id"] for c in active_calls]}
       )
   ```
2. **Graceful Drain Option (`force=True` or `drain_timeout_sec`)**:
   - Set status to `'disabling'`.
   - Prevent new call creation.
   - Wait up to `drain_timeout_sec` (e.g., 30s) for active calls to conclude before deleting trunks.

### Verification & Test Specifications
- **Test 2.6a (Block Disable with Active Calls)**:
  - Seed an active call (`status='in_progress'`) for number `N`.
  - Issue `disable_number(N, force=False)`.
  - **Assert**: Throws 409 Conflict. Number remains active.
- **Test 2.6b (Forced Drain Disable)**:
  - Issue `disable_number(N, force=True)`.
  - **Assert**: Operation succeeds, setting routing status to `disabled`.
