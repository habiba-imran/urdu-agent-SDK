"""Deepgram STT adapter (Phase 6a providers + Phase 6 humanization Flux gate).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py is the gate, not this
file. Constructor args verified against livekit-plugins-deepgram==1.6.5.

Default path: ``deepgram.STT`` Nova-3 + ``endpointing_ms`` (human-turn default 200).

Phase 6 Flux A/B (opt-in only):
  - ``UVA_DEEPGRAM_STT_MODE=flux`` or ``stt_options.stt_mode=flux`` → ``deepgram.STTv2``
    with ``model=flux-general-en`` (EndOfTurn only by default)
  - Eager EOT only when ``resolve_deepgram_flux_eager_threshold`` returns a value
    (Gemini A/B; never Groq)

Requires DEEPGRAM_API_KEY (env var, or api_key= kwarg).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("worker.providers.stt.deepgram")


def build(language: str, stt_options: dict | None = None) -> Any:
    from livekit.plugins import deepgram

    from worker.humanization.turn import (
        resolve_deepgram_endpointing_ms,
        resolve_deepgram_flux_eager_threshold,
        resolve_deepgram_stt_mode,
    )

    lang = "en-US" if language.startswith("en") else language
    mode = resolve_deepgram_stt_mode(stt_options)

    if mode == "flux":
        if not language.startswith("en"):
            logger.warning(
                "deepgram Flux (flux-general-en) is English-only; "
                "language=%s falling back to Nova-3",
                language,
            )
            mode = "nova"
        else:
            options = stt_options or {}
            # Prefer values folded by build_session (llm-aware eager policy).
            if options.get("flux_eager_eot") is False:
                eager = None
            elif options.get("eager_eot_threshold") is not None:
                eager = float(options["eager_eot_threshold"])
            else:
                eager = resolve_deepgram_flux_eager_threshold(options)
            kwargs: dict[str, Any] = {
                "model": "flux-general-en",
                "sample_rate": 16000,
            }
            # Plugin default: eager disabled when NOT_GIVEN — EndOfTurn only.
            if eager is not None:
                kwargs["eager_eot_threshold"] = eager
                # Plugin requires eot_threshold >= eager; keep default 0.7 unless raised.
                if eager > 0.7:
                    kwargs["eot_threshold"] = min(0.9, eager + 0.1)
            logger.info(
                "deepgram STTv2 Flux build language=%s model=flux-general-en "
                "eager_eot_threshold=%s (default EndOfTurn-only)",
                lang,
                eager,
            )
            return deepgram.STTv2(**kwargs)

    endpointing_ms = resolve_deepgram_endpointing_ms(stt_options)
    logger.info(
        "deepgram STT build language=%s endpointing_ms=%s "
        "(default 200=human-turn; set UVA_DEEPGRAM_ENDPOINTING_MS for A/B; "
        "UVA_DEEPGRAM_STT_MODE=flux for Flux)",
        lang,
        endpointing_ms,
    )
    return deepgram.STT(
        model="nova-3",
        language=lang,
        no_delay=True,
        endpointing_ms=endpointing_ms,
        interim_results=True,
        # smart_format adds post-processing latency on finals; voice path prefers speed
        # (numbers/punctuation are fine for Cartesia without it).
        smart_format=False,
    )
