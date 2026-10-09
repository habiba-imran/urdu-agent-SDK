-- 0039_telephony_calls_provider_call_ids.sql
-- A-01.1: Telnyx call.* webhooks carry Telnyx's own call_control_id / call_session_id /
-- call_leg_id. telephony_calls only stored LiveKit's sip_call_id (from CreateSIPParticipant),
-- and the webhook handler matched Telnyx ids against the LiveKit column — two different id
-- spaces, so no call event ever updated a call row.
--
-- These columns hold the provider-side ids. They are bound on the first correlated webhook
-- (matched by direction + from/to + recent creation, tenant-scoped via connection_id) and
-- every later event matches exactly. Additive and idempotent; readers probe for the column
-- so a service deployed before this migration keeps the legacy behaviour.

alter table telephony_calls
  add column if not exists provider_call_control_id text,
  add column if not exists provider_call_session_id text,
  add column if not exists provider_call_leg_id text,
  add column if not exists provider_call_bound_at timestamptz;

comment on column telephony_calls.provider_call_control_id is
  'Telnyx call_control_id for this call leg. Bound from the first correlated call.* webhook; exact-match key for later events.';
comment on column telephony_calls.provider_call_session_id is
  'Telnyx call_session_id (spans legs of one call). Secondary exact-match key.';
comment on column telephony_calls.provider_call_leg_id is
  'Telnyx call_leg_id. Informational.';
comment on column telephony_calls.provider_call_bound_at is
  'When the Telnyx ids were bound to this row (null = never correlated).';

create index if not exists idx_telephony_calls_provider_call_control_id
  on telephony_calls (provider_call_control_id)
  where provider_call_control_id is not null;

create index if not exists idx_telephony_calls_provider_call_session_id
  on telephony_calls (provider_call_session_id)
  where provider_call_session_id is not null;

-- First-event correlation scans only unbound, still-active calls.
create index if not exists idx_telephony_calls_unbound_active
  on telephony_calls (tenant_id, direction, created_at desc)
  where provider_call_control_id is null
    and platform_status in ('queued', 'dialing', 'ringing', 'in_progress');

-- Not granted to authenticated: provider ids are operational, not tenant-facing data.
