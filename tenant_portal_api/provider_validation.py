"""Provider/language field validation for agent create/update (Phase 3 of
docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Checked at language -> provider -> model/voice/options granularity, per the guide's explicit rule
(a provider can support one language's STT but not another's; a TTS provider can support one voice
but not another — a broad provider-level check is not enough). Returns fully-resolved field values
ready to write; callers must not write anything this function didn't return, so there is exactly
one place these rules can be bypassed from (nowhere).

Layer options (`stt_options`/`llm_options`/`tts_options`): Cartesia and Rime TTS consume
``tts_options`` (humanization — model/speed and related keys). STT/LLM options remain
unconsumed; the only valid value for those layers is ``{}``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from worker.providers.capabilities import (  # noqa: E402
    is_language_known,
    llm_capability,
    stt_capability,
    tts_capability,
)
from worker.providers.tts.cartesia_options import (  # noqa: E402
    CartesiaTtsOptionsError,
    validate_cartesia_tts_options,
)
from worker.providers.tts.rime_options import (  # noqa: E402
    RimeTtsOptionsError,
    validate_rime_tts_options,
)

# Mirrors Phase 1's own DB backfill defaults (0016_agents_provider_fields.sql) — the values a
# CREATE gets when the caller supplies nothing beyond the legacy voice_id/llm_model fields.
# English CREATE (agent_language=en) overlays voice defaults below so new EN agents match
# the self-serve test-agent stack (Deepgram + Groq + Cartesia).
_CREATE_DEFAULTS = {
    "agent_language": "ur",
    "stt_provider": "gladia",
    "stt_model": "default",
    "stt_options": {},
    "llm_provider": "gemini",
    "llm_model": "gemini-2.5-flash",
    "llm_options": {},
    "tts_provider": "uplift",
    "tts_options": {},
}

_EN_CREATE_DEFAULTS = {
    "llm_provider": "groq",
    "llm_model": "qwen/qwen3.6-27b",
}


class ProviderValidationError(Exception):
    """An invalid provider/language/model/voice/options combination. Always 422 — these are
    request-shape errors, not auth/not-found errors. `code` is one of the stable error codes from
    the guide's Error Handling list."""

    def __init__(self, code: str, reason: str):
        super().__init__(f"{code}: {reason}")
        self.status = 422
        self.code = code
        self.reason = reason


def resolve_agent_provider_fields(
    conn: psycopg.Connection,
    *,
    agent_language: str | None,
    stt_provider: str | None,
    stt_model: str | None,
    stt_options: dict | None,
    llm_provider: str | None,
    llm_model: str | None,
    llm_options: dict | None,
    tts_provider: str | None,
    tts_voice_id: str | None,
    tts_options: dict | None,
    voice_id: str | None,
    current: dict | None = None,
) -> dict:
    """`current` supplies defaults for fields omitted here (an existing agent's already-resolved
    row, for UPDATE); CREATE has no `current`, so `_CREATE_DEFAULTS` applies instead. Returns the
    resolved values to write, including the voice_id/tts_voice_id sync — tts_voice_id wins when
    both are given (the guide's explicit priority rule), and BOTH columns get the same resolved
    value written, closing the gap Phase 1 flagged (a fresh agent's tts_voice_id was NULL until
    something at this layer started keeping them in sync)."""
    base = dict(current if current is not None else _CREATE_DEFAULTS)

    language = agent_language if agent_language is not None else base["agent_language"]
    if not is_language_known(language):
        raise ProviderValidationError(
            "unsupported_language", f"language {language!r} is not supported"
        )

    # English CREATE: prefer Groq when caller omits llm_provider. CreateAgentBody still
    # defaults llm_model to gemini-2.5-flash — treat that legacy Field default as unset
    # when the resolved provider is Groq so validation does not reject the pair.
    effective_llm_model = llm_model
    if current is None and str(language).lower().startswith("en"):
        if llm_provider is None:
            base["llm_provider"] = _EN_CREATE_DEFAULTS["llm_provider"]
        provider_preview = llm_provider if llm_provider is not None else base["llm_provider"]
        if provider_preview == "groq" and (
            llm_model is None or llm_model == _CREATE_DEFAULTS["llm_model"]
        ):
            base["llm_model"] = _EN_CREATE_DEFAULTS["llm_model"]
            effective_llm_model = None

    resolved_stt_provider = (
        stt_provider if stt_provider is not None else base["stt_provider"]
    )
    stt_cap = stt_capability(language, resolved_stt_provider)
    if stt_cap is None:
        raise ProviderValidationError(
            "unsupported_provider_for_language",
            f"stt provider {resolved_stt_provider!r} does not support language {language!r}",
        )
    if stt_cap["state"] != "enabled":
        raise ProviderValidationError(
            "provider_not_enabled",
            f"stt provider {resolved_stt_provider!r} for {language!r} is {stt_cap['state']!r}, "
            "not enabled",
        )
    resolved_stt_model = stt_model if stt_model is not None else base["stt_model"]
    if resolved_stt_model not in stt_cap["models"]:
        raise ProviderValidationError(
            "unsupported_model_for_provider",
            f"stt model {resolved_stt_model!r} is not supported by provider "
            f"{resolved_stt_provider!r}",
        )
    resolved_stt_options = (
        stt_options if stt_options is not None else base["stt_options"]
    )
    if resolved_stt_options != {}:
        raise ProviderValidationError(
            "invalid_stt_options", "no stt provider accepts options yet"
        )

    resolved_llm_provider = (
        llm_provider if llm_provider is not None else base["llm_provider"]
    )
    llm_cap = llm_capability(language, resolved_llm_provider)
    if llm_cap is None:
        raise ProviderValidationError(
            "unsupported_provider_for_language",
            f"llm provider {resolved_llm_provider!r} does not support language {language!r}",
        )
    if llm_cap["state"] != "enabled":
        raise ProviderValidationError(
            "provider_not_enabled",
            f"llm provider {resolved_llm_provider!r} for {language!r} is {llm_cap['state']!r}, "
            "not enabled",
        )
    resolved_llm_model = (
        effective_llm_model if effective_llm_model is not None else base["llm_model"]
    )
    # llm_model keeps its existing free-text convention (agents.llm_model has always been a plain
    # string, never previously validated against a fixed list) — only checked against the
    # capability's models list when that list is non-empty, so real deprecated-model aliasing
    # (worker/providers/llm/gemini.py::_DEPRECATED_GEMINI_MODELS) keeps working unchanged.
    if llm_cap["models"] and resolved_llm_model not in llm_cap["models"]:
        raise ProviderValidationError(
            "unsupported_model_for_provider",
            f"llm model {resolved_llm_model!r} is not supported by provider "
            f"{resolved_llm_provider!r}",
        )
    resolved_llm_options = (
        llm_options if llm_options is not None else base["llm_options"]
    )
    if resolved_llm_options != {}:
        raise ProviderValidationError(
            "invalid_llm_options", "no llm provider accepts options yet"
        )

    resolved_tts_provider = (
        tts_provider if tts_provider is not None else base["tts_provider"]
    )
    tts_cap = tts_capability(language, resolved_tts_provider)
    if tts_cap is None:
        raise ProviderValidationError(
            "unsupported_provider_for_language",
            f"tts provider {resolved_tts_provider!r} does not support language {language!r}",
        )
    if tts_cap["state"] != "enabled":
        raise ProviderValidationError(
            "provider_not_enabled",
            f"tts provider {resolved_tts_provider!r} for {language!r} is {tts_cap['state']!r}, "
            "not enabled",
        )
    resolved_tts_options = (
        tts_options if tts_options is not None else base["tts_options"]
    )
    if resolved_tts_provider == "cartesia":
        try:
            resolved_tts_options = validate_cartesia_tts_options(resolved_tts_options)
        except CartesiaTtsOptionsError as exc:
            raise ProviderValidationError("invalid_tts_options", str(exc)) from exc
    elif resolved_tts_provider == "rime":
        try:
            resolved_tts_options = validate_rime_tts_options(resolved_tts_options)
        except RimeTtsOptionsError as exc:
            raise ProviderValidationError("invalid_tts_options", str(exc)) from exc
    elif resolved_tts_options != {}:
        raise ProviderValidationError(
            "invalid_tts_options", "no tts provider accepts options yet"
        )

    # tts_voice_id/voice_id priority rule (guide's explicit rule): tts_voice_id wins when given.
    resolved_voice = tts_voice_id if tts_voice_id is not None else voice_id
    if resolved_voice is None:
        resolved_voice = base.get("tts_voice_id") or base.get("voice_id")
    if resolved_voice is None:
        raise ProviderValidationError(
            "unsupported_voice_for_provider", "a voiceId or ttsVoiceId is required"
        )
    voice_row = conn.execute(
        "select provider, language, rollout_state, enabled from voices where id = %s",
        (resolved_voice,),
    ).fetchone()
    if (
        voice_row is None
        or voice_row[0] != resolved_tts_provider
        or voice_row[1] != language
        or voice_row[2] != "enabled"
        or voice_row[3] is not True
    ):
        raise ProviderValidationError(
            "unsupported_voice_for_provider",
            f"voice {resolved_voice!r} is not an enabled {language!r}/{resolved_tts_provider!r} "
            "voice",
        )

    return {
        "agent_language": language,
        "stt_provider": resolved_stt_provider,
        "stt_model": resolved_stt_model,
        "stt_options": resolved_stt_options,
        "llm_provider": resolved_llm_provider,
        "llm_model": resolved_llm_model,
        "llm_options": resolved_llm_options,
        "tts_provider": resolved_tts_provider,
        "tts_voice_id": resolved_voice,
        "voice_id": resolved_voice,
        "tts_options": resolved_tts_options,
    }
