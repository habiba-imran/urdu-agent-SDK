"""Latency helpers for the voice worker (UVA Phase 1–4).

Centralizes turn-handling defaults, provider warm-up, session-identity lookup, per-turn
``turn_latency`` / ``metrics_updated`` telemetry, tool-stage timing, barge-in flush, and
fast room teardown options.

F-L6: room publish of stage timings is opt-in via ``UVA_PUBLISH_TURN_LATENCY``
(default off). Server-side INFO logs always run.
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import json
import logging
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

from worker.telemetry import (
    COMPONENT_VERSIONS, OUTCOMES, POLICY_VERSION, TOOL_NAMES, GenerationTrace,
    LatencyDistributions, identifier, measurement, new_id, percentile_report,
)

# Set by the public speech_created event before LiveKit creates its speech task.
# Child node/provider tasks inherit this context, including speculative tasks.
# Never infer ownership from whichever speech is currently playing.
_speech_scope = contextvars.ContextVar("awaaz_telemetry_speech", default=None)
_generation_scope = contextvars.ContextVar("awaaz_telemetry_generation", default=None)

logger = logging.getLogger("worker.latency")

_TRUTH_ON = frozenset({"1", "true", "yes", "on"})
_TRUTH_OFF = frozenset({"0", "false", "no", "off", ""})


def publish_turn_latency_enabled() -> bool:
    """True only when ``UVA_PUBLISH_TURN_LATENCY`` is explicitly on (default off).

    Gate A / D6 (F-L6): keep server INFO latency logs; do not broadcast stage
    breakdown into the LiveKit room unless a host opts in for debug.
    """
    raw = (os.getenv("UVA_PUBLISH_TURN_LATENCY") or "").strip().lower()
    if raw in _TRUTH_OFF:
        return False
    return raw in _TRUTH_ON

# Phase 2 (UVA-6): 0.15s min endpointing — commit turns faster during conversation.
# Preemptive generation starts LLM while the user is still speaking (UVA-14).
# preemptive_tts=True starts Cartesia synthesis on streamed tokens *before* EOU
# confirms — without this, TTS waits for full turn commit (+ seconds of dead air).
TURN_HANDLING_OPTIONS: dict[str, Any] = {
    # UVA-13: barge-in — discard buffered TTS and cancel in-flight generation.
    # mode is filled by turn_handling_for_channel() (default "vad" — see below).
    #
    # resume_false_interruption is OFF for WebRTC too: laptop speakers → mic echo still
    # trips Silero; pause/resume then flickers audio and can wedge playout
    # (``SegmentSynchronizerImpl.on_playback_started called after start_fut is set``).
    # min_duration balances snappy barge-in vs echo chops (was 0.75 — felt sluggish).
    "interruption": {
        "enabled": True,
        "discard_audio_if_uninterruptible": True,
        "min_duration": 0.65,
        "resume_false_interruption": False,
        "false_interruption_timeout": 0.6,
    },
    "turn_detection": "stt",
    "endpointing": {"min_delay": 0.12, "max_delay": 1.2},
    "preemptive_generation": {
        "enabled": True,
        "preemptive_tts": True,
        "max_speech_duration": 12.0,
        "max_retries": 3,
    },
}

# PSTN/SIP: no browser AEC — same false-interruption resume hazard as WebRTC speakers.
# Keep barge-in enabled; do not discard caller audio after an intentional interrupt.
# Slightly lower min_duration than WebRTC (force barge flush helps on PSTN).
# Preemptive on telephony is re-enabled for non-Groq LLMs in build_turn_profile
# (hides Gemini TTFT); Groq stays off to protect free-tier TPM.
TELEPHONY_TURN_HANDLING_OPTIONS: dict[str, Any] = {
    **TURN_HANDLING_OPTIONS,
    "interruption": {
        "enabled": True,
        "discard_audio_if_uninterruptible": False,
        "min_duration": 0.55,
        "resume_false_interruption": False,
        "false_interruption_timeout": 0.6,
    },
    "preemptive_generation": {
        "enabled": False,
        "preemptive_tts": False,
        "max_speech_duration": 12.0,
        "max_retries": 0,
    },
}


def interruption_mode() -> str:
    """WebRTC/telephony interruption strategy.

    Default ``vad``: local Silero only — skips LiveKit Cloud adaptive-detector init on
    ``session.start`` (often multi-second). Set ``UVA_INTERRUPTION_MODE=adaptive`` for
    ML barge-in. Provider-agnostic (STT/LLM/TTS unchanged).
    """
    raw = (os.environ.get("UVA_INTERRUPTION_MODE") or "vad").strip().lower()
    if raw in ("adaptive", "vad"):
        return raw
    return "vad"


def turn_handling_for_channel(
    audio_channel: str,
    *,
    llm_provider: str | None = None,
    stt_provider: str | None = None,
    agent_language: str | None = None,
) -> dict[str, Any]:
    """Return turn-handling defaults for WebRTC vs telephony audio legs.

    Delegates to ``worker.humanization.turn.build_turn_profile`` (Phase 2). Groq
    free-tier TPM is tight (8k/min): disable preemptive generation so cancelled
    partial turns do not burn tokens before EOU.
    """
    from worker.humanization.turn import (
        build_turn_profile,
        turn_profile_to_livekit_options,
    )

    profile = build_turn_profile(
        audio_channel=audio_channel,
        stt_provider=stt_provider,
        llm_provider=llm_provider,
        agent_language=agent_language,
    )
    return turn_profile_to_livekit_options(profile)


def is_telephony_job(
    *,
    room_name: str | None = None,
    job_metadata: Any = None,
) -> bool:
    """Detect PSTN/SIP jobs from room prefix or dispatch metadata."""
    if isinstance(room_name, str) and room_name.startswith("telephony-"):
        return True
    if not job_metadata:
        return False
    try:
        parsed = job_metadata if isinstance(job_metadata, dict) else json.loads(job_metadata)
    except Exception as exc:
        logger.warning(
            "stage=telephony_meta_parse failed room=%s err=%s",
            room_name or "?",
            exc,
        )
        return False
    if not isinstance(parsed, dict):
        return False
    direction = str(parsed.get("direction") or "").lower()
    if direction in {"inbound", "outbound"}:
        return True
    if parsed.get("e164_number") or parsed.get("phone_number_id") or parsed.get("sip_call_id"):
        return True
    return False

# In-call VAD: keep a tight silence gate for EOU, but require a bit more speech energy
# so agent TTS leaking into the mic does not register as barge-in.
VAD_OPTIONS: dict[str, float] = {
    "min_speech_duration": 0.12,
    "min_silence_duration": 0.32,
    "prefix_padding_duration": 0.32,
    "activation_threshold": 0.45,
}


def load_session_identity(room_name: str) -> dict[str, str] | None:
    """Return ``{tenant_id, agent_id}`` for an open session row, or ``None``.

    Available as soon as the mint commits — before the browser participant joins —
    so the worker can build STT/LLM/TTS in parallel with ``wait_for_participant``.
    """
    from worker.db_pool import worker_db_connection

    try:
        with worker_db_connection(connect_timeout=5) as conn:
            row = conn.execute(
                """
                select tenant_id, agent_id
                from sessions
                where room_name = %s and ended_at is null
                order by started_at desc
                limit 1
                """,
                (room_name,),
            ).fetchone()
    except Exception as exc:
        logger.warning(
            "stage=load_session_identity failed room=%s err=%s",
            room_name,
            exc,
        )
        return None
    if row is None or not row[0] or not row[1]:
        return None
    return {"tenant_id": str(row[0]), "agent_id": str(row[1])}


def parse_dispatch_metadata(raw: str | None) -> dict[str, str] | None:
    """Parse ``tenant_id`` / ``agent_id`` from a LiveKit job or dispatch metadata JSON blob.

    Also preserves a ``direction`` hint when present so the early telephony path can
    select the correct audio profile without waiting for the SIP participant, and an
    optional ``greeting`` override so turn-zero can use mint-time text without a DB race.
    """
    if not raw:
        return None
    try:
        parsed = json.loads(raw) if not isinstance(raw, dict) else raw
    except Exception as exc:
        logger.warning("stage=parse_dispatch_metadata failed err=%s", exc)
        return None
    if not isinstance(parsed, dict):
        return None
    tenant_id = parsed.get("tenant_id")
    agent_id = parsed.get("agent_id")
    if tenant_id and agent_id:
        out: dict[str, str] = {
            "tenant_id": str(tenant_id),
            "agent_id": str(agent_id),
        }
        direction = parsed.get("direction")
        if direction:
            out["direction"] = str(direction)
        greeting = parsed.get("greeting")
        if isinstance(greeting, str) and greeting.strip():
            out["greeting"] = greeting.strip()
        # F-C7 / A.4: host-verified caller phone for cancel/reschedule ownership.
        # Do not copy e164_number / from_number — those are often the trunk.
        verified = parsed.get("verified_caller_phone")
        if isinstance(verified, str) and verified.strip():
            out["verified_caller_phone"] = verified.strip()
        return out
    return None


async def _invoke_provider_prewarm(prewarm: Any) -> None:
    """Call a provider ``prewarm`` hook on the event-loop thread.

    LiveKit websocket pools schedule work via ``asyncio.create_task`` and raise
    ``RuntimeError: no running event loop`` when invoked from ``asyncio.to_thread``.
    """
    if asyncio.iscoroutinefunction(prewarm):
        await prewarm()
    else:
        prewarm()


async def prewarm_tts(tts: Any) -> None:
    """Open the TTS provider websocket pool before the first utterance (UVA-11)."""
    prewarm = getattr(tts, "prewarm", None)
    if prewarm is None:
        return
    await _invoke_provider_prewarm(prewarm)


async def prewarm_stt(stt: Any) -> None:
    """Open the STT provider connection pool before the first user turn (UVA-9/UVA-14)."""
    prewarm = getattr(stt, "prewarm", None)
    if prewarm is None:
        return
    await _invoke_provider_prewarm(prewarm)


def session_room_options(*, audio_channel: str = "webrtc") -> Any:
    """Room I/O options for session teardown.

    Browser WebRTC: close + delete room when the participant disconnects (UVA-15).
    Telephony: still close on disconnect, but do **not** delete the LiveKit room from
    the agent side — Telnyx/SIP owns hangup; aggressive room delete mid-playout has
    cut PSTN legs while TTS was still flushing.
    """
    from livekit.agents.voice.room_io.types import RoomOptions

    if audio_channel == "telephony":
        return RoomOptions(
            close_on_disconnect=True,
            delete_room_on_close=False,
        )
    return RoomOptions(
        close_on_disconnect=True,
        delete_room_on_close=True,
    )


def _force_barge_in_flush_enabled(audio_channel: str) -> bool:
    """Whether to ``interrupt(force=True)`` on bare VAD while the agent speaks.

    WebRTC default **off**: laptop/headset mics routinely trip Silero without an STT
    transcript, which chops replies mid-sentence and leaves dead air (nothing to answer).
    LiveKit native interruption (``min_duration`` + STT turn commit) still barge-in when
    the caller actually speaks, then ``generate_reply`` runs on that transcript.

    Telephony default **on** (faster PSTN flush). Override either way with
    ``UVA_FORCE_BARGE_IN_FLUSH=0|1``.
    """
    raw = (os.environ.get("UVA_FORCE_BARGE_IN_FLUSH") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return (audio_channel or "webrtc").strip().lower() == "telephony"


def wire_barge_in_flush(
    session: Any,
    logger: Any,
    *,
    audio_channel: str = "webrtc",
) -> None:
    """Optionally force-cancel in-flight LLM/TTS when the user speaks over the agent (UVA-13).

    On WebRTC, prefer LiveKit native interruption + STT turn commit so false VAD
    spikes cannot kill a reply with no user transcript to respond to.
    """
    from worker.humanization.coordinator import overlap_enabled
    # Candidate tolerance uses native pause/resume plus transcript takeover; a
    # forced bare-VAD cancellation would destroy the paused generation first.
    force_enabled = _force_barge_in_flush_enabled(audio_channel) and not overlap_enabled()
    agent_state: dict[str, str | None] = {"current": None}

    def _on_agent_state(ev: Any) -> None:
        agent_state["current"] = getattr(ev, "new_state", None)

    def _on_user_state(ev: Any) -> None:
        if getattr(ev, "new_state", None) != "speaking":
            return
        if agent_state["current"] != "speaking":
            return
        userdata = getattr(session, "userdata", None)
        if userdata is not None and getattr(userdata, "opening_active", False):
            logger.info(
                "barge-in: opening active — native interrupt/STT will handle (no force flush)"
            )
            return
        if not force_enabled:
            logger.info(
                "barge-in: VAD speaking during agent speech — force flush off "
                "(channel=%s); native interrupt waits for real STT turn",
                audio_channel,
            )
            return
        try:
            session.interrupt(force=True)
            logger.info("barge-in: interrupted in-flight agent speech")
        except RuntimeError as exc:
            # Expected when nothing is playing; still visible for F-M1 (not silent).
            logger.debug("stage=barge_in_interrupt skipped err=%s", exc)

    logger.info(
        "barge-in force flush configured channel=%s enabled=%s",
        audio_channel,
        force_enabled,
    )
    session.on("agent_state_changed", _on_agent_state)
    session.on("user_state_changed", _on_user_state)


async def prewarm_llm(llm: Any) -> None:
    """One-token LLM request so the first user turn avoids cold HTTP/TLS setup (UVA-7).

    Skip Groq entirely — free-tier TPM is 8k/min and a warm-up call plus front-desk prompts
    429 within the first conversational turns.
    """
    from livekit.agents.llm import ChatContext

    module = type(llm).__module__
    if "groq" in module.lower():
        return

    try:
        chat_ctx = ChatContext.empty()
        chat_ctx.add_message(role="user", content="ok")
        stream = llm.chat(chat_ctx=chat_ctx)
        async for _chunk in stream:
            break
        await stream.aclose()
    except Exception as exc:
        logger.warning("stage=prewarm_llm failed module=%s err=%s", module, exc)


async def prewarm_greeting_providers(
    *,
    tts: Any | None,
    stt: Any | None,
    logger: Any | None = None,
    room_name: str | None = None,
) -> None:
    """Warm TTS (+ STT) before the opening utterance — required for first-audio TTFB.

    Pass ``tts=None`` when a greeting-cache hit will play PCM (no live TTS RTT).
    Uses ``asyncio.wait`` on tasks rather than ``gather``: importing LiveKit's
    ``ChatContext`` (LLM prewarm) concurrent with ``gather`` can stall forever on
    some Windows / livekit-agents 1.6.x event-loop setups.
    """
    started = time.monotonic()
    tasks: list[tuple[str, asyncio.Task[None]]] = []
    if tts is not None:
        tasks.append(("tts", asyncio.create_task(prewarm_tts(tts))))
    if stt is not None:
        tasks.append(("stt", asyncio.create_task(prewarm_stt(stt))))
    if not tasks:
        return
    await asyncio.wait([task for _, task in tasks])
    if logger is not None:
        for label, task in tasks:
            if task.cancelled():
                logger.warning(
                    "provider prewarm %s cancelled room=%s",
                    label,
                    room_name or "?",
                )
                continue
            exc = task.exception()
            if exc is not None:
                logger.warning(
                    "provider prewarm %s failed room=%s: %s",
                    label,
                    room_name or "?",
                    exc,
                )
        logger.info(
            "greeting provider prewarm finished room=%s ms=%s",
            room_name or "?",
            int(round((time.monotonic() - started) * 1000)),
        )


async def prewarm_session_providers(
    *,
    tts: Any,
    llm: Any,
    stt: Any,
    logger: Any | None = None,
    room_name: str | None = None,
) -> None:
    """Warm STT then TTS then LLM (tests / full warm). Prefer schedule_provider_prewarm at runtime."""
    started = time.monotonic()
    # Sequential — avoids gather + LiveKit ChatContext interaction (see prewarm_greeting_providers).
    results: list[tuple[str, Exception | None]] = []
    for label, coro in (
        ("tts", prewarm_tts(tts)),
        ("stt", prewarm_stt(stt)),
        ("llm", asyncio.wait_for(prewarm_llm(llm), timeout=5.0)),
    ):
        try:
            await coro
            results.append((label, None))
        except Exception as exc:
            results.append((label, exc))
    if logger is not None:
        for label, result in results:
            if result is not None:
                logger.warning(
                    "provider prewarm %s failed room=%s: %s",
                    label,
                    room_name or "?",
                    result,
                )
        logger.info(
            "provider prewarm finished room=%s ms=%s",
            room_name or "?",
            int(round((time.monotonic() - started) * 1000)),
        )


def schedule_provider_prewarm(
    *,
    tts: Any | None,
    llm: Any,
    stt: Any | None,
    logger: Any | None = None,
    room_name: str | None = None,
    await_llm: bool = False,
    skip_tts: bool = False,
    skip_stt: bool = False,
) -> asyncio.Task[None]:
    """Start provider warm-up without blocking ``session.start()`` (UVA-2).

    Returns a task that completes when the selected TTS/STT warm steps finish.
    For static ``mode=say`` openings, callers typically pass ``skip_tts=True``
    (greeting PCM synth / cache covers TTS) and **do not await** this task —
    STT warms in the background so barge-in is ready without gating first audio.

    For ``generate_reply``, await this task (TTS+STT) before opening.

    LLM warm-up always runs in the background after TTS/STT. Never block the
    opening greeting on LLM prewarm — that added 10–15s of dead air on PSTN when
    Gemini was slow/failing, while the caller already heard ringing.
    ``await_llm`` is accepted for API compatibility but ignored.
    """
    del await_llm  # kept for call-site compatibility; greeting must not wait on LLM
    warm_tts = None if skip_tts else tts
    warm_stt = None if skip_stt else stt

    async def _llm() -> None:
        try:
            await asyncio.wait_for(prewarm_llm(llm), timeout=12.0)
        except Exception as exc:
            if logger is not None:
                logger.warning(
                    "provider prewarm llm failed room=%s: %s",
                    room_name or "?",
                    exc,
                )

    async def _greeting() -> None:
        try:
            await prewarm_greeting_providers(
                tts=warm_tts,
                stt=warm_stt,
                logger=logger,
                room_name=room_name,
            )
        except Exception as exc:
            if logger is not None:
                logger.warning(
                    "greeting provider prewarm task failed room=%s: %s",
                    room_name or "?",
                    exc,
                )
        # Always background LLM — greeting must start as soon as TTS/STT are warm.
        asyncio.create_task(_llm())

    return asyncio.create_task(_greeting())


async def await_greeting_prewarm(
    task: asyncio.Task[None] | None,
    *,
    timeout: float = 5.0,
    logger: Any | None = None,
    room_name: str | None = None,
) -> None:
    """Wait for TTS/STT warm-up before the opening turn; never raise into the entrypoint."""
    if task is None:
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except Exception as exc:
        if logger is not None:
            logger.warning(
                "greeting prewarm wait failed room=%s: %s",
                room_name or "?",
                exc,
            )


def _ms(seconds: float | None) -> int | None:
    seconds = measurement(seconds)
    if seconds is None:
        return None
    return max(0, int(round(seconds * 1000)))


def _p50(values: list[int]) -> int | None:
    if not values:
        return None
    return int(round(statistics.median(values)))


@dataclass
class RollingLatencyStats:
    """Completed diagnostic samples only; bounded to 256 observations per metric."""

    stt_ms: list[int] = field(default_factory=list)
    llm_ms: list[int] = field(default_factory=list)
    tts_ttfb_ms: list[int] = field(default_factory=list)
    e2e_ms: list[int] = field(default_factory=list)

    def record_turn(
        self,
        *,
        stt_ms: int | None,
        llm_ms: int | None,
        tts_ttfb_ms: int | None,
        e2e_ms: int | None,
        outcome: str = "completed",
        include: bool = True,
    ) -> dict[str, Any]:
        if include and outcome == "completed" and measurement(stt_ms) is not None:
            self.stt_ms.append(stt_ms)
        if include and outcome == "completed" and measurement(llm_ms) is not None:
            self.llm_ms.append(llm_ms)
        if include and outcome == "completed" and measurement(tts_ttfb_ms) is not None:
            self.tts_ttfb_ms.append(tts_ttfb_ms)
        if include and outcome == "completed" and measurement(e2e_ms) is not None:
            self.e2e_ms.append(e2e_ms)
        for values in (self.stt_ms, self.llm_ms, self.tts_ttfb_ms, self.e2e_ms):
            del values[:-256]
        percentiles = {name: percentile_report(values, validated=True) for name, values in (
            ("stt", self.stt_ms), ("llm", self.llm_ms), ("tts", self.tts_ttfb_ms), ("e2e", self.e2e_ms))}
        def median(name: str) -> int | None:
            value = percentiles[name]["p50Ms"]
            return int(round(value)) if value is not None else None
        stt_p50, llm_p50, tts_p50, round_p50 = (median(name) for name in ("stt", "llm", "tts", "e2e"))
        return {
            "type": "metrics_updated",
            "sttP50Ms": stt_p50,
            "stt_ms_p50": stt_p50,
            "llmTtftMs": llm_p50,
            "llm_ms_ttft": llm_p50,
            "ttsLatencyMs": tts_p50,
            "tts_ms": tts_p50,
            "roundTripMs": round_p50,
            "round_trip_ms": round_p50,
            "turnCount": len(self.e2e_ms),
            "sampleCounts": {"stt": len(self.stt_ms), "llm": len(self.llm_ms),
                             "tts": len(self.tts_ttfb_ms), "e2e": len(self.e2e_ms)},
            "percentiles": percentiles,
            "sampleOutcome": "completed",
            "latencyKind": "server_diagnostic_proxy",
            "sampleOperation": "normal_turn",
        }


def build_turn_latency_payload(
    speech_id: str,
    parts: "_TurnParts",
    *,
    e2e_ms: int | None,
) -> dict[str, Any]:
    """Build the per-turn payload expected by browser debug + analytics (UVA-5)."""
    return {
        "type": "turn_latency",
        "speechId": speech_id,
        "e2eMs": e2e_ms,
        "sttMs": parts.stt_ms,
        "turnMs": parts.turn_ms,
        "llmMs": parts.llm_ms,
        "ttsMs": parts.tts_ms,
        "ttsTtfbMs": parts.tts_ttfb_ms,
        "toolMs": parts.tool_ms,
        "toolName": parts.tool_name,
        # Dashboard aliases (self-serve debug panel + dev sandbox).
        "llmTtftMs": parts.llm_ms,
        "ttsLatencyMs": parts.tts_ttfb_ms,
        "roundTripMs": e2e_ms,
        "turn_latency_breakdown": {
            "sttMs": parts.stt_ms,
            "turnMs": parts.turn_ms,
            "llmMs": parts.llm_ms,
            "ttsMs": parts.tts_ms,
            "ttsTtfbMs": parts.tts_ttfb_ms,
            "toolMs": parts.tool_ms,
            "toolName": parts.tool_name,
            "e2eMs": e2e_ms,
        },
        "latencyKind": "server_diagnostic_proxy",
        "acousticVerified": False,
    }


@dataclass
class _TurnParts:
    stt_ms: int | None = None
    turn_ms: int | None = None
    llm_ms: int | None = None
    tts_ms: int | None = None
    tts_ttfb_ms: int | None = None
    tool_ms: int | None = None
    tool_name: str | None = None
    user_stopped_at: float | None = None


class TurnLatencyTracker:
    """Observe baseline execution; IDs/outcomes never control speech or business writes."""

    def __init__(self, room: Any, logger: Any, *, snapshot: dict | None = None,
                 session_id: str | None = None, lifecycle: bool = False) -> None:
        self._room, self._logger = room, logger
        self.session_id = identifier(session_id) or new_id("session")
        self.session_identity_source = "dispatch" if identifier(session_id) else "generated_observability"
        self.snapshot = snapshot or {"language": "unknown", "channel": "unknown"}
        self.policy_version = identifier(self.snapshot.get("humanization_policy_version")) or POLICY_VERSION
        self.component_versions = dict(COMPONENT_VERSIONS)
        effective_versions = self.snapshot.get("component_versions", {})
        for component in self.component_versions:
            if identifier(effective_versions.get(component)):
                self.component_versions[component] = effective_versions[component]
        delivery = self.snapshot.get("delivery", {})
        for component, key in (("delivery", "policy_version"), ("renderer", "renderer_version")):
            if identifier(delivery.get(key)):
                self.component_versions[component] = delivery[key]
        self._lifecycle = lifecycle
        self._turns: dict[str, _TurnParts] = {}
        self._traces: dict[str, GenerationTrace] = {}
        self._speeches: dict[str, dict] = {}
        self._tools: dict[str, dict] = {}
        self._completed_speeches: dict[str, bool] = {}
        self._seen_metrics: dict[tuple, bool] = {}
        self._user_turn_id: str | None = None
        self._user_stages: dict[str, float] = {}
        self._committed_users: dict[str, str] = {}
        self._last_user_stopped_at: float | None = None
        self._sequence = 0
        self._rolling = RollingLatencyStats()
        self._distributions = LatencyDistributions()
        self._background_usage: list[dict] = []
        self._usage_totals: dict[str, dict] = {}

    @staticmethod
    def _bound(mapping: dict, limit: int = 256) -> None:
        while len(mapping) > limit:
            mapping.pop(next(iter(mapping)))

    def _now(self) -> float:
        return time.monotonic()

    def _context_speech(self) -> str | None:
        scope = _speech_scope.get()
        return scope[1] if scope and scope[0] is self else None

    def _speech(self, speech_id: str) -> dict:
        if speech_id not in self._speeches:
            self._speeches[speech_id] = {
                "assistant_turn_id": new_id("assistant_turn"), "user_turn_id": self._user_turn_id,
                "generations": [], "committed": False, "source": "metrics_only",
                "user_stages": self._user_stages,
            }
            self._bound(self._speeches)
        return self._speeches[speech_id]

    def _generation(self, speech_id: str, *, fresh: bool = False) -> GenerationTrace:
        speech = self._speech(speech_id)
        scoped = _generation_scope.get()
        if not fresh and scoped and scoped[0] is self:
            trace = self._traces.get(scoped[1])
            if trace and scoped[1] in speech["generations"]:
                return trace
        if not fresh and speech["generations"]:
            trace = self._traces.get(speech["generations"][-1])
            if trace:
                return trace
        trace = GenerationTrace(self.session_id, speech["user_turn_id"], speech["assistant_turn_id"])
        trace.stages.update(speech["user_stages"] if trace.user_turn_id else {})
        if speech["committed"]:
            trace.stages["turn_committed"] = speech.get("committed_at")
        self._traces[trace.generation_id] = trace
        self._turns[trace.generation_id] = _TurnParts(user_stopped_at=self._last_user_stopped_at)
        speech["generations"].append(trace.generation_id)
        self._bound(self._traces)
        self._bound(self._turns)
        return trace

    def _event(self, event: str, *, trace: GenerationTrace | None = None,
               speech_id: str | None = None, tool: dict | None = None,
               outcome: str | None = None) -> dict:
        self._sequence += 1
        payload = {"event": event, "sequence": self._sequence,
                   "monotonicAt": self._now(), "session_id": self.session_id,
                   "session_identity_source": self.session_identity_source,
                   "user_turn_id": self._user_turn_id,
                   "humanization_policy_version": self.policy_version,
                   "component_versions": self.component_versions, "outcome": outcome}
        if trace:
            payload.update(trace.identity())
        if speech_id:
            payload["speechId"] = speech_id
        if tool:
            payload.update({k: tool.get(k) for k in
                ("tool_call_id", "framework_tool_call_id", "toolName", "user_turn_id", "assistant_turn_id", "generation_id")})
            payload.update(toolMs=tool.get("duration_ms"), toolStartAt=tool.get("started_at"),
                           toolFinishAt=tool.get("finished_at"), toolTimingSource="framework_lifecycle")
        self._logger.info("humanization_event %s", json.dumps(payload))
        return payload

    def mark_user_started_speaking(self) -> None:
        # A speech-state resumption before commit is the same user turn.
        if self._user_turn_id is None or self._user_stages.get("turn_committed") is not None:
            self._user_turn_id = new_id("user_turn")
            self._user_stages = {}
            self._last_user_stopped_at = None
        self._user_stages.setdefault("user_speech_started", self._now())
        self._event("user_speech_started")

    def mark_user_stopped_speaking(self) -> None:
        if self._user_turn_id is None:
            self.mark_user_started_speaking()
        self._last_user_stopped_at = self._now()
        self._user_stages["user_speech_stopped"] = self._last_user_stopped_at
        self._event("user_speech_stopped")

    def mark_turn_committed(self, message_id: str | None = None,
                            speech_id: str | None = None) -> None:
        message_id = identifier(message_id)
        if message_id and message_id in self._committed_users:
            return
        if self._user_turn_id is None or self._user_stages.get("turn_committed") is not None:
            self._user_turn_id = new_id("user_turn")
            self._user_stages = {}
        now = self._now()
        self._user_stages["turn_committed"] = now
        if message_id:
            self._committed_users[message_id] = self._user_turn_id
            self._bound(self._committed_users)
        if speech_id:
            speech = self._speech(speech_id)
            speech.update(committed=True, committed_at=now, user_turn_id=self._user_turn_id,
                          user_stages=self._user_stages)
            for gid in speech["generations"]:
                if trace := self._traces.get(gid):
                    trace.user_turn_id = self._user_turn_id
                    trace.stages.update(self._user_stages)
                    trace.stages["turn_committed"] = now
        self._event("turn_committed", speech_id=speech_id)

    def on_speech_created(self, ev: Any) -> None:
        handle = getattr(ev, "speech_handle", None)
        speech_id = identifier(getattr(handle, "id", None))
        if not speech_id:
            return
        speech = self._speech(speech_id)
        speech["source"] = getattr(ev, "source", None)
        # say() greetings/disclosures/cache playback are not normal user responses.
        if speech["source"] == "say":
            speech["user_turn_id"] = None
        _speech_scope.set((self, speech_id))
        trace = self._generation(speech_id)
        self._event("speech_created", trace=trace, speech_id=speech_id)
        handle.add_done_callback(lambda done: self.on_speech_done(speech_id, done))

    def on_speech_done(self, speech_id: str, handle: Any) -> None:
        if speech_id in self._completed_speeches:
            return
        speech = self._speech(speech_id)
        error = handle.exception() if callable(getattr(handle, "exception", None)) else None
        interrupted = bool(getattr(handle, "interrupted", False))
        if error:
            outcome = "provider_error"
        elif interrupted:
            outcome = "interrupted" if speech["committed"] or speech["source"] == "say" else "cancelled_speculation"
        else:
            outcome = "completed"
        for gid in speech["generations"]:
            trace = self._traces.get(gid)
            if trace is None:
                continue
            if trace.outcome is None or (interrupted and trace.outcome in {"cancelled", "cancelled_speculation"}):
                trace.outcome = outcome
            trace.stages["speech_interrupted" if interrupted else "speech_complete"] = self._now()
        # One latency/outcome report per speech handle. Multiple LLM steps have
        # distinct generation IDs and remain visible inside this report.
        self._emit_speech(speech_id, outcome)
        self._completed_speeches[speech_id] = True
        self._bound(self._completed_speeches)

    def annotate_tool(self, call_id: Any, *, outcome: str, speech_id: Any = None) -> None:
        if outcome not in OUTCOMES:
            raise ValueError("unsupported tool outcome")
        call_id = identifier(call_id)
        if call_id and call_id in self._tools:
            tool = self._tools[call_id]
            tool["outcome"] = outcome
            # RunContext provides exact speech ownership even when an executor
            # event arrives without our task scope. Never attach by most recent turn.
            if (sid := identifier(speech_id)) and sid in self._speeches:
                tool["speechId"] = sid
                tool.update(self._generation(sid).identity())
            return
        # An isolated tool invocation without framework lifecycle has no execution
        # measurement. Do not synthesize a second duration from its HTTP wrapper.
        if call_id:
            self._tools[call_id] = {"tool_call_id": new_id("tool_call"), "framework_tool_call_id": call_id, "outcome": outcome,
                                    "speechId": identifier(speech_id), "started_at": None}
            self._bound(self._tools)

    def on_tool_execution(self, ev: Any) -> None:
        update = getattr(ev, "update", None)
        kind = getattr(update, "type", None)
        if kind == "tool_call_started":
            fc = getattr(update, "function_call", None)
            call_id = identifier(getattr(fc, "call_id", None))
            if not call_id or call_id in self._tools:
                return
            speech_id = self._context_speech()
            trace = self._generation(speech_id) if speech_id else None
            name = getattr(fc, "name", None)
            tool = {"tool_call_id": new_id("tool_call"), "framework_tool_call_id": call_id,
                    "toolName": name if name in TOOL_NAMES else "unknown",
                    "speechId": speech_id, "started_at": self._now(), "finished_at": None,
                    "duration_ms": None, "outcome": None,
                    **(trace.identity() if trace else {"user_turn_id": self._user_turn_id})}
            self._tools[call_id] = tool
            self._bound(self._tools)
            self._event("tool_start", trace=trace, tool=tool, speech_id=speech_id)
        elif kind == "tool_call_ended":
            call_id = identifier(getattr(update, "call_id", None))
            tool = self._tools.get(call_id)
            if not tool or tool.get("finished_at") is not None:
                return
            tool["finished_at"] = self._now()
            start = tool.get("started_at")
            tool["duration_ms"] = _ms(tool["finished_at"] - start) if start is not None else None
            status = getattr(update, "status", None)
            tool["outcome"] = tool.get("outcome") or {
                "done": "completed", "error": "tool_error", "cancelled": "cancelled",
            }.get(status, "tool_error")
            self._event("tool_finish", tool=tool, speech_id=tool.get("speechId"), outcome=tool["outcome"])

    def on_metrics(self, ev: Any) -> None:
        metric = getattr(ev, "metrics", ev)
        speech_id = identifier(getattr(metric, "speech_id", None))
        is_llm = hasattr(metric, "ttft") and not hasattr(metric, "ttfb")
        is_tts = hasattr(metric, "ttfb")
        is_eou = hasattr(metric, "end_of_utterance_delay")
        if not (is_llm or is_tts or is_eou):
            return
        request_id = identifier(getattr(metric, "request_id", None))
        # Metrics can recur through multiple callbacks. Deduplicate only when an
        # actual provider request ID exists; don't collapse distinct missing IDs.
        key = ("tts" if is_tts else "llm", request_id, identifier(getattr(metric, "segment_id", None)))
        if request_id and key in self._seen_metrics:
            return
        if request_id:
            self._seen_metrics[key] = True
            self._bound(self._seen_metrics, 512)
        if not speech_id:
            self.record_activity("unattributed_provider", metric=metric)
            return
        if self._lifecycle and speech_id not in self._speeches:
            self._event("unowned_metric", outcome="stale")
            return
        if speech_id in self._completed_speeches:
            self._event("late_metric", speech_id=speech_id, outcome="stale")
            return
        trace = self._generation(speech_id)
        parts = self._turns[trace.generation_id]
        if is_eou:
            # EOUMetrics uses zero as a missing-VAD sentinel. Keep it unavailable
            # unless our session observed a speech-end transition.
            parts.turn_ms = _ms(getattr(metric, "end_of_utterance_delay", None))
            parts.stt_ms = _ms(getattr(metric, "transcription_delay", None))
            if self._last_user_stopped_at is None:
                parts.turn_ms = parts.turn_ms or None
                parts.stt_ms = parts.stt_ms or None
            speech = self._speech(speech_id)
            speech.update(committed=True, committed_at=speech.get("committed_at") or self._now())
            trace.stages["turn_committed"] = speech["committed_at"]
            self._event("turn_commit_metric_observed", trace=trace, speech_id=speech_id)
        elif is_llm:
            parts.llm_ms = parts.llm_ms if parts.llm_ms is not None else _ms(getattr(metric, "ttft", None))
            value = measurement(getattr(metric, "total_tokens", None))
            if value is not None:
                trace.usage["llm_tokens"] = trace.usage.get("llm_tokens", 0) + value
        else:
            parts.tts_ms = _ms(getattr(metric, "duration", None))
            parts.tts_ttfb_ms = parts.tts_ttfb_ms if parts.tts_ttfb_ms is not None else _ms(getattr(metric, "ttfb", None))
            value = measurement(getattr(metric, "audio_duration", None))
            if value is not None:
                trace.usage["synthesized_audio_seconds"] = trace.usage.get("synthesized_audio_seconds", 0) + value
            self._event("tts_first_audio_metric_observed", trace=trace, speech_id=speech_id)
        if getattr(metric, "cancelled", False):
            trace.outcome = "cancelled_speculation" if not self._speech(speech_id)["committed"] else "cancelled"
        # Direct metrics-only callers retain the legacy two-event contract. The
        # production session always waits for the public speech terminal callback.
        if is_tts and not self._lifecycle:
            self._emit_speech(speech_id, trace.outcome or "completed")

    def record_activity(self, category: str, *, metric: Any = None, cache_hit: bool | None = None) -> None:
        if category not in {"prewarm", "cache", "retry", "unattributed_provider"}:
            raise ValueError("unsupported usage category")
        row = {"activity_id": new_id("activity"), "category": category,
               "cache_hit": cache_hit, "llm_tokens": measurement(getattr(metric, "total_tokens", None)),
               "synthesized_audio_seconds": measurement(getattr(metric, "audio_duration", None))}
        self._background_usage.append(row)
        del self._background_usage[:-64]
        self._event(category)

    def _publish(self, payload: dict[str, Any], *, topic: str) -> None:
        if not publish_turn_latency_enabled():
            return
        try:
            result = self._room.local_participant.publish_data(json.dumps(payload), topic=topic, reliable=True)
            if asyncio.iscoroutine(result):
                task = asyncio.get_running_loop().create_task(result, name=f"publish_{topic}")
                task.add_done_callback(self._publish_done)
        except Exception:
            # Error strings can contain provider URLs/secrets. Structural failure only.
            self._logger.warning("telemetry_publish_failed topic=%s", topic)

    def _publish_done(self, task: Any) -> None:
        if not task.cancelled() and task.exception() is not None:
            self._logger.warning("telemetry_publish_failed")

    def _emit_speech(self, speech_id: str, outcome: str) -> None:
        speech = self._speech(speech_id)
        traces = [self._traces[g] for g in speech["generations"] if g in self._traces]
        if not traces:
            return
        tool_rows = [{k: t.get(k) for k in
                      ("tool_call_id", "framework_tool_call_id", "toolName", "generation_id", "outcome", "duration_ms", "started_at", "finished_at")}
                     for t in self._tools.values() if t.get("speechId") == speech_id]
        durations = [t["duration_ms"] for t in tool_rows if t["duration_ms"] is not None]
        parts = _TurnParts()
        for trace in traces:
            if trace.user_turn_id:
                trace.stages.update(speech["user_stages"])
            p = self._turns.get(trace.generation_id, _TurnParts())
            for name in ("stt_ms", "turn_ms", "llm_ms", "tts_ms", "tts_ttfb_ms"):
                if getattr(parts, name) is None:
                    setattr(parts, name, getattr(p, name))
        parts.tool_ms = sum(durations) if durations else None
        parts.tool_name = tool_rows[-1]["toolName"] if tool_rows else None
        eou = max((v for v in (parts.stt_ms, parts.turn_ms) if v is not None), default=None)
        # Tool sum is a separate execution diagnostic. Parallel tools and model
        # stages overlap, so it must not be added to this latency proxy.
        components = [v for v in (eou, parts.llm_ms, parts.tts_ttfb_ms) if v is not None]
        e2e_ms = sum(components) if components else None
        trace = traces[-1]
        operation = "normal_turn" if trace.user_turn_id or speech["source"] == "metrics_only" else "platform_speech"
        generation_rows = [{**t.identity(), "outcome": t.outcome or outcome,
                            "stages": t.stages, "usage": t.usage} for t in traces]
        for t in traces:
            if t.usage and not t.usage_reported:
                category = "cancelled_generation" if (t.outcome or outcome) in (
                    "cancelled", "cancelled_speculation", "interrupted") else "normal_turn" if t.user_turn_id else "platform_speech"
                bucket = self._usage_totals.setdefault(category, {"sampleCount": 0})
                bucket["sampleCount"] += 1
                for key, value in t.usage.items():
                    bucket[key] = bucket.get(key, 0) + value
                t.usage_reported = True
        # A cancelled/error provider sample remains invalid even if the handle
        # itself later finishes cleanly. Tools have an independent outcome.
        invalid = next((t.outcome for t in traces if t.outcome and t.outcome != "completed"), None)
        sample_outcome = invalid or outcome
        payload = {**build_turn_latency_payload(speech_id, parts, e2e_ms=e2e_ms),
                   **trace.identity(), "outcome": sample_outcome, "providerSnapshot": self.snapshot,
                   "operation": operation,
                   "session_identity_source": self.session_identity_source,
                   "humanization_policy_version": self.policy_version,
                   "component_versions": self.component_versions, "stages": trace.stages,
                   "generations": generation_rows, "tools": tool_rows,
                   "usageAttribution": {"source": "provider_metrics_diagnostic", "invoiceAccurate": False,
                                        "retry_usage": None, "unplayed_audio_seconds": None},
                   "stageTimingSource": "monotonic_observer; metric_observation_is_not_audio_playout",
                   "stageDefinitions": {"llm_request_start": "default_llm_node_entered",
                                        "first_useful_llm_text": "first_nonempty_content_delta; not acoustic/semantic verification",
                                        "tts_request_start": "default_tts_node_entered",
                                        "tts_first_audio": "first_frame_from_default_tts_node; not receiver playout",
                                        "first_speakable_chunk_ready": "unavailable_until_chunk_planning"}}
        event = self._event("turn_latency", trace=trace, speech_id=speech_id, outcome=sample_outcome)
        payload.update(sequence=event["sequence"], monotonicAt=event["monotonicAt"])
        self._logger.info("turn_latency %s", json.dumps(payload))
        self._publish(payload, topic="turn_latency")
        lane = tuple(self.snapshot.get(stage, {}).get(key) for stage in ("stt", "llm", "tts")
                     for key in ("provider", "effective_model")) + (
                         self.snapshot.get("language"), self.snapshot.get("channel"), operation)
        distribution = self._distributions.record(outcome=sample_outcome, lane=lane,
            values={"stt": parts.stt_ms, "llm": parts.llm_ms, "tts": parts.tts_ttfb_ms, "e2e": e2e_ms})
        rolling = self._rolling.record_turn(stt_ms=parts.stt_ms, llm_ms=parts.llm_ms,
            tts_ttfb_ms=parts.tts_ttfb_ms, e2e_ms=e2e_ms, outcome=sample_outcome, include=operation == "normal_turn")
        rolling.update(session_id=self.session_id, humanization_policy_version=self.policy_version,
                       sequence=event["sequence"], distribution=distribution,
                       providerSnapshot=self.snapshot, usageAttribution=self.usage_report())
        self._publish(rolling, topic="metrics_updated")

    def usage_report(self) -> dict:
        return {"source": "provider_metrics_diagnostic", "invoiceAccurate": False,
                "categories": {key: dict(value) for key, value in self._usage_totals.items()},
                "window": "session_terminal_generations",
                "activities": list(self._background_usage[-8:]),
                "retry_usage": None, "unplayed_audio_seconds": None}

    def close(self, ev: Any = None) -> None:
        for speech_id, speech in list(self._speeches.items()):
            if speech_id in self._completed_speeches:
                continue
            for gid in speech["generations"]:
                if trace := self._traces.get(gid):
                    trace.outcome = trace.outcome or "cancelled"
            self._emit_speech(speech_id, "cancelled")
            self._completed_speeches[speech_id] = True
        self._event("session_close")
        self._logger.info("humanization_usage %s", json.dumps({
            "session_id": self.session_id, "humanization_policy_version": self.policy_version,
            **self.usage_report(),
        }))


def observe_agent_nodes(agent: Any, tracker: TurnLatencyTracker) -> None:
    """Pass-through observers on existing public hooks, solely for Phase 1 timings.

    No AwaazAgent, state reducer, prompt rewriting, STT logic or chunk planning.
    Preserve every yielded object and close default generators on cancellation.
    """
    from types import MethodType

    original_llm, original_tts = agent.llm_node, agent.tts_node

    async def llm_node(_agent: Any, chat_ctx: Any, tools: Any, model_settings: Any):
        speech_id = tracker._context_speech()
        trace = None
        if speech_id:
            # Initial speech identity gets one generation; tool continuation gets
            # a fresh one. Parallel speech tasks retain their own context scope.
            previous = tracker._generation(speech_id)
            trace = tracker._generation(speech_id, fresh=previous.stages["llm_request_start"] is not None)
            trace.stages["llm_request_start"] = tracker._now()
            tracker._event("llm_request_start", trace=trace, speech_id=speech_id)
        token = _generation_scope.set((tracker, trace.generation_id) if trace else None)
        stream = None
        try:
            stream = original_llm(chat_ctx, tools, model_settings)
            if inspect.isawaitable(stream):
                stream = await stream
            async for chunk in stream:
                text = chunk if isinstance(chunk, str) else getattr(getattr(chunk, "delta", None), "content", None)
                if trace and trace.stages["first_useful_llm_text"] is None and isinstance(text, str) and text.strip():
                    trace.stages["first_useful_llm_text"] = tracker._now()
                    tracker._event("first_useful_llm_text", trace=trace, speech_id=speech_id)
                yield chunk
        except asyncio.CancelledError:
            if trace:
                trace.outcome = "cancelled" if tracker._speech(speech_id)["committed"] else "cancelled_speculation"
            raise
        except Exception:
            if trace:
                trace.outcome = "provider_error"
            raise
        finally:
            try:
                if callable(getattr(stream, "aclose", None)):
                    await stream.aclose()
            finally:
                _generation_scope.reset(token)

    async def tts_node(_agent: Any, text: Any, model_settings: Any):
        speech_id = tracker._context_speech()
        trace = tracker._generation(speech_id) if speech_id else None
        token = _generation_scope.set((tracker, trace.generation_id) if trace else None)
        if trace:
            trace.stages["tts_request_start"] = tracker._now()
            tracker._event("tts_request_start", trace=trace, speech_id=speech_id)
        stream = None
        try:
            stream = original_tts(text, model_settings)
            if inspect.isawaitable(stream):
                stream = await stream
            async for frame in stream:
                # First frame only; no per-frame timestamps/logging/serialization.
                if trace and trace.stages["tts_first_audio"] is None:
                    trace.stages["tts_first_audio"] = tracker._now()
                    tracker._event("tts_first_audio", trace=trace, speech_id=speech_id)
                yield frame
        except asyncio.CancelledError:
            if trace:
                trace.outcome = "cancelled" if tracker._speech(speech_id)["committed"] else "cancelled_speculation"
            raise
        except Exception:
            if trace:
                trace.outcome = "provider_error"
            raise
        finally:
            try:
                if callable(getattr(stream, "aclose", None)):
                    await stream.aclose()
            finally:
                _generation_scope.reset(token)

    agent.llm_node = MethodType(llm_node, agent)
    agent.tts_node = MethodType(tts_node, agent)


def wire_turn_latency(session: Any, room: Any, logger: Any, *, agent: Any = None,
                      snapshot: dict | None = None, session_id: str | None = None) -> TurnLatencyTracker:
    tracker = TurnLatencyTracker(room, logger, snapshot=snapshot, session_id=session_id, lifecycle=True)

    def user_state(ev: Any) -> None:
        new_state = getattr(ev, "new_state", None)
        if new_state == "speaking":
            tracker.mark_user_started_speaking()
        elif new_state == "listening" and getattr(ev, "old_state", None) == "speaking":
            tracker.mark_user_stopped_speaking()

    def item_added(ev: Any) -> None:
        item = getattr(ev, "item", None)
        if getattr(item, "role", None) == "user":
            tracker.mark_turn_committed(getattr(item, "id", None), tracker._context_speech())

    def false_interruption(ev: Any) -> None:
        speech_id = identifier(getattr(ev, "speech_id", None))
        tracker._event("false_interruption", speech_id=speech_id, outcome="false_interruption")

    def error(ev: Any) -> None:
        speech_id = tracker._context_speech()
        recoverable = bool(getattr(getattr(ev, "error", None), "recoverable", False))
        if recoverable:
            tracker.record_activity("retry")
        elif speech_id and speech_id not in tracker._completed_speeches:
            tracker._generation(speech_id).outcome = "provider_error"
        tracker._event("provider_error", speech_id=speech_id, outcome="provider_error")

    session.on("metrics_collected", tracker.on_metrics)
    session.on("user_state_changed", user_state)
    session.on("tool_execution_updated", tracker.on_tool_execution)
    session.on("speech_created", tracker.on_speech_created)
    session.on("conversation_item_added", item_added)
    session.on("agent_false_interruption", false_interruption)
    session.on("error", error)
    session.on("close", tracker.close)
    if agent is not None:
        observe_agent_nodes(agent, tracker)
    startup = getattr(getattr(session, "userdata", None), "telemetry_startup", None)
    if isinstance(startup, dict):
        tracker.record_activity("cache", cache_hit=startup.get("provider_cache_hit"))
        if startup.get("prewarm_scheduled"):
            tracker.record_activity("prewarm")
    tracker._event("session_observability_ready")
    return tracker
