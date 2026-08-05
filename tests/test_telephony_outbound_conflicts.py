from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from tenant_portal_api.telephony_errors import TelephonyError, TelephonyErrorCode


class _FakeUniqueViolation(Exception):
    pass


class _FakeInvalidColumnReference(Exception):
    pass


sys.modules.setdefault(
    "psycopg",
    types.SimpleNamespace(
        connect=None,
        Connection=object,
        errors=types.SimpleNamespace(
            UniqueViolation=_FakeUniqueViolation,
            InvalidColumnReference=_FakeInvalidColumnReference,
        ),
    ),
)

from tenant_portal_api.telephony_service import TelephonyService


TENANT_ID = "a4231868-2f06-426a-b9a5-1081e89554ec"


class FakeCursor:
    def __init__(self, row: Any = None):
        self._row = row

    def fetchone(self):
        return self._row


class ConflictQuotaDb:
    def execute(self, query: str, params: tuple[Any, ...] = ()):  # noqa: ARG002
        sql = " ".join(query.lower().split())
        if "from telephony_phone_numbers" in sql:
            return FakeCursor(
                (
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
                (
                    "trunk_record_123",
                    TENANT_ID,
                    "ovp_real_123",
                    "lk_tr_out_real_123",
                    "active",
                    "active",
                )
            )
        if "from tenants where id = %s" in sql:
            return FakeCursor((5,))
        if "insert into quota_state" in sql:
            return FakeCursor()
        if "from quota_state where tenant_id = %s for update" in sql:
            raise _FakeInvalidColumnReference(
                "FOR UPDATE cannot be applied to the nullable side of an outer join"
            )
        raise AssertionError(f"Unexpected SQL: {query}")


class StubLiveKitClient:
    def __init__(self, mock_mode: bool):  # noqa: ARG002
        self.sip_participant_calls: list[tuple[str, str, str]] = []

    def create_agent_dispatch(self, room_name: str, metadata: dict[str, Any]):  # noqa: ARG002
        return None

    def create_sip_participant(
        self,
        room_name: str,
        outbound_trunk_id: str,
        to_number: str,
        participant_identity: str | None = None,  # noqa: ARG002
    ):
        self.sip_participant_calls.append((room_name, outbound_trunk_id, to_number))
        return {
            "livekit_sip_call_id": "lk_call_real_123",
            "livekit_sip_call_id_full": "lk_call_real_123_full",
            "status": "dialing",
        }


def test_outbound_call_maps_quota_lock_conflict_to_platform_conflict():
    livekit = StubLiveKitClient(mock_mode=False)
    service = TelephonyService(
        db_conn=ConflictQuotaDb(),
        livekit_client_factory=lambda mock_mode: livekit,
    )

    with pytest.raises(TelephonyError) as excinfo:
        service.create_outbound_call(
            TENANT_ID,
            agent_id="agent_real_123",
            from_number_id="num_real_123",
            to_number="+14155550199",
            idempotency_key="outbound-test-idempotency",
        )

    assert excinfo.value.status == 409
    assert excinfo.value.code == TelephonyErrorCode.CALL_STATE_CONFLICT
    assert livekit.sip_participant_calls == []
