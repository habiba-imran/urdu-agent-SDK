import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "supabase" / "migrations" / "0014_telephony_data_governance_audit.sql"
)

GOVERNED_TABLES = [
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

GOVERNANCE_COLUMNS = [
    "retention_until",
    "deletion_requested_at",
    "deleted_at",
    "offboarded_at",
    "redacted_at",
    "redaction_reason",
]


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", _sql())


def _alter_body(table: str) -> str:
    match = re.search(rf"alter table {table}\s+(.*?);", _sql(), re.DOTALL)
    assert match, f"{table} alter table block not found"
    return match.group(1)


def test_data_governance_migration_stays_in_scope():
    sql = _normalized_sql()

    assert MIGRATION.exists()
    assert "0015_" not in sql
    assert "enable row level security" not in sql
    assert "create policy" not in sql
    assert not re.search(r"\bgrant\b", sql)
    assert "insert into" not in sql
    assert "create table" not in sql


def test_governed_tables_receive_lifecycle_fields():
    for table in GOVERNED_TABLES:
        body = _alter_body(table)
        for column in GOVERNANCE_COLUMNS:
            assert f"add column {column}" in body, f"{table} missing {column}"


def test_restricted_diagnostic_payload_metadata_is_explicit():
    sql = _normalized_sql()
    orders = _alter_body("telephony_number_orders")
    events = _alter_body("telephony_call_events")

    assert (
        "provider_error_payload_access_scope text not null default 'restricted_diagnostic'"
        in orders
    )
    assert "provider_error_payload_redacted_at timestamptz" in orders
    assert "provider_error_payload_redaction_reason text" in orders
    assert "telephony_number_orders_provider_error_payload_access_scope_check" in orders
    assert (
        "payload_access_scope text not null default 'restricted_diagnostic'" in events
    )
    assert "payload_redacted_at timestamptz" in events
    assert "payload_redaction_reason text" in events
    assert "telephony_call_events_payload_access_scope_check" in events
    assert "comment on column telephony_number_orders.provider_error_payload" in sql
    assert "comment on column telephony_call_events.payload" in sql
    assert "add column payload jsonb" not in sql


def test_audit_log_supports_access_export_and_redaction_metadata():
    body = _alter_body("telephony_audit_log")
    sql = _normalized_sql()

    for column in ["request_id", "access_reason", "export_id"]:
        assert f"add column {column} text" in body
    assert "add column restricted_target boolean not null default false" in body
    assert "add column detail_redacted_at timestamptz" in body
    assert "add column detail_redaction_reason text" in body
    assert "comment on column telephony_audit_log.detail" in sql
    assert "restricted-payload access" in sql


def test_no_sample_payloads_numbers_or_credentials_are_added():
    sql = _sql()

    assert not re.search(r"\+\d{7,}", sql)
    assert not re.search(r"\b(api_key|sip_secret|password|token)\b", sql)
    assert not re.search(r"sk_[a-z0-9_]{8,}", sql)
