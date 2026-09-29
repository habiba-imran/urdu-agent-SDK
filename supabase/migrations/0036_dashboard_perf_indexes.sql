-- 0036_dashboard_perf_indexes.sql
-- Speeds live-session / catalogue lookups used by the tenant dashboard.

-- Live "open" sessions for a tenant (Overview live count / reconcile helpers).
create index if not exists sessions_tenant_live_started_idx
  on sessions (tenant_id, started_at desc)
  where ended_at is null;

-- Provider catalogue lookups for /portal/provider-capabilities.
create index if not exists voices_provider_language_enabled_idx
  on voices (provider, language)
  where enabled and rollout_state = 'enabled';
