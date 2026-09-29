-- 0031_login_throttle_and_totp_replay.sql
-- F-H14 (audit §9): neither /admin/login nor /portal/login was rate-limited, throttled or
-- locked out; totp_verify accepted the RFC 6238 +/-1 step window with no record of consumed
-- codes, so a valid code stayed reusable for up to 90 seconds (contrary to §5.2); and
-- record_admin_action only ran on success, so admin_audit_log held no failed attempts.
--
-- The state lives in the database on purpose. The existing in-process rate limiter (F-H5)
-- resets on every deploy and is per worker — fine as a flood damper, useless as a lockout.

-- One row per attempt, success or failure. Doubles as the throttle input and the audit trail
-- the audit found missing.
create table if not exists login_attempts (
  id          bigserial primary key,
  realm       text not null,            -- 'admin' | 'portal'
  identity    text not null,            -- email (admin) or tenant id (portal), lowercased
  client_ip   text,
  successful  boolean not null,
  reason      text,                     -- why it failed, never a credential
  at          timestamptz not null default now()
);

comment on table login_attempts is
  'F-H14: login throttle input and failed-attempt audit trail. Never stores credentials.';

-- The throttle asks "how many failures for this identity/ip in the last N minutes".
create index if not exists login_attempts_identity_at_idx
  on login_attempts (realm, identity, at desc)
  where not successful;

create index if not exists login_attempts_ip_at_idx
  on login_attempts (realm, client_ip, at desc)
  where not successful;

-- Retention: this is authentication telemetry, not something to keep forever (and it is
-- personal data once it holds IPs). scripts/purge_used_nonces.py's sibling job trims it.
create index if not exists login_attempts_at_idx on login_attempts (at);

-- TOTP replay guard: the highest step counter already consumed for an admin. A code is
-- accepted only if its counter is strictly greater, so a code cannot be replayed inside the
-- drift window.
alter table admin_users
  add column if not exists last_totp_counter bigint;

comment on column admin_users.last_totp_counter is
  'F-H14: highest consumed TOTP step counter. A code at or below this is a replay and is refused.';
