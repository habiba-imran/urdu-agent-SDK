-- 0004_nonces.sql — replay-protection nonce store for the control-plane mint (Phase 2).
-- One row per consumed (tenant, nonce). The UNIQUE primary key is the replay check: a second
-- INSERT of the same pair raises unique_violation, which the mint maps to 401.
-- Idempotent so `make db-reset` rebuilds it from zero.

drop table if exists used_nonces cascade;

create table used_nonces (
  tenant_id uuid not null references tenants(id) on delete cascade,
  nonce     text not null,
  used_at   timestamptz not null default now(),
  primary key (tenant_id, nonce)
);
create index used_nonces_used_at_idx on used_nonces (used_at);

-- RLS on (every table, no exceptions — rls_check gates it). No policies: only the control plane,
-- which connects as the table owner (RLS bypass, ADR-005), ever touches this table. The
-- authenticated/anon roles get nothing here.
alter table used_nonces enable row level security;
