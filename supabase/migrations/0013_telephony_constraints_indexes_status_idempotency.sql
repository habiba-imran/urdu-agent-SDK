-- 0013_telephony_constraints_indexes_status_idempotency.sql -- Habiba Phase 4.
-- Scope: tenant-scoped invariants, lookup indexes, status value checks, and
-- idempotency/provider-event dedupe. RLS/grants and governance finalization are
-- reserved for 0014-0015.

alter table agents
  add constraint agents_tenant_id_id_unique unique (tenant_id, id);

alter table sessions
  add constraint sessions_tenant_id_id_unique unique (tenant_id, id);

alter table tenant_telnyx_connections
  add constraint tenant_telnyx_connections_tenant_id_id_unique unique (tenant_id, id),
  add constraint tenant_telnyx_connections_platform_status_check
    check (
      platform_status in (
        'not_connected', 'verifying', 'active', 'verification_failed',
        'rotation_required', 'permission_failed', 'compromised', 'disabled',
        'disconnected'
      )
    );

alter table telnyx_sip_connections
  add constraint telnyx_sip_connections_tenant_id_id_unique unique (tenant_id, id),
  add constraint telnyx_sip_connections_telnyx_connection_tenant_fk
    foreign key (tenant_id, telnyx_connection_id)
    references tenant_telnyx_connections(tenant_id, id),
  add constraint telnyx_sip_connections_platform_status_check
    check (
      platform_status in (
        'draft', 'pending_verification', 'testing', 'active', 'failed',
        'disabled'
      )
    );

alter table telnyx_outbound_voice_profiles
  add constraint telnyx_outbound_voice_profiles_tenant_id_id_unique unique (tenant_id, id),
  add constraint telnyx_outbound_voice_profiles_telnyx_connection_tenant_fk
    foreign key (tenant_id, telnyx_connection_id)
    references tenant_telnyx_connections(tenant_id, id),
  add constraint telnyx_outbound_voice_profiles_sip_connection_tenant_fk
    foreign key (tenant_id, telnyx_sip_connection_id)
    references telnyx_sip_connections(tenant_id, id),
  add constraint telnyx_outbound_voice_profiles_platform_status_check
    check (
      platform_status in (
        'not_configured', 'configuring', 'active', 'destination_restricted',
        'limit_reached', 'verification_required', 'failed', 'disabled'
      )
    );

alter table telephony_phone_numbers
  add constraint telephony_phone_numbers_tenant_id_id_unique unique (tenant_id, id),
  add constraint telephony_phone_numbers_telnyx_connection_tenant_fk
    foreign key (tenant_id, telnyx_connection_id)
    references tenant_telnyx_connections(tenant_id, id),
  add constraint telephony_phone_numbers_sip_connection_tenant_fk
    foreign key (tenant_id, telnyx_sip_connection_id)
    references telnyx_sip_connections(tenant_id, id),
  add constraint telephony_phone_numbers_assigned_agent_tenant_fk
    foreign key (tenant_id, assigned_agent_id)
    references agents(tenant_id, id),
  add constraint telephony_phone_numbers_provisioning_status_check
    check (
      provisioning_status in (
        'discovered', 'import_pending', 'imported', 'purchase_pending',
        'purchase_failed', 'owned', 'provider_removed', 'suspended',
        'disabled', 'released', 'deleted'
      )
    ),
  add constraint telephony_phone_numbers_routing_status_check
    check (
      routing_status in (
        'not_configured', 'configuring', 'ready', 'degraded', 'failed',
        'disabled'
      )
    );

alter table livekit_inbound_trunks
  add constraint livekit_inbound_trunks_tenant_id_id_unique unique (tenant_id, id),
  add constraint livekit_inbound_trunks_phone_number_tenant_fk
    foreign key (tenant_id, phone_number_id)
    references telephony_phone_numbers(tenant_id, id),
  add constraint livekit_inbound_trunks_telnyx_connection_tenant_fk
    foreign key (tenant_id, telnyx_connection_id)
    references tenant_telnyx_connections(tenant_id, id),
  add constraint livekit_inbound_trunks_sip_connection_tenant_fk
    foreign key (tenant_id, telnyx_sip_connection_id)
    references telnyx_sip_connections(tenant_id, id),
  add constraint livekit_inbound_trunks_platform_status_check
    check (
      platform_status in (
        'draft', 'pending_verification', 'testing', 'active', 'failed',
        'disabled'
      )
    );

alter table livekit_outbound_trunks
  add constraint livekit_outbound_trunks_tenant_id_id_unique unique (tenant_id, id),
  add constraint livekit_outbound_trunks_telnyx_connection_tenant_fk
    foreign key (tenant_id, telnyx_connection_id)
    references tenant_telnyx_connections(tenant_id, id),
  add constraint livekit_outbound_trunks_sip_connection_tenant_fk
    foreign key (tenant_id, telnyx_sip_connection_id)
    references telnyx_sip_connections(tenant_id, id),
  add constraint livekit_outbound_trunks_voice_profile_tenant_fk
    foreign key (tenant_id, outbound_voice_profile_record_id)
    references telnyx_outbound_voice_profiles(tenant_id, id),
  add constraint livekit_outbound_trunks_platform_status_check
    check (
      platform_status in (
        'draft', 'pending_verification', 'testing', 'active', 'failed',
        'disabled'
      )
    );

alter table livekit_sip_dispatch_rules
  add constraint livekit_sip_dispatch_rules_tenant_id_id_unique unique (tenant_id, id),
  add constraint livekit_sip_dispatch_rules_phone_number_tenant_fk
    foreign key (tenant_id, phone_number_id)
    references telephony_phone_numbers(tenant_id, id),
  add constraint livekit_sip_dispatch_rules_inbound_trunk_tenant_fk
    foreign key (tenant_id, inbound_trunk_record_id)
    references livekit_inbound_trunks(tenant_id, id),
  add constraint livekit_sip_dispatch_rules_platform_status_check
    check (
      platform_status in (
        'draft', 'pending_verification', 'testing', 'active', 'failed',
        'disabled'
      )
    );

alter table telephony_number_orders
  add constraint telephony_number_orders_tenant_id_id_unique unique (tenant_id, id),
  add constraint telephony_number_orders_telnyx_connection_tenant_fk
    foreign key (tenant_id, telnyx_connection_id)
    references tenant_telnyx_connections(tenant_id, id),
  add constraint telephony_number_orders_idempotency_key_unique
    unique (tenant_id, idempotency_key),
  add constraint telephony_number_orders_provider_status_check
    check (
      provider_status is null
      or provider_status in ('pending', 'success', 'failure', 'cancelled', 'deleted')
    ),
  add constraint telephony_number_orders_platform_status_check
    check (
      platform_status in (
        'pending', 'purchased', 'configuring_routing', 'ready',
        'action_required', 'failed', 'cancelled', 'deleted'
      )
    );

alter table telephony_calls
  add constraint telephony_calls_tenant_id_id_unique unique (tenant_id, id),
  add constraint telephony_calls_session_tenant_fk
    foreign key (tenant_id, session_id)
    references sessions(tenant_id, id),
  add constraint telephony_calls_agent_tenant_fk
    foreign key (tenant_id, agent_id)
    references agents(tenant_id, id),
  add constraint telephony_calls_phone_number_tenant_fk
    foreign key (tenant_id, phone_number_id)
    references telephony_phone_numbers(tenant_id, id),
  add constraint telephony_calls_inbound_trunk_tenant_fk
    foreign key (tenant_id, inbound_trunk_record_id)
    references livekit_inbound_trunks(tenant_id, id),
  add constraint telephony_calls_outbound_trunk_tenant_fk
    foreign key (tenant_id, outbound_trunk_record_id)
    references livekit_outbound_trunks(tenant_id, id),
  add constraint telephony_calls_sip_dispatch_rule_tenant_fk
    foreign key (tenant_id, sip_dispatch_rule_record_id)
    references livekit_sip_dispatch_rules(tenant_id, id),
  add constraint telephony_calls_direction_check
    check (direction in ('inbound', 'outbound')),
  add constraint telephony_calls_platform_status_check
    check (
      platform_status in (
        'queued', 'dialing', 'ringing', 'in_progress', 'completed', 'busy',
        'no_answer', 'failed', 'cancelled'
      )
    );

alter table telephony_call_events
  add constraint telephony_call_events_telephony_call_tenant_fk
    foreign key (tenant_id, telephony_call_id)
    references telephony_calls(tenant_id, id);

alter table telephony_idempotency_keys
  add constraint telephony_idempotency_keys_pkey
    primary key (tenant_id, idempotency_key, action);

create unique index tenant_telnyx_connections_one_active_per_tenant_uidx
  on tenant_telnyx_connections (tenant_id)
  where platform_status in ('verifying', 'active', 'rotation_required');

create unique index telnyx_sip_connections_one_active_per_connection_uidx
  on telnyx_sip_connections (tenant_id, telnyx_connection_id)
  where disabled_at is null
    and platform_status in ('pending_verification', 'testing', 'active');

create unique index telephony_phone_numbers_one_active_e164_per_tenant_uidx
  on telephony_phone_numbers (tenant_id, e164_number)
  where disabled_at is null
    and provisioning_status not in ('released', 'deleted');

create unique index livekit_inbound_trunks_one_active_per_number_uidx
  on livekit_inbound_trunks (tenant_id, phone_number_id)
  where disabled_at is null
    and platform_status in ('pending_verification', 'testing', 'active');

create unique index livekit_outbound_trunks_one_active_per_connection_uidx
  on livekit_outbound_trunks (tenant_id, telnyx_connection_id)
  where disabled_at is null
    and platform_status in ('pending_verification', 'testing', 'active');

create unique index livekit_sip_dispatch_rules_one_active_per_number_uidx
  on livekit_sip_dispatch_rules (tenant_id, phone_number_id)
  where disabled_at is null
    and platform_status in ('pending_verification', 'testing', 'active');

create unique index telephony_call_events_provider_event_dedupe_uidx
  on telephony_call_events (source, provider_event_id)
  where provider_event_id is not null;

create index idx_tenant_telnyx_connections_status_verified
  on tenant_telnyx_connections (platform_status, last_verified_at);

create index idx_telnyx_sip_connections_status_verified
  on telnyx_sip_connections (platform_status, last_verified_at);

create index idx_telnyx_outbound_voice_profiles_status_verified
  on telnyx_outbound_voice_profiles (platform_status, last_verified_at);

create index idx_telephony_phone_numbers_e164_number
  on telephony_phone_numbers (e164_number);

create index idx_telephony_phone_numbers_assigned_agent_id
  on telephony_phone_numbers (assigned_agent_id)
  where assigned_agent_id is not null;

create index idx_telephony_phone_numbers_status_synced
  on telephony_phone_numbers (provisioning_status, routing_status, last_synced_at);

create index idx_livekit_inbound_trunks_provider_id
  on livekit_inbound_trunks (livekit_inbound_trunk_id)
  where livekit_inbound_trunk_id is not null;

create index idx_livekit_inbound_trunks_status_reconciled
  on livekit_inbound_trunks (platform_status, last_reconciled_at);

create index idx_livekit_outbound_trunks_provider_id
  on livekit_outbound_trunks (livekit_outbound_trunk_id)
  where livekit_outbound_trunk_id is not null;

create index idx_livekit_outbound_trunks_status_reconciled
  on livekit_outbound_trunks (platform_status, last_reconciled_at);

create index idx_livekit_sip_dispatch_rules_provider_id
  on livekit_sip_dispatch_rules (livekit_sip_dispatch_rule_id)
  where livekit_sip_dispatch_rule_id is not null;

create index idx_livekit_sip_dispatch_rules_status_reconciled
  on livekit_sip_dispatch_rules (platform_status, last_reconciled_at);

create index idx_telephony_number_orders_status_created
  on telephony_number_orders (platform_status, created_at);

create index idx_telephony_calls_room_name
  on telephony_calls (room_name)
  where room_name is not null;

create index idx_telephony_calls_livekit_sip_call_id
  on telephony_calls (livekit_sip_call_id)
  where livekit_sip_call_id is not null;

create index idx_telephony_calls_livekit_sip_call_id_full
  on telephony_calls (livekit_sip_call_id_full)
  where livekit_sip_call_id_full is not null;

create index idx_telephony_calls_platform_status
  on telephony_calls (platform_status);

create index idx_telephony_calls_created_at
  on telephony_calls (created_at);

create index idx_telephony_call_events_provider_event_id
  on telephony_call_events (provider_event_id)
  where provider_event_id is not null;

create index idx_telephony_call_events_tenant_created
  on telephony_call_events (tenant_id, created_at);

create index idx_telephony_audit_log_tenant_created
  on telephony_audit_log (tenant_id, created_at);
