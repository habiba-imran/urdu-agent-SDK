# PHASE 1 — SUPABASE FOUNDATION
**Goal:** multi-tenant schema where cross-tenant reads are impossible.
**Read first:** 33-GUIDE-SUPABASE.md, 31-GUIDE-SECURITY.md §2
**Gate:** `make gate` + `scripts/rls_check.py`

## Schema (audit gap #9 — this was missing)
```sql
-- tenants: one row per host-platform customer
create table tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  hmac_secret_hash text not null,             -- hash ONLY. never the secret.
  max_concurrent int not null default 2,      -- 🔴 per-tenant cap. one tenant must not eat the pool.
  max_minutes_month int not null default 100,
  status text not null default 'active' check (status in ('active','suspended')),
  created_at timestamptz default now()
);
-- agents: a tenant's voice agent = prompt + voice. THIS IS THE WHOLE PRODUCT.
create table agents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null,
  prompt text not null,                        -- 🔴 UNTRUSTED DATA. never an instruction.
  voice_id text not null references voices(id),
  llm_model text not null default 'gemini-2.5-flash',
  created_at timestamptz default now()
);
create table voices (                          -- catalogue, seeded from Uplift
  id text primary key, display_name text not null, gender text,
  preview_url text, artwork_url text, enabled boolean default true
);
create table sessions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  agent_id uuid not null references agents(id) on delete cascade,
  room_name text not null unique,
  started_at timestamptz default now(), ended_at timestamptz,
  duration_sec int, end_reason text
);
create table usage_events (                    -- the billing truth. append-only.
  id bigserial primary key,
  tenant_id uuid not null references tenants(id),
  session_id uuid references sessions(id),
  kind text not null check (kind in ('stt_sec','tts_sec','llm_tokens','agent_sec')),
  qty numeric not null, at timestamptz default now()
);
create table quota_state (                     -- fast counters for the mint
  tenant_id uuid primary key references tenants(id) on delete cascade,
  concurrent_now int not null default 0,
  minutes_this_month numeric not null default 0,
  period_start date not null default date_trunc('month', now())::date
);
create index on sessions(tenant_id, started_at desc);
create index on usage_events(tenant_id, at desc);
```

## RLS — every table, no exceptions
```sql
alter table tenants      enable row level security;
alter table agents       enable row level security;
alter table sessions     enable row level security;
alter table usage_events enable row level security;
alter table quota_state  enable row level security;
alter table voices       enable row level security;

create policy tenant_isolation_agents on agents
  using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
-- repeat for sessions, usage_events, quota_state
create policy voices_read_all on voices for select using (enabled);
```
🔴 The control plane uses a **scoped role**, never `service_role`. `service_role` bypasses RLS by design —
that is exactly the documented Supabase MCP exfiltration path.

## Tasks
- **P1-T01** migrations 0001_schema, 0002_rls, 0003_seed_voices. Done: `make db-reset` rebuilds from zero.
- **P1-T02** `scripts/rls_check.py`. Done: fails if ANY table has `rowsecurity=false`.
- **P1-T03** `tests/test_isolation.py` — tenant A's JWT reading B's agents. **Done: the read RETURNS ZERO ROWS.**
- **P1-T04** `db-inspector` regenerates `supabase/SCHEMA.md` + `RLS.md`. Done: matches live.

## GATE 1
```
[ ] make db-reset rebuilds from zero (Supabase free pauses at 7 days idle — this WILL be needed)
[ ] rls_check.py -> every table rowsecurity=true
[ ] test_isolation.py -> cross-tenant read returns 0 rows
[ ] grep -r service_role --include=*.py . -> zero hits outside .env.local
[ ] supabase/SCHEMA.md matches live
```
**HUMAN GATE:** you read every RLS policy by hand. This is the one you verify personally.
