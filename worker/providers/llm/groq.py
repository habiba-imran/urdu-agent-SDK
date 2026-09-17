"""Groq LLM adapter (Phase 6b, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py is the gate, not this
file. `model` constructor arg verified directly against the installed livekit-plugins-groq==1.6.5
package (inspect.signature), not assumed from docs: real keyword-only param.

``getProviderCapabilities()`` still advertises historical Groq Llama / Qwen IDs so existing agent
rows and client pickers keep validating. Free/developer Llama IDs were retired (enterprise-only
now), and ``qwen/qwen3.6-27b`` 404s on many keys — this adapter remaps them to a live production
model (same pattern as ``worker/providers/llm/gemini.py::_DEPRECATED_GEMINI_MODELS``).

Free-tier voice default is ``openai/gpt-oss-20b`` (~1000 t/s production) with
``reasoning_effort=low`` and a tight ``max_completion_tokens`` cap. Override via
``GROQ_LLM_MODEL`` (dead IDs in that env var are ignored). Prompt size (not model "size") is
what usually causes 429s — keep ``GROQ_PROMPT_SOFT_CHARS`` low and check
``docs/last_session_prompt.txt``.

Installing this package also pulls in livekit-plugins-openai as a real dependency — Groq's plugin
is built on the OpenAI-compatible interface (base_url defaults to
"https://api.groq.com/openai/v1"), not a bespoke Groq wire protocol.

Requires GROQ_API_KEY (env var, or api_key= kwarg) — the plugin itself raises a clear ValueError
if neither is set, checked eagerly at construction (same pattern as every other provider adapter
in this repo).

Groq must never be selectable for `ur` (guide's explicit rule) — enforced structurally in
worker/providers/capabilities.py by Groq's absence from `ur`'s llm dict entirely, not by any
check in this file.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

# Live free/developer production default (Groq docs, 2026-09).
_FALLBACK_GROQ_MODEL = "openai/gpt-oss-20b"
# Spoken replies stay short; reserving a large completion budget inflates free-tier TPM use.
_MAX_COMPLETION_TOKENS = int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "96"))
# Retired / 404 on free+developer keys — never send these to Groq.
_DEAD_GROQ_MODELS = frozenset(
    {
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "qwen/qwen3.6-27b",
        "qwen/qwen3-32b",
        "qwen/qwen3.8-27b",
        "moonshotai/kimi-k2-instruct-0905",
    }
)


def _live_default_model() -> str:
    raw = (os.getenv("GROQ_LLM_MODEL") or "").strip() or _FALLBACK_GROQ_MODEL
    if raw in _DEAD_GROQ_MODELS:
        return _FALLBACK_GROQ_MODEL
    return raw


def build(model: str) -> Any:
    from livekit.plugins import groq

    requested = (model or "").strip()
    default = _live_default_model()
    if not requested or requested in _DEAD_GROQ_MODELS:
        resolved_model = default
    else:
        resolved_model = requested

    kwargs: dict[str, Any] = {
        "model": resolved_model,
        # Gemini already sets a 30s HTTP timeout after LiveKit's 10s default 504'd in demo.
        "timeout": httpx.Timeout(30.0),
        "max_completion_tokens": _MAX_COMPLETION_TOKENS,
        # Free-tier: do not burn retries into the same TPM window (LiveKit already retries).
        "max_retries": 0,
    }
    if resolved_model.startswith("openai/gpt-oss"):
        # Keep reasoning cheap on the voice path (ITPM + TTFT).
        kwargs["reasoning_effort"] = "low"
    elif resolved_model.startswith("qwen/"):
        kwargs["reasoning_effort"] = "none"
    return groq.LLM(**kwargs)
