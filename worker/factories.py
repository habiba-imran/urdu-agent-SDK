"""Session component factories — provider selection behind env flags (docs/23-PHASE-3-WORKER.md).

Plugins are imported LAZILY so this module (and the config/usage tests) load without every provider
plugin installed and nothing touches the network at import. Real media wiring runs only in a live
session or against fixtures — never here.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

_DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_LLM_MODEL", "gemini-3.1-flash-lite")
_DEPRECATED_GEMINI_MODELS = {
    "gemini-2.5-flash": _DEFAULT_GEMINI_MODEL,
}


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _phrase_config_id() -> str | None:
    """Resolve an optional Uplift phrase replacement configId.

    Uplift config IDs are tied to the Uplift account/API key that created them. A committed
    `.uplift_phrase_config` can therefore become stale when the local `.env.local` key changes.
    Prefer an explicit environment variable; only use the checked-in file when opted in.
    """
    if _env_truthy("UPLIFT_DISABLE_PHRASE_CONFIG"):
        return None

    explicit = os.getenv("UPLIFT_PHRASE_CONFIG_ID")
    if explicit is not None:
        return explicit.strip() or None

    if not _env_truthy("UPLIFT_USE_PHRASE_CONFIG_FILE"):
        return None

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
                wav = _require(self._voice_id, self._input_text)
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

        return upliftai.TTS(
            voice_id=voice_id,
            output_format="PCM_22050_16",
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

    # code_switching EXPLICIT False — the livekit-plugins-gladia STT() constructor default is
    # actually True (gladia/stt.py L211); it's functionally moot here since Gladia's own API
    # docs say a single-element `languages` list makes the setting ignored server-side, but
    # leaving it implicit was fragile: if this ever grows a second language, the plugin default
    # would silently re-enable code_switching. D19 (ported DECISIONS.md) measured CER 0.14
    # ur-only vs 0.43 with ur+en code_switching=True on the OLD raw-Gladia-WebSocket
    # integration — checked 2026-07-17 against Gladia's current docs/changelog for a material
    # change since: none found for Urdu specifically (Solaria-3, June 2026, and the Hebrew
    # upgrade, March 2026, are the only recent model-accuracy changelog entries, both unrelated
    # to Urdu; docs.gladia.io/chapters/language/code-switching still warns broad language sets
    # cause "frequent misdetections"). See docs/40-ADR.md ADR-009.
    return gladia.STT(languages=["ur"], code_switching=False)


def make_llm(model: str):
    """Google Gemini, BYO key. NOT LiveKit Inference — its concurrency cap sits below the
    agent-session cap and would become the real ceiling (docs/23-PHASE-3-WORKER.md)."""
    from livekit.plugins import google

    resolved_model = _DEPRECATED_GEMINI_MODELS.get(model, model or _DEFAULT_GEMINI_MODEL)
    return google.LLM(model=resolved_model)
