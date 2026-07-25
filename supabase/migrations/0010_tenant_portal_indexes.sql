-- 0010_tenant_portal_indexes.sql — support Phase 4 tenant portal reads.
-- Safe, additive indexes only.

create index if not exists agents_tenant_created_idx
  on agents (tenant_id, created_at desc);

create index if not exists sessions_tenant_agent_started_idx
  on sessions (tenant_id, agent_id, started_at desc);

create index if not exists usage_events_tenant_kind_at_idx
  on usage_events (tenant_id, kind, at desc);
