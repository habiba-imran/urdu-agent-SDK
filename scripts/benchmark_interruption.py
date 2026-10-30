"""Synthetic installed-runtime benchmark; no microphone, provider, or phone calls.

Run: .venv/Scripts/python.exe scripts/benchmark_interruption.py
Speech duration is injected at LiveKit's VAD hook, not measured by a real VAD.
The direct audio source has an intentionally injected 750 ms cleanup delay.
Output-control timing is NOT receiver/caller-heard latency.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from livekit.agents import AgentSession  # noqa: E402
from worker.interruption import (  # noqa: E402
    aec_warmup_duration, interruption_min_duration, wire_interruption_output_stop,
)
from test_smooth_interruption import PausableSink, SlowCleanupAgent  # noqa: E402
from test_humanization_observability_framework import SyntheticTTS  # noqa: E402


async def scenario(channel: str, opening: bool, candidate: bool) -> dict:
    os.environ['UVA_FAST_INTERRUPTION_OUTPUT'] = '1' if candidate else '0'
    duration = interruption_min_duration(channel) if candidate else (.55 if channel == 'telephony' else .65)
    warmup = (aec_warmup_duration(channel) if candidate else 3.0) if opening else 0.0
    session = AgentSession(tts=SyntheticTTS(), aec_warmup_duration=warmup,
                           turn_handling={'interruption': {'mode': 'vad', 'min_duration': duration,
                                                          'min_words': 0, 'resume_false_interruption': False}})
    sink, agent = PausableSink(), SlowCleanupAgent()
    session.output.audio = sink
    wire_interruption_output_stop(session)
    await session.start(agent, record=False)
    tasks = []
    try:
        handle = session.say('Synthetic interruption benchmark.', audio=agent.audio_source())
        await asyncio.wait_for(sink.started.wait(), 3)
        sink.cleared.clear()
        await asyncio.sleep(.05)
        started = time.monotonic()
        session._activity.on_start_of_speech(None, time.time())

        async def feed_voice():
            while not handle.interrupted:
                session._activity.on_vad_inference_done(SimpleNamespace(
                    speech_duration=time.monotonic()-started, raw_accumulated_silence=0, speaking=True))
                await asyncio.sleep(.01)

        async def slow_cleanup():
            await agent.cleaning.wait()
            await asyncio.sleep(.75)
            agent.release_cleanup.set()

        async def stopped():
            waiters = [asyncio.create_task(sink.paused.wait()), asyncio.create_task(sink.cleared.wait())]
            try:
                await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
                return time.monotonic()
            finally:
                for waiter in waiters:
                    if not waiter.done():
                        waiter.cancel()
                await asyncio.gather(*waiters, return_exceptions=True)

        tasks = [asyncio.create_task(feed_voice()), asyncio.create_task(slow_cleanup()), asyncio.create_task(stopped())]
        stop_at = await asyncio.wait_for(tasks[2], 5)
        await asyncio.wait_for(handle.wait_for_playout(), 5)
        return {'channel': channel, 'phase': 'opening' if opening else 'mid_conversation',
                'policy': 'candidate' if candidate else 'previous',
                'voice_onset_to_output_control_ms': round((stop_at-started)*1000, 1),
                'speech_gate_ms': duration*1000, 'initial_aec_guard_ms': warmup*1000,
                'injected_source_cleanup_ms': 750, 'measurement': 'synthetic_worker_output_control_not_caller_audio'}
    finally:
        agent.release_cleanup.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await session.aclose()


async def main():
    rows = []
    for channel in ('webrtc', 'telephony'):
        for opening in (True, False):
            for candidate in (False, True):
                rows.append(await scenario(channel, opening, candidate))
    print(json.dumps({'fixtures_only': True, 'rows': rows}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
