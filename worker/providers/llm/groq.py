"""Groq LLM adapter (Phase 6b, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py is the gate, not this
file. `model` constructor arg verified directly against the installed livekit-plugins-groq==1.6.5
package (inspect.signature), not assumed from docs: real keyword-only param.

``getProviderCapabilities()`` still advertises the historical Groq Llama IDs so existing agent
rows and client pickers keep validating. Groq retired those IDs on 2026-08-16 (developer/free
tier), so this adapter remaps them to Groq's documented replacements — same pattern as
``worker/providers/llm/gemini.py::_DEPRECATED_GEMINI_MODELS``.

Voice default is ``openai/gpt-oss-20b`` (not 120b): isolated probes on 2026-08-19 showed 20b
first content in ~0.6s vs ~3.5s for 120b, and 120b spends its first tokens on a `reasoning`
channel that is not speakable. The Gemini adapter already pins thinking to `minimal` for the
same reason.

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

# Groq's recommended replacements after the 2026-08-16 Llama shutdown:
# https://console.groq.com/docs/deprecations
# Voice uses gpt-oss-20b (llama-3.1-8b replacement) rather than gpt-oss-120b so TTFB stays
# under LiveKit's 10s llm_conn_options timeout.
_DEFAULT_GROQ_MODEL = os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-20b")
_DEPRECATED_GROQ_MODELS = {
    "llama-3.3-70b-versatile": _DEFAULT_GROQ_MODEL,
    "llama-3.1-8b-instant": _DEFAULT_GROQ_MODEL,
    "meta-llama/llama-4-scout-17b-16e-instruct": _DEFAULT_GROQ_MODEL,
    "qwen/qwen3-32b": _DEFAULT_GROQ_MODEL,
    "moonshotai/kimi-k2-instruct-0905": _DEFAULT_GROQ_MODEL,
}


def build(model: str) -> Any:
    from livekit.plugins import groq

    resolved_model = _DEPRECATED_GROQ_MODELS.get(model, model or _DEFAULT_GROQ_MODEL)
    kwargs: dict[str, Any] = {
        "model": resolved_model,
        # Gemini already sets a 30s HTTP timeout after LiveKit's 10s default 504'd in demo.
        "timeout": httpx.Timeout(30.0),
    }
    if resolved_model.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = "low"
    return groq.LLM(**kwargs)
