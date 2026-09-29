"""F-H8 — SSRF protection on tenant-supplied tool gateway URLs.

The worker POSTs to this URL from inside the platform network with the tenant's
`x-tool-gateway-secret`. The validator claimed to be "SSRF-aware" while checking only the
scheme, credentials and query string, so cloud metadata, loopback and private ranges were
all accepted targets.

Hosted behaviour is what matters; local development deliberately stays permissive so a
developer can point an agent at a tool server on their own machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from tenant_portal_api.tools_webhook import (  # noqa: E402
    ToolsWebhookError,
    normalize_tools_base_url,
)


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setenv("UVA_ENV", "production")


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setenv("UVA_ENV", "development")


BLOCKED_WHEN_HOSTED = [
    # The one that matters most: cloud instance metadata.
    "http://169.254.169.254/latest/meta-data/",
    "https://169.254.169.254/",
    "https://metadata.google.internal/computeMetadata/v1/",
    # Loopback, in several spellings.
    "https://127.0.0.1/hook",
    "https://127.1/hook",
    "https://[::1]/hook",
    "https://localhost/hook",
    # RFC1918.
    "https://10.0.0.5/hook",
    "https://172.16.4.2/hook",
    "https://192.168.1.10/hook",
    # Internal naming.
    "https://payments.internal/hook",
    "https://db.svc.cluster.local/hook",
    "https://intranet/hook",
    # Unspecified address.
    "https://0.0.0.0/hook",
]


@pytest.mark.parametrize("url", BLOCKED_WHEN_HOSTED)
def test_internal_targets_are_refused_when_hosted(hosted, url):
    with pytest.raises(ToolsWebhookError) as excinfo:
        normalize_tools_base_url(url)
    assert excinfo.value.status == 422


def test_plain_http_is_refused_when_hosted(hosted):
    """The gateway secret is sent on every request; http would put it on the wire."""
    with pytest.raises(ToolsWebhookError) as excinfo:
        normalize_tools_base_url("http://api.example.com/uva")
    assert "https" in excinfo.value.reason


def test_a_normal_public_https_url_is_accepted(hosted):
    assert (
        normalize_tools_base_url("https://api.example.com/uva/")
        == "https://api.example.com/uva"
    )


def test_credentials_and_query_are_still_refused(hosted):
    for bad in (
        "https://user:pass@api.example.com/uva",
        "https://api.example.com/uva?token=abc",
        "https://api.example.com/uva#frag",
        "ftp://api.example.com/uva",
    ):
        with pytest.raises(ToolsWebhookError):
            normalize_tools_base_url(bad)


def test_local_development_may_use_localhost(local):
    assert normalize_tools_base_url("http://localhost:3000/api/tools") == (
        "http://localhost:3000/api/tools"
    )
    assert normalize_tools_base_url("http://127.0.0.1:3000") == "http://127.0.0.1:3000"


def test_empty_and_none_still_clear_the_setting(hosted):
    assert normalize_tools_base_url(None) is None
    assert normalize_tools_base_url("   ") is None


def test_overlong_url_is_refused(hosted):
    with pytest.raises(ToolsWebhookError):
        normalize_tools_base_url("https://api.example.com/" + "a" * 4000)
