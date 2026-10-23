"""Anthropic (Claude) LLM adapter.

Added 2026-10-23 so the voice path has a working LLM while Gemini is returning
``503 UNAVAILABLE`` (docs/LATENCY_AUDIT_2026_10_21.md, OB-F12). Selectable for both ``ur``
and ``en`` — ``rollout_state`` in worker/providers/capabilities.py is the gate, not this file.

Constructor args were verified against the installed
``livekit-plugins-anthropic==1.6.5`` with ``inspect.signature``, not assumed from docs:
``model``, ``api_key``, ``base_url``, ``user``, ``client``, ``top_k``, ``max_tokens``,
``temperature``, ``parallel_tool_calls``, ``tool_choice``, ``caching``, ``timeout``.

Three things about that surface matter, each checked against the live API on 2026-10-23:

1. **Never send ``temperature`` or ``top_k``.** Current Claude models removed sampling
   parameters — ``temperature=0.35`` returns **HTTP 400** on ``claude-opus-5-5`` and
   ``claude-haiku-5-5`` alike. The plugin forwards whatever it is given and its own default
   model (``claude-sonnet-4-6``) still accepts them, so copying ``gemini.py``'s
   ``temperature=0.35`` here would 400 every single turn. Both are left unset.

2. **Thinking depth is only reachable through ``output_config``.** The plugin exposes no
   ``thinking`` or ``effort`` argument, and on ``claude-opus-5-5`` thinking cannot be
   disabled at all — effort is the single lever, and its default is ``medium``. Thinking is
   latency on a phone call, so ``chat()`` is overridden to inject
   ``output_config={"effort": ...}`` (default ``low``) through ``extra_kwargs``, which the
   plugin merges straight into ``messages.create``. ``output_config.effort`` returns 200.

3. **Forced tool choice is not available on current models.** The plugin maps
   ``tool_choice="required"`` to ``{"type": "any"}``, which current models reject with a 400.
   This repo only ever passes ``tool_choice="none"`` (worker/humanization/agent.py), which is
   unaffected — but a future caller asking for ``required`` would break the turn rather than
   degrade.

Spoken replies are one or two sentences — measured 34-61 output tokens — so ``max_tokens``
is capped tightly via ``ANTHROPIC_MAX_TOKENS``. Output is the expensive side of the bill and
an uncapped 1024 (the plugin's fallback) would be ~17x the headroom this path needs.

Prompt caching is deliberately left alone: the plugin already applies ``cache_control`` to
the trailing system/user blocks, and a voice system prompt is far below the minimum
cacheable prefix, so no cache would be created either way.

Requires ANTHROPIC_API_KEY. Spend limits are a Console setting (Billing -> Spend limits);
nothing in this process can enforce a budget, so the cap must be set there.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger("worker.providers.llm.anthropic")

# Haiku 5.5, chosen by the owner on 2026-10-23 after measuring all three through this
# adapter (3 runs each, effort=low): haiku 735ms, sonnet 781ms, opus-5-5 3,203ms to first
# token. Opus 5.5 cannot have thinking disabled -- effort is the only lever and `low` still
# thinks -- so it lands in the same 2.5-4.9s band as the Gemini latency this replaces.
# Override per deployment with ANTHROPIC_LLM_MODEL; per agent row via llm_model.
_FALLBACK_MODEL = "claude-haiku-5-5"
# Thinking is always on for Opus 5.5, so effort is the only latency lever we have.
_DEFAULT_EFFORT = "low"
_EFFORT_LEVELS = frozenset({"low", "medium", "high", "xhigh", "max"})


def _default_model() -> str:
    return (os.getenv("ANTHROPIC_LLM_MODEL") or "").strip() or _FALLBACK_MODEL


def _max_tokens() -> int:
    raw = (os.getenv("ANTHROPIC_MAX_TOKENS") or "").strip()
    if not raw:
        return 160
    try:
        value = int(raw)
    except ValueError:
        logger.warning("invalid ANTHROPIC_MAX_TOKENS=%r — using 160", raw)
        return 160
    # A spoken turn never needs thousands of tokens; refuse a cap that would let one
    # runaway reply dominate the development budget.
    return max(32, min(value, 2048))


def resolve_effort() -> str:
    raw = (os.getenv("ANTHROPIC_EFFORT") or "").strip().lower()
    if raw in _EFFORT_LEVELS:
        return raw
    if raw:
        logger.warning("invalid ANTHROPIC_EFFORT=%r — using %s", raw, _DEFAULT_EFFORT)
    return _DEFAULT_EFFORT


def resolve_anthropic_model(model: str) -> tuple[str, str | None]:
    """Return ``(effective_model, remap_reason)``.

    ``remap_reason`` is None when the requested ID is used as-is. Mirrors the gemini and
    groq adapters: an empty ID is filled rather than passed through to the plugin, whose
    own default (``claude-sonnet-4-6``) is a different generation than this repo targets.
    """
    requested = (model or "").strip()
    if not requested:
        return _default_model(), "empty_model"
    return requested, None


def _make_client() -> Any:
    """Own the AsyncAnthropic client so warm-up and chat share one connection."""
    import anthropic as anthropic_sdk

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY is required")
    return anthropic_sdk.AsyncAnthropic(
        api_key=key,
        # LiveKit already retries at the session layer; a second retry budget here would
        # stack inside the 6s useful-progress watchdog (worker/provider_retries.py).
        max_retries=0,
        timeout=httpx.Timeout(30.0),
    )


def build(model: str) -> Any:
    # Import paths match the plugin's own (livekit/plugins/anthropic/llm.py): NOT_GIVEN
    # comes from .types, is_given from .utils — they are not in the same module.
    from livekit.agents.types import NOT_GIVEN
    from livekit.agents.utils import is_given
    from livekit.plugins import anthropic as anthropic_plugin

    requested = (model or "").strip()
    resolved_model, reason = resolve_anthropic_model(model)
    if reason is not None:
        logger.info(
            "llm model remapped provider=anthropic requested=%r effective=%s reason=%s",
            requested or "",
            resolved_model,
            reason,
        )

    effort = resolve_effort()
    max_tokens = _max_tokens()
    logger.info(
        "anthropic llm model=%s effort=%s max_tokens=%s "
        "(env ANTHROPIC_LLM_MODEL / ANTHROPIC_EFFORT / ANTHROPIC_MAX_TOKENS)",
        resolved_model,
        effort,
        max_tokens,
    )

    class VoiceClaude(anthropic_plugin.LLM):
        def __init__(self) -> None:
            self._transport_client = _make_client()
            self._transport_warmed_at: float | None = None
            # No temperature / top_k on purpose — both return 400 on current models.
            super().__init__(
                model=resolved_model,
                client=self._transport_client,
                max_tokens=max_tokens,
            )

        def chat(self, **kwargs: Any) -> Any:
            """Inject ``output_config.effort``, the only thinking control this plugin has.

            Takes ``**kwargs`` rather than restating the signature so a plugin upgrade that
            adds a parameter cannot silently drop it. A caller-supplied ``extra_kwargs``
            wins, so an explicit ``output_config`` is never overwritten.
            """
            extra: dict[str, Any] = {"output_config": {"effort": effort}}
            caller = kwargs.pop("extra_kwargs", NOT_GIVEN)
            if is_given(caller) and caller:
                extra.update(caller)
            return super().chat(extra_kwargs=extra, **kwargs)

        async def prewarm(self) -> None:
            """Open the HTTPS connection before the first turn.

            ``models.list`` is free and consumes no tokens, so this costs nothing against
            the development budget. Same pattern as the Groq adapter; failure is purely
            diagnostic and never changes provider or model.
            """
            if (
                self._transport_warmed_at is not None
                and time.monotonic() - self._transport_warmed_at < 30
            ):
                return
            await self._transport_client.models.list(timeout=4.0)
            self._transport_warmed_at = time.monotonic()

        async def aclose(self) -> None:
            try:
                await super().aclose()
            finally:
                close = getattr(self._transport_client, "close", None)
                if close is not None:
                    await close()

    return VoiceClaude()
