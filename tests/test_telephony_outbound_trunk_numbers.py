"""Outbound LiveKit trunk number eligibility tests.

These tests avoid live provider calls and prove the backend derives tenant-owned
E.164 numbers before configuring the LiveKit outbound trunk.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tenant_portal_api.telephony_credentials import encrypt_provider_secret
from tenant_portal_api.telephony_errors import TelephonyError
from tenant_portal_api.telephony_service import TelephonyService

TENANT_A = "a4231868-2f06-426a-b9a5-1081e89554ec"
TENANT_B = "b5231868-2f06-426a-b9a5-1081e89554ec"
TEST_ENC_SECRET = encrypt_provider_secret("sip-secret")



@pytest.fixture(autouse=True)
def real_provider_env(monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER_MODE", "real")


class FakeCursor:
    def __init__(self, row: Any = None, rows: list[Any] | None = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class OutboundTrunkDb:
    def __init__(self, numbers: list[dict[str, Any]], existing_trunk: bool = False):
        self.numbers = numbers
        self.trunks: list[dict[str, Any]] = []
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        if existing_trunk:
            self.trunks.append(
                {
                    "id": "out_trunk_record_a",
                    "tenant_id": TENANT_A,
                    "profile_id": "profile_a",
                    "livekit_outbound_trunk_id": "lk_tr_out_conn_a",
                    "platform_status": "active",
                    "provider_status": "active",
                }
            )

    def execute(self, query: str, params: tuple[Any, ...] = ()):  # noqa: C901 - compact SQL fake
        self.calls.append((query, params))
        sql = " ".join(query.lower().split())
        if "from tenant_telnyx_connections" in sql:
            return FakeCursor(row=self._connection_row(params[0]))
        if "from telnyx_sip_connections" in sql:
            return FakeCursor(row=self._sip_row(params[0], params[1]))
        if "from telnyx_outbound_voice_profiles" in sql:
            return FakeCursor(row=self._profile_row(params[0], params[1]))
        if (
            "select distinct e164_number" in sql
            and "from telephony_phone_numbers" in sql
        ):
            return FakeCursor(
                rows=[
                    (number,) for number in self._eligible_numbers(params[0], params[1])
                ]
            )
        if "from livekit_outbound_trunks" in sql:
            return FakeCursor(row=self._existing_trunk_row(params[0], params[1]))
        if "insert into livekit_outbound_trunks" in sql:
            return self._insert_trunk(params)
        if "update livekit_outbound_trunks" in sql:
            return self._update_trunk(params)
        raise AssertionError(f"Unexpected SQL: {query}")

    def _connection_row(self, tenant_id: str):
        if tenant_id == TENANT_A:
            connection_id = "conn_a"
        elif tenant_id == TENANT_B:
            connection_id = "conn_b"
        else:
            return None
        return (
            connection_id,
            tenant_id,
            "primary",
            "active",
            "active",
            "fingerprint",
            "acct_real_123",
            "2026-08-01T12:00:00Z",
            "2026-08-01T12:00:00Z",
            TEST_ENC_SECRET,
        )

    def _sip_row(self, tenant_id: str, connection_id: str):
        expected = "conn_a" if tenant_id == TENANT_A else "conn_b"
        if connection_id != expected:
            return None
        return (
            f"sip_{connection_id}",
            tenant_id,
            connection_id,
            f"provider_sip_{connection_id}",
            "sip.telnyx.com",

            "sip-user",
            TEST_ENC_SECRET,
            "active",
            "active",
            "2026-08-01T12:00:00Z",
        )


    def _profile_row(self, tenant_id: str, connection_id: str):
        expected = "conn_a" if tenant_id == TENANT_A else "conn_b"
        if connection_id != expected:
            return None
        return (
            "profile_a" if tenant_id == TENANT_A else "profile_b",
            tenant_id,
            connection_id,
            f"sip_{connection_id}",
            f"provider_profile_{connection_id}",
            "active",
            "active",
            ["US"],
            10,
            100.0,
        )

    def _eligible_numbers(self, tenant_id: str, connection_id: str) -> list[str]:
        return sorted(
            {
                item["e164_number"]
                for item in self.numbers
                if item.get("tenant_id") == tenant_id
                and item.get("telnyx_connection_id") == connection_id
                and item.get("provider_number_id") is not None
                and item.get("disabled_at") is None
                and item.get("deleted_at") is None
                and item.get("provisioning_status") in {"owned", "active"}
                and re.match(r"^\+[1-9][0-9]{7,14}$", item.get("e164_number", ""))
            }
        )

    def _existing_trunk_row(self, tenant_id: str, profile_id: str):
        trunk = next(
            (
                item
                for item in self.trunks
                if item["tenant_id"] == tenant_id
                and item["profile_id"] == profile_id
                and item["platform_status"]
                in {"pending_verification", "testing", "active"}
            ),
            None,
        )
        if not trunk:
            return None
        return self._trunk_row(trunk)

    def _insert_trunk(self, params: tuple[Any, ...]):
        tenant_id, _connection_id, _sip_id, profile_id, provider_id, provider_status = (
            params
        )
        trunk = {
            "id": f"out_trunk_record_{len(self.trunks) + 1}",
            "tenant_id": tenant_id,
            "profile_id": profile_id,
            "livekit_outbound_trunk_id": provider_id,
            "platform_status": "active",
            "provider_status": provider_status,
        }
        self.trunks.append(trunk)
        return FakeCursor(row=self._trunk_row(trunk))

    def _update_trunk(self, params: tuple[Any, ...]):
        provider_id, provider_status, tenant_id, record_id = params
        trunk = next(
            item
            for item in self.trunks
            if item["tenant_id"] == tenant_id and item["id"] == record_id
        )
        trunk["livekit_outbound_trunk_id"] = provider_id
        trunk["platform_status"] = "active"
        trunk["provider_status"] = provider_status
        return FakeCursor(row=self._trunk_row(trunk))

    @staticmethod
    def _trunk_row(trunk: dict[str, Any]):
        return (
            trunk["id"],
            trunk["tenant_id"],
            trunk["profile_id"],
            trunk["livekit_outbound_trunk_id"],
            trunk["platform_status"],
            trunk["provider_status"],
        )


class CapturingLiveKitClient:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.mock_mode: bool | None = None
        self.outbound_calls: list[
            tuple[str, str, list[str], str | None, str | None]
        ] = []

    def create_or_get_outbound_trunk(
        self,
        telnyx_connection_id: str,
        sip_fqdn: str,
        trunk_numbers: list[str],
        sip_username: str | None = None,
        sip_secret: str | None = None,
    ):
        self.outbound_calls.append(
            (
                telnyx_connection_id,
                sip_fqdn,
                list(trunk_numbers),
                sip_username,
                sip_secret,
            )
        )
        if self.fail:
            raise TelephonyError(
                status=409,
                code="outbound_not_ready",
                message="Tenant has no eligible managed phone numbers for outbound trunk setup.",
            )
        return {
            "livekit_outbound_trunk_id": f"lk_tr_out_{telnyx_connection_id}",
            "status": "active",
        }


def managed_number(
    e164_number: str = "+14402248161",
    *,
    tenant_id: str = TENANT_A,
    connection_id: str = "conn_a",
    provider_number_id: str | None = "pn_real_123",
    provisioning_status: str = "owned",
    disabled_at: str | None = None,
    deleted_at: str | None = None,
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "telnyx_connection_id": connection_id,
        "provider_number_id": provider_number_id,
        "e164_number": e164_number,
        "provisioning_status": provisioning_status,
        "disabled_at": disabled_at,
        "deleted_at": deleted_at,
    }


def service_for(
    db: OutboundTrunkDb, livekit: CapturingLiveKitClient
) -> TelephonyService:
    def factory(mock_mode: bool):
        livekit.mock_mode = mock_mode
        return livekit

    return TelephonyService(db_conn=db, livekit_client_factory=factory)


def test_configure_outbound_trunk_sends_one_eligible_managed_number_to_livekit():
    db = OutboundTrunkDb([managed_number()])
    livekit = CapturingLiveKitClient()

    result = service_for(db, livekit).configure_outbound_trunk(TENANT_A)

    assert result["platform_status"] == "active"
    assert livekit.outbound_calls == [
        ("conn_a", "sip.telnyx.com", ["+14402248161"], "sip-user", "sip-secret")
    ]
    assert len(db.trunks) == 1


def test_configure_outbound_trunk_sends_multiple_eligible_numbers_to_livekit():
    db = OutboundTrunkDb(
        [
            managed_number("+14402248161"),
            managed_number("+14155550123", provider_number_id="pn_real_456"),
        ]
    )
    livekit = CapturingLiveKitClient()

    service_for(db, livekit).configure_outbound_trunk(TENANT_A)

    assert livekit.outbound_calls == [
        (
            "conn_a",
            "sip.telnyx.com",
            ["+14155550123", "+14402248161"],
            "sip-user",
            "sip-secret",
        )
    ]


def test_configure_outbound_trunk_fails_closed_when_no_eligible_numbers():
    db = OutboundTrunkDb([])
    livekit = CapturingLiveKitClient()

    with pytest.raises(TelephonyError) as exc_info:
        service_for(db, livekit).configure_outbound_trunk(TENANT_A)

    assert exc_info.value.code == "outbound_not_ready"
    assert exc_info.value.status == 409
    assert livekit.outbound_calls == []
    assert db.trunks == []


def test_configure_outbound_trunk_excludes_disabled_released_and_deleted_numbers():
    db = OutboundTrunkDb(
        [
            managed_number("+14402248161", disabled_at="2026-08-01T00:00:00Z"),
            managed_number(
                "+14155550123",
                provider_number_id="pn_released",
                provisioning_status="released",
            ),
            managed_number(
                "+14155550124",
                provider_number_id="pn_deleted",
                deleted_at="2026-08-01T00:00:00Z",
            ),
            managed_number("+14155550125", provider_number_id="pn_active"),
        ]
    )
    livekit = CapturingLiveKitClient()

    service_for(db, livekit).configure_outbound_trunk(TENANT_A)

    assert livekit.outbound_calls == [
        ("conn_a", "sip.telnyx.com", ["+14155550125"], "sip-user", "sip-secret")
    ]


def test_configure_outbound_trunk_excludes_cross_tenant_numbers():
    db = OutboundTrunkDb(
        [
            managed_number("+14402248161", tenant_id=TENANT_B, connection_id="conn_b"),
            managed_number("+14155550123", provider_number_id="pn_tenant_a"),
        ]
    )
    livekit = CapturingLiveKitClient()

    service_for(db, livekit).configure_outbound_trunk(TENANT_A)

    assert livekit.outbound_calls == [
        ("conn_a", "sip.telnyx.com", ["+14155550123"], "sip-user", "sip-secret")
    ]



def test_configure_outbound_trunk_requires_provider_number_identity():
    db = OutboundTrunkDb(
        [
            managed_number("+14402248161", provider_number_id=None),
        ]
    )
    livekit = CapturingLiveKitClient()

    with pytest.raises(TelephonyError) as exc_info:
        service_for(db, livekit).configure_outbound_trunk(TENANT_A)

    assert exc_info.value.code == "outbound_not_ready"
    assert livekit.outbound_calls == []


def test_repeated_outbound_trunk_configuration_reuses_existing_record():
    db = OutboundTrunkDb([managed_number()])
    livekit = CapturingLiveKitClient()
    service = service_for(db, livekit)

    first = service.configure_outbound_trunk(TENANT_A)
    second = service.configure_outbound_trunk(TENANT_A)

    assert (
        first["outbound_trunk_id"] == second["outbound_trunk_id"] == "lk_tr_out_conn_a"
    )
    assert len(db.trunks) == 1
    assert len(livekit.outbound_calls) == 2


def test_livekit_validation_error_remains_stable_platform_error():
    db = OutboundTrunkDb([managed_number()])
    livekit = CapturingLiveKitClient(fail=True)

    with pytest.raises(TelephonyError) as exc_info:
        service_for(db, livekit).configure_outbound_trunk(TENANT_A)

    assert exc_info.value.code == "outbound_not_ready"
    assert exc_info.value.status == 409
    assert db.trunks == []
