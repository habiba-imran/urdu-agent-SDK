"""Focused purchase-flow tests for immediate managed-number reconciliation."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tenant_portal_api.telephony_service import TelephonyService


class FakeCursor:
    def __init__(self, row: Any = None):
        self._row = row

    def fetchone(self):
        return self._row


class PurchaseFlowDb:
    def __init__(self):
        self.connection = {
            "id": "conn_123",
            "tenant_id": "tenant_123",
            "label": "primary",
            "platform_status": "active",
            "provider_status": "active",
            "key_fingerprint": "fingerprint",
            "telnyx_account_id": "acct_123",
            "last_verified_at": "2026-08-03T12:00:00Z",
            "permission_last_checked_at": "2026-08-03T12:00:00Z",
            "encrypted_api_key_ref": "encrypted-ref",
        }
        self.idempotency: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.number_orders: list[dict[str, Any]] = []
        self.phone_numbers: list[dict[str, Any]] = []

    def execute(self, query: str, params: tuple[Any, ...] = ()):  # noqa: C901
        sql = " ".join(query.lower().split())

        if "from tenant_telnyx_connections" in sql:
            row = self.connection
            return FakeCursor(
                (
                    row["id"],
                    row["tenant_id"],
                    row["label"],
                    row["platform_status"],
                    row["provider_status"],
                    row["key_fingerprint"],
                    row["telnyx_account_id"],
                    row["last_verified_at"],
                    row["permission_last_checked_at"],
                    row["encrypted_api_key_ref"],
                )
            )

        if "from telephony_idempotency_keys" in sql:
            row = self.idempotency.get((params[0], params[1], params[2]))
            if not row:
                return FakeCursor(None)
            return FakeCursor(
                (row["request_hash"], row["response_body"], row["platform_status"])
            )

        if "insert into telephony_idempotency_keys" in sql:
            self.idempotency[(params[0], params[1], params[2])] = {
                "request_hash": params[3],
                "response_body": json.loads(params[4]),
                "platform_status": "completed",
            }
            return FakeCursor(None)

        if "insert into telephony_number_orders" in sql:
            order = {
                "id": f"ord_db_{len(self.number_orders) + 1}",
                "tenant_id": params[0],
                "telnyx_connection_id": params[1],
                "idempotency_key": params[2],
                "provider_order_id": params[3],
                "selected_e164_number": params[4],
                "provider_status": params[5],
                "platform_status": params[6],
                "raw_provider_status": params[7],
                "error_code": None,
                "error_message": None,
                "created_at": "2026-08-03T12:10:00Z",
            }
            self.number_orders.append(order)
            return FakeCursor(
                (
                    order["id"],
                    order["tenant_id"],
                    order["idempotency_key"],
                    order["provider_order_id"],
                    order["selected_e164_number"],
                    order["platform_status"],
                    order["provider_status"],
                    order["error_code"],
                    order["error_message"],
                    order["created_at"],
                )
            )

        if "update telephony_phone_numbers" in sql and "provider_number_id = %s" in sql:
            (
                connection_id,
                provider_number_id,
                country,
                number_type,
                features,
                provisioning_status,
                routing_status,
                provider_status,
                external_customer_ref,
                tenant_id,
                e164_number,
                provider_number_id_match,
            ) = params
            for number in self.phone_numbers:
                if (
                    number["tenant_id"] == tenant_id
                    and number["e164_number"] == e164_number
                    and (
                        number["provider_number_id"] is None
                        or number["provider_number_id"] == provider_number_id_match
                    )
                ):
                    number.update(
                        {
                            "telnyx_connection_id": connection_id,
                            "provider_number_id": provider_number_id,
                            "country": country,
                            "number_type": number_type,
                            "features": json.loads(features),
                            "provisioning_status": provisioning_status,
                            "routing_status": routing_status,
                            "provider_status": provider_status,
                            "external_customer_ref": external_customer_ref,
                            "disabled_at": None,
                        }
                    )
                    return FakeCursor((number["id"],))
            return FakeCursor(None)

        if "insert into telephony_phone_numbers" in sql:
            phone = {
                "id": f"num_{len(self.phone_numbers) + 1}",
                "tenant_id": params[0],
                "telnyx_connection_id": params[1],
                "provider_number_id": params[2] if len(params) > 10 else None,
                "e164_number": params[3] if len(params) > 10 else params[2],
                "country": params[4] if len(params) > 10 else params[3],
                "number_type": params[5] if len(params) > 10 else params[4],
                "features": json.loads(params[6] if len(params) > 10 else params[5]),
                "provisioning_status": params[7] if len(params) > 10 else params[6],
                "routing_status": params[8] if len(params) > 10 else params[7],
                "provider_status": params[9] if len(params) > 10 else params[8],
                "external_customer_ref": params[10] if len(params) > 10 else params[9],
                "disabled_at": None,
            }
            self.phone_numbers.append(phone)
            return FakeCursor((phone["id"],))

        raise AssertionError(f"Unexpected SQL: {query}")


class ReconcilingTelnyxClient:
    def __init__(self, api_key: str, mock_mode: bool):
        self.api_key = api_key
        self.mock_mode = mock_mode
        self._order_status_calls = 0
        self._inventory_calls = 0

    def purchase_number(self, e164_number: str) -> dict[str, Any]:
        return {
            "provider_order_id": "ord_provider_1",
            "selected_e164_number": e164_number,
            "status": "pending",
            "provider_status": "pending",
            "platform_status": "pending",
        }

    def get_number_order_status(self, order_id: str) -> dict[str, Any]:
        self._order_status_calls += 1
        return {
            "provider_order_id": order_id,
            "status": "success",
            "provider_status": "success",
            "platform_status": "purchased",
        }

    def list_owned_numbers(
        self, filter_phone_number: str | None = None
    ) -> list[dict[str, Any]]:
        self._inventory_calls += 1
        if self._inventory_calls < 2:
            return []
        return [
            {
                "provider_number_id": "pn_real_123",
                "e164_number": filter_phone_number,
                "country": "US",
                "number_type": "local",
                "features": ["voice"],
                "status": "active",
            }
        ]


@pytest.fixture(autouse=True)
def real_provider_env(monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER_MODE", "real")


def test_purchase_number_reconciles_pending_order_into_managed_number():
    db = PurchaseFlowDb()

    service = TelephonyService(
        db_conn=db,
        telnyx_client_factory=lambda api_key, mock_mode: ReconcilingTelnyxClient(
            api_key, mock_mode
        ),
        purchase_reconcile_attempts=2,
        purchase_reconcile_delay_sec=0,
    )

    result = service.purchase_number(
        tenant_id="tenant_123",
        e164_number="+14155550123",
        idempotency_key="idemp-buy-1",
    )

    assert result["platform_status"] == "purchased"
    assert result["provider_status"] == "success"
    assert result["managed_number_id"] == "num_1"
    assert db.phone_numbers[0]["provider_number_id"] == "pn_real_123"
    assert db.phone_numbers[0]["provisioning_status"] == "owned"
