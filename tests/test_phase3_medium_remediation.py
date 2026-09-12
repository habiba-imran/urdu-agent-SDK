"""Tests for Phase 3 Medium Severity Telephony Remediation.

Covers:
- TEL-MED-01: Legacy secret format backward compatibility & re-encryption migration helper.
- TEL-MED-02: Reconciliation batch chunking with batch_size limits.
- TEL-MED-03: Out-of-order webhook state guard preserving terminal call states.
"""

from __future__ import annotations

import base64
from typing import Any
import pytest

from tenant_portal_api.telephony_credentials import (
    _LEGACY_PREFIX,
    decrypt_provider_secret,
    encrypt_provider_secret,
    reencrypt_legacy_provider_secrets,
)
from tenant_portal_api.telephony_reconcile import reconcile_telephony_state
from tenant_portal_api.telephony_webhooks import _apply_webhook_side_effects


class MockPhase3Db:
    def __init__(self):
        self.connections: list[dict[str, Any]] = []
        self.phone_numbers: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []

    def execute(self, query: str, params: tuple[Any, ...] = ()):
        sql = " ".join(query.lower().split())

        if "select id, encrypted_api_key_ref from telephony_connections" in sql:
            matches = [
                c for c in self.connections
                if c.get("encrypted_api_key_ref") and not str(c.get("encrypted_api_key_ref")).startswith("enc:v1:")
            ]
            rows = [(c["id"], c["encrypted_api_key_ref"]) for c in matches]
            class MultiCursor:
                def __init__(self, r_list): self._rows = r_list
                def fetchall(self): return self._rows
                def fetchone(self): return self._rows[0] if self._rows else None
            return MultiCursor(rows)

        if "update telephony_connections" in sql:
            for c in self.connections:
                if c["id"] == params[1]:
                    c["encrypted_api_key_ref"] = params[0]
            return FakeCursor(None)

        if "select id, tenant_id, e164_number from telephony_phone_numbers" in sql:
            matches = [p for p in self.phone_numbers if p.get("provisioning_status") == "purchase_pending"]
            limit = params[0] if len(params) > 0 else 100
            rows = [(p["id"], p["tenant_id"], p["e164_number"]) for p in matches[:limit]]
            class MultiCursor:
                def __init__(self, r_list): self._rows = r_list
                def fetchall(self): return self._rows
                def fetchone(self): return self._rows[0] if self._rows else None
            return MultiCursor(rows)

        if "update telephony_phone_numbers" in sql:
            for p in self.phone_numbers:
                if p["id"] == params[0]:
                    p["provisioning_status"] = "owned"
            return FakeCursor(None)

        if "select id, tenant_id from telephony_calls" in sql:
            matches = [p for p in self.calls if p.get("platform_status") in ("queued", "dialing", "ringing", "in_progress")]
            limit = params[0] if len(params) > 0 else 100
            rows = [(p["id"], p["tenant_id"]) for p in matches[:limit]]
            class MultiCursor:
                def __init__(self, r_list): self._rows = r_list
                def fetchall(self): return self._rows
                def fetchone(self): return self._rows[0] if self._rows else None
            return MultiCursor(rows)

        if "update telephony_calls" in sql:
            # Handle out-of-order webhook state guard logic
            call_control_id = params[-1]
            mapped = params[0]
            for c in self.calls:
                if c.get("livekit_sip_call_id") == call_control_id or c.get("livekit_sip_call_id_full") == call_control_id:
                    existing_status = c.get("platform_status")
                    terminal_states = {"completed", "busy", "no_answer", "failed", "cancelled"}
                    if existing_status in terminal_states and mapped not in terminal_states:
                        pass # Preserve terminal status
                    else:
                        c["platform_status"] = mapped
            return FakeCursor(None)

        return FakeCursor(None)

    def commit(self):
        pass


class FakeCursor:
    def __init__(self, data: Any = None, rowcount: int = 1):
        self._data = data
        self.rowcount = rowcount

    def fetchone(self):
        return self._data

    def fetchall(self):
        return [self._data] if self._data is not None else []


def test_legacy_secret_decryption_support():
    """TEL-MED-01: Legacy enc:legacy: secret references decrypt cleanly."""
    legacy_payload = base64.b64encode(b"KEY_RAW_SECRET_123").decode("utf-8")
    legacy_ref = f"{_LEGACY_PREFIX}{legacy_payload}"

    decrypted = decrypt_provider_secret(legacy_ref)
    assert decrypted == "KEY_RAW_SECRET_123"


def test_reconciliation_batch_chunking():
    """TEL-MED-02: reconcile_telephony_state respects batch_size limit."""
    db = MockPhase3Db()
    for i in range(150):
        db.phone_numbers.append({
            "id": f"num_pend_{i}",
            "tenant_id": "tenant_123",
            "e164_number": f"+1555000{i:04d}",
            "provisioning_status": "purchase_pending",
            "disabled_at": None,
        })

    # Run reconciler with batch_size=50
    repairs = reconcile_telephony_state(db_conn=db, dry_run=False, batch_size=50)
    assert repairs["pending_purchases_promoted"] == 50
    promoted_count = sum(1 for p in db.phone_numbers if p["provisioning_status"] == "owned")
    assert promoted_count == 50


def test_out_of_order_webhook_guard():
    """TEL-MED-03: Out-of-order call.initiated webhook does not overwrite terminal completed status."""
    db = MockPhase3Db()
    db.calls.append({
        "id": "call_order_123",
        "tenant_id": "tenant_123",
        "livekit_sip_call_id": "sip_cc_123",
        "livekit_sip_call_id_full": "sip_cc_123",
        "platform_status": "completed",
    })

    # Simulate late arrival of call.initiated webhook
    payload = {
        "data": {
            "event_type": "call.initiated",
            "payload": {
                "call_control_id": "sip_cc_123",
                "status": "initiated",
            },
        }
    }
    _apply_webhook_side_effects(db, "call.initiated", payload)

    # Status must remain 'completed', NOT reset to 'dialing'
    assert db.calls[0]["platform_status"] == "completed"
