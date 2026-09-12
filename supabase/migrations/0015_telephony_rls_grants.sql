-- 0015_telephony_rls_grants.sql -- Habiba telephony RLS/grants slice.
-- Scope: enable RLS, tenant-scoped policies, no anon table access, and
-- column-scoped authenticated reads that exclude credentials/restricted payloads.

alter table tenant_telnyx_connections enable row level security;
alter table telnyx_sip_connections enable row level security;
alter table telnyx_outbound_voice_profiles enable row level security;
alter table telephony_phone_numbers enable row level security;
alter table livekit_inbound_trunks enable row level security;
alter table livekit_outbound_trunks enable row level security;
alter table livekit_sip_dispatch_rules enable row level security;
alter table telephony_number_orders enable row level security;
alter table telephony_calls enable row level security;
alter table telephony_call_events enable row level security;
alter table telephony_idempotency_keys enable row level security;
alter table telephony_audit_log enable row level security;

revoke all on table
  tenant_telnyx_connections, telnyx_sip_connections,
  telnyx_outbound_voice_profiles, telephony_phone_numbers,
  livekit_inbound_trunks, livekit_outbound_trunks,
  livekit_sip_dispatch_rules, telephony_number_orders,
  telephony_calls, telephony_call_events, telephony_idempotency_keys,
  telephony_audit_log
from public, anon, authenticated;

drop policy if exists tele_tenant_telnyx_connections_select on tenant_telnyx_connections;
create policy tele_tenant_telnyx_connections_select on tenant_telnyx_connections for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_tenant_telnyx_connections_insert on tenant_telnyx_connections;
create policy tele_tenant_telnyx_connections_insert on tenant_telnyx_connections for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_tenant_telnyx_connections_update on tenant_telnyx_connections;
create policy tele_tenant_telnyx_connections_update on tenant_telnyx_connections for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_telnyx_sip_connections_select on telnyx_sip_connections;
create policy tele_telnyx_sip_connections_select on telnyx_sip_connections for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_telnyx_sip_connections_insert on telnyx_sip_connections;
create policy tele_telnyx_sip_connections_insert on telnyx_sip_connections for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_telnyx_sip_connections_update on telnyx_sip_connections;
create policy tele_telnyx_sip_connections_update on telnyx_sip_connections for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_outbound_voice_profiles_select on telnyx_outbound_voice_profiles;
create policy tele_outbound_voice_profiles_select on telnyx_outbound_voice_profiles for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_outbound_voice_profiles_insert on telnyx_outbound_voice_profiles;
create policy tele_outbound_voice_profiles_insert on telnyx_outbound_voice_profiles for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_outbound_voice_profiles_update on telnyx_outbound_voice_profiles;
create policy tele_outbound_voice_profiles_update on telnyx_outbound_voice_profiles for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_phone_numbers_select on telephony_phone_numbers;
create policy tele_phone_numbers_select on telephony_phone_numbers for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_phone_numbers_insert on telephony_phone_numbers;
create policy tele_phone_numbers_insert on telephony_phone_numbers for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_phone_numbers_update on telephony_phone_numbers;
create policy tele_phone_numbers_update on telephony_phone_numbers for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_livekit_inbound_trunks_select on livekit_inbound_trunks;
create policy tele_livekit_inbound_trunks_select on livekit_inbound_trunks for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_livekit_inbound_trunks_insert on livekit_inbound_trunks;
create policy tele_livekit_inbound_trunks_insert on livekit_inbound_trunks for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_livekit_inbound_trunks_update on livekit_inbound_trunks;
create policy tele_livekit_inbound_trunks_update on livekit_inbound_trunks for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_livekit_outbound_trunks_select on livekit_outbound_trunks;
create policy tele_livekit_outbound_trunks_select on livekit_outbound_trunks for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_livekit_outbound_trunks_insert on livekit_outbound_trunks;
create policy tele_livekit_outbound_trunks_insert on livekit_outbound_trunks for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_livekit_outbound_trunks_update on livekit_outbound_trunks;
create policy tele_livekit_outbound_trunks_update on livekit_outbound_trunks for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_sip_dispatch_rules_select on livekit_sip_dispatch_rules;
create policy tele_sip_dispatch_rules_select on livekit_sip_dispatch_rules for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_sip_dispatch_rules_insert on livekit_sip_dispatch_rules;
create policy tele_sip_dispatch_rules_insert on livekit_sip_dispatch_rules for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_sip_dispatch_rules_update on livekit_sip_dispatch_rules;
create policy tele_sip_dispatch_rules_update on livekit_sip_dispatch_rules for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_number_orders_select on telephony_number_orders;
create policy tele_number_orders_select on telephony_number_orders for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_number_orders_insert on telephony_number_orders;
create policy tele_number_orders_insert on telephony_number_orders for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_number_orders_update on telephony_number_orders;
create policy tele_number_orders_update on telephony_number_orders for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_calls_select on telephony_calls;
create policy tele_calls_select on telephony_calls for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_calls_insert on telephony_calls;
create policy tele_calls_insert on telephony_calls for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_calls_update on telephony_calls;
create policy tele_calls_update on telephony_calls for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_call_events_select on telephony_call_events;
create policy tele_call_events_select on telephony_call_events for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_call_events_insert on telephony_call_events;
create policy tele_call_events_insert on telephony_call_events for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_call_events_update on telephony_call_events;
create policy tele_call_events_update on telephony_call_events for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_idempotency_keys_select on telephony_idempotency_keys;
create policy tele_idempotency_keys_select on telephony_idempotency_keys for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_idempotency_keys_insert on telephony_idempotency_keys;
create policy tele_idempotency_keys_insert on telephony_idempotency_keys for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_idempotency_keys_update on telephony_idempotency_keys;
create policy tele_idempotency_keys_update on telephony_idempotency_keys for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

drop policy if exists tele_audit_log_select on telephony_audit_log;
create policy tele_audit_log_select on telephony_audit_log for select to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_audit_log_insert on telephony_audit_log;
create policy tele_audit_log_insert on telephony_audit_log for insert to authenticated with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
drop policy if exists tele_audit_log_update on telephony_audit_log;
create policy tele_audit_log_update on telephony_audit_log for update to authenticated using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid) with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

grant select (
  id, tenant_id, label, platform_status, provider_status, key_fingerprint,
  telnyx_account_id, last_verified_at, permission_last_checked_at, created_at,
  updated_at, disabled_at, disconnected_at, compromised_at, retention_until,
  deletion_requested_at, deleted_at, offboarded_at, redacted_at, redaction_reason
) on tenant_telnyx_connections to authenticated;

grant select (
  id, tenant_id, telnyx_connection_id, provider_sip_connection_id, sip_fqdn,
  sip_username, platform_status, provider_status, last_verified_at, created_at,
  updated_at, disabled_at, retention_until, deletion_requested_at, deleted_at,
  offboarded_at, redacted_at, redaction_reason
) on telnyx_sip_connections to authenticated;

grant select (
  id, tenant_id, telnyx_connection_id, telnyx_sip_connection_id,
  provider_outbound_voice_profile_id, platform_status, provider_status,
  allowed_destinations, concurrency_limit, channel_limit, daily_spending_limit,
  last_verified_at, created_at, updated_at, disabled_at, retention_until,
  deletion_requested_at, deleted_at, offboarded_at, redacted_at, redaction_reason
) on telnyx_outbound_voice_profiles to authenticated;

grant select (
  id, tenant_id, telnyx_connection_id, telnyx_sip_connection_id,
  provider_number_id, e164_number, country, number_type, features,
  provisioning_status, routing_status, provider_status, assigned_agent_id,
  external_customer_ref, last_synced_at, created_at, updated_at, disabled_at,
  retention_until, deletion_requested_at, deleted_at, offboarded_at,
  redacted_at, redaction_reason
) on telephony_phone_numbers to authenticated;

grant select (
  id, tenant_id, phone_number_id, telnyx_connection_id, telnyx_sip_connection_id,
  livekit_inbound_trunk_id, platform_status, provider_status,
  last_reconciled_at, created_at, updated_at, disabled_at, retention_until,
  deletion_requested_at, deleted_at, offboarded_at, redacted_at, redaction_reason
) on livekit_inbound_trunks to authenticated;

grant select (
  id, tenant_id, telnyx_connection_id, telnyx_sip_connection_id,
  outbound_voice_profile_record_id, livekit_outbound_trunk_id, platform_status,
  provider_status, last_reconciled_at, created_at, updated_at, disabled_at,
  retention_until, deletion_requested_at, deleted_at, offboarded_at,
  redacted_at, redaction_reason
) on livekit_outbound_trunks to authenticated;

grant select (
  id, tenant_id, phone_number_id, inbound_trunk_record_id,
  livekit_sip_dispatch_rule_id, platform_status, provider_status,
  last_reconciled_at, created_at, updated_at, disabled_at, retention_until,
  deletion_requested_at, deleted_at, offboarded_at, redacted_at, redaction_reason
) on livekit_sip_dispatch_rules to authenticated;

grant select (
  id, tenant_id, telnyx_connection_id, idempotency_key, provider_order_id,
  selected_e164_number, country, area_code, number_type, features, price_amount,
  price_currency, provider_status, platform_status, error_code, error_message,
  created_at, updated_at, retention_until, deletion_requested_at, deleted_at,
  offboarded_at, redacted_at, redaction_reason
) on telephony_number_orders to authenticated;

grant select (
  id, tenant_id, session_id, agent_id, phone_number_id, direction, room_name,
  from_number, to_number, recipient, external_customer_ref,
  external_workflow_ref, inbound_trunk_record_id, outbound_trunk_record_id,
  sip_dispatch_rule_record_id, livekit_agent_dispatch_id, livekit_sip_call_id,
  livekit_sip_call_id_full, sip_trunk_phone_number, platform_status,
  provider_status, outcome, error_code, error_message, quota_reserved_at,
  quota_released_at, usage_recorded_at, started_at, answered_at, ended_at,
  duration_sec, created_at, updated_at, retention_until, deletion_requested_at,
  deleted_at, offboarded_at, redacted_at, redaction_reason,
  export_requested_at, export_completed_at, last_access_audited_at
) on telephony_calls to authenticated;
