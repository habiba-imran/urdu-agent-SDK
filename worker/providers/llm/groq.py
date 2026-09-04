"""Groq LLM adapter (Phase 6b, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py is the gate, not this
file. `model` constructor arg verified directly against the installed livekit-plugins-groq==1.6.5
package (inspect.signature), not assumed from docs: real keyword-only param.

``getProviderCapabilities()`` still advertises the historical Groq Llama IDs so existing agent
rows and client pickers keep validating. Groq retired those IDs on 2026-08-16 (developer/free
tier), so this adapter remaps them to Groq's documented replacements — same pattern as
``worker/providers/llm/gemini.py::_DEPRECATED_GEMINI_MODELS``.

Free-tier voice default is ``qwen/qwen3.6-27b`` with ``reasoning_effort=none`` and a tight
``max_completion_tokens`` cap. ``openai/gpt-oss-20b`` is still remapped here because free-tier
TPM is only 8k and gpt-oss spends completion budget on a reasoning channel — PSTN prompts of
~3–5k tokens then 429 within 1–2 turns. Paid/dev tier can override via ``GROQ_LLM_MODEL``.

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

# Free-tier voice: qwen3.6-27b + reasoning none. gpt-oss-20b is fast but burns TPM on
# reasoning tokens and 429s under 8k TPM with front-desk-sized prompts.
_DEFAULT_GROQ_MODEL = os.getenv("GROQ_LLM_MODEL", "qwen/qwen3.6-27b")
# Spoken replies stay short; reserving a large completion budget inflates free-tier TPM use.
_MAX_COMPLETION_TOKENS = int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "96"))
_DEPRECATED_GROQ_MODELS = {
    "llama-3.3-70b-versatile": _DEFAULT_GROQ_MODEL,
    "llama-3.1-8b-instant": _DEFAULT_GROQ_MODEL,
    "meta-llama/llama-4-scout-17b-16e-instruct": _DEFAULT_GROQ_MODEL,
    "qwen/qwen3-32b": _DEFAULT_GROQ_MODEL,
    "moonshotai/kimi-k2-instruct-0905": _DEFAULT_GROQ_MODEL,
    # Free-tier TPM: prefer qwen without reasoning unless caller sets GROQ_LLM_MODEL=gpt-oss.
    "openai/gpt-oss-20b": _DEFAULT_GROQ_MODEL,
    "openai/gpt-oss-120b": _DEFAULT_GROQ_MODEL,
}


def build(model: str) -> Any:
    from livekit.plugins import groq

    resolved_model = _DEPRECATED_GROQ_MODELS.get(model, model or _DEFAULT_GROQ_MODEL)
    # If env pins gpt-oss explicitly as the default, honor a direct request for it.
    if model in ("openai/gpt-oss-20b", "openai/gpt-oss-120b") and os.getenv(
        "GROQ_ALLOW_GPT_OSS", ""
    ).strip() in ("1", "true", "yes"):
        resolved_model = model

    kwargs: dict[str, Any] = {
        "model": resolved_model,
        # Gemini already sets a 30s HTTP timeout after LiveKit's 10s default 504'd in demo.
        "timeout": httpx.Timeout(30.0),
        "max_completion_tokens": _MAX_COMPLETION_TOKENS,
        # Free-tier: do not burn retries into the same TPM window (LiveKit already retries).
        "max_retries": 0,
    }
    if resolved_model.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = "low"
    elif resolved_model.startswith("qwen/"):
        # qwen3.6 on Groq: none disables <think> and keeps completion budget speakable.
        kwargs["reasoning_effort"] = "none"
    return groq.LLM(**kwargs)
