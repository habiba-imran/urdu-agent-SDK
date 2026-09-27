-- 0034_tenant_members.sql
-- Phase 1: link Supabase Auth humans to tenants.
--
-- auth_user_id is the Supabase auth.users.id (UUID). We do not FK to auth.users so
-- local/test DBs without the auth schema still apply this migration; integrity is
-- enforced by the portal bootstrap / invite paths.

create table if not exists tenant_members (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id) on delete cascade,
  auth_user_id  uuid not null,
  email         text,
  role          text not null,
  created_at    timestamptz not null default now(),
  constraint tenant_members_role_check check (role in ('owner', 'member')),
  constraint tenant_members_auth_user_unique unique (auth_user_id)
);

create index if not exists tenant_members_tenant_id_idx
  on tenant_members (tenant_id);

comment on table tenant_members is
  'Maps a Supabase Auth user to exactly one tenant (Phase 1). Credentials live on tenants, not here.';

comment on column tenant_members.auth_user_id is
  'Supabase auth.users.id';

comment on column tenant_members.role is
  'owner = first user / can invite later; member = invited. Invite UI is Phase 2.';

alter table tenant_members enable row level security;

-- Portal/admin connect as DB owner (bypass RLS). Policies keep authenticated JWTs
-- from reading other tenants if this table is ever queried via PostgREST.
drop policy if exists tenant_members_isolation on tenant_members;
create policy tenant_members_isolation on tenant_members
  for select using (
    tenant_id = (auth.jwt() ->> 'tenant_id')::uuid
    or auth_user_id = auth.uid()
  );

grant select on tenant_members to authenticated;
