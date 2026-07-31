-- 0012_telephony_core_tables.sql -- Habiba Phase 3: core telephony tables only.
-- Scope: normalized tables and base foreign-key relationships. Constraints, indexes,
-- status enforcement, RLS/grants, and governance finalization are reserved for 0013-0015.

create table if not exists tenant_telnyx_connections (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  label text,
  platform_status text not null default 'not_connected',
  provider_status text,
  encrypted_api_key_ref text,
  key_fingerprint text,
  telnyx_account_id text,
  last_verified_at timestamptz,
  permission_last_checked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  disabled_at timestamptz,
  disconnected_at timestamptz,
  compromised_at timestamptz
);

create table if not exists telnyx_sip_connections (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  telnyx_connection_id uuid not null references tenant_telnyx_connections(id) on delete cascade,
  provider_sip_connection_id text,
  sip_fqdn text,
  sip_username text,
  encrypted_sip_secret_ref text,
  platform_status text not null default 'draft',
  provider_status text,
  last_verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  disabled_at timestamptz
);

create table if not exists telnyx_outbound_voice_profiles (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  telnyx_connection_id uuid not null references tenant_telnyx_connections(id) on delete cascade,
  telnyx_sip_connection_id uuid references telnyx_sip_connections(id) on delete set null,
  provider_outbound_voice_profile_id text,
  platform_status text not null default 'not_configured',
  provider_status text,
  allowed_destinations text[] not null default '{}',
  concurrency_limit int,
  channel_limit int,
  daily_spending_limit numeric,
  last_verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  disabled_at timestamptz
);

create table if not exists telephony_phone_numbers (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  telnyx_connection_id uuid not null references tenant_telnyx_connections(id) on delete cascade,
  telnyx_sip_connection_id uuid references telnyx_sip_connections(id) on delete set null,
  provider_number_id text,
  e164_number text not null,
  country text,
  number_type text,
  features text[] not null default '{}',
  provisioning_status text not null default 'discovered',
  routing_status text not null default 'not_configured',
  provider_status text,
  assigned_agent_id uuid references agents(id) on delete set null,
  external_customer_ref text,
  last_synced_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  disabled_at timestamptz
);

create table if not exists livekit_inbound_trunks (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  phone_number_id uuid not null references telephony_phone_numbers(id) on delete cascade,
  telnyx_connection_id uuid not null references tenant_telnyx_connections(id) on delete cascade,
  telnyx_sip_connection_id uuid not null references telnyx_sip_connections(id) on delete cascade,
  livekit_inbound_trunk_id text,
  platform_status text not null default 'draft',
  provider_status text,
  last_reconciled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  disabled_at timestamptz
);

create table if not exists livekit_outbound_trunks (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  telnyx_connection_id uuid not null references tenant_telnyx_connections(id) on delete cascade,
  telnyx_sip_connection_id uuid not null references telnyx_sip_connections(id) on delete cascade,
  outbound_voice_profile_record_id uuid not null references telnyx_outbound_voice_profiles(id) on delete cascade,
  livekit_outbound_trunk_id text,
  platform_status text not null default 'draft',
  provider_status text,
  last_reconciled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  disabled_at timestamptz
);

create table if not exists livekit_sip_dispatch_rules (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  phone_number_id uuid not null references telephony_phone_numbers(id) on delete cascade,
  inbound_trunk_record_id uuid not null references livekit_inbound_trunks(id) on delete cascade,
  livekit_sip_dispatch_rule_id text,
  platform_status text not null default 'draft',
  provider_status text,
  last_reconciled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  disabled_at timestamptz
);

create table if not exists telephony_number_orders (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  telnyx_connection_id uuid not null references tenant_telnyx_connections(id) on delete cascade,
  idempotency_key text not null,
  provider_order_id text,
  selected_e164_number text not null,
  country text,
  area_code text,
  number_type text,
  features text[] not null default '{}',
  price_amount numeric,
  price_currency text,
  provider_status text,
  platform_status text not null default 'pending',
  raw_provider_status text,
  provider_error_payload jsonb,
  error_code text,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists telephony_calls (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  session_id uuid references sessions(id) on delete set null,
  agent_id uuid references agents(id) on delete set null,
  phone_number_id uuid references telephony_phone_numbers(id) on delete set null,
  direction text not null,
  room_name text,
  from_number text,
  to_number text,
  recipient text,
  call_context jsonb not null default '{}',
  external_customer_ref text,
  external_workflow_ref text,
  inbound_trunk_record_id uuid references livekit_inbound_trunks(id) on delete set null,
  outbound_trunk_record_id uuid references livekit_outbound_trunks(id) on delete set null,
  sip_dispatch_rule_record_id uuid references livekit_sip_dispatch_rules(id) on delete set null,
  livekit_agent_dispatch_id text,
  livekit_sip_call_id text,
  livekit_sip_call_id_full text,
  sip_trunk_phone_number text,
  raw_livekit_sip_participant_status text,
  platform_status text not null default 'queued',
  provider_status text,
  outcome text,
  error_code text,
  error_message text,
  quota_reserved_at timestamptz,
  quota_released_at timestamptz,
  usage_recorded_at timestamptz,
  started_at timestamptz,
  answered_at timestamptz,
  ended_at timestamptz,
  duration_sec int,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists telephony_call_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  telephony_call_id uuid not null references telephony_calls(id) on delete cascade,
  source text not null,
  event_type text not null,
  provider_event_id text,
  internal_stage text,
  payload jsonb,
  created_at timestamptz not null default now()
);

-- Primary key/unique constraint on (tenant_id, idempotency_key, action) is added in 0013.
create table if not exists telephony_idempotency_keys (
  tenant_id uuid not null references tenants(id) on delete cascade,
  idempotency_key text not null,
  action text not null,
  request_hash text not null,
  response_body jsonb,
  platform_status text not null default 'pending',
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists telephony_audit_log (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  actor_type text not null,
  actor_id text,
  action text not null,
  target_type text not null,
  target_id text,
  detail jsonb,
  created_at timestamptz not null default now()
);
