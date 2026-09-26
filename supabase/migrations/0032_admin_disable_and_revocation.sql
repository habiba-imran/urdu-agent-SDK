-- 0032_admin_disable_and_revocation.sql
-- Audit §3.5: "No admin JWT revocation and no disable flag on admin_users" — an 8-hour
-- admin token stayed valid after the account should have been disabled, and the only way to
-- kill a stolen or departed-admin token was rotating ADMIN_JWT_SECRET, which invalidates
-- every other admin session at the same time.
--
-- Two columns, two different needs:
--   disabled_at       — the account is off. Login fails and existing tokens stop working.
--   tokens_valid_from — "sign everyone out": tokens issued before this instant are refused,
--                       without disabling the account or touching the signing key.

alter table admin_users
  add column if not exists disabled_at timestamptz,
  add column if not exists tokens_valid_from timestamptz;

comment on column admin_users.disabled_at is
  'Set to disable the account: login is refused and existing admin tokens stop being accepted.';

comment on column admin_users.tokens_valid_from is
  'Admin tokens issued before this instant are refused. Revokes sessions without rotating ADMIN_JWT_SECRET (which would sign out every admin).';
