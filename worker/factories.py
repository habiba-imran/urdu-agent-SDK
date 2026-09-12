"""Session component factories — THIN BACKWARD-COMPATIBLE WRAPPERS.

Phase 2 of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036): the real STT/LLM/TTS
logic moved to worker/providers/ (registry + per-provider adapters), which is what
worker/main.py::build_session() calls now. This module is kept, unchanged in signature, ONLY
because `scripts/probe_soniox_402.py` and `scratch/test_tts_resilient.py` still import it directly
— deleting it would break those two working scripts for no reason within this phase's scope.

Deliberately NOT duplicated logic: every function below just resolves the same env vars the
original did and delegates to the matching worker/providers/ adapter, so there is exactly one
place (the adapter) that can drift from the real behavior — not two copies that can silently
diverge (the exact class of bug flagged in this plan's Phase 0 audit, finding #5).
"""

from __future__ import annotations

import os


def make_tts(voice_id: str):
    """Uplift TTS — delegates to worker.providers.tts.uplift.build(). See that module for the
    real fixture/record/live logic and the phrase-replacement-config resolution."""
    from .providers.tts.uplift import build

    return build(voice_id)


def make_stt():
    """STT behind STT_PROVIDER: gladia (default) | soniox | deepgram — delegates to the matching
    worker.providers.stt.* adapter with language="ur" (this function never took a language
    parameter, so "ur" preserves the exact original behavior).

    P3-T05 acceptance: STT_PROVIDER=soniox must fail with 402 payment-required (needs funds), NOT an
    ImportError — proving the seam is one env var. That check is a live call, human-approved.
    """
    provider = os.getenv("STT_PROVIDER", "gladia").lower()
    if provider == "soniox":
        from .providers.stt.soniox import build

        return build()
    if provider == "deepgram":
        from .providers.stt.deepgram import build

        return build("ur")
    from .providers.stt.gladia import build

    return build("ur")


def make_llm(model: str):
    """Google Gemini, BYO key — delegates to worker.providers.llm.gemini.build()."""
    from .providers.llm.gemini import build

    return build(model)
