"""Gemini LLM adapter — moved verbatim from worker/factories.py::make_llm()
(Phase 2, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036). Zero logic change.
"""

from __future__ import annotations

import os
from typing import Any

_DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_LLM_MODEL", "gemini-3.1-flash-lite")
_DEPRECATED_GEMINI_MODELS = {
    "gemini-2.5-flash": _DEFAULT_GEMINI_MODEL,
}


def build(model: str) -> Any:
    """Google Gemini, BYO key. NOT LiveKit Inference — its concurrency cap sits below the
    agent-session cap and would become the real ceiling (docs/23-PHASE-3-WORKER.md)."""
    from livekit.plugins import google

    resolved_model = _DEPRECATED_GEMINI_MODELS.get(
        model, model or _DEFAULT_GEMINI_MODEL
    )
    return google.LLM(model=resolved_model)
