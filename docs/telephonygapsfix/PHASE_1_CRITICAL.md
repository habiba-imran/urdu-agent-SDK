# Phase 1: Critical Idempotency & Provisioning Lifecycle Fixes

## Executive Overview
Phase 1 targets the three highest-risk critical vulnerabilities in the telephony subsystem: outbound call duplicate side effects (`TEL-CRIT-01`), provider purchase race conditions leading to double billing (`TEL-CRIT-02`), and stuck `purchase_pending` numbers (`TEL-CRIT-03`).

---

## Gap 1.1: Outbound Call Idempotency in Real DB Mode (`TEL-CRIT-01`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telephony_service.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_service.py) (`create_outbound_call`), [`tenant_portal_api/telephony_queries.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_queries.py).
- **Anomaly**: `idempotency_key` is accepted in API requests, but persistent DB idempotency validation and record locking are omitted in real DB mode (`is_mock_provider_mode() == False`).
- **Impact**: Network retries or concurrent client requests generate duplicate SIP room participants in LiveKit, double-consume call quota, and create orphaned `telephony_calls` records.

### Detailed Architectural Fix Specification
1. **Action Key Formatting**:
   - Construct unique idempotency action identifier: `outbound_call:<tenant_id>:<idempotency_key>`.
2. **Leader Election & Transaction Flow**:
   ```sql
   INSERT INTO telephony_idempotency (
       id, tenant_id, action, idempotency_key, payload_hash, status, response_payload, created_at, updated_at
   ) VALUES (
       gen_random_uuid(), %s, 'outbound_call', %s, %s, 'in_progress', NULL, NOW(), NOW()
   ) ON CONFLICT (tenant_id, action, idempotency_key) DO NOTHING;
   ```
3. **Leader vs. Follower Control Logic**:
   - **If Row Inserted (Leader)**:
     - Reserve call quota and generate session metadata.
     - Call LiveKit API `create_sip_participant()`.
     - Insert `telephony_calls` record.
     - Update `telephony_idempotency` status to `'completed'` and store `response_payload` (JSON containing `call_id`, `room_name`, `status`).
     - Commit transaction.
   - **If Row Exists (Follower)**:
     - Query `telephony_idempotency` `FOR UPDATE` or read status.
     - Check `payload_hash`: If different from current request parameters, raise `TelephonyError(status=409, message="Idempotency key payload mismatch")`.
     - If status is `'completed'`, deserialize and return `response_payload` directly without invoking LiveKit.
     - If status is `'in_progress'`, block on row lock or raise `TelephonyError(status=409, message="Concurrent request in progress for this idempotency key")`.
   - **Failure Rollback**:
     - If LiveKit API call fails with upstream error, update idempotency record status to `'failed'` or delete row to allow safe client retries.

### Verification & Test Specifications
- **Test 1.1a (Concurrent Storm)**:
  - Spawn 5 parallel threads submitting `create_outbound_call` with identical `idempotency_key` and payload.
  - **Assert**: LiveKit client `create_sip_participant` is invoked **exactly 1 time**. All 5 threads return identical `call_id`.
- **Test 1.1b (Payload Hash Mismatch)**:
  - Call `create_outbound_call` with `idempotency_key="key-123"` and `to_number="+15550001"`.
  - Immediately call with `idempotency_key="key-123"` and `to_number="+15550002"`.
  - **Assert**: Second call throws `TelephonyError(409, "Idempotency key payload mismatch")`.
- **Test 1.1c (Replay Stability)**:
  - Complete call creation. Re-issue request 10 seconds later.
  - **Assert**: Replayed response matches original `call_id` and does not alter DB call count.

---

## Gap 1.2: Purchase Idempotency Race Closure (`TEL-CRIT-02`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telephony_service.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_service.py) (`purchase_number`).
- **Anomaly**: `purchase_number` checks for existing idempotency records, but does not acquire a lock or write an `in_progress` record **before** issuing the external API call `telnyx_client.create_number_order()`.
- **Impact**: Two concurrent purchase requests both observe "no idempotency record", both send order purchase requests to Telnyx (resulting in double provider billing and duplicate purchased numbers), and one fails later during DB constraint insertion.

### Detailed Architectural Fix Specification
1. **Pre-Provider Lock Insertion**:
   - Before executing `_telnyx_client.create_number_order()`:
     ```python
     inserted = queries.try_insert_idempotency_lock(
         conn,
         tenant_id=tenant_id,
         action="purchase_number",
         idempotency_key=idempotency_key,
         payload_hash=payload_hash,
         status="in_progress"
     )
     ```
2. **Execution & State Finalization**:
   - **Leader (inserted == True)**:
     - Proceed to `telnyx_client.create_number_order(phone_number=...)`.
     - Materialize number order in DB.
     - Atomically update idempotency record status to `'completed'` with order details.
   - **Follower (inserted == False)**:
     - Retrieve existing idempotency record.
     - If `status == 'completed'`, return cached purchase result.
     - If `status == 'in_progress'`, return HTTP 409 Conflict.
3. **Error Recovery**:
   - If Telnyx API returns 4xx/5xx error, update idempotency status to `'failed'` and roll back pre-allocated status.

### Verification & Test Specifications
- **Test 1.2a (Provider Call Deduplication)**:
  - Trigger 3 concurrent calls to `purchase_number` with same `idempotency_key` and phone number.
  - **Assert**: `telnyx_client.create_number_order` is called **exactly once**.
  - **Assert**: DB `telephony_number_orders` contains exactly 1 order row for this key.
- **Test 1.2b (Cached Result Verification)**:
  - Perform purchase. Repeat request after completion.
  - **Assert**: Returns original order JSON instantly with zero provider calls.

---

## Gap 1.3: `purchase_pending` Progression Repair (`TEL-CRIT-03`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telephony_service.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_service.py) (`_materialize_managed_number`, `sync_telnyx_owned_numbers`), [`tenant_portal_api/telephony_reconcile.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_reconcile.py).
- **Anomaly**: Phone numbers inserted during asynchronous order placement remain set to `NumberProvisioningStatus.PURCHASE_PENDING`. When `sync_telnyx_owned_numbers` or inventory sync runs, existing rows with `purchase_pending` status are skipped or preserved without checking actual provider order state.
- **Impact**: Successfully fulfilled numbers remain stuck in `purchase_pending` in the tenant portal, preventing routing configuration or outbound dialing.

### Detailed Architectural Fix Specification
1. **Transition Table Update in `telephony_status.py`**:
   - Explicitly permit transitions:
     - `PURCHASE_PENDING` $\rightarrow$ `OWNED` (upon provider active confirmation).
     - `PURCHASE_PENDING` $\rightarrow$ `PURCHASE_FAILED` (upon order rejection/cancellation).
2. **Reconciliation & Sync Promotion Logic**:
   - In `sync_telnyx_owned_numbers` and `telephony_reconcile.py`:
     - Fetch all local numbers in `PURCHASE_PENDING` status.
     - For each number, query provider inventory / order status API (`telnyx_client.get_number_order(order_id)` or check active Telnyx inventory).
     - If provider status is `'active'` / `'complete'`, execute state update:
       - Set `provisioning_status = 'owned'`.
       - Trigger LiveKit SIP trunk & dispatch rule provisioning check (`_ensure_livekit_sip_trunk_and_dispatch`).
3. **Integration into Background Reconciler**:
   - Add `reconcile_pending_purchases(conn)` sweep task to `telephony_reconcile.py` running on periodic intervals.

### Verification & Test Specifications
- **Test 1.3a (Delayed Provider Completion Promotion)**:
  - Insert a mock number record in `PURCHASE_PENDING` status with provider `order_id="ord-999"`.
  - Configure mock Telnyx client to return `order_status="complete"` for `"ord-999"`.
  - Run `sync_telnyx_owned_numbers()`.
  - **Assert**: Number provisioning status changes to `OWNED`.
  - **Assert**: LiveKit SIP dispatch rules and trunks are auto-provisioned for the newly owned number.
- **Test 1.3b (Failed Order Handling)**:
  - Configure mock Telnyx client to return `order_status="failed"` for `"ord-999"`.
  - Run reconciler sweep.
  - **Assert**: Number provisioning status changes to `PURCHASE_FAILED`.
