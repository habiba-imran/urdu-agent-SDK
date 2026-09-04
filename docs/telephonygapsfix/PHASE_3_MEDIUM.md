# Phase 3: Medium Severity Resilience & Reconciler Completeness

## Executive Overview
Phase 3 focuses on operational resilience, memory stability, transient error recovery, and background state reconciliation: bounded TTL webhook deduplication (`TEL-MED-01`), exponential retry/backoff policy (`TEL-MED-02`), and complete reconciler sweeps (`TEL-MED-03`).

---

## Gap 3.1: Bounded TTL-Backed Replay Protection (`TEL-MED-01`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telephony_webhooks.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_webhooks.py).
- **Anomaly**: Webhook deduplication uses process-local, unbounded Python memory sets (`set()`), which grow indefinitely under high throughput and clear on worker restarts.
- **Impact**: Server memory consumption steadily increases; process restarts re-expose the system to replay attacks for events delivered across service restarts.

### Detailed Architectural Fix Specification
1. **DB-Backed Deduplication with TTL Pruning**:
   - Webhook event uniqueness is backed by the `telephony_webhook_events` database table using `(tenant_id, source, provider_event_id)`.
   - Implement bounded cache in memory (LRU with `maxsize=10000`) for fast-path check, falling back to DB query.
2. **Automated TTL Pruning Sweep**:
   - Add retention cleanup function in `telephony_reconcile.py`:
     ```sql
     DELETE FROM telephony_webhook_events
     WHERE processed_at < NOW() - INTERVAL '7 days';
     ```

### Verification & Test Specifications
- **Test 3.1a (Deduplication Across Restarts)**:
  - Process webhook event `E1` for tenant `T1`.
  - Simulate app restart (clear in-memory structures).
  - Re-send webhook event `E1` for `T1`.
  - **Assert**: Database lookup identifies `E1` as processed; event is safely ignored without duplicate execution.

---

## Gap 3.2: Retry & Exponential Backoff Standardization (`TEL-MED-02`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telnyx_client.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telnyx_client.py), [`tenant_portal_api/livekit_sip.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/livekit_sip.py), [`tenant_portal_api/telephony_service.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_service.py).
- **Anomaly**: Upstream API requests fail immediately on transient HTTP status codes (429 Rate Limit, 502 Bad Gateway, 503 Service Unavailable, 504 Gateway Timeout) or transient network disconnects.
- **Impact**: Increased user-facing API errors during temporary upstream provider turbulence.

### Detailed Architectural Fix Specification
1. **Backoff Decorator Utility (`tenant_portal_api/telephony_utils.py`)**:
   ```python
   def retry_with_backoff(
       max_retries: int = 3,
       initial_delay: float = 0.2,
       max_delay: float = 3.0,
       backoff_factor: float = 2.0,
       retryable_status_codes: tuple[int, ...] = (429, 502, 503, 504),
   ):
       def decorator(func):
           @wraps(func)
           def wrapper(*args, **kwargs):
               delay = initial_delay
               for attempt in range(1, max_retries + 1):
                   try:
                       return func(*args, **kwargs)
                   except TelephonyError as err:
                       if err.status not in retryable_status_codes or attempt == max_retries:
                           raise
                       # Apply full jitter backoff formula
                       sleep_time = random.uniform(0, min(max_delay, delay))
                       time.sleep(sleep_time)
                       delay *= backoff_factor
           return wrapper
       return decorator
   ```
2. **Integration into Provider Clients**:
   Apply `@retry_with_backoff` to idempotent calls:
   - `TelnyxClient.list_phone_numbers`
   - `TelnyxClient.get_number_order`
   - `LiveKitSipClient.list_sip_inbound_trunks`

### Verification & Test Specifications
- **Test 3.2a (Transient 429 Recovery)**:
  - Configure mock Telnyx API to return HTTP 429 on first call, HTTP 200 on second call.
  - Execute API method.
  - **Assert**: Function retries after backoff delay and completes successfully on second attempt.
- **Test 3.2b (Fast Failure for 401/403)**:
  - Mock HTTP 401 Unauthorized.
  - **Assert**: Fails immediately on first attempt without retrying.

---

## Gap 3.3: Reconciler Completeness (`TEL-MED-03`)

### Problem Statement & Root Cause
- **Location**: [`tenant_portal_api/telephony_reconcile.py`](file:///d:/FinovaSolution/habiba-sdk-agent/tenant_portal_api/telephony_reconcile.py).
- **Anomaly**: `telephony_reconcile.py` is missing sweep tasks for stale pending number orders and leaked tenant call quota reservations.
- **Impact**: Abandoned orders remain pending indefinitely; crashed sessions leak allocated call quota, gradually reducing tenant capacity.

### Detailed Architectural Fix Specification
1. **Stale Order Reconciler Task**:
   ```python
   def reconcile_stale_orders(conn, max_age_hours: int = 1) -> int:
       # Query orders stuck in 'pending' longer than max_age_hours
       stale_orders = queries.get_stale_pending_orders(conn, max_age_hours)
       reconciled_count = 0
       for order in stale_orders:
           status = telnyx_client.get_number_order(order["provider_order_id"])
           queries.update_order_and_number_status(conn, order["id"], status)
           reconciled_count += 1
       return reconciled_count
   ```
2. **Quota Leak Reconciler Task**:
   ```python
   def reconcile_quota_leaks(conn) -> int:
       # Query active quota reservations where call is completed/failed or session missing
       leaked_reservations = queries.get_orphaned_quota_reservations(conn)
       for res in leaked_reservations:
           queries.release_quota_reservation(conn, res["id"])
       return len(leaked_reservations)
   ```

### Verification & Test Specifications
- **Test 3.3a (Stale Order Sweep)**:
  - Seed an order in `'pending'` status created 2 hours ago.
  - Execute `reconcile_stale_orders()`.
  - **Assert**: Order is polled from provider and status updated to terminal state.
- **Test 3.3b (Quota Leak Release)**:
  - Seed a quota reservation for a call that reached `'completed'` status 10 minutes ago.
  - Execute `reconcile_quota_leaks()`.
  - **Assert**: Quota reservation is released and tenant active call counter decremented.
