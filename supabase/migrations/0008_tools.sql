-- 0008_tools.sql -- ADR-013 deferred pass: fixed, platform-owned tool functions for the worker.
-- Scope decided 2026-07-18 (see docs/40-ADR.md ADR-029): minimal, domain-agnostic tools only --
-- NOT a rebuild of the old TechZone demo's product/customer/reservation catalogue. Every tenant
-- gets the same two tools regardless of business: end-of-call summary, and escalate-to-human.

alter table sessions add column if not exists summary text;

create table if not exists escalations (
  id bigserial primary key,
  tenant_id uuid not null references tenants(id),
  session_id uuid references sessions(id),
  reason text not null,
  contact_info text,
  requested_at timestamptz not null default now(),
  status text not null default 'pending'
);

alter table escalations enable row level security;

drop policy if exists tenant_isolation_escalations on escalations;
create policy tenant_isolation_escalations on escalations
  for select using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

grant select on escalations to authenticated;
