"""Regression tests for explicit real-provider telephony wiring.

These tests avoid live Telnyx/LiveKit calls. They prove staging/production mode
uses stored tenant credentials and fails closed instead of returning synthetic
provider resources.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from tenant_portal_api.livekit_sip import LiveKitSipClient
from tenant_portal_api.telephony_credentials import encrypt_provider_secret
from tenant_portal_api.telephony_errors import TelephonyError
from tenant_portal_api.telephony_service import TelephonyService
import tenant_portal_api.telephony_webhooks as telephony_webhooks

TENANT_ID = "a4231868-2f06-426a-b9a5-1081e89554ec"
RAW_TELNYX_KEY = "KEY01_REAL_STYLE_TEST_SECRET_1234567890"
ENCRYPTION_KEY = "local-test-encryption-key-for-telephony-real-mode"


@pytest.fixture(autouse=True)
def real_provider_env(monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER_MODE", "real")
    monkeypatch.setenv("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY", ENCRYPTION_KEY)
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    monkeypatch.delenv("TELNYX_PUBLIC_KEY", raising=False)
    telephony_webhooks._seen_webhook_signatures.clear()
    telephony_webhooks._seen_webhook_event_ids.clear()


class FakeCursor:
    def __init__(self, row: Any = None, rows: list[Any] | None = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class ActiveConnectionDb:
    def __init__(self, encrypted_ref: str | None):
        self.encrypted_ref = encrypted_ref
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.numbers: dict[str, tuple[Any, ...]] = {}

    def active_row(self):
        return (
            "conn_real_123",
            TENANT_ID,
            "Primary Telnyx",
            "active",
            "active",
            "fingerprint_123",
            "acct_real_123",
            "2026-08-01T12:00:00Z",
            "2026-08-01T12:00:00Z",
            self.encrypted_ref,
        )

    def execute(self, query: str, params: tuple[Any, ...] = ()):
        self.calls.append((query, params))
        sql = " ".join(query.lower().split())
        if "from tenant_telnyx_connections" in sql:
            return FakeCursor(row=self.active_row())
        if "update telephony_phone_numbers" in sql:
            return FakeCursor(row=None)
        if "insert into telephony_phone_numbers" in sql:
            row = (
                "num_real_123",
                params[0],
                params[2],
                params[3],
                params[4],
                params[5],
                params[6] if not isinstance(params[6], str) else json.loads(params[6]),
                "owned",
                "not_configured",
                None,
                None,
                None,
            )
            self.numbers["num_real_123"] = row
            return FakeCursor(row=("num_real_123",))
        if "from telephony_phone_numbers" in sql:
            return FakeCursor(row=self.numbers.get(params[1]))
        raise AssertionError(f"Unexpected SQL: {query}")


class ConnectWriteDb(ActiveConnectionDb):
    def __init__(self):
        super().__init__(encrypted_ref=None)
        self.stored_encrypted_ref: str | None = None

    def execute(self, query: str, params: tuple[Any, ...] = ()):
        self.calls.append((query, params))
        sql = " ".join(query.lower().split())
        if (
            "from tenant_telnyx_connections" in sql
            and self.stored_encrypted_ref is None
        ):
            return FakeCursor(row=None)
        if "insert into tenant_telnyx_connections" in sql:
            self.stored_encrypted_ref = params[3]
            self.encrypted_ref = self.stored_encrypted_ref
            return FakeCursor(
                row=(
                    "conn_real_123",
                    params[0],
                    params[1],
                    "verifying",
                    params[2],
                    "2026-08-01T12:00:00Z",
                )
            )
        if "update tenant_telnyx_connections" in sql:
            return FakeCursor()
        return super().execute(query, params)


class RoutingDb(ActiveConnectionDb):
    def __init__(self):
        super().__init__(encrypted_ref=encrypt_provider_secret(RAW_TELNYX_KEY))
        self.updated_number = False

    def execute(self, query: str, params: tuple[Any, ...] = ()):
        self.calls.append((query, params))
        sql = " ".join(query.lower().split())
        if "from telephony_phone_numbers" in sql:
            return FakeCursor(
                row=(
                    "num_real_123",
                    TENANT_ID,
                    "pn_real_123",
                    "+14155550123",
                    "US",
                    "local",
                    ["voice"],
                    "owned",
                    "not_configured",
                    None,
                    None,
                    None,
                )
            )
        if "from tenant_telnyx_connections" in sql:
            return FakeCursor(row=self.active_row())
        if "from telnyx_sip_connections" in sql:
            return FakeCursor(
                row=(
                    "sip_real_123",
                    TENANT_ID,
                    "conn_real_123",
                    "fqdn_real_123",
                    "sip.telnyx.example",
                    "sip-user",
                    "active",
                    "active",
                    "2026-08-01T12:00:00Z",
                )
            )
        if "from livekit_inbound_trunks" in sql:
            return FakeCursor(row=None)
        if "insert into livekit_inbound_trunks" in sql:
            return FakeCursor(
                row=(
                    "trunk_record_123",
                    TENANT_ID,
                    "num_real_123",
                    params[4],
                    "active",
                    params[5],
                )
            )
        if "from livekit_sip_dispatch_rules" in sql:
            return FakeCursor(row=None)
        if "insert into livekit_sip_dispatch_rules" in sql:
            return FakeCursor(
                row=(
                    "rule_record_123",
                    TENANT_ID,
                    "num_real_123",
                    params[3],
                    "active",
                    params[4],
                )
            )
        if "update telephony_phone_numbers" in sql:
            self.updated_number = True
            return FakeCursor()
        raise AssertionError(f"Unexpected SQL: {query}")


class FakeTelnyxClient:
    def __init__(self, api_key: str, mock_mode: bool):
        self.api_key = api_key
        self.mock_mode = mock_mode

    def verify_api_key(self):
        return {
            "telnyx_account_id": "acct_real_123",
            "verification_record_type": "balance",
            "status": "active",
        }

    def list_owned_numbers(self, filter_phone_number: str | None = None):
        items = [
            {
                "provider_number_id": "pn_real_123",
                "e164_number": "+14155550123",
                "country": "US",
                "number_type": "local",
                "features": ["voice"],
                "status": "active",
            }
        ]
        if filter_phone_number:
            return [
                item for item in items if item["e164_number"] == filter_phone_number
            ]
        return items


class FakeLiveKitClient:
    def __init__(self, mock_mode: bool):
        self.mock_mode = mock_mode
        self.inbound_calls: list[tuple[str, str]] = []
        self.rule_calls: list[tuple[str, str, str]] = []

    def create_or_get_inbound_trunk(self, phone_number_id: str, e164_number: str):
        self.inbound_calls.append((phone_number_id, e164_number))
        return {"livekit_inbound_trunk_id": "lk_tr_in_real_123", "status": "active"}

    def create_or_get_dispatch_rule(
        self, inbound_trunk_id: str, phone_number_id: str, e164_number: str
    ):
        self.rule_calls.append((inbound_trunk_id, phone_number_id, e164_number))
        return {"livekit_sip_dispatch_rule_id": "lk_rule_real_123", "status": "active"}


def test_service_uses_stored_tenant_credential_for_real_telnyx_inventory():
    encrypted_ref = encrypt_provider_secret(RAW_TELNYX_KEY)
    captured: dict[str, Any] = {}

    def factory(api_key: str, mock_mode: bool):
        captured["api_key"] = api_key
        captured["mock_mode"] = mock_mode
        return FakeTelnyxClient(api_key, mock_mode)

    service = TelephonyService(
        db_conn=ActiveConnectionDb(encrypted_ref), telnyx_client_factory=factory
    )
    numbers = service.list_telnyx_owned_numbers(TENANT_ID)

    assert captured == {"api_key": RAW_TELNYX_KEY, "mock_mode": False}
    assert numbers[0]["provider_number_id"] == "pn_real_123"
    assert not numbers[0]["provider_number_id"].startswith("pn_mock_")
    assert numbers[0]["e164_number"] != "+15550001111"


def test_service_missing_tenant_credential_fails_closed():
    service = TelephonyService(db_conn=ActiveConnectionDb(encrypted_ref=None))

    with pytest.raises(TelephonyError) as exc_info:
        service.list_telnyx_owned_numbers(TENANT_ID)

    assert exc_info.value.code == "provider_credentials_missing"
    assert exc_info.value.status == 503


def test_sync_owned_numbers_uses_real_adapter_and_upserts_inventory():
    encrypted_ref = encrypt_provider_secret(RAW_TELNYX_KEY)
    db = ActiveConnectionDb(encrypted_ref)
    captured: dict[str, Any] = {}

    def factory(api_key: str, mock_mode: bool):
        captured["api_key"] = api_key
        captured["mock_mode"] = mock_mode
        return FakeTelnyxClient(api_key, mock_mode)

    service = TelephonyService(db_conn=db, telnyx_client_factory=factory)
    result = service.sync_telnyx_owned_numbers(TENANT_ID)

    assert captured == {"api_key": RAW_TELNYX_KEY, "mock_mode": False}
    assert result["synced_count"] == 1
    assert result["items"][0]["provider_number_id"] == "pn_real_123"
    assert any(
        "insert into telephony_phone_numbers" in call[0].lower() for call in db.calls
    )


def test_connect_missing_encryption_config_fails_before_provider_verification(
    monkeypatch,
):
    monkeypatch.delenv("TELEPHONY_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    factory_called = False

    def factory(api_key: str, mock_mode: bool):
        nonlocal factory_called
        factory_called = True
        return FakeTelnyxClient(api_key, mock_mode)

    service = TelephonyService(db_conn=ConnectWriteDb(), telnyx_client_factory=factory)

    with pytest.raises(TelephonyError) as exc_info:
        service.connect_telnyx_account(TENANT_ID, RAW_TELNYX_KEY, "Primary")

    assert exc_info.value.code == "provider_credentials_missing"
    assert factory_called is False


def test_connect_telnyx_account_stores_encrypted_ref_and_sanitizes_response(caplog):
    db = ConnectWriteDb()

    def factory(api_key: str, mock_mode: bool):
        assert api_key == RAW_TELNYX_KEY
        assert mock_mode is False
        return FakeTelnyxClient(api_key, mock_mode)

    service = TelephonyService(db_conn=db, telnyx_client_factory=factory)
    response = service.connect_telnyx_account(TENANT_ID, RAW_TELNYX_KEY, "Primary")

    response_json = json.dumps(response, default=str)
    assert RAW_TELNYX_KEY not in response_json
    assert "encrypted_api_key_ref" not in response
    assert db.stored_encrypted_ref is not None
    assert db.stored_encrypted_ref.startswith("enc:v1:")
    assert RAW_TELNYX_KEY not in db.stored_encrypted_ref
    assert all(RAW_TELNYX_KEY not in record.getMessage() for record in caplog.records)


def test_livekit_routing_uses_real_adapter_path_when_configured():
    db = RoutingDb()
    fake_livekit = FakeLiveKitClient(mock_mode=False)

    service = TelephonyService(
        db_conn=db, livekit_client_factory=lambda mock_mode: fake_livekit
    )
    result = service.configure_number_routing(
        TENANT_ID, "num_real_123", inbound_agent_id="agent_real_123"
    )

    assert fake_livekit.mock_mode is False
    assert fake_livekit.inbound_calls == [("num_real_123", "+14155550123")]
    assert fake_livekit.rule_calls == [
        ("lk_tr_in_real_123", "num_real_123", "+14155550123")
    ]
    assert result["inbound_trunk_id"] == "lk_tr_in_real_123"
    assert result["dispatch_rule_id"] == "lk_rule_real_123"
    assert not result["inbound_trunk_id"].startswith("lk_tr_in_mock_")
    assert db.updated_number is True


def test_livekit_missing_credentials_do_not_produce_mock_success():
    client = LiveKitSipClient(mock_mode=False)

    with pytest.raises(TelephonyError) as exc_info:
        client.create_or_get_outbound_trunk(
            "conn_real_123", "sip.telnyx.example", ["+14155550123"]
        )

    assert exc_info.value.code == "provider_credentials_missing"
    assert exc_info.value.status == 503


def _telnyx_test_keypair() -> tuple[Ed25519PrivateKey, str]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_key, base64.b64encode(public_key).decode("ascii")


def _telnyx_signature(
    private_key: Ed25519PrivateKey, timestamp: str, body: bytes
) -> str:
    signed_payload = timestamp.encode("utf-8") + b"|" + body
    return base64.b64encode(private_key.sign(signed_payload)).decode("ascii")


def test_webhook_real_mode_verifies_telnyx_api_v2_ed25519_signature(monkeypatch):
    private_key, public_key = _telnyx_test_keypair()
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", public_key)
    body = b'{"data":{"event_type":"call.initiated","id":"evt_real_123"}}'
    timestamp = str(int(time.time()))
    signature = _telnyx_signature(private_key, timestamp, body)

    assert (
        telephony_webhooks.verify_telnyx_webhook_signature(body, None, timestamp)
        is False
    )
    assert (
        telephony_webhooks.verify_telnyx_webhook_signature(body, "bad", timestamp)
        is False
    )
    assert (
        telephony_webhooks.verify_telnyx_webhook_signature(body, signature, timestamp)
        is True
    )
    assert (
        telephony_webhooks.verify_telnyx_webhook_signature(body, signature, timestamp)
        is False
    )


def test_webhook_real_mode_rejects_stale_timestamp(monkeypatch):
    private_key, public_key = _telnyx_test_keypair()
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", public_key)
    body = b'{"data":{"event_type":"call.initiated","id":"evt_stale_123"}}'
    timestamp = str(int(time.time()) - 301)
    signature = _telnyx_signature(private_key, timestamp, body)

    assert (
        telephony_webhooks.verify_telnyx_webhook_signature(body, signature, timestamp)
        is False
    )


def test_webhook_endpoint_accepts_signed_request_and_dedupes_event_id(monkeypatch):
    private_key, public_key = _telnyx_test_keypair()
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", public_key)
    body = b'{"data":{"event_type":"call.initiated","id":"evt_endpoint_123"}}'
    timestamp = str(int(time.time()))
    signature = _telnyx_signature(private_key, timestamp, body)
    app = FastAPI()
    app.include_router(telephony_webhooks.router)
    client = TestClient(app)

    first = client.post(
        "/webhooks/telephony/telnyx",
        content=body,
        headers={
            "content-type": "application/json",
            "telnyx-signature-ed25519": signature,
            "telnyx-timestamp": timestamp,
        },
    )
    assert first.status_code == 200
    assert first.json()["status"] == "accepted"

    telephony_webhooks._seen_webhook_signatures.clear()
    second_signature = _telnyx_signature(private_key, timestamp, body)
    duplicate = client.post(
        "/webhooks/telephony/telnyx",
        content=body,
        headers={
            "content-type": "application/json",
            "telnyx-signature-ed25519": second_signature,
            "telnyx-timestamp": timestamp,
        },
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"


def test_webhook_endpoint_rejects_unsigned_request_in_real_mode(monkeypatch):
    _private_key, public_key = _telnyx_test_keypair()
    monkeypatch.setenv("TELNYX_PUBLIC_KEY", public_key)
    app = FastAPI()
    app.include_router(telephony_webhooks.router)
    client = TestClient(app)

    resp = client.post(
        "/webhooks/telephony/telnyx",
        json={"data": {"event_type": "call.initiated", "id": "evt_unsigned_123"}},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "webhook_signature_invalid"


class OutboundCallDb(ActiveConnectionDb):
    def __init__(self):
        super().__init__(encrypted_ref=encrypt_provider_secret(RAW_TELNYX_KEY))
        self.inserted_call_params: tuple[Any, ...] | None = None

    def execute(self, query: str, params: tuple[Any, ...] = ()):  # noqa: C901 - focused SQL fake
        self.calls.append((query, params))
        sql = " ".join(query.lower().split())
        if "from tenant_telnyx_connections" in sql:
            return FakeCursor(row=self.active_row())
        if "from telephony_phone_numbers" in sql:
            return FakeCursor(
                row=(
                    "num_real_123",
                    TENANT_ID,
                    "pn_real_123",
                    "+14155550123",
                    "US",
                    "local",
                    ["voice"],
                    "owned",
                    "ready",
                    "agent_real_123",
                    None,
                    None,
                )
            )
        if "from livekit_outbound_trunks" in sql:
            return FakeCursor(
                row=(
                    "trunk_record_123",
                    TENANT_ID,
                    "ovp_real_123",
                    "lk_tr_out_real_123",
                    "active",
                    "active",
                )
            )
        if "from quota_state" in sql:
            return FakeCursor(row=None)
        if "insert into telephony_calls" in sql:
            self.inserted_call_params = params
            return FakeCursor()
        raise AssertionError(f"Unexpected SQL: {query}")


class OutboundLiveKitClient:
    def __init__(self, mock_mode: bool):
        self.mock_mode = mock_mode
        self.sip_participant_calls: list[tuple[str, str, str]] = []

    def create_sip_participant(
        self,
        room_name: str,
        outbound_trunk_id: str,
        to_number: str,
        participant_identity: str | None = None,
    ):
        self.sip_participant_calls.append((room_name, outbound_trunk_id, to_number))
        return {
            "livekit_sip_call_id": "lk_call_real_123",
            "livekit_sip_call_id_full": "lk_call_real_123_full",
            "status": "dialing",
        }


def test_outbound_call_uses_uuid_database_id_and_no_fake_session_id():
    db = OutboundCallDb()
    livekit = OutboundLiveKitClient(mock_mode=False)
    service = TelephonyService(
        db_conn=db, livekit_client_factory=lambda mock_mode: livekit
    )

    result = service.create_outbound_call(
        TENANT_ID,
        agent_id="agent_real_123",
        from_number_id="num_real_123",
        to_number="+14155550199",
        idempotency_key="outbound-test-idempotency",
    )

    uuid.UUID(result["telephony_call_id"])
    assert result["session_id"] is None
    assert db.inserted_call_params is not None
    assert db.inserted_call_params[0] == result["telephony_call_id"]
    uuid.UUID(db.inserted_call_params[0])
    assert livekit.sip_participant_calls == [
        (result["room_name"], "lk_tr_out_real_123", "+14155550199")
    ]
