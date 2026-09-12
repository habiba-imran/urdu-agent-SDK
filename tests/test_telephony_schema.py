import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "0012_telephony_core_tables.sql"
PHASE4_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "0013_telephony_constraints_indexes_status_idempotency.sql"
)

TELEPHONY_TABLES = [
    "tenant_telnyx_connections",
    "telnyx_sip_connections",
    "telnyx_outbound_voice_profiles",
    "telephony_phone_numbers",
    "livekit_inbound_trunks",
    "livekit_outbound_trunks",
    "livekit_sip_dispatch_rules",
    "telephony_number_orders",
    "telephony_calls",
    "telephony_call_events",
    "telephony_idempotency_keys",
    "telephony_audit_log",
]

REQUIRED_COLUMNS = {
    "tenant_telnyx_connections": {
        "id",
        "tenant_id",
        "platform_status",
        "provider_status",
        "encrypted_api_key_ref",
        "key_fingerprint",
        "telnyx_account_id",
        "created_at",
        "updated_at",
    },
    "telnyx_sip_connections": {
        "id",
        "tenant_id",
        "telnyx_connection_id",
        "provider_sip_connection_id",
        "sip_fqdn",
        "sip_username",
        "encrypted_sip_secret_ref",
        "platform_status",
        "provider_status",
    },
    "telnyx_outbound_voice_profiles": {
        "id",
        "tenant_id",
        "telnyx_connection_id",
        "telnyx_sip_connection_id",
        "provider_outbound_voice_profile_id",
        "platform_status",
        "provider_status",
        "allowed_destinations",
    },
    "telephony_phone_numbers": {
        "id",
        "tenant_id",
        "telnyx_connection_id",
        "telnyx_sip_connection_id",
        "provider_number_id",
        "e164_number",
        "provisioning_status",
        "routing_status",
        "assigned_agent_id",
        "external_customer_ref",
    },
    "livekit_inbound_trunks": {
        "id",
        "tenant_id",
        "phone_number_id",
        "telnyx_connection_id",
        "telnyx_sip_connection_id",
        "livekit_inbound_trunk_id",
        "platform_status",
        "provider_status",
    },
    "livekit_outbound_trunks": {
        "id",
        "tenant_id",
        "telnyx_connection_id",
        "telnyx_sip_connection_id",
        "outbound_voice_profile_record_id",
        "livekit_outbound_trunk_id",
        "platform_status",
        "provider_status",
    },
    "livekit_sip_dispatch_rules": {
        "id",
        "tenant_id",
        "phone_number_id",
        "inbound_trunk_record_id",
        "livekit_sip_dispatch_rule_id",
        "platform_status",
        "provider_status",
    },
    "telephony_number_orders": {
        "id",
        "tenant_id",
        "telnyx_connection_id",
        "idempotency_key",
        "provider_order_id",
        "selected_e164_number",
        "platform_status",
        "provider_status",
        "provider_error_payload",
    },
    "telephony_calls": {
        "id",
        "tenant_id",
        "session_id",
        "agent_id",
        "phone_number_id",
        "direction",
        "room_name",
        "call_context",
        "external_customer_ref",
        "external_workflow_ref",
        "inbound_trunk_record_id",
        "outbound_trunk_record_id",
        "sip_dispatch_rule_record_id",
        "livekit_sip_call_id",
        "livekit_sip_call_id_full",
        "platform_status",
    },
    "telephony_call_events": {
        "id",
        "tenant_id",
        "telephony_call_id",
        "source",
        "event_type",
        "provider_event_id",
        "internal_stage",
        "payload",
        "created_at",
    },
    "telephony_idempotency_keys": {
        "tenant_id",
        "idempotency_key",
        "action",
        "request_hash",
        "response_body",
        "platform_status",
        "created_at",
        "completed_at",
    },
    "telephony_audit_log": {
        "id",
        "tenant_id",
        "actor_type",
        "actor_id",
        "action",
        "target_type",
        "target_id",
        "detail",
        "created_at",
    },
}


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _phase4_sql() -> str:
    return re.sub(r"\s+", " ", PHASE4_MIGRATION.read_text(encoding="utf-8").lower())


def _table_body(table: str) -> str:
    pattern = rf"create table if not exists {table}\s*\((.*?)\n\);"
    match = re.search(pattern, _sql(), flags=re.IGNORECASE | re.DOTALL)
    assert match, f"{table} create table block not found"
    return match.group(1).lower()


def _has_column(table: str, column: str) -> bool:
    return re.search(rf"^\s*{column}\b", _table_body(table), re.MULTILINE) is not None


def test_phase3_migration_creates_only_reserved_core_tables():
    sql = _sql().lower()

    assert "0012_telephony_core_tables.sql" in MIGRATION.name
    assert "usage_events" not in sql
    assert "p2f" not in sql
    assert "enable row level security" not in sql
    assert not re.search(r"\bgrant\b", sql)
    assert "create index" not in sql
    assert "create unique" not in sql

    for table in TELEPHONY_TABLES:
        assert f"create table if not exists {table}" in sql


def test_phase4_migration_adds_constraints_indexes_without_phase5_scope():
    sql = _phase4_sql()
    required = [
        "add constraint agents_tenant_id_id_unique unique (tenant_id, id)",
        "add constraint sessions_tenant_id_id_unique unique (tenant_id, id)",
        "foreign key (tenant_id, assigned_agent_id) references agents(tenant_id, id)",
        "foreign key (tenant_id, session_id) references sessions(tenant_id, id)",
        "foreign key (tenant_id, inbound_trunk_record_id) references livekit_inbound_trunks(tenant_id, id)",
        "foreign key (tenant_id, sip_dispatch_rule_record_id) references livekit_sip_dispatch_rules(tenant_id, id)",
        "add constraint telephony_number_orders_idempotency_key_unique unique (tenant_id, idempotency_key)",
        "add constraint telephony_idempotency_keys_pkey primary key (tenant_id, idempotency_key, action)",
        "create unique index telephony_call_events_provider_event_dedupe_uidx",
        "create unique index tenant_telnyx_connections_one_active_per_tenant_uidx",
        "create unique index telnyx_sip_connections_one_active_per_connection_uidx",
        "create unique index telephony_phone_numbers_one_active_e164_per_tenant_uidx",
        "create unique index livekit_inbound_trunks_one_active_per_number_uidx",
        "create unique index livekit_outbound_trunks_one_active_per_connection_uidx",
        "create unique index livekit_sip_dispatch_rules_one_active_per_number_uidx",
        "create index idx_telephony_phone_numbers_e164_number",
        "create index idx_telephony_phone_numbers_assigned_agent_id",
        "create index idx_livekit_inbound_trunks_provider_id",
        "create index idx_livekit_outbound_trunks_provider_id",
        "create index idx_livekit_sip_dispatch_rules_provider_id",
        "create index idx_telephony_calls_room_name",
        "create index idx_telephony_calls_livekit_sip_call_id",
        "create index idx_telephony_calls_livekit_sip_call_id_full",
        "create index idx_telephony_calls_platform_status",
        "create index idx_telephony_calls_created_at",
        "create index idx_telephony_call_events_provider_event_id",
    ]
    status_checks = "tenant_telnyx_connections_platform_status_check telnyx_sip_connections_platform_status_check telnyx_outbound_voice_profiles_platform_status_check telephony_phone_numbers_provisioning_status_check telephony_phone_numbers_routing_status_check telephony_number_orders_provider_status_check telephony_number_orders_platform_status_check telephony_calls_direction_check telephony_calls_platform_status_check".split()

    assert PHASE4_MIGRATION.exists()
    assert not re.search(r"\bgrant\b", sql)
    for snippet in ["0014_", "0015_", "enable row level security", "usage_events"]:
        assert snippet not in sql
    for snippet in required + status_checks:
        assert snippet in sql


def test_every_tenant_owned_telephony_table_has_tenant_id():
    for table in TELEPHONY_TABLES:
        assert _has_column(table, "tenant_id"), f"{table} missing tenant_id"
        assert (
            "tenant_id uuid not null references tenants(id) on delete cascade"
            in _table_body(table)
        )


def test_required_phase3_columns_exist():
    for table, columns in REQUIRED_COLUMNS.items():
        for column in columns:
            assert _has_column(table, column), f"{table} missing {column}"


def test_base_foreign_key_relationships_exist():
    assert (
        "telnyx_connection_id uuid not null references tenant_telnyx_connections(id)"
        in _table_body("telnyx_sip_connections")
    )
    assert (
        "telnyx_sip_connection_id uuid references telnyx_sip_connections(id)"
        in _table_body("telnyx_outbound_voice_profiles")
    )
    assert (
        "assigned_agent_id uuid references agents(id) on delete set null"
        in _table_body("telephony_phone_numbers")
    )
    assert (
        "phone_number_id uuid not null references telephony_phone_numbers(id)"
        in _table_body("livekit_inbound_trunks")
    )
    assert (
        "outbound_voice_profile_record_id uuid not null references telnyx_outbound_voice_profiles(id)"
        in _table_body("livekit_outbound_trunks")
    )
    assert (
        "inbound_trunk_record_id uuid not null references livekit_inbound_trunks(id)"
        in _table_body("livekit_sip_dispatch_rules")
    )
    assert "session_id uuid references sessions(id) on delete set null" in _table_body(
        "telephony_calls"
    )
    assert (
        "telephony_call_id uuid not null references telephony_calls(id)"
        in _table_body("telephony_call_events")
    )


def test_telephony_calls_uses_internal_trunk_rule_references_only():
    body = _table_body("telephony_calls")

    assert "inbound_trunk_record_id uuid references livekit_inbound_trunks(id)" in body
    assert (
        "outbound_trunk_record_id uuid references livekit_outbound_trunks(id)" in body
    )
    assert (
        "sip_dispatch_rule_record_id uuid references livekit_sip_dispatch_rules(id)"
        in body
    )
    assert not re.search(r"^\s*livekit_inbound_trunk_id\b", body, re.MULTILINE)
    assert not re.search(r"^\s*livekit_outbound_trunk_id\b", body, re.MULTILINE)
    assert not re.search(r"^\s*livekit_sip_dispatch_rule_id\b", body, re.MULTILINE)


def test_external_refs_are_opaque_text_fields():
    calls = _table_body("telephony_calls")

    assert re.search(r"^\s*external_customer_ref text\b", calls, re.MULTILINE)
    assert re.search(r"^\s*external_workflow_ref text\b", calls, re.MULTILINE)


def test_raw_provider_credentials_are_not_plaintext_columns():
    sql = _sql().lower()

    assert not re.search(r"^\s*api_key\s+text\b", sql, re.MULTILINE)
    assert not re.search(r"^\s*sip_secret\s+text\b", sql, re.MULTILINE)
    assert not re.search(r"^\s*encrypted_api_key_ciphertext\b", sql, re.MULTILINE)
    assert not re.search(r"^\s*encrypted_sip_secret_ciphertext\b", sql, re.MULTILINE)
