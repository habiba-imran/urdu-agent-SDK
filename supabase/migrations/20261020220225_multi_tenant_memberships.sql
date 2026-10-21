-- One Auth user can belong to several tenants; keep exactly one row per pair.
alter table public.tenant_members
  drop constraint if exists tenant_members_auth_user_unique;

alter table public.tenant_members
  add constraint tenant_members_tenant_auth_user_unique unique (tenant_id, auth_user_id);

create index if not exists tenant_members_auth_user_id_idx
  on public.tenant_members (auth_user_id);

comment on table public.tenant_members is
  'Workspace memberships. A Supabase Auth user may belong to multiple tenants with independent roles and permissions.';

comment on column public.tenant_members.can_view_api_keys is
  'Owner-controlled publishable-key visibility only. Defaults to false. HMAC reveal always requires the owner role.';

-- Keep permission and membership writes behind the tenant-scoped portal API.
revoke insert, update, delete on public.tenant_members from anon, authenticated;
