"""Regression tests for Telnyx inventory sync and key rotation database behavior."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tenant_portal_api.telephony_credentials import decrypt_provider_secret, encrypt_provider_secret
from tenant_portal_api.telephony_errors import TelephonyError
from tenant_portal_api.telephony_service import TelephonyService

TENANT_A = "a4231868-2f06-426a-b9a5-1081e89554ec"
TENANT_B = "b5231868-2f06-426a-b9a5-1081e89554ec"
OLD_KEY = "KEY01_OLD_REAL_STYLE_SECRET_1234567890"
NEW_KEY = "KEY01_NEW_REAL_STYLE_SECRET_1234567890"
ENCRYPTION_KEY = "local-test-encryption-key-for-telephony-db-fixes"
PARTIAL_MIGRATION_PATH = Path("supabase/migrations/20260801185628_telephony_provider_number_identity.sql")
NORMAL_UNIQUE_MIGRATION_PATH = Path("supabase/migrations/20260801193716_telephony_provider_number_normal_unique.sql")


@pytest.fixture(autouse=True)
def real_provider_env(monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER_MODE", "real")
    monkeypatch.setenv("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY", ENCRYPTION_KEY)


class FakeCursor:
    def __init__(self, row: Any = None, rows: list[Any] | None = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class MutableTelnyxClient:
    def __init__(self, api_key: str, mock_mode: bool, inventory: list[dict[str, Any]], fail_verify: bool = False):
        self.api_key = api_key
        self.mock_mode = mock_mode
        self.inventory = inventory
        self.fail_verify = fail_verify

    def verify_api_key(self):
        if self.fail_verify:
            raise TelephonyError(status=401, code="telnyx_key_invalid", message="Invalid Telnyx API key.")
        return {
            "telnyx_account_id": "acct_real_123",
            "status": "active",
        }

    def list_owned_numbers(self, filter_phone_number: str | None = None):
        if filter_phone_number:
            return [item for item in self.inventory if item.get("e164_number") == filter_phone_number]
        return list(self.inventory)


class StatefulTelephonyDb:
    def __init__(self):
        self.connections: dict[str, dict[str, Any]] = {}
        self.numbers: list[dict[str, Any]] = []
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.last_sync_sql = ""
        self.connection_update_count = 0
        self.add_connection(TENANT_A, "conn_a", OLD_KEY)
        self.add_connection(TENANT_B, "conn_b", OLD_KEY)

    def add_connection(self, tenant_id: str, connection_id: str, api_key: str):
        self.connections[tenant_id] = {
            "id": connection_id,
            "tenant_id": tenant_id,
            "label": "primary",
            "platform_status": "active",
            "provider_status": "active",
            "key_fingerprint": hashlib.sha256(api_key.encode()).hexdigest()[:12],
            "telnyx_account_id": "acct_real_123",
            "last_verified_at": "2026-08-01T12:00:00Z",
            "permission_last_checked_at": "2026-08-01T12:00:00Z",
            "encrypted_api_key_ref": encrypt_provider_secret(api_key),
        }

    def active_connection_count(self, tenant_id: str) -> int:
        conn = self.connections.get(tenant_id)
        return int(bool(conn and conn["platform_status"] == "active"))

    def execute(self, query: str, params: tuple[Any, ...] = ()):  # noqa: C901 - compact SQL fake
        self.calls.append((query, params))
        sql = " ".join(query.lower().split())
        if "from tenant_telnyx_connections" in sql:
            return FakeCursor(row=self._connection_row(params[0]))
        if "update tenant_telnyx_connections" in sql:
            return self._update_connection(params)
        if "insert into telephony_phone_numbers" in sql:
            self.last_sync_sql = sql
            return self._upsert_number(params)
        raise AssertionError(f"Unexpected SQL: {query}")

    def _connection_row(self, tenant_id: str):
        conn = self.connections.get(tenant_id)
        if not conn or conn["platform_status"] not in {"verifying", "active", "rotation_required"}:
            return None
        return (
            conn["id"],
            conn["tenant_id"],
            conn["label"],
            conn["platform_status"],
            conn["provider_status"],
            conn["key_fingerprint"],
            conn["telnyx_account_id"],
            conn["last_verified_at"],
            conn["permission_last_checked_at"],
            conn["encrypted_api_key_ref"],
        )

    def _update_connection(self, params: tuple[Any, ...]):
        label, provider_status, fingerprint, encrypted_ref, account_id, tenant_id, connection_id = params
        conn = self.connections[tenant_id]
        if conn["id"] != connection_id:
            return FakeCursor(row=None)
        self.connection_update_count += 1
        conn.update(
            {
                "label": label or conn["label"],
                "platform_status": "active",
                "provider_status": provider_status or "active",
                "key_fingerprint": fingerprint,
                "encrypted_api_key_ref": encrypted_ref,
                "telnyx_account_id": account_id,
                "last_verified_at": "2026-08-01T13:00:00Z",
                "permission_last_checked_at": "2026-08-01T13:00:00Z",
            }
        )
        return FakeCursor(row=self._connection_row(tenant_id))

    def _upsert_number(self, params: tuple[Any, ...]):
        tenant_id, connection_id, provider_id, e164, country, number_type, features, provider_status = params
        existing = next(
            (
                number
                for number in self.numbers
                if provider_id is not None
                and number["tenant_id"] == tenant_id
                and number["provider_number_id"] == provider_id
            ),
            None,
        )
        if existing:
            if existing.get("disabled_at") or existing.get("provisioning_status") in {"released", "deleted"}:
                existing["provisioning_status"] = "owned"
                existing["routing_status"] = "not_configured"
            existing.update(
                {
                    "telnyx_connection_id": connection_id,
                    "e164_number": e164,
                    "country": country,
                    "number_type": number_type,
                    "features": features,
                    "provider_status": provider_status,
                    "disabled_at": None,
                }
            )
            return FakeCursor(row=self._number_row(existing))

        number = {
            "id": f"num_{len(self.numbers) + 1}",
            "tenant_id": tenant_id,
            "telnyx_connection_id": connection_id,
            "provider_number_id": provider_id,
            "e164_number": e164,
            "country": country,
            "number_type": number_type,
            "features": features,
            "provisioning_status": "owned",
            "routing_status": "not_configured",
            "provider_status": provider_status,
            "assigned_agent_id": None,
            "external_customer_ref": None,
            "disabled_at": None,
        }
        self.numbers.append(number)
        return FakeCursor(row=self._number_row(number))

    def _number_row(self, number: dict[str, Any]):
        return (
            number["id"],
            number["tenant_id"],
            number["provider_number_id"],
            number["e164_number"],
            number["country"],
            number["number_type"],
            number["features"],
            number["provisioning_status"],
            number["routing_status"],
            number["assigned_agent_id"],
            number["external_customer_ref"],
            number["disabled_at"],
        )


class ConflictTelephonyDb(StatefulTelephonyDb):
    def _upsert_number(self, params: tuple[Any, ...]):
        raise psycopg.errors.UniqueViolation("duplicate telephony number")


def inventory(provider_id: str = "pn_real_123", e164: str = "+14155550123") -> list[dict[str, Any]]:
    return [
        {
            "provider_number_id": provider_id,
            "e164_number": e164,
            "country": "US",
            "number_type": "local",
            "features": ["voice"],
            "status": "active",
        }
    ]


def service_for(db: StatefulTelephonyDb, items: list[dict[str, Any]], fail_verify: bool = False) -> TelephonyService:
    def factory(api_key: str, mock_mode: bool):
        return MutableTelnyxClient(api_key, mock_mode, items, fail_verify=fail_verify)

    return TelephonyService(db_conn=db, telnyx_client_factory=factory)


def test_previous_partial_provider_number_migration_is_unchanged():
    sql = PARTIAL_MIGRATION_PATH.read_text(encoding="utf-8").lower()

    assert "telephony_phone_numbers_provider_number_per_tenant_uidx" in sql
    assert "on telephony_phone_numbers (tenant_id, provider_number_id)" in sql
    assert "where provider_number_id is not null" in sql


def test_corrective_provider_number_normal_unique_migration_exists():
    sql = NORMAL_UNIQUE_MIGRATION_PATH.read_text(encoding="utf-8").lower()

    assert "having count(*) > 1" in sql
    assert "raise exception" in sql
    assert "drop index if exists telephony_phone_numbers_provider_number_per_tenant_uidx" in sql
    assert "telephony_phone_numbers_provider_number_per_tenant_key" in sql
    assert "unique (tenant_id, provider_number_id)" in sql
    assert "nulls not distinct" not in sql


def test_first_number_synchronization_creates_provider_identity_row():
    db = StatefulTelephonyDb()
    result = service_for(db, inventory()).sync_telnyx_owned_numbers(TENANT_A)

    assert result["synced_count"] == 1
    assert result["items"][0]["provider_number_id"] == "pn_real_123"
    assert len(db.numbers) == 1
    assert "on conflict (tenant_id, provider_number_id) do update set" in db.last_sync_sql
    assert "where provider_number_id is not null do update" not in db.last_sync_sql


def test_repeat_synchronization_updates_the_same_provider_number_row():
    db = StatefulTelephonyDb()
    service_for(db, inventory()).sync_telnyx_owned_numbers(TENANT_A)
    first_id = db.numbers[0]["id"]

    result = service_for(db, inventory(e164="+14155550124")).sync_telnyx_owned_numbers(TENANT_A)

    assert result["items"][0]["id"] == first_id
    assert result["items"][0]["e164_number"] == "+14155550124"
    assert len(db.numbers) == 1


def test_two_tenants_synchronize_separate_number_records():
    db = StatefulTelephonyDb()
    service_for(db, inventory()).sync_telnyx_owned_numbers(TENANT_A)
    service_for(db, inventory()).sync_telnyx_owned_numbers(TENANT_B)

    assert len(db.numbers) == 2
    assert {number["tenant_id"] for number in db.numbers} == {TENANT_A, TENANT_B}


def test_empty_provider_inventory_syncs_zero_numbers():
    db = StatefulTelephonyDb()
    result = service_for(db, []).sync_telnyx_owned_numbers(TENANT_A)

    assert result == {"tenant_id": TENANT_A, "synced_count": 0, "drift_count": 0, "items": []}
    assert db.numbers == []


def test_stateful_normal_unique_model_allows_multiple_null_provider_ids():
    db = StatefulTelephonyDb()

    first = db._upsert_number((TENANT_A, "conn_a", None, "+14155550130", "US", "local", ["voice"], "active")).fetchone()
    second = db._upsert_number((TENANT_A, "conn_a", None, "+14155550131", "US", "local", ["voice"], "active")).fetchone()

    assert first[0] != second[0]
    assert len([number for number in db.numbers if number["provider_number_id"] is None]) == 2

def test_existing_disabled_number_becomes_synchronized_again():
    db = StatefulTelephonyDb()
    db.numbers.append(
        {
            "id": "num_existing",
            "tenant_id": TENANT_A,
            "telnyx_connection_id": "conn_a",
            "provider_number_id": "pn_real_123",
            "e164_number": "+14155550123",
            "country": "US",
            "number_type": "local",
            "features": ["voice"],
            "provisioning_status": "released",
            "routing_status": "not_configured",
            "provider_status": "deleted",
            "assigned_agent_id": None,
            "external_customer_ref": None,
            "disabled_at": "2026-08-01T00:00:00Z",
        }
    )

    result = service_for(db, inventory()).sync_telnyx_owned_numbers(TENANT_A)

    assert result["items"][0]["id"] == "num_existing"
    assert result["items"][0]["provisioning_status"] == "owned"
    assert result["items"][0]["disabled_at"] is None
    assert len(db.numbers) == 1


def test_successful_active_connection_key_rotation_preserves_row_and_redacts_secret(caplog):
    db = StatefulTelephonyDb()
    service = service_for(db, [])

    response = service.rotate_telnyx_account_key(TENANT_A, NEW_KEY)

    assert response["id"] == "conn_a"
    assert response["platform_status"] == "active"
    assert response["key_fingerprint"] == hashlib.sha256(NEW_KEY.encode()).hexdigest()[:12]
    assert decrypt_provider_secret(db.connections[TENANT_A]["encrypted_api_key_ref"]) == NEW_KEY
    assert db.active_connection_count(TENANT_A) == 1
    assert NEW_KEY not in json.dumps(response, default=str)
    assert all(NEW_KEY not in record.getMessage() for record in caplog.records)


def test_failed_new_key_verification_preserves_old_credential():
    db = StatefulTelephonyDb()
    service = service_for(db, [], fail_verify=True)

    with pytest.raises(TelephonyError) as exc_info:
        service.rotate_telnyx_account_key(TENANT_A, NEW_KEY)

    assert exc_info.value.code == "telnyx_key_invalid"
    assert db.connection_update_count == 0
    assert decrypt_provider_secret(db.connections[TENANT_A]["encrypted_api_key_ref"]) == OLD_KEY


def test_repeated_rotation_with_same_key_is_safe_and_keeps_one_active_connection():
    db = StatefulTelephonyDb()
    service = service_for(db, [])

    first = service.rotate_telnyx_account_key(TENANT_A, NEW_KEY)
    second = service.rotate_telnyx_account_key(TENANT_A, NEW_KEY)

    assert first["id"] == second["id"] == "conn_a"
    assert first["key_fingerprint"] == second["key_fingerprint"]
    assert db.active_connection_count(TENANT_A) == 1
    assert db.connection_update_count == 2


def test_number_sync_database_conflict_maps_to_stable_platform_error():
    db = ConflictTelephonyDb()
    service = service_for(db, inventory())

    with pytest.raises(TelephonyError) as exc_info:
        service.sync_telnyx_owned_numbers(TENANT_A)

    assert exc_info.value.status == 409
    assert exc_info.value.code == "call_state_conflict"
    assert OLD_KEY not in exc_info.value.message
    assert NEW_KEY not in exc_info.value.message


def _postgres_conn_kwargs_or_skip():
    try:
        from scripts.dbconn import conn_kwargs

        return conn_kwargs()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"SUPABASE_DB_URL not configured for real PostgreSQL constraint check: {exc}")


def test_provider_number_unique_constraint_works_against_real_postgres_schema():
    kwargs = _postgres_conn_kwargs_or_skip()
    try:
        conn = psycopg.connect(**kwargs, connect_timeout=10, autocommit=True, prepare_threshold=None)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL connection not available for constraint check: {exc}")

    with conn:
        conn.execute("drop table if exists pg_temp.telephony_provider_unique_test")
        conn.execute(
            """
            create temporary table telephony_provider_unique_test (
                id text primary key,
                tenant_id uuid not null,
                provider_number_id text,
                e164_number text not null,
                provisioning_status text not null default 'owned',
                routing_status text not null default 'not_configured',
                disabled_at timestamptz,
                updated_at timestamptz not null default now()
            ) on commit preserve rows
            """
        )
        conn.execute(
            """
            alter table telephony_provider_unique_test
              add constraint telephony_provider_unique_test_provider_key
              unique (tenant_id, provider_number_id)
            """
        )

        conn.execute(
            """
            insert into telephony_provider_unique_test (id, tenant_id, provider_number_id, e164_number)
            values (%s, %s, null, %s), (%s, %s, null, %s)
            """,
            ("null_1", TENANT_A, "+14155550140", "null_2", TENANT_A, "+14155550141"),
        )
        null_count = conn.execute(
            """
            select count(*)
            from telephony_provider_unique_test
            where tenant_id = %s and provider_number_id is null
            """,
            (TENANT_A,),
        ).fetchone()[0]
        assert null_count == 2

        conn.execute(
            """
            insert into telephony_provider_unique_test (id, tenant_id, provider_number_id, e164_number)
            values (%s, %s, %s, %s)
            """,
            ("provider_a_1", TENANT_A, "pn_shared_real", "+14155550142"),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(
                """
                insert into telephony_provider_unique_test (id, tenant_id, provider_number_id, e164_number)
                values (%s, %s, %s, %s)
                """,
                ("provider_a_2", TENANT_A, "pn_shared_real", "+14155550143"),
            )
        conn.rollback()

        conn.execute(
            """
            insert into telephony_provider_unique_test (id, tenant_id, provider_number_id, e164_number)
            values (%s, %s, %s, %s)
            """,
            ("provider_b_1", TENANT_B, "pn_shared_real", "+14155550144"),
        )

        conn.execute(
            """
            insert into telephony_provider_unique_test (
                id, tenant_id, provider_number_id, e164_number, provisioning_status, disabled_at
            ) values (%s, %s, %s, %s, 'released', now())
            """,
            ("released_original", TENANT_A, "pn_reactivated_real", "+14155550145"),
        )
        reactivated = conn.execute(
            """
            insert into telephony_provider_unique_test (
                id, tenant_id, provider_number_id, e164_number, provisioning_status, routing_status, disabled_at
            ) values (%s, %s, %s, %s, 'owned', 'not_configured', null)
            on conflict (tenant_id, provider_number_id) do update set
                e164_number = excluded.e164_number,
                provisioning_status = case
                    when telephony_provider_unique_test.disabled_at is not null
                      or telephony_provider_unique_test.provisioning_status in ('released', 'deleted')
                    then excluded.provisioning_status
                    else telephony_provider_unique_test.provisioning_status
                end,
                routing_status = case
                    when telephony_provider_unique_test.disabled_at is not null
                    then excluded.routing_status
                    else telephony_provider_unique_test.routing_status
                end,
                disabled_at = null,
                updated_at = now()
            returning id, e164_number, provisioning_status, disabled_at
            """,
            ("released_duplicate", TENANT_A, "pn_reactivated_real", "+14155550146"),
        ).fetchone()

        assert reactivated == ("released_original", "+14155550146", "owned", None)
