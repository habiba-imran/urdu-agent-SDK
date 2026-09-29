-- 0035_tenant_members_status.sql
-- Phase 2: invited vs active for member list UI.

alter table tenant_members
  add column if not exists status text not null default 'active';

alter table tenant_members
  drop constraint if exists tenant_members_status_check;

alter table tenant_members
  add constraint tenant_members_status_check
  check (status in ('invited', 'active'));

comment on column tenant_members.status is
  'invited = Auth user created, not yet logged in; active = has exchanged a portal session';
