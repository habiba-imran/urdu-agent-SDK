-- 0007_admin.sql — super-admin portal (docs/26-PHASE-6-ADMIN.md).
-- admin_users/admin_audit_log are a COMPLETELY SEPARATE auth domain from tenants/agents:
-- different table, no tenant_id column anywhere, no RLS policy ever grants authenticated/anon
-- access. Only the admin backend (admin/app.py), connecting as the table owner via
-- SUPABASE_DB_URL (the same trusted owner connection mint.py uses, ADR-005), ever reads/writes
-- these. mint_rejections gives the P6-T06 "blockers" view (429/403 rates) a real usage_events-
-- adjacent source of truth — until this migration, no MintError/rate-limit rejection was ever
-- persisted anywhere, so that view had no data to query. Idempotent: drops before it creates so
-- `make db-reset` rebuilds from zero.

drop table if exists admin_audit_log cascade;
drop table if exists admin_users cascade;
drop table if exists mint_rejections cascade;

-- admin_users: one row per human with portal access. MFA is NOT optional — totp_secret is
-- NOT NULL, so an account cannot exist in a state where only a password gates it.
create table admin_users (
  id            uuid primary key default gen_random_uuid(),
  email         text not null unique,
  password_hash text not null,   -- pbkdf2_hmac (admin/security.py), never plaintext, never reused from tenant secrets
  totp_secret   text not null,   -- base32 RFC 4648, RFC 6238 TOTP — mandatory second factor
  created_at    timestamptz not null default now()
);

-- admin_audit_log: append-only. GATE 6 line 3 — every admin action writes here.
create table admin_audit_log (
  id       bigserial primary key,
  admin_id uuid not null references admin_users(id),
  action   text not null,        -- e.g. "list_tenants", "list_sessions"
  detail   jsonb,
  at       timestamptz not null default now()
);
create index admin_audit_log_admin_at_idx on admin_audit_log (admin_id, at desc);

-- mint_rejections: every MintError (401/403/429) and every control-plane rate-limit 429,
-- persisted so "is a tenant being throttled?" is an answerable SQL query, not a guess.
create table mint_rejections (
  id        bigserial primary key,
  tenant_id uuid,                -- nullable: an unknown-tenant 401 has no valid tenant row to reference
  status    int not null,
  reason    text not null,
  at        timestamptz not null default now()
);
create index mint_rejections_tenant_at_idx on mint_rejections (tenant_id, at desc);

-- RLS on every table, no exceptions (CLAUDE.md rule 6, rls_check.py gates it). No policies on
-- any of these three: the authenticated/anon roles get NOTHING here, by design — matches the
-- used_nonces precedent (0004_nonces.sql).
alter table admin_users     enable row level security;
alter table admin_audit_log enable row level security;
alter table mint_rejections enable row level security;
