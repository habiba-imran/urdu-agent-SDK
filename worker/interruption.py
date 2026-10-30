"""Provider-independent interruption timing and early output stop.

LiveKit owns speech detection, interruption acceptance, history and cancellation.
Only pause a handle it has ALREADY interrupted: never cancel on bare VAD, resume
cancelled speech, bypass a disclosure, or cancel a business operation.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def _seconds(name: str, default: float, lower: float, upper: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
        if math.isfinite(value) and lower <= value <= upper:
            return value
    except ValueError:
        pass
    logger.warning("invalid %s; using %.2fs", name, default)
    return default


def interruption_min_duration(audio_channel: str) -> float:
    # Silero already requires 120 ms of speech. Keep a sustained-speech gate;
    # don't wait for STT, words, end-of-turn, or a provider network response.
    return _seconds("UVA_INTERRUPTION_MIN_DURATION", .30 if audio_channel == "telephony" else .35, .15, 1.5)


def aec_warmup_duration(audio_channel: str) -> float:
    # The framework defaults to a 3s STT/interrupt blackout on the first reply.
    # Browser capture already requests AEC. Retain a brief startup echo guard;
    # a PSTN leg has no browser AEC to warm. Required disclosures are protected
    # separately by allow_interruptions=False.
    return _seconds("UVA_AEC_WARMUP_SECONDS", 0.0 if audio_channel == "telephony" else .25, 0.0, 3.0)


def wire_interruption_output_stop(session: Any) -> None:
    """Pause accepted interruptions before potentially slow TTS/LLM cleanup.

    Uses public SpeechHandle and AudioOutput APIs. Native clearing still owns
    playback position and history truncation. Resume the output only AFTER that
    old segment finishes/clears, or its handle completes. This never resumes the
    old speech. Outputs without pause support retain the framework's clear path.
    """
    if os.getenv("UVA_FAST_INTERRUPTION_OUTPUT", "1").strip().lower() in {"0", "false", "off", "no"}:
        return
    tasks: set[asyncio.Task] = set()
    closed = False
    voice_detected_at: float | None = None

    def on_user_state(event: Any) -> None:
        nonlocal voice_detected_at
        if event.new_state == "speaking":
            voice_detected_at = time.monotonic()

    async def watch(handle: Any) -> None:
        finished = asyncio.get_running_loop().create_future()
        playout = None
        paused_output = None
        interrupted_at = None

        def done(_handle: Any) -> None:
            if not finished.done():
                finished.set_result(None)

        handle.add_done_callback(done)
        try:
            await handle.wait_if_not_interrupted([finished])
            if closed or not handle.interrupted or handle.done() or not handle.allow_interruptions:
                return
            if session.current_speech is not handle:
                return
            # Native false-interruption recovery already pauses immediately and
            # owns its resume. Don't compete with its pause ownership.
            if session.options.interruption["resume_false_interruption"]:
                return
            output = session.output.audio
            if output is None or not output.can_pause:
                return
            paused_output = output
            interrupted_at = time.monotonic()
            output.pause()
            detected_ms = ((interrupted_at - voice_detected_at) * 1000
                           if voice_detected_at is not None else None)
            logger.info("interruption_output_paused speech_id=%s voice_detected_to_pause_ms=%s measurement=worker_output_control",
                        handle.id, round(detected_ms, 1) if detected_ms is not None else None)
            # Also handles a clear that raced ahead of this observer. A tool can
            # keep its speech handle alive after media is already cleared.
            playout = asyncio.create_task(output.wait_for_playout())
            await asyncio.wait([finished, playout], return_when=asyncio.FIRST_COMPLETED)
        finally:
            handle.remove_done_callback(done)
            if playout is not None:
                if not playout.done():
                    playout.cancel()
                await asyncio.gather(playout, return_exceptions=True)
            if paused_output is not None:
                # Keep cancellation and shutdown from leaving a shared sink
                # paused for the next turn. No old audio survives native clear.
                if session.output.audio is paused_output:
                    paused_output.resume()
                logger.debug("interruption_output_released speech_id=%s cleanup_wait_ms=%.1f",
                             handle.id, (time.monotonic() - interrupted_at) * 1000)

    def on_speech(event: Any) -> None:
        handle = event.speech_handle
        if closed or not handle.allow_interruptions:
            return
        task = asyncio.create_task(watch(handle), name="interruption_output_stop")
        tasks.add(task)

        def completed(task: asyncio.Task) -> None:
            tasks.discard(task)
            if not task.cancelled() and (error := task.exception()) is not None:
                logger.warning("interruption output observer failed error_type=%s", type(error).__name__)
        task.add_done_callback(completed)

    def on_close(_event: Any) -> None:
        nonlocal closed
        closed = True
        for task in tuple(tasks):
            task.cancel()

    session.on("user_state_changed", on_user_state)
    session.on("speech_created", on_speech)
    session.on("close", on_close)
