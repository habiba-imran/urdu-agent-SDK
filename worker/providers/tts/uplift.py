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


def build(voice_id: str) -> Any:
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
