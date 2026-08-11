from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv


async def synth(output_format: str) -> int:
    from livekit.plugins import upliftai

    text = os.environ.get(
        "UPLIFT_PROBE_TEXT",
        "السلام علیکم، یہ ایک مختصر ٹیسٹ ہے۔",
    )
    voice_id = os.environ.get("UPLIFT_VOICE_ID", "v_meklc281")
    tts = upliftai.TTS(
        voice_id=voice_id,
        output_format=output_format,
        phrase_replacement_config_id=os.environ.get("UPLIFT_PHRASE_CONFIG_ID") or None,
    )
    frames = 0
    total_bytes = 0
    total_duration = 0.0
    peak = 0
    try:
        async for ev in tts.synthesize(text):
            frames += 1
            data = bytes(ev.frame.data)
            total_bytes += len(data)
            total_duration += ev.frame.duration
            for i in range(0, min(len(data), 200000) - 1, 2):
                sample = int.from_bytes(data[i : i + 2], "little", signed=True)
                peak = max(peak, abs(sample))
    finally:
        await tts.aclose()
    print(
        f"{output_format}: frames={frames} bytes={total_bytes} "
        f"duration={total_duration:.2f}s peak={peak}"
    )
    return 0 if frames and total_bytes and peak > 500 else 1


async def main() -> int:
    load_dotenv(".env.local")
    failures = 0
    for output_format in ("WAV_22050_16", "PCM_22050_16"):
        failures += await synth(output_format)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
