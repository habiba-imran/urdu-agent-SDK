"""Uplift TTS adapter — moved from worker/factories.py::make_tts()
(Phase 2, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Phrase-replacement config (Phase 4 humanization):
  UPLIFT_PHRASE_CONFIG_ID          preferred — account-scoped config id
  UPLIFT_USE_PHRASE_CONFIG_FILE=1  optional fallback to repo ``.uplift_phrase_config``
  UPLIFT_DISABLE_PHRASE_CONFIG=1   force off

Tenant/portal sync of phrase dictionaries is not wired yet — ops set the env id to match
the Uplift account that owns the worker API key.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("worker.providers.tts.uplift")


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_uplift_phrase_config_id() -> str | None:
    """Resolve an optional Uplift phrase replacement configId.

    Uplift config IDs are tied to the Uplift account/API key that created them. A committed
    ``.uplift_phrase_config`` can therefore become stale when the local ``.env.local`` key
    changes. Prefer an explicit environment variable; only use the checked-in file when
    opted in.
    """
    if _env_truthy("UPLIFT_DISABLE_PHRASE_CONFIG"):
        return None

    explicit = os.getenv("UPLIFT_PHRASE_CONFIG_ID")
    if explicit is not None:
        return explicit.strip() or None

    if not _env_truthy("UPLIFT_USE_PHRASE_CONFIG_FILE"):
        return None

    cfg_path = (
        Path(__file__).resolve().parent.parent.parent.parent / ".uplift_phrase_config"
    )
    if cfg_path.exists():
        raw = cfg_path.read_text(encoding="utf-8").strip()
        return raw or None
    return None


# Backward-compatible private alias (tests / older imports).
_phrase_config_id = resolve_uplift_phrase_config_id


def build(voice_id: str, *, rendered_identity: str | None = None) -> Any:
    """Uplift TTS. UPLIFT_MODE=fixture (default) replays committed fixtures; record/live call Uplift.

    Fixture mode delegates to FixtureTTS, which reads from services/tts_cache.py.  A cache miss
    is a hard LookupError — never a silent live call.  Record/live mode creates a real
    livekit-plugins-upliftai TTS instance.
    """
    mode = os.getenv("UPLIFT_MODE", "fixture")
    phrase_id = resolve_uplift_phrase_config_id()
    if phrase_id:
        logger.info(
            "uplift phrase_replacement_config_id=%s mode=%s voice=%s",
            phrase_id,
            mode,
            voice_id,
        )
    elif mode in ("record", "live"):
        logger.info(
            "uplift phrase_replacement_config_id unset mode=%s "
            "(set UPLIFT_PHRASE_CONFIG_ID for brand/pronunciation replacements)",
            mode,
        )

    if mode == "fixture":
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
        from services.tts_cache import require as _require  # noqa: E402

        # register_fixture_tts – we define the adapter inline so the LiveKit import
        # stays lazy (only loaded inside the FixtureTTS class body).
        from livekit.agents.tts import TTS, ChunkedStream, TTSCapabilities  # noqa: E402
        from livekit.agents import APIConnectOptions  # noqa: E402

        _default_conn = APIConnectOptions(max_retry=0)

        class FixtureTTS(TTS):
            def __init__(self):
                super().__init__(
                    capabilities=TTSCapabilities(streaming=False),
                    sample_rate=22050,
                    num_channels=1,
                )

            def synthesize(self, text, *, conn_options=None):
                return _FixtureChunkedStream(
                    tts=self,
                    input_text=text,
                    conn_options=conn_options or _default_conn,
                    voice_id=voice_id,
                )

        class _FixtureChunkedStream(ChunkedStream):
            def __init__(self, *, tts, input_text, conn_options, voice_id):
                super().__init__(
                    tts=tts, input_text=input_text, conn_options=conn_options
                )
                self._voice_id = voice_id

            async def _run(self, output_emitter):
                wav = (
                    _require(self._voice_id, self._input_text, rendered_identity=rendered_identity)
                    if rendered_identity is not None else _require(self._voice_id, self._input_text)
                )
                sample_rate = 22050
                num_channels = 1
                pcm = wav[44:]
                request_id = str(uuid.uuid4())
                output_emitter.initialize(
                    request_id=request_id,
                    sample_rate=sample_rate,
                    num_channels=num_channels,
                    mime_type="audio/pcm",
                )
                output_emitter.push(pcm)
                output_emitter.flush()
                output_emitter.end_input()
                await output_emitter.join()

        return FixtureTTS()

    if mode in ("record", "live"):
        from livekit.plugins import upliftai

        return _build_prewarmable(
            upliftai,
            voice_id=voice_id,
            output_format="PCM_22050_16",
            phrase_replacement_config_id=phrase_id,
        )


def _build_prewarmable(upliftai: Any, **kwargs: Any) -> Any:
    """Uplift TTS that opens its websocket before the first utterance.

    ``worker/latency.py:prewarm_tts`` duck-types a ``prewarm`` attribute, and
    ``wire_interruption_tts_prewarm`` duck-types ``prewarm_after_interruption``. Cartesia
    implemented both; this adapter implemented neither, so warm-up found nothing, returned
    immediately and logged success while the first Urdu utterance of every call paid full
    connection setup.

    Measured against the Uplift REST streaming endpoint on 2026-10-21: first byte cost
    ~1.0-1.5s cold, and ~1.23s again whenever requests were 6s apart — i.e. at
    conversational spacing a per-request connection is always cold. Back-to-back requests
    reached ~350ms, which is why a naive benchmark makes this look solved.

    livekit-plugins-upliftai==1.6.5 avoids that by holding one socket.io connection
    (``WebSocketClient``) for the whole session, but it constructs it lazily inside the
    first ``synthesize`` call. Opening it during the greeting window moves that cost off
    the first reply, and keeping it open keeps it off every later reply.

    Everything here is best-effort: ``connect()`` is idempotent and returns a bool rather
    than raising, and any failure must leave synthesis to construct the client itself as
    before. Warm-up never blocks or breaks the greeting.
    """
    import asyncio

    base = getattr(upliftai, "TTS", None)
    if not isinstance(base, type):
        # ``upliftai.TTS`` is not a class — a test double or a plugin shape we do not
        # recognise. Subclassing it would raise, so construct exactly as before and go
        # without warm-up rather than break the caller.
        logger.debug("Uplift prewarm unavailable: TTS is %s, not a class", type(base).__name__)
        return base(**kwargs)

    class PrewarmableUpliftTTS(base):
        _interruption_warm_task: asyncio.Task | None = None
        _closing = False

        def _ws_client(self) -> Any | None:
            """Existing socket.io client, constructing one if the plugin has not yet.

            Reaches into plugin internals (``_client`` / ``_opts``), as the Cartesia
            adapter does with ``_pool``. Guarded so a plugin upgrade that renames either
            degrades to "no warm-up" instead of failing the call.
            """
            client = getattr(self, "_client", None)
            if client is not None:
                return client
            opts = getattr(self, "_opts", None)
            try:
                from livekit.plugins.upliftai import tts as _plugin_tts
            except Exception:
                return None
            factory = getattr(_plugin_tts, "WebSocketClient", None)
            if opts is None or factory is None:
                return None
            client = factory(opts)
            self._client = client
            return client

        async def prewarm(self) -> None:
            if self._closing:
                return
            try:
                client = self._ws_client()
                if client is None:
                    logger.debug("Uplift prewarm unavailable: plugin internals changed")
                    return
                # The plugin's own connect() waits up to 5s for the socket and passes
                # wait_timeout=10 to socket.io, so a tighter bound here would cancel
                # handshakes that were about to succeed and leak the half-built client
                # (a later connect() replaces self.sio without disconnecting it).
                # The greeting is already protected: await_greeting_prewarm wraps this
                # task in asyncio.shield with its own 5s timeout, so the opening proceeds
                # on time and a slow handshake keeps warming in the background for the
                # turns that follow — which is where most of the saving is.
                connected = await asyncio.wait_for(client.connect(), timeout=12.0)
                logger.debug("Uplift transport prewarm connected=%s", bool(connected))
            except Exception as exc:
                logger.warning(
                    "Uplift prewarm unavailable error_type=%s", type(exc).__name__
                )

        def prewarm_after_interruption(self) -> None:
            """Re-open the socket after a barge-in, without blocking the next turn.

            A 6s-spaced experiment found aborted and fully-drained REST streams
            indistinguishable (~1.3s vs ~1.2s first byte), so an interrupted *request*
            does not appear to poison anything. This covers the different case the
            websocket path actually has: the shared socket being closed or dropped, after
            which the plugin would rebuild it inside the next utterance.
            """
            if self._closing:
                return
            task = self._interruption_warm_task
            if task is not None and not task.done():
                return
            client = getattr(self, "_client", None)
            if client is not None and getattr(client, "connected", False):
                return

            self._interruption_warm_task = asyncio.create_task(
                self.prewarm(), name="uplift_interruption_prewarm"
            )

        def cancel_interruption_prewarm(self) -> None:
            task = self._interruption_warm_task
            if task is not None and not task.done():
                task.cancel()

        async def aclose(self) -> None:
            self._closing = True
            self.cancel_interruption_prewarm()
            if self._interruption_warm_task is not None:
                await asyncio.gather(
                    self._interruption_warm_task, return_exceptions=True
                )
            await super().aclose()

    return PrewarmableUpliftTTS(**kwargs)
