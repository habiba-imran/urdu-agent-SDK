"""Decide how a session opens: wait, speak a tenant greeting, or generate one.

Tenant ``greeting`` is untrusted DATA (same class as ``agents.prompt``). When present it is
spoken via ``session.say()`` — never concatenated into system instructions or generate_reply
instructions. ``first_speaker='user'`` skips the opening turn entirely.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Any, Literal

from livekit import rtc

from .cartesia_spoken_output import greeting_instructions
from .config import AgentConfig
from .greeting_cache import (
    GreetingCacheKey,
    get_greeting_cache,
    make_greeting_cache_key,
)

OpeningMode = Literal["wait", "say", "generate_reply"]

# Opening-path prewarm / synthesis budgets (seconds).
# Cache hits skip the wait entirely. Say-miss awaits single-flight TTS (not STT).
_SAY_SYNTHESIS_AWAIT_SEC = 5.0
_GENERATE_REPLY_PREWARM_SEC = 2.0


@dataclass(frozen=True)
class SessionOpening:
    mode: OpeningMode
    text: str | None = None
    instructions: str | None = None


@dataclass(frozen=True)
class GreetingPrewarmPlan:
    """How long (if at all) the entrypoint should block before opening.

    For ``mode=say`` cache miss, ``await_prewarm`` is False — opening awaits single-flight
    greeting synthesis instead of the TTS+STT provider prewarm task. STT is deferred until
    after the greeting speaks (see ``_await_opening_and_speak``).
    ``await_prewarm`` True is for ``generate_reply`` (needs live TTS websocket).
    """

    mode: OpeningMode
    cache_hit: bool
    await_prewarm: bool
    prewarm_timeout: float
    cache_key: GreetingCacheKey | None = None
    greeting_frames: list[rtc.AudioFrame] | None = None
    # When True, opening awaits single-flight PCM synth (say miss) rather than live TTS.
    await_synthesis: bool = False


def _spoken_greeting(cfg: AgentConfig, text: str) -> str:
    from .cartesia_spoken_output import enrich_static_greeting_for_tts
    from .spoken_sanitize import sanitizer_for_provider

    sanitize = sanitizer_for_provider(cfg.tts_provider, tts_options=cfg.tts_options)
    cleaned = sanitize(text).strip() if sanitize is not None else text.strip()
    return enrich_static_greeting_for_tts(cfg, cleaned)


def resolve_session_opening(cfg: AgentConfig) -> SessionOpening:
    speaker = (cfg.first_speaker or "agent").strip().lower()
    if speaker != "agent":
        return SessionOpening(mode="wait")

    raw = (cfg.greeting or "").strip()
    if raw:
        spoken = _spoken_greeting(cfg, raw)
        if spoken:
            return SessionOpening(mode="say", text=spoken)

    return SessionOpening(
        mode="generate_reply",
        instructions=greeting_instructions(cfg),
    )


def greeting_allow_interruptions(explicit: bool | None = None) -> bool:
    """WebRTC/telephony greetings are interruptible by default (Retell/Vapi feel).

    Real barge-in must be answered (STT warm during opening + native turn commit).
    Echo-only chops without a user transcript are handled by
    ``resume_false_interruption`` and by not force-flushing VAD during opening.
    Set ``UVA_GREETING_INTERRUPTIBLE=0`` only if you need a locked opening line.
    An explicit ``allow_interruptions`` argument always wins.
    """
    if explicit is not None:
        return bool(explicit)
    raw = (os.environ.get("UVA_GREETING_INTERRUPTIBLE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def plan_greeting_prewarm(
    cfg: AgentConfig,
    *,
    provider_voice_id: str,
    audio_channel: str,
) -> GreetingPrewarmPlan:
    """Decide prewarm wait + whether cached PCM can open immediately."""
    opening = resolve_session_opening(cfg)
    if opening.mode == "wait":
        return GreetingPrewarmPlan(
            mode="wait",
            cache_hit=False,
            await_prewarm=False,
            prewarm_timeout=0.0,
        )
    if opening.mode == "say" and opening.text:
        key = make_greeting_cache_key(
            agent_id=cfg.agent_id,
            tts_provider=cfg.tts_provider,
            provider_voice_id=provider_voice_id or "",
            greeting_text=opening.text,
            audio_channel=audio_channel,
            tts_options=cfg.tts_options,
        )
        frames = get_greeting_cache().get(key)
        if frames is not None:
            return GreetingPrewarmPlan(
                mode="say",
                cache_hit=True,
                await_prewarm=False,
                prewarm_timeout=0.0,
                cache_key=key,
                greeting_frames=frames,
                await_synthesis=False,
            )
        # Miss: do not block on STT/TTS provider prewarm — await single-flight synth.
        return GreetingPrewarmPlan(
            mode="say",
            cache_hit=False,
            await_prewarm=False,
            prewarm_timeout=_SAY_SYNTHESIS_AWAIT_SEC,
            cache_key=key,
            await_synthesis=True,
        )
    return GreetingPrewarmPlan(
        mode="generate_reply",
        cache_hit=False,
        await_prewarm=True,
        prewarm_timeout=_GENERATE_REPLY_PREWARM_SEC,
        await_synthesis=False,
    )


async def apply_session_opening(
    session: Any,
    cfg: AgentConfig,
    logger: Any,
    *,
    allow_interruptions: bool | None = None,
    greeting_audio: AsyncIterable[rtc.AudioFrame] | None = None,
) -> SessionOpening:
    """Speak or generate the opening turn.

    When ``greeting_audio`` is provided for ``mode=say``, PCM is replayed via
    ``session.say(..., audio=)`` (no live TTS RTT). Interruptibility defaults to
    True; set ``UVA_GREETING_INTERRUPTIBLE=0`` to lock the opening line.
    """
    opening = resolve_session_opening(cfg)
    interruptible = greeting_allow_interruptions(allow_interruptions)
    userdata = getattr(session, "userdata", None)

    def _clear_opening_flag(_handle: Any = None) -> None:
        if userdata is not None:
            userdata.opening_active = False

    def _arm_opening_flag() -> None:
        if userdata is not None:
            userdata.opening_active = True

    if opening.mode == "wait":
        logger.info("session opening first_speaker=user — waiting for caller")
        return opening
    if opening.mode == "say":
        logger.info(
            "session opening first_speaker=agent custom_greeting_chars=%s "
            "allow_interruptions=%s cached_audio=%s",
            len(opening.text or ""),
            interruptible,
            greeting_audio is not None,
        )
        # Static greeting: TTS-only, no LLM (UVA-10). Prefer cached PCM when present.
        _arm_opening_flag()
        if greeting_audio is not None:
            handle = session.say(
                opening.text,
                audio=greeting_audio,
                allow_interruptions=interruptible,
            )
        else:
            handle = session.say(opening.text, allow_interruptions=interruptible)
        if handle is not None and hasattr(handle, "add_done_callback"):
            handle.add_done_callback(_clear_opening_flag)
        else:
            _clear_opening_flag()
        return opening
    logger.info(
        "session opening first_speaker=agent generated_greeting allow_interruptions=%s",
        interruptible,
    )
    _arm_opening_flag()
    handle = session.generate_reply(
        instructions=opening.instructions,
        allow_interruptions=interruptible,
    )
    if handle is not None and hasattr(handle, "add_done_callback"):
        handle.add_done_callback(_clear_opening_flag)
    else:
        _clear_opening_flag()
    return opening
