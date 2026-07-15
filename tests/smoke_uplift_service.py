"""Standalone smoke test for services/uplift_tts.UpliftTTSService (STEP 2 requirement).

Runs the service in a minimal Pipeline (no transport, no mic), speaks one Urdu
sentence via TTSSpeakFrame, captures TTSAudioRawFrames in a sink, writes a WAV
and asserts duration > 0 and non-silence.

Run: uv run python tests/smoke_uplift_service.py
"""

# Imports intentionally follow sys.path setup + load_dotenv() below, so E402 is expected here.
# ruff: noqa: E402

import asyncio
import os
import sys
import time
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from loguru import logger

from pipecat.frames.frames import (
    Frame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TTSStoppedFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.worker import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from services.uplift_tts import UpliftTTSService

OUT_WAV = os.path.join(os.path.dirname(__file__), "out_uplift_service_smoke.wav")
TEXT = (
    "جی بالکل، میک بُک ایئر ایم ٹو اسٹاک میں موجود ہے۔ قیمت تین لاکھ پندرہ ہزار روپے ہے۔"
)
SAMPLE_RATE = 22050


class AudioSink(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.audio = bytearray()
        self.first_audio_at: float | None = None
        self.stopped = asyncio.Event()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            if self.first_audio_at is None:
                self.first_audio_at = time.monotonic()
            self.audio.extend(frame.audio)
        elif isinstance(frame, TTSStoppedFrame):
            self.stopped.set()
        await self.push_frame(frame, direction)


async def main() -> int:
    phrase_cfg = None
    cfg_path = os.path.join(os.path.dirname(__file__), "..", ".uplift_phrase_config")
    if os.path.exists(cfg_path):
        phrase_cfg = open(cfg_path, encoding="utf-8").read().strip()

    tts = UpliftTTSService(
        api_key=os.environ["UPLIFTAI_API_KEY"],
        voice_id=os.environ.get("UPLIFT_VOICE_ID", "v_meklc281"),
        phrase_replacement_config_id=phrase_cfg,
    )
    sink = AudioSink()
    pipeline = Pipeline([tts, sink])
    task = PipelineTask(
        pipeline,
        params=PipelineParams(audio_out_sample_rate=SAMPLE_RATE),
        idle_timeout_secs=None,
    )
    runner = PipelineRunner(handle_sigint=False)

    async def drive():
        t_send = time.monotonic()
        await task.queue_frame(TTSSpeakFrame(TEXT))
        try:
            await asyncio.wait_for(sink.stopped.wait(), timeout=30)
        except asyncio.TimeoutError:
            logger.error("timeout waiting for TTSStoppedFrame")
        if sink.first_audio_at:
            logger.info(f"service TTFB: {(sink.first_audio_at - t_send) * 1000:.0f}ms")
        await task.cancel()

    await asyncio.gather(runner.run(task), drive())

    if not sink.audio:
        print("FAIL: no audio captured")
        return 1

    with wave.open(OUT_WAV, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(sink.audio))

    dur = len(sink.audio) / 2 / SAMPLE_RATE
    peak = max(
        abs(int.from_bytes(sink.audio[i : i + 2], "little", signed=True))
        for i in range(0, len(sink.audio) - 1, 2)
    )
    print(f"duration={dur:.2f}s peak={peak}")
    if dur <= 0.5 or peak < 500:
        print("FAIL: audio too short or silent")
        return 1
    print(f"PASS: {OUT_WAV}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
