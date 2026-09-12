"""Provider registry — dispatches an AgentRuntimeConfig to the right STT/LLM/TTS adapter
(Phase 2, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

This is the ONE place that reads AgentRuntimeConfig fields to pick an adapter — every adapter's
build() takes only the plain values it actually needs (language / model / voice_id), not the whole
config, so adapters stay simple and match their pre-refactor factories.py signatures as closely as
possible. Adapters are imported lazily inside each branch, matching the discipline
worker/factories.py already established: this module must load without every provider plugin
installed and without touching the network at import time.

No silent provider fallback (guide's explicit rule): an unrecognized provider raises
UnsupportedProviderError rather than defaulting to something else.
"""

from __future__ import annotations

from .types import AgentRuntimeConfig, ProviderComponents


class UnsupportedProviderError(Exception):
    """No adapter registered for this provider — never silently substituted."""


def build_components(cfg: AgentRuntimeConfig) -> ProviderComponents:
    return ProviderComponents(
        stt=_build_stt(cfg),
        llm=_build_llm(cfg),
        tts=_build_tts(cfg),
    )


def _build_stt(cfg: AgentRuntimeConfig):
    if cfg.stt_provider == "gladia":
        from .stt.gladia import build

        return build(cfg.agent_language)
    if cfg.stt_provider == "deepgram":
        from .stt.deepgram import build

        return build(cfg.agent_language)
    if cfg.stt_provider == "soniox":
        from .stt.soniox import build

        return build()
    raise UnsupportedProviderError(f"no STT adapter for provider={cfg.stt_provider!r}")


def _build_llm(cfg: AgentRuntimeConfig):
    if cfg.llm_provider == "gemini":
        from .llm.gemini import build

        return build(cfg.llm_model)
    if cfg.llm_provider == "groq":
        from .llm.groq import build

        return build(cfg.llm_model)
    raise UnsupportedProviderError(f"no LLM adapter for provider={cfg.llm_provider!r}")


def _build_tts(cfg: AgentRuntimeConfig):
    if cfg.tts_provider == "uplift":
        from .tts.uplift import build

        return build(cfg.tts_voice_id)
    if cfg.tts_provider == "cartesia":
        from .tts.cartesia import build

        return build(cfg.tts_voice_id, cfg.agent_language, cfg.tts_options, audio_channel=cfg.audio_channel)
    if cfg.tts_provider == "elevenlabs":
        from .tts.elevenlabs import build

        return build(cfg.tts_voice_id, cfg.agent_language)
    if cfg.tts_provider == "fish_audio":
        from .tts.fish_audio import build

        return build(cfg.tts_voice_id)
    if cfg.tts_provider == "rime":
        from .tts.rime import build

        return build(
            cfg.tts_voice_id,
            cfg.agent_language,
            cfg.tts_options,
            audio_channel=cfg.audio_channel,
        )
    raise UnsupportedProviderError(f"no TTS adapter for provider={cfg.tts_provider!r}")
