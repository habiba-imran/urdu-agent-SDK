"""Wave 3 — P1-H3 machine rate limit + P1-H4 SSRF pin helpers."""

from __future__ import annotations

import time
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_machine_auth_bad_signature_does_not_burn_tenant_bucket(monkeypatch):
    from tenant_portal_api import machine_auth

    machine_auth._hits.clear()
    tenant_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    fake_time = 2_000_000.0
    monkeypatch.setattr(time, "time", lambda: fake_time)

    class _Conn:
        def execute(self, sql, params=None):
            class _R:
                def fetchone(self_inner):
                    if "from tenants" in sql.lower():
                        return ("active",)
                    return None

            return _R()

    class _Secrets:
        def get(self, tid):
            return "real-secret-value-for-hmac"

    # Flood with bad signatures — must not fill the tenant bucket.
    for i in range(machine_auth.MACHINE_RATE_LIMIT_PER_MIN + 5):
        with pytest.raises(machine_auth.MachineAuthError) as exc:
            machine_auth.verify_machine_request(
                _Conn(),
                _Secrets(),
                tenant_id=tenant_id,
                ts=str(int(fake_time)),
                nonce=f"n-{i}",
                action="agent.list",
                body={},
                signature="deadbeef",
            )
        assert exc.value.status == 401

    # Tenant bucket still empty of authenticated hits — check should not 429 yet.
    assert not machine_auth._rate_limit_exceeded(
        tenant_id, machine_auth.MACHINE_RATE_LIMIT_PER_MIN
    )


def test_ssrf_guard_rejects_metadata_when_hosted(monkeypatch):
    from worker import ssrf_guard

    monkeypatch.setattr(ssrf_guard, "is_hosted", lambda: True)
    with pytest.raises(ssrf_guard.ToolsSsrfError):
        ssrf_guard.prepare_tools_post_url("http://169.254.169.254/latest", hosted=True)
    with pytest.raises(ssrf_guard.ToolsSsrfError):
        ssrf_guard.prepare_tools_post_url(
            "https://metadata.google.internal/", hosted=True
        )


def test_ssrf_guard_pins_public_hostname(monkeypatch):
    from worker import ssrf_guard

    monkeypatch.setattr(
        ssrf_guard,
        "_resolve_ips",
        lambda host: ["93.184.216.34"],
    )
    pinned, headers = ssrf_guard.prepare_tools_post_url(
        "https://example.com/hooks/tool", hosted=True
    )
    assert "93.184.216.34" in pinned
    assert headers.get("Host") == "example.com"


def test_ssrf_guard_allows_loopback_when_not_hosted():
    from worker import ssrf_guard

    url, headers = ssrf_guard.prepare_tools_post_url(
        "http://127.0.0.1:9911/tool", hosted=False
    )
    assert url.startswith("http://127.0.0.1")
    assert headers == {}
