"""Unit tests for tenant_portal_api.tools_webhook."""

import pytest

from tenant_portal_api.tools_webhook import (
    ToolsWebhookError,
    normalize_tools_auth_secret,
    normalize_tools_base_url,
)


def test_normalize_tools_base_url_strips_slash():
    assert (
        normalize_tools_base_url("https://api.example.com/uva/")
        == "https://api.example.com/uva"
    )


def test_normalize_tools_base_url_allows_localhost_http():
    assert normalize_tools_base_url("http://localhost:3001") == "http://localhost:3001"


def test_normalize_tools_base_url_rejects_bad_scheme():
    with pytest.raises(ToolsWebhookError) as exc:
        normalize_tools_base_url("ftp://evil.example.com")
    assert exc.value.code == "invalid_tools_base_url"


def test_normalize_tools_base_url_rejects_embedded_creds():
    with pytest.raises(ToolsWebhookError):
        normalize_tools_base_url("https://user:pass@api.example.com")


def test_normalize_tools_auth_secret_blank_is_none():
    assert normalize_tools_auth_secret("  ") is None
    assert normalize_tools_auth_secret(None) is None
