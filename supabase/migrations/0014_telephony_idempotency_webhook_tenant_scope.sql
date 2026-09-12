-- Migration 0014: Telephony Idempotency & Webhook Tenant Scope Index
-- Ensures tenant-scoped uniqueness for webhook event deduplication and persistent idempotency locks.

CREATE UNIQUE INDEX IF NOT EXISTS idx_telephony_call_events_tenant_event_id
ON telephony_call_events (tenant_id, provider_event_id)
WHERE provider_event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_telephony_idempotency_keys_tenant_action
ON telephony_idempotency_keys (tenant_id, action, idempotency_key);
