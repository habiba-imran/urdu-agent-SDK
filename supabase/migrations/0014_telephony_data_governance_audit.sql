-- 0014_telephony_data_governance_audit.sql -- Habiba data governance slice.
-- Scope: lifecycle, redaction, restricted diagnostic metadata, and audit metadata.
-- RLS and role access policy work remains reserved for a later migration.

alter table tenant_telnyx_connections
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text;

alter table telnyx_sip_connections
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text;

alter table telnyx_outbound_voice_profiles
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text;

alter table telephony_phone_numbers
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text;

alter table livekit_inbound_trunks
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text;

alter table livekit_outbound_trunks
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text;

alter table livekit_sip_dispatch_rules
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text;

alter table telephony_number_orders
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text,
  add column provider_error_payload_access_scope text not null default 'restricted_diagnostic',
  add column provider_error_payload_redacted_at timestamptz,
  add column provider_error_payload_redaction_reason text,
  add constraint telephony_number_orders_provider_error_payload_access_scope_check
    check (provider_error_payload_access_scope in ('restricted_diagnostic', 'redacted'));

alter table telephony_calls
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text,
  add column export_requested_at timestamptz,
  add column export_completed_at timestamptz,
  add column last_access_audited_at timestamptz;

alter table telephony_call_events
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text,
  add column payload_access_scope text not null default 'restricted_diagnostic',
  add column payload_redacted_at timestamptz,
  add column payload_redaction_reason text,
  add constraint telephony_call_events_payload_access_scope_check
    check (payload_access_scope in ('restricted_diagnostic', 'redacted'));

alter table telephony_idempotency_keys
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text;

alter table telephony_audit_log
  add column retention_until timestamptz,
  add column deletion_requested_at timestamptz,
  add column deleted_at timestamptz,
  add column offboarded_at timestamptz,
  add column redacted_at timestamptz,
  add column redaction_reason text,
  add column request_id text,
  add column access_reason text,
  add column export_id text,
  add column restricted_target boolean not null default false,
  add column detail_redacted_at timestamptz,
  add column detail_redaction_reason text;

comment on column telephony_number_orders.provider_error_payload is
  'Restricted diagnostics only. Do not expose raw provider payloads in tenant-facing responses.';

comment on column telephony_call_events.payload is
  'Restricted diagnostics only. Do not expose raw provider payloads in tenant-facing responses.';

comment on column telephony_audit_log.detail is
  'Audit detail metadata only. Redact provider payloads and credential material before storage.';

comment on column telephony_audit_log.action is
  'Audit credential changes, number purchases/imports, assignments, SIP changes, outbound calls, number disconnections, transcript access, call-record access, exports, and restricted-payload access.';
