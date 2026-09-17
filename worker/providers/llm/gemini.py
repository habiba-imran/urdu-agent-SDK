"""Gemini LLM adapter — moved verbatim from worker/factories.py::make_llm()
(Phase 2, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

``getProviderCapabilities()`` still advertises ``gemini-2.5-flash``. Google retires
model IDs frequently, so the worker remaps to a live flash model (default
``gemini-3.6-flash``). LiveKit's default generateContent timeout is 10s and 504'd in
the client demo, so we set a 30s request timeout and disable thinking on the voice path.

Gemini 3 does **not** honor ``thinking_budget`` — LiveKit logs a warning and ignores it
unless ``thinking_level`` is set (``minimal`` / ``low`` / …). English PSTN additionally
remaps Gemini → Groq (see ``force_groq_for_telephony``) because 3.6 Flash TTFT stays
multi-second even with minimal thinking.

Phase 5E A/B (defaults unchanged until TTFT + listening pass):
  - ``GEMINI_LLM_MODEL`` — remaps deprecated IDs and fills empty model (existing)
  - ``GEMINI_THINKING_LEVEL`` — ``minimal`` (default) | ``low`` | ``medium`` | ``high``
    for Gemini 3 only. Does **not** change ``temperature`` / ``max_output_tokens``
    (research: do not copy sampling settings blindly into 3.8).
"""

from __future__ import annotations

import os
from typing import Any

_DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_LLM_MODEL", "gemini-3.6-flash")
_DEPRECATED_GEMINI_MODELS = {
    # Google retires model IDs frequently; keep voice path on a live flash model.
    # gemini-2.0-flash / 2.5-flash returned 404 for new keys (2026-09).
    "gemini-2.5-flash": _DEFAULT_GEMINI_MODEL,
    "gemini-2.5-flash-lite": _DEFAULT_GEMINI_MODEL,
    "gemini-3.1-flash-lite": _DEFAULT_GEMINI_MODEL,
    "gemini-2.0-flash": _DEFAULT_GEMINI_MODEL,
    "gemini-2.0-flash-lite": _DEFAULT_GEMINI_MODEL,
}

_THINKING_LEVELS = frozenset({"minimal", "low", "medium", "high"})


def _resolve_thinking_level() -> str:
    raw = (os.getenv("GEMINI_THINKING_LEVEL") or "minimal").strip().lower()
    if raw not in _THINKING_LEVELS:
        return "minimal"
    return raw


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
        # Voice turns: shorter, more deterministic completions reduce TTFT variance.
        # Phase 5E: keep these fixed when A/B'ing thinking_level or 3.8 model ids.
        "temperature": 0.4,
        "max_output_tokens": 256,
    }
    # Gemini 3: only thinking_level is honored (budget is ignored with a plugin warning).
    # Gemini 2.5 and earlier: thinking_budget=0 disables thinking.
    if "gemini-3" in resolved_model.lower():
        level = _resolve_thinking_level()
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=level)
    else:
        try:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass
    return google.LLM(**kwargs)
