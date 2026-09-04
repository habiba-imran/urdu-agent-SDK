# Telephony Architecture Remediation & Gap Fix Plan

## Executive Summary
This directory contains the detailed architectural, implementation, and testing blueprints for resolving the 13 critical-to-low security, concurrency, state-progression, and livekit-drift anomalies identified in the Telephony Subsystem Audit.

The remediation plan is partitioned into 4 phased, isolated lanes. Each phase defines:
- **Problem Statement & Root Cause Analysis**: Detailed technical breakdown of the anomaly and affected files.
- **Architectural & Code Fix Specifications**: Component-by-component design changes, data structure updates, and DB transaction flows without modifying production code.
- **Verification & Test Protocols**: Deterministic unit, integration, and fault-injection test scenarios to validate the fix before progressing to the next phase.

---

## Phase Matrix & Index

| Phase | Target Gaps | Scope / Focus | Documentation File |
| :--- | :--- | :--- | :--- |
| **Phase 1** | `TEL-CRIT-01`<br>`TEL-CRIT-02`<br>`TEL-CRIT-03` | **Critical Concurrency & Idempotency**: Outbound call leader election, purchase race prevention, `purchase_pending` lifecycle progression. | [`PHASE_1_CRITICAL.md`](./PHASE_1_CRITICAL.md) |
| **Phase 2** | `TEL-HIGH-01`<br>`TEL-HIGH-02`<br>`TEL-HIGH-03`<br>`TEL-HIGH-04`<br>`TEL-HIGH-05`<br>`TEL-HIGH-06` | **High Severity Routing & Webhook Security**: Provider status mapping, LiveKit trunk/dispatch disable propagation, worker metadata revalidation, disabled-state preservation, tenant-scoped webhook deduplication, active-call drain guardrails. | [`PHASE_2_HIGH.md`](./PHASE_2_HIGH.md) |
| **Phase 3** | `TEL-MED-01`<br>`TEL-MED-02`<br>`TEL-MED-03` | **Medium Resilience & Reconciler Completeness**: Bounded TTL webhook replay cache, exponential retry/backoff with jitter, reconciler completeness (stale orders & quota leak repair). | [`PHASE_3_MEDIUM.md`](./PHASE_3_MEDIUM.md) |
| **Phase 4** | `TEL-LOW-01`<br>*(Smoke Matrix)* | **Low Enum Alignment & E2E Smoke Matrix**: Alignment of `_eligible_outbound_trunk_numbers` status enums, end-to-end regression soak matrix & release gates. | [`PHASE_4_LOW_AND_SMOKE.md`](./PHASE_4_LOW_AND_SMOKE.md) |

---

## Governance & Phase Progression Rules
1. **Zero Unvalidated Code Execution**: No production code should be edited without first finalizing and reviewing the corresponding phase document.
2. **Strict Phase Gating**: Phase $N$ tests must pass synchronously before proceeding to Phase $N+1$.
3. **Database Migration Standard**: Schema updates (`0014_telephony_idempotency_webhook_tenant_scope.sql`) must be backward-compatible and tested against real PostgreSQL transactions.
4. **Mock vs Real Separation**: Idempotency locks and webhook replay caches must function identically in both DB real-mode and mock-provider test modes.
