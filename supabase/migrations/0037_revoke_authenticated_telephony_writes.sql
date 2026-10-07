-- M11-F02: telephony mutations go through the portal/service role, not PostgREST.
-- 0015 already GRANTs only SELECT to authenticated, but INSERT/UPDATE policies remained
-- and would become live if anyone re-granted write privileges. Drop write policies.

drop policy if exists tele_tenant_telnyx_connections_insert on tenant_telnyx_connections;
drop policy if exists tele_tenant_telnyx_connections_update on tenant_telnyx_connections;

drop policy if exists tele_telnyx_sip_connections_insert on telnyx_sip_connections;
drop policy if exists tele_telnyx_sip_connections_update on telnyx_sip_connections;

drop policy if exists tele_outbound_voice_profiles_insert on telnyx_outbound_voice_profiles;
drop policy if exists tele_outbound_voice_profiles_update on telnyx_outbound_voice_profiles;

drop policy if exists tele_phone_numbers_insert on telephony_phone_numbers;
drop policy if exists tele_phone_numbers_update on telephony_phone_numbers;

drop policy if exists tele_livekit_inbound_trunks_insert on livekit_inbound_trunks;
drop policy if exists tele_livekit_inbound_trunks_update on livekit_inbound_trunks;

drop policy if exists tele_livekit_outbound_trunks_insert on livekit_outbound_trunks;
drop policy if exists tele_livekit_outbound_trunks_update on livekit_outbound_trunks;

drop policy if exists tele_sip_dispatch_rules_insert on livekit_sip_dispatch_rules;
drop policy if exists tele_sip_dispatch_rules_update on livekit_sip_dispatch_rules;

drop policy if exists tele_number_orders_insert on telephony_number_orders;
drop policy if exists tele_number_orders_update on telephony_number_orders;

drop policy if exists tele_calls_insert on telephony_calls;
drop policy if exists tele_calls_update on telephony_calls;

drop policy if exists tele_call_events_insert on telephony_call_events;
drop policy if exists tele_call_events_update on telephony_call_events;

drop policy if exists tele_idempotency_keys_insert on telephony_idempotency_keys;
drop policy if exists tele_idempotency_keys_update on telephony_idempotency_keys;

drop policy if exists tele_audit_log_insert on telephony_audit_log;
drop policy if exists tele_audit_log_update on telephony_audit_log;

-- Belt-and-suspenders: ensure authenticated cannot write even if a policy is re-added.
revoke insert, update, delete on
  tenant_telnyx_connections, telnyx_sip_connections,
  telnyx_outbound_voice_profiles, telephony_phone_numbers,
  livekit_inbound_trunks, livekit_outbound_trunks,
  livekit_sip_dispatch_rules, telephony_number_orders,
  telephony_calls, telephony_call_events, telephony_idempotency_keys,
  telephony_audit_log
from authenticated;
