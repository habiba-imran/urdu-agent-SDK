-- 0009_tenant_secrets.sql — add raw HMAC secret storage for tenant DB secret provider.
-- Idempotent: ALTER TABLE ADD COLUMN IF NOT EXISTS.

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS hmac_secret TEXT;

-- Security documentation comment:
COMMENT ON COLUMN tenants.hmac_secret IS 
  'Raw URL-safe HMAC secret used by control_plane DbSecretProvider. Never exposed via anon/authenticated JWT RLS.';
