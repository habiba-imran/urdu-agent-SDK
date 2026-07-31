import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "0015_telephony_rls_grants.sql"

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

RESTRICTED_COLUMNS = [
    "encrypted_api_key_ref",
    "encrypted_sip_secret_ref",
    "raw_provider_status",
    "provider_error_payload",
    "provider_error_payload_access_scope",
    "provider_error_payload_redacted_at",
    "provider_error_payload_redaction_reason",
    "raw_livekit_sip_participant_status",
    "call_context",
    "payload",
    "payload_access_scope",
    "payload_redacted_at",
    "payload_redaction_reason",
    "request_hash",
    "response_body",
    "detail",
    "restricted_target",
    "detail_redacted_at",
    "detail_redaction_reason",
]


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", _sql())


def _grant_select_blocks() -> list[str]:
    return re.findall(r"grant select \((.*?)\) on ([a-z_]+) to authenticated;", _sql(), re.DOTALL)


def test_rls_is_enabled_for_all_telephony_tables():
    sql = _normalized_sql()

    assert MIGRATION.exists()
    for table in TELEPHONY_TABLES:
        assert f"alter table {table} enable row level security;" in sql


def test_authenticated_policies_are_tenant_scoped_and_not_broad():
    sql = _normalized_sql()
    tenant_check = "tenant_id = (auth.jwt() ->> 'tenant_id')::uuid"

    assert "security definer" not in sql
    assert "using (true)" not in sql
    assert "with check (true)" not in sql
    assert "for all to authenticated" not in sql
    assert "to anon" not in sql
    for table in TELEPHONY_TABLES:
        assert f"on {table} for select to authenticated using ({tenant_check})" in sql
        assert f"on {table} for insert to authenticated with check ({tenant_check})" in sql
        assert f"on {table} for update to authenticated using ({tenant_check}) with check ({tenant_check})" in sql


def test_no_anon_or_broad_authenticated_grants_exist():
    sql = _normalized_sql()

    assert "revoke all on table" in sql
    assert "from public, anon, authenticated" in sql
    assert not re.search(r"\bgrant\b[^;]*\bto\s+anon\b", sql)
    assert not re.search(r"\bgrant\s+all\b", sql)
    assert not re.search(r"\bgrant\s+select\s+on\b", sql)
    assert not re.search(r"\bgrant\s+(insert|update|delete)\b", sql)


def test_restricted_columns_are_not_granted_to_authenticated():
    blocks = _grant_select_blocks()
    granted_text = " ".join(columns for columns, _table in blocks)
    granted_tables = {table for _columns, table in blocks}

    assert granted_tables == {
        "tenant_telnyx_connections",
        "telnyx_sip_connections",
        "telnyx_outbound_voice_profiles",
        "telephony_phone_numbers",
        "livekit_inbound_trunks",
        "livekit_outbound_trunks",
        "livekit_sip_dispatch_rules",
        "telephony_number_orders",
        "telephony_calls",
    }
    for column in RESTRICTED_COLUMNS:
        assert not re.search(rf"\b{column}\b", granted_text), f"{column} was granted"


def test_migration_does_not_add_out_of_scope_artifacts():
    sql = _normalized_sql()

    assert "0016_" not in sql
    assert "create table" not in sql
    assert "create function" not in sql
    assert "tenant_portal_api" not in sql
    assert "dashboard" not in sql
    assert "sdk" not in sql
