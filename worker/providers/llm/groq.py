"""Groq LLM adapter (Phase 6b, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py is the gate, not this
file. `model` constructor arg verified directly against the installed livekit-plugins-groq==1.6.5
package (inspect.signature), not assumed from docs: real keyword-only param.

F-M15: capabilities ``models`` lists live runtime IDs only; dead Llama/Qwen IDs are
``legacy_aliases`` (still validate on agent rows). This adapter remaps dead/empty IDs to a live
production model and logs ``requested`` → ``effective`` (never silent).

Free-tier voice default is ``openai/gpt-oss-20b`` (~1000 t/s production) with
``reasoning_effort=low`` and a tight ``max_completion_tokens`` cap. Override via
``GROQ_LLM_MODEL`` (dead IDs in that env var are ignored).

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

import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger("worker.providers.llm.groq")

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


def resolve_groq_model(model: str) -> tuple[str, str | None]:
    """Return ``(effective_model, remap_reason)``.

    ``remap_reason`` is None when the requested ID is used as-is.
    """
    requested = (model or "").strip()
    default = _live_default_model()
    if not requested:
        return default, "empty_model"
    if requested in _DEAD_GROQ_MODELS:
        return default, "dead_model"
    return requested, None


def _make_transport_client() -> Any:
    """Own the public OpenAI-compatible client used for both warm-up and chat."""
    import openai
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise ValueError("GROQ_API_KEY is required")
    return openai.AsyncClient(
        api_key=key, base_url="https://api.groq.com/openai/v1", max_retries=0,
        http_client=httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=50, keepalive_expiry=120)),
    )


def build(model: str) -> Any:
    from livekit.plugins import groq

    requested = (model or "").strip()
    resolved_model, reason = resolve_groq_model(model)
    if reason is not None:
        logger.info(
            "llm model remapped provider=groq requested=%r effective=%s reason=%s",
            requested or "",
            resolved_model,
            reason,
        )

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
        # "none" is not a value Groq accepts. Sending it fails the request outright:
        #   HTTP 400 `reasoning_effort` must be one of `low`, `medium`, or `high`
        # (verified against the live API, 2026-10-21). Every qwen id currently resolves
        # away via _DEAD_GROQ_MODELS, so this branch was unreachable — but a new qwen id
        # in GROQ_LLM_MODEL would have reached it and 400'd every single turn.
        kwargs["reasoning_effort"] = "low"
    class TransportWarmedGroq(groq.LLM):
        def __init__(self):
            self._transport_client = _make_transport_client()
            self._transport_warmed_at: float | None = None
            super().__init__(client=self._transport_client, **kwargs)

        async def prewarm(self) -> None:
            # Reuse the same connection for chat without consuming completion TPM.
            # Failure remains diagnostic; it never changes provider or model.
            if self._transport_warmed_at is not None and time.monotonic() - self._transport_warmed_at < 30:
                return
            await self._transport_client.models.list(timeout=4.0)
            self._transport_warmed_at = time.monotonic()

        async def aclose(self) -> None:
            try:
                await super().aclose()
            finally:
                await self._transport_client.close()

    return TransportWarmedGroq()
