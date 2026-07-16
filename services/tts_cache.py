"""Fixture cache for Uplift TTS (docs/30-GUIDE-FREE-TIER.md §2).

Record each unique (voiceId, text) output ONCE, replay forever. In `UPLIFT_MODE=fixture` (the
default) a cache MISS is a hard LookupError — never a silent live call, so a runaway loop cannot eat
Uplift's 10-minute lifetime budget. Recording (`UPLIFT_MODE=record`) is human-approved and writes
here via `store()`; the worker only ever READS via `require()`.

Pure stdlib on purpose — no livekit/plugin import — so it loads fast and is testable offline.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import wave
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "tts"
MANIFEST = FIXTURES / "manifest.json"
SAMPLE_RATE = 22050
SAMPLE_WIDTH = 2  # 16-bit
CHANNELS = 1


def key(voice_id: str, text: str) -> str:
    return hashlib.sha256(f"{voice_id}|{text}".encode()).hexdigest()[:32]


def mode() -> str:
    return os.getenv("UPLIFT_MODE", "fixture")


def path(voice_id: str, text: str) -> Path:
    return FIXTURES / f"{key(voice_id, text)}.wav"


def get(voice_id: str, text: str) -> bytes | None:
    """Cached WAV bytes for this exact (voice, text), or None. Never touches the network."""
    p = path(voice_id, text)
    return p.read_bytes() if p.exists() else None


def require(voice_id: str, text: str) -> bytes:
    """Cached WAV bytes, or a hard LookupError. NEVER calls Uplift — this is the whole point.

    A cache miss in any non-record mode is a test/worker failure, not a silent paid API call.
    """
    cached = get(voice_id, text)
    if cached is not None:
        return cached
    k = key(voice_id, text)
    raise LookupError(
        f"TTS FIXTURE MISS {k}\n"
        f"  voice={voice_id}\n  text={text!r}\n"
        f"  This did NOT call Uplift — free tier protected (UPLIFT_MODE={mode()}).\n"
        f"  To record (human-approved only):\n"
        f"    UPLIFT_MODE=record python scripts/record_fixture.py --voice {voice_id} --text <text>"
    )


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw 16-bit mono PCM samples in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def store(voice_id: str, text: str, wav_bytes: bytes, meta: dict) -> Path:
    """Write a recorded fixture + its manifest entry. Called only from the record path."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    p = path(voice_id, text)
    p.write_bytes(wav_bytes)
    manifest = (
        json.loads(MANIFEST.read_text(encoding="utf-8") or "{}")
        if MANIFEST.exists()
        else {}
    )
    manifest[key(voice_id, text)] = {"voiceId": voice_id, "text": text, **meta}
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return p
