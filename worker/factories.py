"""Session component factories — provider selection behind env flags (docs/23-PHASE-3-WORKER.md).

Plugins are imported LAZILY so this module (and the config/usage tests) load without every provider
plugin installed and nothing touches the network at import. Real media wiring runs only in a live
session or against fixtures — never here.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path


def _phrase_config_id() -> str | None:
    """Read the committed phrase replacement configId, if any."""
    cfg_path = Path(__file__).resolve().parent.parent / ".uplift_phrase_config"
    if cfg_path.exists():
        raw = cfg_path.read_text(encoding="utf-8").strip()
        return raw or None
    return None


def make_tts(voice_id: str):
    """Uplift TTS. UPLIFT_MODE=fixture (default) replays committed fixtures; record/live call Uplift.

    Fixture mode delegates to FixtureTTS, which reads from services/tts_cache.py.  A cache miss
    is a hard LookupError — never a silent live call.  Record/live mode creates a real
    livekit-plugins-upliftai TTS instance.
    """
    mode = os.getenv("UPLIFT_MODE", "fixture")
    phrase_id = _phrase_config_id()
    if mode == "fixture":
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from services.tts_cache import require as _require, key as _tts_key  # noqa: E402

        # register_fixture_tts – we define the adapter inline so the LiveKit import
        # stays lazy (only loaded inside the FixtureTTS class body).
        from livekit.agents.tts import TTS, ChunkedStream, SynthesizedAudio, TTSCapabilities  # noqa: E402
        from livekit.agents import APIConnectOptions  # noqa: E402
        from livekit import rtc  # noqa: E402

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
                    tts=self, input_text=text,
                    conn_options=conn_options or _default_conn,
                    voice_id=voice_id,
                )

        class _FixtureChunkedStream(ChunkedStream):
            def __init__(self, *, tts, input_text, conn_options, voice_id):
                super().__init__(tts=tts, input_text=input_text,
                                 conn_options=conn_options)
                self._voice_id = voice_id

            async def _run(self, output_emitter):
                wav = _require(self._voice_id, self._input_text)
                sample_rate = 22050
                num_channels = 1
                pcm = wav[44:]
                samples_per_channel = len(pcm) // (num_channels * 2)
                request_id = str(uuid.uuid4())
                output_emitter.initialize(
                    request_id=request_id,
                    sample_rate=sample_rate, num_channels=num_channels,
                    mime_type="audio/pcm",
                )
                output_emitter.push(pcm)
                output_emitter.flush()
                output_emitter.end_input()
                await output_emitter.join()

        return FixtureTTS()

    if mode in ("record", "live"):
        from livekit.plugins import upliftai

        return upliftai.TTS(
            voice_id=voice_id,
            output_format="WAV_22050_16",
            phrase_replacement_config_id=phrase_id,
        )


def make_stt():
    """STT behind STT_PROVIDER: gladia (default) | soniox | deepgram.

    P3-T05 acceptance: STT_PROVIDER=soniox must fail with 402 payment-required (needs funds), NOT an
    ImportError — proving the seam is one env var. That check is a live call, human-approved.
    """
    provider = os.getenv("STT_PROVIDER", "gladia").lower()
    if provider == "soniox":
        from livekit.plugins import soniox

        return soniox.STT()
    if provider == "deepgram":
        from livekit.plugins import deepgram

        return deepgram.STT(model="nova-3", language="ur")
    from livekit.plugins import gladia

    return gladia.STT(languages=["ur"])


def make_llm(model: str):
    """Google Gemini, BYO key. NOT LiveKit Inference — its concurrency cap sits below the
    agent-session cap and would become the real ceiling (docs/23-PHASE-3-WORKER.md)."""
    from livekit.plugins import google

    return google.LLM(model=model)
