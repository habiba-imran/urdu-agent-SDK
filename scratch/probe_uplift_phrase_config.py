from __future__ import annotations

import asyncio
import base64
import os
import sys
import time
import uuid
from pathlib import Path

import socketio
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
NAMESPACE = "/text-to-speech/multi-stream"
URL = "https://api.upliftai.org"
TEXT = "السلام علیکم، یہ ایک مختصر ٹیسٹ ہے۔"


async def synth(*, include_phrase_config: bool) -> int:
    api_key = os.environ["UPLIFTAI_API_KEY"]
    voice_id = os.environ.get("UPLIFT_VOICE_ID", "v_meklc281")
    phrase_id = (ROOT / ".uplift_phrase_config").read_text(encoding="utf-8").strip()
    request_id = str(uuid.uuid4())
    payload = {
        "requestId": request_id,
        "text": TEXT,
        "voiceId": voice_id,
        "outputFormat": "PCM_22050_16",
    }
    if include_phrase_config:
        payload["phraseReplacementConfigId"] = phrase_id

    sio = socketio.AsyncClient(logger=False, engineio_logger=False)
    done = asyncio.Event()
    audio = bytearray()
    errors: list[str] = []
    started = time.monotonic()

    @sio.on("message", namespace=NAMESPACE)
    async def on_message(data):
        message_type = data.get("type") if isinstance(data, dict) else None
        if message_type == "audio":
            chunk = data.get("audio")
            if chunk:
                audio.extend(base64.b64decode(chunk))
        elif message_type == "error":
            errors.append(str(data))
            done.set()
        elif message_type == "audio_end":
            done.set()

    await sio.connect(
        URL,
        auth={"token": api_key},
        namespaces=[NAMESPACE],
        transports=["websocket"],
        wait_timeout=15,
    )
    await sio.emit("synthesize", payload, namespace=NAMESPACE)
    try:
        await asyncio.wait_for(done.wait(), timeout=20)
    finally:
        await sio.disconnect()

    label = "with_phrase_config" if include_phrase_config else "without_phrase_config"
    duration = len(audio) / 2 / 22050
    print(
        f"{label}: bytes={len(audio)} duration={duration:.2f}s "
        f"errors={len(errors)} elapsed={time.monotonic() - started:.2f}s"
    )
    for error in errors:
        print(f"{label} error: {error}")
    return 1 if errors or not audio else 0


async def main() -> int:
    load_dotenv(ROOT / ".env.local")
    first = await synth(include_phrase_config=False)
    second = await synth(include_phrase_config=True)
    return 0 if first == 0 and second == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
