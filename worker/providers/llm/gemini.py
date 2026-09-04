"""Gemini LLM adapter — moved verbatim from worker/factories.py::make_llm()
(Phase 2, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

``getProviderCapabilities()`` still advertises ``gemini-2.5-flash``. Google has retired
that ID for new API keys, so the worker remaps it to a live model. Isolated ``llm.chat()``
calls return in ~2–3s; the LiveKit generateContent stream used a 10s HTTP timeout and
504'd in the client demo, so we set a 30s request timeout and pin Gemini 3 thinking to
``minimal``.
"""

from __future__ import annotations

import os
from typing import Any

_DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_LLM_MODEL", "gemini-3.1-flash-lite")
_DEPRECATED_GEMINI_MODELS = {
    "gemini-2.5-flash": _DEFAULT_GEMINI_MODEL,
    "gemini-2.0-flash": _DEFAULT_GEMINI_MODEL,
}


def build(model: str) -> Any:
    """Google Gemini, BYO key. NOT LiveKit Inference — its concurrency cap sits below the
    agent-session cap and would become the real ceiling (docs/23-PHASE-3-WORKER.md)."""
    from google.genai import types
    from livekit.plugins import google

    resolved_model = _DEPRECATED_GEMINI_MODELS.get(
        model, model or _DEFAULT_GEMINI_MODEL
    )
    kwargs: dict[str, Any] = {
        "model": resolved_model,
        # livekit-plugins-google copies this onto generateContent; LiveKit's default
        # conn_options.timeout is 10s and produced DEADLINE_EXCEEDED in the demo.
        "http_options": types.HttpOptions(timeout=30_000),
    }
    # Voice path: no reasoning/thinking — keeps TTFT within budget (UVA-7).
    if "gemini-3" in resolved_model.lower():
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="minimal")
    else:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    return google.LLM(**kwargs)
