-- 0001_schema.sql — multi-tenant foundation (docs/21-PHASE-1-SUPABASE.md).
-- Idempotent: drops before it creates so `make db-reset` rebuilds from zero
-- (Supabase free projects pause after 7 days idle and come back empty).

-- Drop in reverse dependency order.
drop table if exists usage_events cascade;
drop table if exists quota_state cascade;
drop table if exists sessions cascade;
drop table if exists agents cascade;
drop table if exists voices cascade;
drop table if exists tenants cascade;

-- voices: catalogue seeded from Uplift. Created first: agents references it.
create table voices (
  id           text primary key,
  display_name text not null,
  gender       text,
  preview_url  text,
  artwork_url  text,
  enabled      boolean not null default true
);

-- tenants: one row per host-platform customer.
create table tenants (
  id                uuid primary key default gen_random_uuid(),
  name              text not null,
  hmac_secret_hash  text not null,                                 -- hash ONLY, never the secret
  max_concurrent    int  not null default 2,                       -- per-tenant cap; one tenant must not eat the pool
  max_minutes_month int  not null default 100,
  allowed_origins   text[] not null default '{}',                  -- CORS/origin allowlist; empty = not enforced (dev)
  status            text not null default 'active' check (status in ('active', 'suspended')),
  created_at        timestamptz not null default now()
);

-- agents: a tenant's voice agent = prompt + voice. This is the whole product.
create table agents (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references tenants(id) on delete cascade,
  name       text not null,
  prompt     text not null,                                        -- UNTRUSTED DATA, never an instruction
  voice_id   text not null references voices(id),
  llm_model  text not null default 'gemini-2.5-flash',
  created_at timestamptz not null default now()
);

create table sessions (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references tenants(id) on delete cascade,
  agent_id   uuid not null references agents(id) on delete cascade,
  room_name  text not null unique,
  started_at timestamptz not null default now(),
  ended_at   timestamptz,
  duration_sec int,
  end_reason text
);

-- usage_events: the billing truth. Append-only.
create table usage_events (
  id         bigserial primary key,
  tenant_id  uuid not null references tenants(id),
  session_id uuid references sessions(id),
  kind       text not null check (kind in ('stt_sec', 'tts_sec', 'llm_tokens', 'agent_sec')),
  qty        numeric not null,
  at         timestamptz not null default now()
);

-- quota_state: fast counters read by the token mint (Phase 2).
create table quota_state (
  tenant_id          uuid primary key references tenants(id) on delete cascade,
  concurrent_now     int not null default 0,
  minutes_this_month numeric not null default 0,
  period_start       date not null default date_trunc('month', now())::date
);

create index sessions_tenant_started_idx on sessions (tenant_id, started_at desc);
create index usage_events_tenant_at_idx on usage_events (tenant_id, at desc);
