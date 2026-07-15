-- 0002_rls.sql — row-level security on every table. No exceptions.
-- The app reaches these tables only through the Supabase `authenticated` role,
-- which carries a per-request JWT with a `tenant_id` claim. RLS keys every read
-- to that claim, so one tenant's JWT can never see another tenant's rows.
-- (Migrations run as the table owner, which bypasses RLS by design — that is how
-- this file and the seed can write; the app never connects as the owner.)

alter table tenants      enable row level security;
alter table agents       enable row level security;
alter table sessions     enable row level security;
alter table usage_events enable row level security;
alter table quota_state  enable row level security;
alter table voices       enable row level security;

-- tenant isolation: a row is visible only to a JWT whose tenant_id matches it.
drop policy if exists tenant_isolation_tenants on tenants;
create policy tenant_isolation_tenants on tenants
  for select using (id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tenant_isolation_agents on agents;
create policy tenant_isolation_agents on agents
  for select using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tenant_isolation_sessions on sessions;
create policy tenant_isolation_sessions on sessions
  for select using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tenant_isolation_usage on usage_events;
create policy tenant_isolation_usage on usage_events
  for select using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tenant_isolation_quota on quota_state;
create policy tenant_isolation_quota on quota_state
  for select using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- voices are a shared catalogue: any caller may read the enabled ones.
drop policy if exists voices_read_all on voices;
create policy voices_read_all on voices
  for select using (enabled);

-- Grants: reads flow through the authenticated role, gated by the policies above.
-- Writes are the control plane's job (Phase 2), via a scoped role — never service_role.
grant usage on schema public to authenticated, anon;
grant select on tenants, agents, sessions, usage_events, quota_state, voices to authenticated;
grant select on voices to anon;
