"""Session component factories — provider selection behind env flags (docs/23-PHASE-3-WORKER.md).

Plugins are imported LAZILY so this module (and the config/usage tests) load without every provider
plugin installed and nothing touches the network at import. Real media wiring runs only in a live
session or against fixtures — never here.
"""

from __future__ import annotations

import os
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

    Fixture replay (a FixtureTTS reading services/tts_cache.py) is wired in P3-T04, once the
    reference fixture has been recorded (UPLIFT_MODE=record, human-approved) — until then there is
    nothing to replay, so fixture mode raises rather than silently returning a broken TTS.
    """
    mode = os.getenv("UPLIFT_MODE", "fixture")
    phrase_id = _phrase_config_id()
    if mode in ("record", "live"):
        from livekit.plugins import upliftai

        return upliftai.TTS(
            voice_id=voice_id,
            output_format="WAV_22050_16",
            phrase_replacement_config_id=phrase_id,
        )
    raise NotImplementedError(
        "FixtureTTS replay lands in P3-T04, after the reference fixture is recorded "
        "(human-approved). See services/tts_cache.py and scripts/record_fixture.py."
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
