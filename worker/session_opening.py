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


@dataclass
class OpeningState:
    phase: str = "PLAYBACK_NOT_READY"
    playback_ready: bool | None = None
    server_playout_complete: bool = False
    # Permission/readiness is separate from delivery completion and caller hearing.
    caller_heard: bool | None = None


def opening_state(session: Any) -> OpeningState:
    userdata = getattr(session, "userdata", None)
    state = getattr(userdata, "opening_state", None)
    if state is None:
        state = OpeningState()
        if userdata is not None:
            userdata.opening_state = state
    return state


def opening_gate_enabled() -> bool:
    return os.getenv("UVA_OPENING_POLICY", "baseline") == "opening_v1"


def bind_opening_transport(session: Any, room: Any, channel: str) -> None:
    import asyncio
    import json
    state = opening_state(session)
    ready = asyncio.Event()
    session._awaaz_playback_event = ready
    runtime = getattr(getattr(session, "userdata", None), "humanization_runtime", None)
    def mark(value):
        state.playback_ready = value
        if runtime is not None:
            runtime.playback_ready = value
            transport = runtime.provider_snapshot.get("transport")
            if transport is not None:
                transport["playback_ready"] = value
        if value:
            ready.set()
        else:
            ready.clear()
    def on_data(packet):
        # Only authenticated caller participants can report their own readiness.
        participant = getattr(packet, "participant", None)
        if channel != "webrtc" or participant is None or getattr(participant, "kind", None) == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT or "agent" in str(getattr(participant, "kind", "")).lower():
            return
        remotes = getattr(room, "remote_participants", {})
        if remotes and getattr(participant, "identity", None) not in {p.identity for p in remotes.values()}:
            return
        try:
            data = json.loads(packet.data)
        except (ValueError, TypeError, UnicodeDecodeError):
            return
        if isinstance(data, dict) and data.get("type") == "awaaz_playback_state" and isinstance(data.get("ready"), bool):
            mark(data["ready"])
    def sip_ready(participant):
        status = (getattr(participant, "attributes", None) or {}).get("sip.callStatus")
        if channel == "telephony" and status == "active":
            mark(True)
    def attrs_changed(_attrs, participant):
        sip_ready(participant)
    room.on("data_received", on_data)
    room.on("participant_attributes_changed", attrs_changed)
    room.on("participant_connected", sip_ready)
    for participant in (getattr(room, "remote_participants", None) or {}).values():
        sip_ready(participant)
    # Late workers request a fresh snapshot instead of relying on a packet sent
    # before dispatch. Public SDK responds even when the browser is blocked.
    async def request():
        if channel == "webrtc":
            try:
                await room.local_participant.publish_data(b'{"type":"awaaz_playback_request"}', reliable=True)
            except Exception:
                pass
    task = asyncio.create_task(request())
    def close(_ev):
        task.cancel()
        state.phase = "CLOSED"
        mark(False)
        room.off("data_received", on_data)
        room.off("participant_attributes_changed", attrs_changed)
        room.off("participant_connected", sip_ready)
        ready.set()  # unblock the waiter; close is checked before speaking
    session.on("close", close)


async def await_playback_ready(session: Any, *, timeout: float = 10.0) -> bool:
    import asyncio
    state = opening_state(session)
    if state.playback_ready is True:
        return True
    event = getattr(session, "_awaaz_playback_event", None)
    if event is None:
        return False
    try:
        await asyncio.wait_for(event.wait(), timeout)
    except TimeoutError:
        return False
    return state.playback_ready is True

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
    from .humanization.delivery.policy import resolve_delivery_policy
    if resolve_delivery_policy(cfg.tts_provider).enabled:
        from .humanization.delivery.canonical import canonical_spoken_text
        return canonical_spoken_text(text)
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
            language=cfg.agent_language,
            tenant_id=cfg.tenant_id,
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
    state = opening_state(session)

    def _clear_opening_flag(_handle: Any = None) -> None:
        state.phase = "INTERACTIVE"
        failed = callable(getattr(_handle, "exception", None)) and _handle.exception() is not None
        state.server_playout_complete = _handle is not None and not getattr(_handle, "interrupted", False) and not failed
        if userdata is not None:
            userdata.opening_active = False

    def _arm_opening_flag() -> None:
        state.phase = "GREETING_PLAYING"
        if userdata is not None:
            userdata.opening_active = True

    state.phase = "GREETING_PENDING"
    if opening.mode == "wait":
        state.phase = "INTERACTIVE"
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
