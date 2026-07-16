"""Standalone smoke test / protocol probe for Uplift AI WebSocket (Socket.IO) TTS.

Connects to the multi-stream namespace, synthesizes one Urdu sentence to WAV,
and verifies duration > 0 and non-silence. Logs every event it receives so we
can confirm the wire protocol before wiring the pipeline service.

Run: uv run python tests/smoke_uplift_ws.py
"""

import asyncio
import base64
import os
import sys
import time
import uuid
import wave

import socketio
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["UPLIFTAI_API_KEY"]
VOICE_ID = os.environ.get("UPLIFT_VOICE_ID", "v_meklc281")
NAMESPACE = "/text-to-speech/multi-stream"
URL = "https://api.upliftai.org"
OUT_WAV = os.path.join(os.path.dirname(__file__), "out_uplift_smoke.wav")

TEXT = "السلام علیکم! ٹیک زون لیپ ٹاپس میں خوش آمدید، میں مہ نور بات کر رہی ہوں۔"


async def main() -> int:
    sio = socketio.AsyncClient(logger=False, engineio_logger=False)
    audio = bytearray()
    done = asyncio.Event()
    errors: list[str] = []
    t0 = time.monotonic()
    first_chunk_at: list[float] = []

    @sio.event(namespace=NAMESPACE)
    async def connect():
        print(
            f"[{time.monotonic() - t0:6.3f}s] connected, sid={sio.get_sid(NAMESPACE)}"
        )

    @sio.on("*", namespace=NAMESPACE)
    async def any_event(event, data=None):
        stamp = f"[{time.monotonic() - t0:6.3f}s]"
        # Uplift wraps server->client messages in a Socket.IO 'message' event
        # with a 'type' field: ready / audio_start / audio / audio_end / error.
        if event == "message" and isinstance(data, dict):
            event = data.get("type", "message")
        if event == "audio":
            chunk = data.get("audio") if isinstance(data, dict) else None
            if isinstance(chunk, str):
                raw = base64.b64decode(chunk)
            elif isinstance(chunk, (bytes, bytearray)):
                raw = bytes(chunk)
            else:
                raw = b""
            if not first_chunk_at:
                first_chunk_at.append(time.monotonic() - t0)
                print(
                    f"{stamp} first audio chunk ({len(raw)} bytes) seq={data.get('sequence')}"
                )
            audio.extend(raw)
        elif event == "audio_end":
            print(f"{stamp} audio_end: {data}")
            done.set()
        elif event == "error":
            print(f"{stamp} ERROR event: {data}")
            errors.append(str(data))
            done.set()
        else:
            preview = str(data)[:300] if data is not None else ""
            print(f"{stamp} event={event!r} data={preview}")

    @sio.event(namespace=NAMESPACE)
    async def disconnect():
        print(f"[{time.monotonic() - t0:6.3f}s] disconnected")

    print(f"connecting to {URL} ns={NAMESPACE} voice={VOICE_ID}")
    await sio.connect(
        URL,
        auth={"token": API_KEY},
        namespaces=[NAMESPACE],
        transports=["websocket"],
        wait_timeout=15,
    )

    req_id = str(uuid.uuid4())
    send_at = time.monotonic()
    await sio.emit(
        "synthesize",
        {
            "requestId": req_id,
            "text": TEXT,
            "voiceId": VOICE_ID,
            "outputFormat": "PCM_22050_16",
        },
        namespace=NAMESPACE,
    )
    print(f"[{time.monotonic() - t0:6.3f}s] synthesize sent requestId={req_id}")

    try:
        await asyncio.wait_for(done.wait(), timeout=30)
    except asyncio.TimeoutError:
        print("TIMEOUT waiting for audio_end")

    await sio.disconnect()

    if errors:
        print(f"FAIL: server error: {errors}")
        return 1
    if not audio:
        print("FAIL: no audio received")
        return 1

    with wave.open(OUT_WAV, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(bytes(audio))

    dur = len(audio) / 2 / 22050
    peak = 0
    for i in range(0, min(len(audio), 2_000_000) - 1, 2):
        s = int.from_bytes(audio[i : i + 2], "little", signed=True)
        peak = max(peak, abs(s))
    ttfb = first_chunk_at[0] - (send_at - t0) if first_chunk_at else -1
    print(
        f"PASS: wrote {OUT_WAV}: {dur:.2f}s audio, peak={peak}, tts_ttfb={ttfb * 1000:.0f}ms"
    )
    if dur <= 0 or peak < 500:
        print("FAIL: audio too short or silent")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
