-- 0030_agents_archive.sql
-- F-M13 (audit §9): there was no DELETE route for agents anywhere in tenant_portal_api or
-- admin, so agents accumulated permanently and tenant offboarding was impossible.
--
-- This adds an ARCHIVE marker rather than supporting a hard delete, deliberately:
-- sessions.agent_id is `references agents(id) on delete cascade` (0001_schema.sql:49), so a
-- real DELETE would silently take every session row — and with it the usage history that
-- billing and the audit trail are reconstructed from. Erasure of personal data is the purge
-- job's business (F-C4 / 0028), not a side effect of removing a configuration row.
--
-- Archived agents keep their history, stop appearing in the portal list, and cannot mint new
-- sessions (enforced in tenant_portal_api, alongside the existing tenant/agent ownership
-- checks).

alter table agents
  add column if not exists archived_at timestamptz;

comment on column agents.archived_at is
  'F-M13: when the tenant archived this agent. Archived agents keep their sessions and usage history, are hidden from the portal list, and cannot start new sessions.';

-- The portal lists a tenant's live agents on its most-visited page; keep that lookup cheap
-- now that it carries an extra predicate.
create index if not exists agents_tenant_live_idx
  on agents (tenant_id)
  where archived_at is null;
