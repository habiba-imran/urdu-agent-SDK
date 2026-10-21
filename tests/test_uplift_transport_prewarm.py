"""Uplift TTS transport warm-up (L-01 / L-02, docs/LATENCY_AUDIT_2026_10_21.md).

``worker/latency.py:prewarm_tts`` duck-types ``prewarm`` and
``wire_interruption_tts_prewarm`` duck-types ``prewarm_after_interruption``. Before this,
only Cartesia implemented either, so the Urdu path silently got no warm-up and the first
utterance of every call paid websocket setup.

These tests exercise the real adapter against a fake plugin module, so they assert the
contract the worker relies on (hook exists, is awaited, never raises, never blocks) rather
than the plugin's internals.
"""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

import worker.providers.tts.uplift as uplift


class _FakeWebSocketClient:
    """Stands in for livekit-plugins-upliftai's socket.io client."""

    instances: list["_FakeWebSocketClient"] = []

    def __init__(self, opts):
        self.opts = opts
        self.connected = False
        self.connect_calls = 0
        self.fail = False
        self.hang = False
        _FakeWebSocketClient.instances.append(self)

    async def connect(self) -> bool:
        self.connect_calls += 1
        if self.hang:
            await asyncio.sleep(30)
        if self.fail:
            return False
        self.connected = True
        return True


class _FakeBaseTTS:
    """Minimal stand-in for ``upliftai.TTS``."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._opts = SimpleNamespace(voice_id=kwargs.get("voice_id"))
        self._client = None
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_plugin(monkeypatch):
    """Install a fake ``livekit.plugins.upliftai`` whose internals match 1.6.5's shape."""
    _FakeWebSocketClient.instances = []

    plugin_tts = ModuleType("livekit.plugins.upliftai.tts")
    plugin_tts.WebSocketClient = _FakeWebSocketClient
    package = ModuleType("livekit.plugins.upliftai")
    package.TTS = _FakeBaseTTS
    package.tts = plugin_tts

    monkeypatch.setitem(sys.modules, "livekit.plugins.upliftai", package)
    monkeypatch.setitem(sys.modules, "livekit.plugins.upliftai.tts", plugin_tts)
    return package


def _build(fake_plugin):
    return uplift._build_prewarmable(fake_plugin, voice_id="v_test", output_format="PCM_22050_16")


def test_adapter_exposes_the_hooks_the_worker_duck_types(fake_plugin):
    tts = _build(fake_plugin)
    # These exact names are what worker/latency.py looks for; a rename silently
    # disables warm-up, which is the bug this file exists to prevent.
    assert callable(getattr(tts, "prewarm", None))
    assert callable(getattr(tts, "prewarm_after_interruption", None))
    assert callable(getattr(tts, "cancel_interruption_prewarm", None))


def test_prewarm_opens_the_socket_before_any_synthesis(fake_plugin):
    tts = _build(fake_plugin)
    asyncio.run(tts.prewarm())

    assert len(_FakeWebSocketClient.instances) == 1
    client = _FakeWebSocketClient.instances[0]
    assert client.connect_calls == 1
    assert client.connected is True
    # The plugin reuses whatever is on _client, so the warm socket is the one used.
    assert tts._client is client


def test_prewarm_is_idempotent_and_reuses_the_same_client(fake_plugin):
    tts = _build(fake_plugin)

    async def run() -> None:
        await tts.prewarm()
        await tts.prewarm()

    asyncio.run(run())
    assert len(_FakeWebSocketClient.instances) == 1


def test_prewarm_never_raises_when_the_handshake_fails(fake_plugin):
    tts = _build(fake_plugin)

    async def run() -> None:
        await tts.prewarm()

    _FakeWebSocketClient.instances = []

    class Failing(_FakeWebSocketClient):
        async def connect(self) -> bool:
            self.connect_calls += 1
            raise OSError("handshake refused")

    fake_plugin.tts.WebSocketClient = Failing
    # A failed warm-up must leave the greeting alone; synthesis builds its own client.
    asyncio.run(run())


def test_prewarm_is_bounded_so_a_hung_handshake_cannot_delay_the_greeting(fake_plugin):
    tts = _build(fake_plugin)

    class Hanging(_FakeWebSocketClient):
        def __init__(self, opts):
            super().__init__(opts)
            self.hang = True

    fake_plugin.tts.WebSocketClient = Hanging

    async def run() -> float:
        loop = asyncio.get_running_loop()
        started = loop.time()
        await tts.prewarm()
        return loop.time() - started

    # 12s internal bound (above the plugin's own 5s wait); 30s means the bound was lost.
    # The greeting itself is protected by await_greeting_prewarm's shielded 5s wait.
    assert asyncio.run(run()) < 20


def test_prewarm_degrades_to_a_noop_if_the_plugin_renames_its_internals(fake_plugin):
    tts = _build(fake_plugin)
    del fake_plugin.tts.WebSocketClient

    asyncio.run(tts.prewarm())
    assert tts._client is None


def test_interruption_rewarm_reconnects_only_when_the_socket_is_gone(fake_plugin):
    tts = _build(fake_plugin)

    async def run() -> None:
        await tts.prewarm()
        client = _FakeWebSocketClient.instances[0]

        # Still connected: must not churn the transport.
        tts.prewarm_after_interruption()
        assert tts._interruption_warm_task is None
        assert client.connect_calls == 1

        # Dropped socket: reconnect in the background without blocking the turn.
        client.connected = False
        tts.prewarm_after_interruption()
        assert tts._interruption_warm_task is not None
        await tts._interruption_warm_task
        assert client.connect_calls == 2
        assert client.connected is True

    asyncio.run(run())


def test_aclose_cancels_a_pending_rewarm_and_closes_the_base(fake_plugin):
    tts = _build(fake_plugin)

    async def run() -> None:
        await tts.prewarm()
        _FakeWebSocketClient.instances[0].connected = False
        _FakeWebSocketClient.instances[0].hang = True
        tts.prewarm_after_interruption()
        await tts.aclose()

    asyncio.run(run())
    assert tts.closed is True
    assert tts._closing is True
    assert tts._interruption_warm_task.done()


def test_closing_suppresses_further_warm_up(fake_plugin):
    tts = _build(fake_plugin)

    async def run() -> None:
        await tts.aclose()
        await tts.prewarm()

    asyncio.run(run())
    # No client built after close — a late warm-up must not resurrect the transport.
    assert not _FakeWebSocketClient.instances


def test_build_returns_a_prewarmable_tts_in_live_mode(fake_plugin, monkeypatch):
    """The contract that actually matters: what ``build()`` hands the session.

    ``build()`` does ``from livekit.plugins import upliftai``, which resolves the
    *attribute* on the already-imported package — a ``sys.modules`` entry alone does not
    intercept it (the same trap that makes four latency tests fail only in a full-suite
    run, OB-F13). So patch the attribute too, or this test passes while ``build()``
    quietly returns a bare TTS with no warm-up hooks.
    """
    import livekit.plugins

    monkeypatch.setattr(livekit.plugins, "upliftai", fake_plugin, raising=False)
    monkeypatch.setenv("UPLIFT_MODE", "live")
    monkeypatch.setenv("UPLIFT_DISABLE_PHRASE_CONFIG", "1")

    tts = uplift.build("v_test")

    assert callable(getattr(tts, "prewarm", None)), "build() lost the warm-up hooks"
    assert callable(getattr(tts, "prewarm_after_interruption", None))
    asyncio.run(tts.prewarm())
    assert _FakeWebSocketClient.instances[0].connected is True


def test_build_tolerates_a_non_class_tts_double(monkeypatch):
    """``upliftai.TTS`` replaced by a plain callable must still construct.

    tests/test_humanization_batch_b.py patches it with a lambda to capture constructor
    kwargs. Subclassing a lambda raises ``TypeError: function() argument 'code' must be
    code, not str``, so the wrapper has to fall back to calling it directly and simply go
    without warm-up.
    """
    captured: list[dict] = []
    fake = SimpleNamespace(TTS=lambda **kw: captured.append(kw))

    uplift._build_prewarmable(fake, voice_id="v", output_format="PCM_22050_16")

    assert captured == [{"voice_id": "v", "output_format": "PCM_22050_16"}]
