"""M4-F03: LiveKit SIP client must pass an explicit HTTP timeout."""

from __future__ import annotations

from tenant_portal_api.livekit_sip import LiveKitSipClient


def test_livekit_api_uses_configured_timeout(monkeypatch):
    monkeypatch.setenv("LIVEKIT_HTTP_TIMEOUT_SEC", "7.5")
    client = LiveKitSipClient(
        url="https://example.livekit.cloud",
        api_key="key",
        api_secret="secret",
        mock_mode=False,
    )
    assert client.http_timeout_sec == 7.5

    captured: dict = {}

    class _FakeAPI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class _FakeTimeout:
        def __init__(self, *, total):
            self.total = total

    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientTimeout", _FakeTimeout)

    import livekit.api as lk

    monkeypatch.setattr(lk, "LiveKitAPI", _FakeAPI)

    api = client._livekit_api()
    assert isinstance(api, _FakeAPI)
    assert captured["timeout"].total == 7.5
