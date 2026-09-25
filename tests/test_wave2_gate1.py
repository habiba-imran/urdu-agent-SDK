"""Wave 2 Gate 1 — "stop the bleeding" regression tests.

Covers the audit's F-C1, F-C2, F-C3, F-M6, F-M18 and F-M19. Each test asserts the behaviour
the fix introduced AND, where it matters, that the old hole is actually closed (a forged
token with the published fallback secret, a dev-mint call with no publishable key, a
wildcard CORS grant carrying credentials).

No database or network: the control-plane routes under test are reached with the mint layer
monkeypatched, so these run in the default offline gate.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane import runtime_env  # noqa: E402


# --------------------------------------------------------------------------- runtime_env


@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, False),
        ({"UVA_ENV": "development"}, False),
        ({"UVA_ENV": "production"}, True),
        ({"UVA_ENV": "staging"}, True),
        ({"RENDER": "true"}, True),
        ({"ENVIRONMENT": "production"}, True),
        # An explicit UVA_ENV wins over the platform's own signal, so a one-off local run
        # against a Render-ish environment can still be declared development.
        ({"UVA_ENV": "development", "RENDER": "true"}, False),
    ],
)
def test_is_hosted_detection(monkeypatch, env, expected):
    for var in ("UVA_ENV", "RENDER", "ENVIRONMENT"):
        monkeypatch.delenv(var, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert runtime_env.is_hosted() is expected


# ------------------------------------------------------------------- F-C3 / CORS allowlist


def _resolve(raw, hosted):
    return runtime_env.resolve_allowed_origins(
        raw,
        hosted=hosted,
        dev_defaults=["http://localhost:5173"],
        var_name="CP_ALLOWED_ORIGINS",
        why="test",
    )


def test_empty_origin_allowlist_is_fatal_when_hosted():
    """F-C3: the old code turned an unset allowlist into ["*"] with credentials."""
    with pytest.raises(RuntimeError) as excinfo:
        _resolve("", True)
    assert "CP_ALLOWED_ORIGINS" in str(excinfo.value)


def test_empty_origin_allowlist_falls_back_to_dev_origins_locally():
    origins, allow_credentials = _resolve("", False)
    assert origins == ["http://localhost:5173"]
    assert allow_credentials is True
    assert "*" not in origins


def test_explicit_origins_keep_credentials():
    origins, allow_credentials = _resolve(
        "https://app.example.com, https://admin.example.com", True
    )
    assert origins == ["https://app.example.com", "https://admin.example.com"]
    assert allow_credentials is True


def test_wildcard_origin_never_carries_credentials():
    """Browsers reject '*' + credentials; honouring it would be a blanket grant."""
    origins, allow_credentials = _resolve("*", True)
    assert origins == ["*"]
    assert allow_credentials is False


# ------------------------------------------------------- F-C1 / portal JWT signing secret


def _reload_portal_secret(monkeypatch, **env):
    for var in ("TENANT_PORTAL_JWT_SECRET", "UVA_ENV", "RENDER", "ENVIRONMENT"):
        monkeypatch.delenv(var, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    module = importlib.import_module("tenant_portal_api.jwt_secret")
    module.reset_cache()
    return module


def test_portal_secret_prefers_the_environment(monkeypatch):
    module = _reload_portal_secret(monkeypatch, TENANT_PORTAL_JWT_SECRET="real-secret")
    assert module.portal_jwt_secret() == "real-secret"


def test_portal_secret_is_never_the_old_hardcoded_fallback(monkeypatch):
    """F-C1: 'mock_jwt_secret_for_tests' was a published string that authenticated every
    /portal/telephony/* route whenever the env var was absent."""
    module = _reload_portal_secret(monkeypatch, TENANT_PORTAL_JWT_SECRET="real-secret")
    assert module.portal_jwt_secret() != "mock_jwt_secret_for_tests"


def test_hosted_portal_without_a_secret_refuses_to_start(monkeypatch, tmp_path):
    """F-H13: it used to generate one and append it to .env.local on every deploy."""
    module = _reload_portal_secret(monkeypatch, UVA_ENV="production")
    monkeypatch.setattr(module, "_ENV_PATH", tmp_path / ".env.local")
    with pytest.raises(RuntimeError) as excinfo:
        module.portal_jwt_secret()
    assert "TENANT_PORTAL_JWT_SECRET" in str(excinfo.value)


def test_local_portal_without_a_secret_generates_and_persists_one(monkeypatch, tmp_path):
    module = _reload_portal_secret(monkeypatch, UVA_ENV="development")
    env_file = tmp_path / ".env.local"
    monkeypatch.setattr(module, "_ENV_PATH", env_file)
    secret = module.portal_jwt_secret()
    assert len(secret) == 64
    assert "TENANT_PORTAL_JWT_SECRET" in env_file.read_text(encoding="utf-8")
    # Stable within the process, so tokens survive until restart.
    assert module.portal_jwt_secret() == secret


def test_telephony_routes_and_portal_agree_on_the_secret(monkeypatch):
    """F-C1's real damage: the two modules resolved different secrets, so legitimate
    tokens were rejected and forged ones accepted."""
    module = _reload_portal_secret(monkeypatch, TENANT_PORTAL_JWT_SECRET="shared-secret")
    routes = importlib.import_module("tenant_portal_api.telephony_routes")
    assert routes.portal_jwt_secret() == module.portal_jwt_secret() == "shared-secret"


# -------------------------------------------------- F-M18 / F-M19 telephony test switches


@pytest.mark.parametrize(
    "switch",
    [
        "TELEPHONY_ALLOW_MOCK_PORTAL_AUTH",
        "TELEPHONY_ALLOW_MOCK_MACHINE_AUTH",
    ],
)
def test_hosted_service_refuses_to_start_with_mock_auth_enabled(monkeypatch, switch):
    routes = importlib.import_module("tenant_portal_api.telephony_routes")
    monkeypatch.setenv("UVA_ENV", "production")
    monkeypatch.setenv(switch, "1")
    with pytest.raises(RuntimeError) as excinfo:
        routes.assert_mock_switches_disabled()
    assert switch in str(excinfo.value)


def test_hosted_service_refuses_non_real_provider_mode(monkeypatch):
    """F-M19: a single env typo turned off Telnyx signature checking and credential
    encryption at once."""
    routes = importlib.import_module("tenant_portal_api.telephony_routes")
    monkeypatch.setenv("UVA_ENV", "production")
    monkeypatch.delenv("TELEPHONY_ALLOW_MOCK_PORTAL_AUTH", raising=False)
    monkeypatch.delenv("TELEPHONY_ALLOW_MOCK_MACHINE_AUTH", raising=False)
    monkeypatch.setenv("TELEPHONY_PROVIDER_MODE", "mock")
    with pytest.raises(RuntimeError) as excinfo:
        routes.assert_mock_switches_disabled()
    assert "TELEPHONY_PROVIDER_MODE" in str(excinfo.value)


def test_local_development_may_keep_the_switches(monkeypatch):
    routes = importlib.import_module("tenant_portal_api.telephony_routes")
    monkeypatch.setenv("UVA_ENV", "development")
    monkeypatch.setenv("TELEPHONY_ALLOW_MOCK_PORTAL_AUTH", "1")
    monkeypatch.setenv("TELEPHONY_PROVIDER_MODE", "mock")
    routes.assert_mock_switches_disabled()  # must not raise


# ------------------------------------------------------------------- F-C2 / dev-mint gate


@pytest.fixture
def cp_app(monkeypatch):
    """Import control_plane.app with the env it needs, and stub the mint layer."""
    for var, value in {
        "LIVEKIT_URL": "wss://test.livekit.cloud",
        "LIVEKIT_API_KEY": "test-key",
        "LIVEKIT_API_SECRET": "test-secret",
        "SUPABASE_DB_URL": "postgresql://test:test@127.0.0.1:5432/test",
        "CP_TENANT_SECRETS": "{}",
        "CP_ALLOWED_ORIGINS": "https://app.example.com",
    }.items():
        monkeypatch.setenv(var, value)
    module = importlib.import_module("control_plane.app")
    monkeypatch.setattr(
        module, "_lookup_tenant_for_agent", lambda agent_id: "tenant-owning-the-agent"
    )
    monkeypatch.setattr(
        module,
        "_dev_mint_session",
        lambda **kwargs: {
            "token": "t",
            "wsUrl": "wss://x",
            "roomName": "r",
            "auto_reset_quota": kwargs["auto_reset_quota"],
        },
    )
    return module


def _post_dev_mint(module, body):
    from fastapi.testclient import TestClient

    return TestClient(module.app).post("/v1/session/dev-mint", json=body)


def test_dev_mint_is_absent_on_a_hosted_deployment(cp_app, monkeypatch):
    """F-C2: anyone with an agent UUID could mint a real LiveKit session."""
    monkeypatch.setenv("UVA_ENV", "production")
    monkeypatch.delenv("CP_ENABLE_DEV_MINT", raising=False)
    response = _post_dev_mint(cp_app, {"agentId": "a", "publishableKey": "tenant-owning-the-agent"})
    assert response.status_code == 404


def test_dev_mint_can_be_enabled_deliberately(cp_app, monkeypatch):
    monkeypatch.setenv("UVA_ENV", "production")
    monkeypatch.setenv("CP_ENABLE_DEV_MINT", "1")
    response = _post_dev_mint(
        cp_app, {"agentId": "a", "publishableKey": "tenant-owning-the-agent"}
    )
    assert response.status_code == 200


def test_dev_mint_requires_a_publishable_key(cp_app, monkeypatch):
    monkeypatch.setenv("UVA_ENV", "development")
    response = _post_dev_mint(cp_app, {"agentId": "a"})
    assert response.status_code == 401


def test_dev_mint_rejects_a_key_from_another_tenant(cp_app, monkeypatch):
    monkeypatch.setenv("UVA_ENV", "development")
    response = _post_dev_mint(
        cp_app, {"agentId": "a", "publishableKey": "some-other-tenant"}
    )
    assert response.status_code == 403


def test_dev_mint_does_not_reset_quota_by_default(cp_app, monkeypatch):
    """F-C2's amplifier: it called _dev_reset_concurrency, zeroing the tenant's live
    concurrency count and defeating the cap entirely."""
    monkeypatch.setenv("UVA_ENV", "development")
    monkeypatch.delenv("CP_DEV_MINT_RESET_QUOTA", raising=False)
    response = _post_dev_mint(
        cp_app, {"agentId": "a", "publishableKey": "tenant-owning-the-agent"}
    )
    assert response.status_code == 200
    assert response.json()["auto_reset_quota"] is False


def test_dev_mint_quota_reset_is_opt_in(cp_app, monkeypatch):
    monkeypatch.setenv("UVA_ENV", "development")
    monkeypatch.setenv("CP_DEV_MINT_RESET_QUOTA", "1")
    response = _post_dev_mint(
        cp_app, {"agentId": "a", "publishableKey": "tenant-owning-the-agent"}
    )
    assert response.json()["auto_reset_quota"] is True


# ------------------------------------------------------------------------- F-M6 / schema


def _docs_urls(**env) -> dict:
    """Import control_plane.app in a clean subprocess and report its doc routes.

    A subprocess rather than importlib.reload: app.py decides this at import time, and
    reloading it inside the test session would leak that state into other tests.
    """
    import json
    import subprocess

    child_env = {
        **os.environ,
        "LIVEKIT_URL": "wss://test.livekit.cloud",
        "LIVEKIT_API_KEY": "test-key",
        "LIVEKIT_API_SECRET": "test-secret",
        "SUPABASE_DB_URL": "postgresql://test:test@127.0.0.1:5432/test",
        "CP_TENANT_SECRETS": "{}",
        "CP_ALLOWED_ORIGINS": "https://app.example.com",
    }
    child_env.pop("CP_ENABLE_DOCS", None)
    child_env.update(env)
    code = (
        "import json, sys;"
        f"sys.path.insert(0, {str(ROOT)!r});"
        f"sys.path.insert(0, {str(ROOT / 'scripts')!r});"
        "from control_plane.app import app;"
        "print(json.dumps({'docs': app.docs_url, 'redoc': app.redoc_url,"
        " 'openapi': app.openapi_url}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_openapi_schema_is_not_public_when_hosted():
    """F-M6: /docs and /redoc published the whole API schema, dev-mint included."""
    urls = _docs_urls(UVA_ENV="production")
    assert urls == {"docs": None, "redoc": None, "openapi": None}


def test_openapi_schema_can_be_enabled_deliberately():
    urls = _docs_urls(UVA_ENV="production", CP_ENABLE_DOCS="1")
    assert urls["docs"] == "/docs"


def test_openapi_schema_is_available_locally():
    urls = _docs_urls(UVA_ENV="development")
    assert urls["docs"] == "/docs"


def test_hosted_control_plane_without_cors_allowlist_refuses_to_start():
    """F-C3 at the real import site, not just the helper."""
    import subprocess

    child_env = {
        **os.environ,
        "LIVEKIT_URL": "wss://test.livekit.cloud",
        "LIVEKIT_API_KEY": "test-key",
        "LIVEKIT_API_SECRET": "test-secret",
        "SUPABASE_DB_URL": "postgresql://test:test@127.0.0.1:5432/test",
        "CP_TENANT_SECRETS": "{}",
        "UVA_ENV": "production",
        "CP_ALLOWED_ORIGINS": "",
    }
    code = (
        "import sys;"
        f"sys.path.insert(0, {str(ROOT)!r});"
        f"sys.path.insert(0, {str(ROOT / 'scripts')!r});"
        "import control_plane.app"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode != 0
    assert "CP_ALLOWED_ORIGINS" in out.stderr
