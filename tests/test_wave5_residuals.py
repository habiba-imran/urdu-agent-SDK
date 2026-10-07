"""Wave 5 — residual mediums: P4-M3, P1-M1/M2/M4, P3-H2, P2-C1 (no network)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def test_db_reset_refuses_without_allow_flag(monkeypatch):
    """P4-M3: accidental wipe is refused unless ALLOW_DB_RESET is set."""
    monkeypatch.delenv("ALLOW_DB_RESET", raising=False)
    monkeypatch.delenv("UVA_ENV", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    import db_reset

    importlib.reload(db_reset)
    with pytest.raises(SystemExit) as excinfo:
        db_reset._assert_reset_allowed()
    assert "ALLOW_DB_RESET" in str(excinfo.value)


def test_db_reset_refuses_when_hosted(monkeypatch):
    monkeypatch.setenv("ALLOW_DB_RESET", "1")
    monkeypatch.setenv("UVA_ENV", "production")
    import db_reset

    importlib.reload(db_reset)
    with pytest.raises(SystemExit) as excinfo:
        db_reset._assert_reset_allowed()
    assert "hosted" in str(excinfo.value).lower() or "migrate" in str(excinfo.value).lower()


def test_db_reset_allows_local_dev(monkeypatch):
    monkeypatch.setenv("ALLOW_DB_RESET", "1")
    monkeypatch.setenv("UVA_ENV", "development")
    monkeypatch.delenv("RENDER", raising=False)
    import db_reset

    importlib.reload(db_reset)
    db_reset._assert_reset_allowed()  # must not raise


def test_tools_webhook_pair_requires_secret():
    """P1-M4: portal save rejects tools_base_url without secret."""
    from tenant_portal_api.tools_webhook import (
        ToolsWebhookError,
        assert_tools_webhook_pair,
    )

    assert_tools_webhook_pair(None, None)
    assert_tools_webhook_pair(None, "secret")
    assert_tools_webhook_pair("https://api.example.com/uva", "secret")
    with pytest.raises(ToolsWebhookError) as excinfo:
        assert_tools_webhook_pair("https://api.example.com/uva", None)
    assert excinfo.value.code == "tools_auth_secret_required"


def test_worker_refuses_tools_call_without_secret(monkeypatch):
    """P1-M4: worker never POSTs tenant IDs without a gateway secret."""
    import asyncio
    from types import SimpleNamespace

    from worker import tools as tools_mod

    ctx = SimpleNamespace(
        userdata=SimpleNamespace(
            tools_base_url="https://api.example.com/uva",
            tools_auth_secret=None,
            tenant_id="t1",
            agent_id="a1",
            latency_tracker=None,
        )
    )
    monkeypatch.delenv("TOOL_GATEWAY_SECRET", raising=False)
    monkeypatch.delenv("UVA_TOOLS_BASE_URL", raising=False)

    result = asyncio.run(
        tools_mod._post_client_tool(
            ctx, path="/lookup", payload={}, tool_name="lookup_customer"
        )
    )
    assert result.get("success") is False
    assert "tools_auth_secret" in result.get("error", "")


def test_webhook_insert_failure_aborts_side_effects(monkeypatch):
    """P3-H2: durable insert failure must not apply call-status side effects."""
    from tenant_portal_api import telephony_webhooks as hooks

    side_effects: list[str] = []

    class _BoomConn:
        def execute(self, sql, params=None):
            low = " ".join(sql.lower().split())
            if "insert into telephony_webhook_claims" in low:

                class _Claimed:
                    def fetchone(self):
                        return ("evt-1",)

                return _Claimed()
            if "from telephony_call_events" in low and "provider_event_id" in low:

                class _Empty:
                    def fetchone(self):
                        return None

                return _Empty()
            if "from telephony_calls" in low:

                class _Match:
                    def fetchone(self):
                        return ("call-1", "tenant-1")

                return _Match()
            if "insert into telephony_call_events" in low:
                raise RuntimeError("unique index missing")
            raise AssertionError(f"unexpected sql: {sql}")

        def commit(self):
            raise AssertionError("commit must not run after insert failure")

    class _Ctx:
        def __enter__(self):
            return _BoomConn()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        hooks.psycopg,
        "connect",
        lambda **kwargs: _Ctx(),
    )
    monkeypatch.setattr(
        hooks,
        "_apply_webhook_side_effects",
        lambda *a, **k: side_effects.append("applied"),
    )

    with pytest.raises(RuntimeError, match="unique index"):
        hooks._persist_telnyx_webhook_event(
            "evt-1",
            "call.hangup",
            {"data": {"payload": {"call_control_id": "cc-1"}}},
        )
    assert side_effects == []


def test_client_docs_no_longer_point_at_deleted_trees():
    """P2-C1: CLIENT_* guides must not send engineers to examples/ or demo-app/."""
    banned = ("examples/host-backend", "examples/web-client", "demo-app/")
    required = "client-deliverables-final"
    for name in (
        "CLIENT_QUICKSTART.md",
        "CLIENT_HANDOFF_GUIDE.md",
        "CLIENT_ONBOARDING_EMAIL_TEMPLATE.md",
    ):
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert required in text, name
        for bad in banned:
            assert bad not in text, f"{name} still references {bad}"
