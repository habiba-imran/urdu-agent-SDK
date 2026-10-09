"""Offline Phase 1 overhead benchmark; no provider calls or audio/network I/O.

Run with the repository Python environment:
    python scripts/benchmark_humanization_telemetry.py --output <local JSON path>
Measures event handling, serialization and log formatting; deployment log/network
sink overhead is deliberately not claimed. Threshold is 3 ms p95 per tool turn,
including two LLM node passes, TTS observation and a full provider snapshot.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worker.latency import TurnLatencyTracker, observe_agent_nodes  # noqa: E402
from worker.telemetry import percentile_report  # noqa: E402

SNAPSHOT = {
    "language": "en", "channel": "webrtc", "source": "local_constructor_configuration", "deployed_verified": False,
    "stt": {"provider": "deepgram", "requested_model": "nova-3", "effective_model": "nova-3", "plugin_version": "1.6.5",
            "effective_options": {"stt_mode": "nova", "language": "en-US", "endpointing_ms": 200,
                                  "sample_rate": 16000, "interim_results": True, "smart_format": False, "no_delay": True}},
    "llm": {"provider": "groq", "requested_model": "openai/gpt-oss-20b", "effective_model": "openai/gpt-oss-20b",
            "plugin_version": "1.6.5", "effective_options": {"max_completion_tokens": 96, "reasoning_effort": "low",
                                                           "timeout_seconds": 30, "max_retries": 0}},
    "tts": {"provider": "cartesia", "requested_model": None, "effective_model": "sonic-3.5", "voice": "synthetic_voice",
            "plugin_version": "1.6.5", "effective_options": {"model": "sonic-3.5", "language": "en", "sample_rate": 16000,
                                                            "encoding": "pcm_s16le", "speed": .95, "word_timestamps": False}},
}


class Sink:
    def write(self, value):
        return len(value)

    def flush(self):
        pass


class Room:
    def __init__(self):
        self.local_participant = self
        self.max_payload_bytes = 0

    def publish_data(self, value, **kwargs):
        self.max_payload_bytes = max(self.max_payload_bytes, len(value.encode("utf8")))


class Handle:
    def __init__(self, index):
        self.id = f"speech_{index}"
        self.interrupted = False
        self.exception = lambda: None

    def add_done_callback(self, callback):
        self.callback = callback


async def trial(concurrency, *, enabled, publish):
    os.environ["UVA_PUBLISH_TURN_LATENCY"] = "1" if publish else "0"
    logger = logging.getLogger("benchmark.telemetry")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers = [logging.StreamHandler(Sink())]
    latencies, max_bytes = [], []
    async def session():
        room = Room()
        tracker = TurnLatencyTracker(room, logger, lifecycle=True,
                                     snapshot=SNAPSHOT) if enabled else None
        async def llm_source(*args):
            yield "synthetic text"
        async def tts_source(*args):
            yield object()
        agent = SimpleNamespace(llm_node=llm_source, tts_node=tts_source)
        if tracker:
            observe_agent_nodes(agent, tracker)
        for index in range(300):
            started = time.perf_counter()
            handle = Handle(index)
            if tracker:
                tracker.mark_user_started_speaking()
                tracker.mark_user_stopped_speaking()
                tracker.on_speech_created(SimpleNamespace(speech_handle=handle, source="generate_reply"))
                tracker.mark_turn_committed(f"user_{index}", handle.id)
                async for _ in agent.llm_node(None, [], None):
                    pass
                tracker.on_metrics(SimpleNamespace(speech_id=handle.id, ttft=.1, total_tokens=20,
                                                  request_id=f"llm_tool_{index}"))
                tracker.on_tool_execution(SimpleNamespace(update=SimpleNamespace(
                    type="tool_call_started", function_call=SimpleNamespace(call_id=f"tool_{index}", name="lookup_business_info"))))
                tracker.on_tool_execution(SimpleNamespace(update=SimpleNamespace(
                    type="tool_call_ended", call_id=f"tool_{index}", status="done")))
                async for _ in agent.llm_node(None, [], None):
                    pass
                async for _ in agent.tts_node(None, None):
                    pass
                tracker.on_metrics(SimpleNamespace(speech_id=handle.id, ttft=.1, total_tokens=20,
                                                  request_id=f"llm_{index}"))
                tracker.on_metrics(SimpleNamespace(speech_id=handle.id, ttfb=.05, duration=.2, audio_duration=.1,
                                                  request_id=f"tts_{index}"))
                tracker.on_speech_done(handle.id, handle)
            else:
                for _ in range(2):
                    async for _ in agent.llm_node(None, [], None):
                        pass
                async for _ in agent.tts_node(None, None):
                    pass
            latencies.append((time.perf_counter() - started) * 1000)
            await asyncio.sleep(0)
        max_bytes.append(room.max_payload_bytes)
    started = time.perf_counter()
    await asyncio.gather(*(session() for _ in range(concurrency)))
    return {"concurrent_sessions": concurrency, "instrumented": enabled, "room_publish": publish,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "turn_handling": percentile_report(latencies), "max_payload_bytes": max(max_bytes)}


async def stream_trial():
    frames = [object()] * 100_000
    async def source(*args):
        for frame in frames:
            yield frame
    agent = SimpleNamespace(llm_node=source, tts_node=source)
    room = Room()
    tracker = TurnLatencyTracker(room, logging.getLogger("benchmark.telemetry"), lifecycle=True)
    handle = Handle("stream")
    tracker.on_speech_created(SimpleNamespace(speech_handle=handle, source="say"))
    started = time.perf_counter()
    async for _ in source():
        pass
    baseline = time.perf_counter() - started
    observe_agent_nodes(agent, tracker)
    started = time.perf_counter()
    async for _ in agent.tts_node(None, None):
        pass
    instrumented = time.perf_counter() - started
    return {"frames": len(frames), "baseline_ms": baseline * 1000,
            "observed_ms": instrumented * 1000,
            "added_microseconds_per_frame": max(0, instrumented - baseline) * 1e6 / len(frames)}


async def benchmark():
    trials = []
    for concurrency in (1, 16):
        for publish in (False, True):
            for enabled in (False, True):
                trials.append(await trial(concurrency, enabled=enabled, publish=publish))
    stream = await stream_trial()
    passed = all(t["turn_handling"]["p95Ms"] <= 3 for t in trials if t["instrumented"])
    passed = passed and stream["added_microseconds_per_frame"] <= 10
    passed = passed and max(t["max_payload_bytes"] for t in trials) < 14_000
    return {"scope": "offline CPU/event/serialization/log-format overhead; synthetic providers",
            "unverified": ["real provider/audio E2E", "deployed log sink I/O", "room publish network I/O"],
            "budgets": {"turn_p95_ms": 3, "added_frame_us": 10, "room_payload_bytes": 14_000},
            "trials": trials, "stream": stream, "pass": passed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(benchmark())
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
