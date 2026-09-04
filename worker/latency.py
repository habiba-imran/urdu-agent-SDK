"""Latency helpers for the voice worker (UVA Phase 1–4).

Centralizes turn-handling defaults, provider warm-up, session-identity lookup, per-turn
``turn_latency`` / ``metrics_updated`` telemetry, tool-stage timing, barge-in flush, and
fast room teardown options.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Phase 2 (UVA-6): 0.15s min endpointing — commit turns faster during conversation.
# Preemptive generation starts LLM while the user is still speaking (UVA-14).
# preemptive_tts=True starts Cartesia synthesis on streamed tokens *before* EOU
# confirms — without this, TTS waits for full turn commit (+ seconds of dead air).
TURN_HANDLING_OPTIONS: dict[str, Any] = {
    # UVA-13: faster barge-in — discard buffered TTS and cancel in-flight generation.
    "interruption": {
        "enabled": True,
        "discard_audio_if_uninterruptible": True,
        "min_duration": 0.3,
        "resume_false_interruption": True,
        "false_interruption_timeout": 1.5,
    },
    "turn_detection": "stt",
    "endpointing": {"min_delay": 0.15, "max_delay": 1.5},
    "preemptive_generation": {
        "enabled": True,
        "preemptive_tts": True,
        "max_speech_duration": 12.0,
        "max_retries": 3,
    },
}

# PSTN/SIP: no browser AEC — false-interruption resume causes mid-utterance flicker.
# Keep barge-in enabled; do not discard caller audio after an intentional interrupt.
TELEPHONY_TURN_HANDLING_OPTIONS: dict[str, Any] = {
    **TURN_HANDLING_OPTIONS,
    "interruption": {
        "enabled": True,
        "discard_audio_if_uninterruptible": False,
        "min_duration": 0.3,
        "resume_false_interruption": False,
        "false_interruption_timeout": 0.7,
    },
}


def turn_handling_for_channel(audio_channel: str) -> dict[str, Any]:
    """Return turn-handling defaults for WebRTC vs telephony audio legs."""
    if audio_channel == "telephony":
        return TELEPHONY_TURN_HANDLING_OPTIONS
    return TURN_HANDLING_OPTIONS


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
    except Exception:
        return False
    if not isinstance(parsed, dict):
        return False
    direction = str(parsed.get("direction") or "").lower()
    if direction in {"inbound", "outbound"}:
        return True
    if parsed.get("e164_number") or parsed.get("phone_number_id") or parsed.get("sip_call_id"):
        return True
    return False

# Tighter VAD silence gate for in-call turns — less dead air after the caller stops.
VAD_OPTIONS: dict[str, float] = {
    "min_speech_duration": 0.05,
    "min_silence_duration": 0.35,
    "prefix_padding_duration": 0.35,
    "activation_threshold": 0.35,
}


def load_session_identity(room_name: str) -> dict[str, str] | None:
    """Return ``{tenant_id, agent_id}`` for an open session row, or ``None``.

    Available as soon as the mint commits — before the browser participant joins —
    so the worker can build STT/LLM/TTS in parallel with ``wait_for_participant``.
    """
    import psycopg

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        from scripts.dbconn import conn_kwargs
    except ImportError:
        from dbconn import conn_kwargs  # type: ignore # noqa: E402

    try:
        with psycopg.connect(**conn_kwargs(), connect_timeout=5) as conn:
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
    except Exception:
        return None
    if row is None or not row[0] or not row[1]:
        return None
    return {"tenant_id": str(row[0]), "agent_id": str(row[1])}


def parse_dispatch_metadata(raw: str | None) -> dict[str, str] | None:
    """Parse ``tenant_id`` / ``agent_id`` from a LiveKit job or dispatch metadata JSON blob.

    Also preserves a ``direction`` hint when present so the early telephony path can
    select the correct audio profile without waiting for the SIP participant.
    """
    if not raw:
        return None
    try:
        parsed = json.loads(raw) if not isinstance(raw, dict) else raw
    except Exception:
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


def wire_barge_in_flush(session: Any, logger: Any) -> None:
    """Force-cancel in-flight LLM/TTS when the user speaks over the agent (UVA-13).

    LiveKit's adaptive interruption handles most cases; ``interrupt(force=True)`` ensures
    buffered outbound audio is flushed and generation is cancelled promptly.

    Safe with telephony because greetings are interruptible and
    ``discard_audio_if_uninterruptible`` is disabled on the PSTN turn-handling profile.
    """
    agent_state: dict[str, str | None] = {"current": None}

    def _on_agent_state(ev: Any) -> None:
        agent_state["current"] = getattr(ev, "new_state", None)

    def _on_user_state(ev: Any) -> None:
        if getattr(ev, "new_state", None) != "speaking":
            return
        if agent_state["current"] != "speaking":
            return
        try:
            session.interrupt(force=True)
            logger.info("barge-in: interrupted in-flight agent speech")
        except RuntimeError:
            pass

    session.on("agent_state_changed", _on_agent_state)
    session.on("user_state_changed", _on_user_state)


async def prewarm_llm(llm: Any) -> None:
    """One-token LLM request so the first user turn avoids cold HTTP/TLS setup (UVA-7)."""
    from livekit.agents.llm import ChatContext

    try:
        chat_ctx = ChatContext.empty()
        chat_ctx.add_message(role="user", content="ok")
        stream = llm.chat(chat_ctx=chat_ctx)
        async for _chunk in stream:
            break
        await stream.aclose()
    except Exception:
        pass


async def prewarm_greeting_providers(
    *,
    tts: Any,
    stt: Any,
    logger: Any | None = None,
    room_name: str | None = None,
) -> None:
    """Warm TTS (+ STT) before the opening utterance — required for first-audio TTFB.

    Uses ``asyncio.wait`` on tasks rather than ``gather``: importing LiveKit's
    ``ChatContext`` (LLM prewarm) concurrent with ``gather`` can stall forever on
    some Windows / livekit-agents 1.6.x event-loop setups.
    """
    started = time.monotonic()
    tasks = (
        ("tts", asyncio.create_task(prewarm_tts(tts))),
        ("stt", asyncio.create_task(prewarm_stt(stt))),
    )
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
    tts: Any,
    llm: Any,
    stt: Any,
    logger: Any | None = None,
    room_name: str | None = None,
    await_llm: bool = False,
) -> asyncio.Task[None]:
    """Start provider warm-up without blocking ``session.start()`` (UVA-2).

    Returns a task that completes when **TTS + STT** are warm — await it before
    ``apply_session_opening`` so the greeting does not pay a cold websocket.

    LLM warm-up always runs in the background after TTS/STT. Never block the
    opening greeting on LLM prewarm — that added 10–15s of dead air on PSTN when
    Gemini was slow/failing, while the caller already heard ringing.
    ``await_llm`` is accepted for API compatibility but ignored.
    """
    del await_llm  # kept for call-site compatibility; greeting must not wait on LLM

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
                tts=tts,
                stt=stt,
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
    if seconds is None:
        return None
    return max(0, int(round(seconds * 1000)))


def _p50(values: list[int]) -> int | None:
    if not values:
        return None
    return int(round(statistics.median(values)))


@dataclass
class RollingLatencyStats:
    """Rolling p50 stats published as ``metrics_updated`` after each turn (UVA-5)."""

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
    ) -> dict[str, Any]:
        if stt_ms is not None:
            self.stt_ms.append(stt_ms)
        if llm_ms is not None:
            self.llm_ms.append(llm_ms)
        if tts_ttfb_ms is not None:
            self.tts_ttfb_ms.append(tts_ttfb_ms)
        if e2e_ms is not None:
            self.e2e_ms.append(e2e_ms)
        stt_p50 = _p50(self.stt_ms)
        llm_p50 = _p50(self.llm_ms)
        tts_p50 = _p50(self.tts_ttfb_ms)
        round_p50 = _p50(self.e2e_ms)
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
        "toolMs": parts.tool_ms or 0,
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
            "toolMs": parts.tool_ms or 0,
            "toolName": parts.tool_name,
            "e2eMs": e2e_ms,
        },
    }


@dataclass
class _TurnParts:
    stt_ms: int | None = None
    turn_ms: int | None = None
    llm_ms: int | None = None
    tts_ms: int | None = None
    tts_ttfb_ms: int | None = None
    tool_ms: int = 0
    tool_name: str | None = None
    user_stopped_at: float | None = None


class TurnLatencyTracker:
    """Aggregate LiveKit stage metrics and publish per-turn telemetry (UVA-3/UVA-5/UVA-8)."""

    def __init__(self, room: Any, logger: Any) -> None:
        self._room = room
        self._logger = logger
        self._turns: dict[str, _TurnParts] = {}
        self._last_user_stopped_at: float | None = None
        self._tool_starts: dict[str, tuple[float, str]] = {}
        self._pending_tool_ms: int = 0
        self._pending_tool_names: list[str] = []
        self._rolling = RollingLatencyStats()

    def mark_user_stopped_speaking(self) -> None:
        self._last_user_stopped_at = time.monotonic()

    def record_tool_duration(self, tool_name: str, duration_ms: int) -> None:
        """Record tool execution time from ``tool_execution_updated`` or tool wrappers."""
        self._pending_tool_ms += max(0, duration_ms)
        self._pending_tool_names.append(tool_name)

    def _attach_pending_tools(self, parts: _TurnParts) -> None:
        if self._pending_tool_ms > 0:
            parts.tool_ms = self._pending_tool_ms
            parts.tool_name = self._pending_tool_names[-1]
            self._pending_tool_ms = 0
            self._pending_tool_names.clear()

    def on_tool_execution(self, ev: Any) -> None:
        update = getattr(ev, "update", None)
        if update is None:
            return
        update_type = getattr(update, "type", None)
        if update_type == "tool_call_started":
            fc = getattr(update, "function_call", None)
            if fc is None:
                return
            call_id = getattr(fc, "call_id", None) or getattr(fc, "id", None)
            name = getattr(fc, "name", "unknown")
            if call_id:
                self._tool_starts[str(call_id)] = (time.monotonic(), str(name))
            return
        if update_type == "tool_call_ended":
            call_id = getattr(update, "call_id", None)
            if not call_id:
                return
            started = self._tool_starts.pop(str(call_id), None)
            if started is None:
                return
            duration_ms = int(round((time.monotonic() - started[0]) * 1000))
            self.record_tool_duration(started[1], duration_ms)

    def on_metrics(self, ev: Any) -> None:
        metric = getattr(ev, "metrics", ev)

        if hasattr(metric, "end_of_utterance_delay") and hasattr(
            metric, "transcription_delay"
        ):
            speech_id = getattr(metric, "speech_id", None) or "_default"
            parts = self._turns.setdefault(speech_id, _TurnParts())
            parts.turn_ms = _ms(getattr(metric, "end_of_utterance_delay", None))
            parts.stt_ms = _ms(getattr(metric, "transcription_delay", None))
            if self._last_user_stopped_at is not None:
                parts.user_stopped_at = self._last_user_stopped_at
            return

        if hasattr(metric, "ttft") and not hasattr(metric, "ttfb"):
            speech_id = getattr(metric, "speech_id", None) or "_default"
            parts = self._turns.setdefault(speech_id, _TurnParts())
            parts.llm_ms = _ms(getattr(metric, "ttft", None))
            self._attach_pending_tools(parts)
            return

        if hasattr(metric, "ttfb"):
            speech_id = getattr(metric, "speech_id", None) or "_default"
            parts = self._turns.setdefault(speech_id, _TurnParts())
            parts.tts_ms = _ms(getattr(metric, "duration", None))
            parts.tts_ttfb_ms = _ms(getattr(metric, "ttfb", None))
            self._attach_pending_tools(parts)
            self._maybe_emit(speech_id, parts)
            self._turns.pop(speech_id, None)

    def _publish(self, payload: dict[str, Any], *, topic: str) -> None:
        try:
            self._room.local_participant.publish_data(
                json.dumps(payload),
                topic=topic,
                reliable=True,
            )
        except Exception as exc:
            self._logger.warning("%s publish failed: %s", topic, exc)

    def _maybe_emit(self, speech_id: str, parts: _TurnParts) -> None:
        if parts.llm_ms is None and parts.turn_ms is None and parts.stt_ms is None:
            return

        components = [
            x
            for x in (
                parts.stt_ms,
                parts.turn_ms,
                parts.llm_ms,
                parts.tts_ttfb_ms,
                parts.tool_ms or None,
            )
            if x is not None
        ]
        e2e_ms = sum(components) if components else None
        if parts.user_stopped_at is not None and parts.tts_ttfb_ms is not None:
            e2e_ms = max(
                e2e_ms or 0,
                int(round((time.monotonic() - parts.user_stopped_at) * 1000)),
            )

        turn_payload = build_turn_latency_payload(speech_id, parts, e2e_ms=e2e_ms)
        self._logger.info(
            "turn_latency room=%s e2e=%sms stt=%s turn=%s llm=%s tts_ttfb=%s tool=%s(%s)",
            getattr(self._room, "name", "?"),
            e2e_ms,
            parts.stt_ms,
            parts.turn_ms,
            parts.llm_ms,
            parts.tts_ttfb_ms,
            parts.tool_ms,
            parts.tool_name,
        )
        self._publish(turn_payload, topic="turn_latency")

        rolling = self._rolling.record_turn(
            stt_ms=parts.stt_ms,
            llm_ms=parts.llm_ms,
            tts_ttfb_ms=parts.tts_ttfb_ms,
            e2e_ms=e2e_ms,
        )
        self._publish(rolling, topic="metrics_updated")


def wire_turn_latency(session: Any, room: Any, logger: Any) -> TurnLatencyTracker:
    """Hook session events to emit per-turn latency payloads to the browser (UVA-5)."""
    tracker = TurnLatencyTracker(room, logger)

    def _on_metrics(ev: Any) -> None:
        tracker.on_metrics(ev)

    def _on_user_state(ev: Any) -> None:
        new_state = getattr(ev, "new_state", None)
        if new_state == "listening":
            tracker.mark_user_stopped_speaking()

    def _on_tool_execution(ev: Any) -> None:
        tracker.on_tool_execution(ev)

    session.on("metrics_collected", _on_metrics)
    session.on("user_state_changed", _on_user_state)
    session.on("tool_execution_updated", _on_tool_execution)
    return tracker
