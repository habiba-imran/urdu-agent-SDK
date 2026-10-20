-- Members must be individually approved by the workspace owner to reveal API keys.
-- Existing and newly invited members start with access off; owners are allowed by role.
alter table public.tenant_members
  add column if not exists can_view_api_keys boolean not null default false;

comment on column public.tenant_members.can_view_api_keys is
  'Owner-controlled permission for publishable-key display and explicit audited HMAC reveal. Read live by the portal, never trusted from a JWT.';

-- Permission writes go through the owner-authorized portal API. A browser Auth
-- user must never grant itself access through PostgREST, even if grants drifted.
revoke update on public.tenant_members from anon, authenticated;
revoke update (can_view_api_keys) on public.tenant_members from anon, authenticated;
