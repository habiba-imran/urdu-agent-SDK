"""STT / EOU / interruption TurnProfile (Phase 2 + Phase 6).

Composes LiveKit ``turn_handling`` options from channel + LLM (same defaults as the
former ``turn_handling_for_channel`` implementation). STT-provider knobs such as
Deepgram ``endpointing_ms`` / Flux live on the STT adapter (via ``stt_options`` + env).

Phase 6 gated experiments (defaults unchanged — Nova + ``turn_detection=\"stt\"``):
  - ``UVA_DEEPGRAM_STT_MODE=flux`` → Deepgram ``STTv2`` / ``flux-general-en`` (EndOfTurn only)
  - ``UVA_DEEPGRAM_FLUX_EAGER_EOT=1`` → Eager EOT for non-Groq only (Gemini A/B); Groq ignored
  - ``UVA_TURN_DETECTOR=v1-mini|v1`` → ``livekit.agents.inference.TurnDetector`` (English only)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from worker.humanization.types import TurnProfile
from worker.latency import (
    TELEPHONY_TURN_HANDLING_OPTIONS,
    TURN_HANDLING_OPTIONS,
    interruption_mode,
)

logger = logging.getLogger("worker.humanization.turn")

# Log / listening checklist for Deepgram endpointing A/B (humanization.md §27 B,I,F).
TURN_AB_LISTEN_LOG_FIELDS = (
    "turn_profile channel/detector/preemptive/interruption_mode",
    "deepgram_endpointing_ms (worker log at STT build)",
    "deepgram_stt_mode nova|flux + flux_eager (Phase 6)",
    "UVA_TURN_DETECTOR off|v1-mini|v1 + session.start start_ms (Phase 6 cold-start)",
    "turn_latency.turnMs (EOU delay)",
    "turn_latency.llmMs / ttsTtfbMs / e2eMs",
    "agent_false_interruption events",
    "session.start start_ms (cold-start must stay stable when only endpointing changes)",
)

# LiveKit audio TurnDetector local languages (v1-mini) — Urdu is NOT included.
_TURN_DETECTOR_LANGS = frozenset(
    {"ar", "de", "en", "es", "fr", "hi", "id", "it", "ja", "ko", "nl", "pt", "tr", "zh"}
)


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_deepgram_stt_mode(stt_options: dict | None = None) -> str:
    """``nova`` (default Nova-3 STT) or ``flux`` (STTv2 / flux-general-en)."""
    options = stt_options or {}
    raw = options.get("stt_mode") or options.get("backend")
    if raw is None or raw == "":
        raw = (os.getenv("UVA_DEEPGRAM_STT_MODE") or "").strip() or "nova"
    mode = str(raw).strip().lower()
    if mode in {"flux", "sttv2", "v2"}:
        return "flux"
    return "nova"


def resolve_deepgram_flux_eager_threshold(
    stt_options: dict | None = None,
    *,
    llm_provider: str | None = None,
) -> float | None:
    """Eager EOT threshold for Flux, or None to keep EndOfTurn-only (Deepgram default).

    Suggested policy (research §12 / plan Phase 6):
      - Default: disabled (EndOfTurn only)
      - Groq: always disabled (cancelled speculative / TPM pressure)
      - Gemini: optional via ``UVA_DEEPGRAM_FLUX_EAGER_EOT=1`` or stt_options
    """
    if (llm_provider or "").strip().lower() == "groq":
        if _env_truthy("UVA_DEEPGRAM_FLUX_EAGER_EOT") or (stt_options or {}).get(
            "flux_eager_eot"
        ):
            logger.warning(
                "UVA_DEEPGRAM_FLUX_EAGER_EOT ignored for Groq (token/TPM cost); "
                "EndOfTurn-only remains"
            )
        return None

    options = stt_options or {}
    if options.get("flux_eager_eot") is False:
        return None
    enabled = _env_truthy("UVA_DEEPGRAM_FLUX_EAGER_EOT") or options.get(
        "flux_eager_eot"
    ) is True
    if not enabled:
        return None

    raw = options.get("eager_eot_threshold")
    if raw is None or raw == "":
        raw = (os.getenv("UVA_DEEPGRAM_FLUX_EAGER_EOT_THRESHOLD") or "").strip() or None
    if raw is None or raw == "":
        return 0.5  # mid of plugin's 0.3–0.9 guidance
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.5
    if not 0.3 <= value <= 0.9:
        logger.warning(
            "eager_eot_threshold=%s out of 0.3–0.9; using 0.5",
            value,
        )
        return 0.5
    return value


def resolve_turn_detector_version(agent_language: str | None) -> str | None:
    """Return ``v1-mini`` / ``v1`` when env opts in, else None (keep STT detector).

    Uses ``livekit.agents.inference.TurnDetector`` (pinned agents 1.6.5) — not the
    deprecated ``livekit.plugins.turn_detector`` package.
    """
    raw = (os.getenv("UVA_TURN_DETECTOR") or "off").strip().lower()
    if raw in {"", "0", "off", "false", "no", "stt"}:
        return None
    if raw in {"v1-mini", "mini", "turn_detector_v1_mini"}:
        version = "v1-mini"
    elif raw in {"v1", "turn_detector_v1"}:
        version = "v1"
    else:
        logger.warning(
            "UVA_TURN_DETECTOR=%r unrecognized — expected off|v1-mini|v1; using STT",
            raw,
        )
        return None

    lang = (agent_language or "en").strip().lower()
    base = lang.split("-", 1)[0]
    if base == "ur" or base not in _TURN_DETECTOR_LANGS:
        logger.warning(
            "UVA_TURN_DETECTOR=%s ignored for agent_language=%r "
            "(audio TurnDetector language list has no Urdu / unsupported lang)",
            version,
            agent_language,
        )
        return None
    return version


def build_turn_profile(
    *,
    audio_channel: str,
    stt_provider: str | None = None,
    llm_provider: str | None = None,
    agent_language: str | None = None,
) -> TurnProfile:
    """Build turn policy for the *effective* providers (after telephony remaps).

    Defaults match historical ``TURN_HANDLING_OPTIONS`` / telephony / Groq preemptive
    disable. Phase 6 TurnDetector opt-in is English-only via ``UVA_TURN_DETECTOR``.
    """
    channel = (audio_channel or "webrtc").strip().lower()
    if channel == "telephony":
        base = TELEPHONY_TURN_HANDLING_OPTIONS
    else:
        base = TURN_HANDLING_OPTIONS

    interruption = {
        **base["interruption"],
        "mode": interruption_mode(),
    }
    from .coordinator import overlap_enabled
    if overlap_enabled():
        interruption["resume_false_interruption"] = True
        interruption["false_interruption_timeout"] = .6
    preemptive = dict(base["preemptive_generation"])
    endpointing = dict(base.get("endpointing") or {})
    detector = str(base.get("turn_detection") or "stt")

    td_version = resolve_turn_detector_version(agent_language)
    if td_version == "v1-mini":
        detector = "turn_detector_v1_mini"
    elif td_version == "v1":
        detector = "turn_detector_v1"

    llm = (llm_provider or "").strip().lower()

    # Hide Gemini (and other non-Groq) TTFT on PSTN by starting generation early.
    # Groq stays preemptive-off on every channel — cancelled turns burn free-tier TPM.
    if channel == "telephony" and llm and llm != "groq":
        preemptive = {
            "enabled": True,
            "preemptive_tts": True,
            "max_speech_duration": 12.0,
            "max_retries": 2,
        }

    if llm == "groq":
        preemptive = {
            "enabled": False,
            "preemptive_tts": False,
            "max_speech_duration": 12.0,
            "max_retries": 0,
        }

    return TurnProfile(
        channel=channel,
        stt_provider=(stt_provider or "").strip().lower(),
        llm_provider=llm,
        detector=detector,
        endpointing_min_delay=float(endpointing.get("min_delay", 0.12)),
        endpointing_max_delay=float(endpointing.get("max_delay", 1.2)),
        preemptive_generation_enabled=bool(preemptive.get("enabled", False)),
        preemptive_tts=bool(preemptive.get("preemptive_tts", False)),
        interruption_enabled=bool(interruption.get("enabled", True)),
        interruption_mode=str(interruption.get("mode") or interruption_mode()),
        resume_false_interruption=bool(
            interruption.get("resume_false_interruption", False)
        ),
        false_interruption_timeout=float(
            interruption.get("false_interruption_timeout", 0.6)
        ),
        discard_audio_if_uninterruptible=bool(
            interruption.get("discard_audio_if_uninterruptible", True)
        ),
        interruption_min_duration=float(interruption.get("min_duration", 0.65)),
        preemptive_max_speech_duration=float(
            preemptive.get("max_speech_duration", 12.0)
        ),
        preemptive_max_retries=int(preemptive.get("max_retries", 0)),
    )


def materialize_turn_detection(profile: TurnProfile) -> Any:
    """Value for ``turn_handling[\"turn_detection\"]`` — string or TurnDetector instance."""
    if profile.detector == "turn_detector_v1_mini":
        from livekit.agents.inference import TurnDetector

        return TurnDetector(version="v1-mini")
    if profile.detector == "turn_detector_v1":
        from livekit.agents.inference import TurnDetector

        return TurnDetector(version="v1")
    return profile.detector


def turn_profile_to_livekit_options(profile: TurnProfile) -> dict[str, Any]:
    """LiveKit AgentSession ``turn_handling=`` dict (deep-copied nested maps)."""
    return {
        "interruption": {
            "enabled": profile.interruption_enabled,
            "discard_audio_if_uninterruptible": profile.discard_audio_if_uninterruptible,
            "min_duration": profile.interruption_min_duration,
            "resume_false_interruption": profile.resume_false_interruption,
            "false_interruption_timeout": profile.false_interruption_timeout,
            "mode": profile.interruption_mode,
        },
        "turn_detection": materialize_turn_detection(profile),
        "endpointing": {
            "min_delay": profile.endpointing_min_delay,
            "max_delay": profile.endpointing_max_delay,
        },
        "preemptive_generation": {
            "enabled": profile.preemptive_generation_enabled,
            "preemptive_tts": profile.preemptive_tts,
            "max_speech_duration": profile.preemptive_max_speech_duration,
            "max_retries": profile.preemptive_max_retries,
        },
    }


def resolve_deepgram_endpointing_ms(
    stt_options: dict | None = None,
) -> int:
    """Deepgram Nova endpointing in ms (voice default 100).

    Resolution order:
      1. ``stt_options[\"endpointing_ms\"]`` when present
      2. ``UVA_DEEPGRAM_ENDPOINTING_MS`` env
      3. default ``100`` (snappy EOU; use ``200``/``300`` via env for more natural pauses)

    Allowed A/B values (research): 10, 100, 200, 300, 500.
    """
    options = stt_options or {}
    raw: Any = options.get("endpointing_ms")
    if raw is None or raw == "":
        raw = (os.getenv("UVA_DEEPGRAM_ENDPOINTING_MS") or "").strip() or None
    if raw is None or raw == "":
        return 100
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 100
    if value <= 0:
        return 100
    return value


async def coalesce_structured_finals(source, runtime, *, settle_seconds=1.8):
    """Hold only a recognizably incomplete Pakistani phone; other speech stays immediate.

    Deduplicate provider retransmissions only with matching nonzero acoustic offsets.
    Flush before stop/repair/non-digit input; retain original segment evidence upstream.
    LiveKit continues to own commitment, interruption, preemption and tool lifetime.
    """
    import asyncio
    from dataclasses import replace
    from livekit.agents import stt
    from .understanding import phone_digits
    queue = asyncio.Queue(maxsize=32)
    end = object()

    async def read():
        try:
            async for event in source:
                await queue.put(event)
        except Exception as exc:
            await queue.put(exc)
        finally:
            await queue.put(end)

    reader = asyncio.create_task(read())
    pending = None
    deadline = None
    last_final = None
    deferred_end = None
    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), max(0, deadline-loop.time())) if pending else await queue.get()
            except asyncio.TimeoutError:
                yield pending
                pending = None
                if deferred_end is not None:
                    yield deferred_end
                    deferred_end = None
                continue
            if event is end or isinstance(event, Exception):
                if pending is not None:
                    yield pending
                if deferred_end is not None:
                    yield deferred_end
                if isinstance(event, Exception):
                    raise event
                break
            if event.type == stt.SpeechEventType.START_OF_SPEECH:
                last_final = None
                deferred_end = None  # caller resumed; never replay an older EOT over live speech
            alternatives = getattr(event, "alternatives", ())
            final = event.type == stt.SpeechEventType.FINAL_TRANSCRIPT and bool(alternatives)
            if final:
                alt = alternatives[0]
                key = (alt.text, alt.start_time, alt.end_time)
                if alt.end_time > alt.start_time and key == last_final:
                    continue
                last_final = key
                digits = phone_digits(alt.text)
                if pending is not None:
                    previous = pending.alternatives[0]
                    prior_digits = phone_digits(previous.text)
                    if digits and len(digits) <= 3 and len(prior_digits + digits) <= 15:
                        # This is a continuation, never silently discard another final.
                        alt = replace(previous, text=previous.text + " " + alt.text,
                                      end_time=alt.end_time, confidence=min(previous.confidence, alt.confidence))
                        event = replace(pending, alternatives=[alt])
                        digits = prior_digits + digits
                        pending = None
                        if len(digits) == 11:
                            yield event
                            if deferred_end is not None:
                                yield deferred_end
                                deferred_end = None
                            continue
                    else:
                        yield pending
                        pending = None
                        if deferred_end is not None:
                            yield deferred_end
                            deferred_end = None
                if digits and digits.startswith("03") and 7 <= len(digits) < 11:
                    pending = event
                    deadline = loop.time() + settle_seconds
                    continue
            if pending is not None and event.type == stt.SpeechEventType.END_OF_SPEECH:
                deferred_end = event
                continue
            yield event
    finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)
        close = getattr(source, "aclose", None)
        if close is not None:
            await close()
