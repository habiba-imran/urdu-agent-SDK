#!/usr/bin/env python3
"""Record ONE Uplift TTS fixture (P3-T01 plugin verification). HUMAN-APPROVED ONLY.

Refuses to run unless UPLIFT_MODE=record. Synthesizes exactly one utterance via
livekit-plugins-upliftai, enforces a hard `--max-seconds` ceiling on produced audio (plus a
pre-call text-length guard so nothing is spent if the text is too long), writes the result to
tests/fixtures/tts/ (+ manifest) so it is never re-recorded, and logs the ACTUAL seconds consumed
to state/usage_ledger.json.

    UPLIFT_MODE=record python scripts/record_fixture.py \
        --voice v_meklc281 --format WAV_22050_16 --max-seconds 12 --text "<urdu utterance>"
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from services.tts_cache import key, pcm_to_wav, store  # noqa: E402

CHARS_PER_SEC = (
    20  # generous upper bound on Urdu speech rate, for the pre-call spend guard
)


def main() -> int:
    if os.environ.get("UPLIFT_MODE") != "record":
        sys.exit(
            "REFUSED: set UPLIFT_MODE=record to record a fixture (human-approved only). "
            "In fixture mode this script does nothing — the worker replays from tests/fixtures/."
        )
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="v_meklc281")
    ap.add_argument("--format", default="WAV_22050_16")
    ap.add_argument("--max-seconds", type=float, default=12.0)
    ap.add_argument("--text", required=True)
    args = ap.parse_args()

    # pre-call spend guard: refuse a text that could exceed the ceiling BEFORE calling Uplift
    est = len(args.text) / CHARS_PER_SEC
    if len(args.text) > args.max_seconds * CHARS_PER_SEC:
        sys.exit(
            f"REFUSED: text is ~{est:.0f}s of speech (> {args.max_seconds}s cap by length). Shorten it."
        )

    api_key = dotenv_values(ROOT / ".env.local").get("UPLIFTAI_API_KEY")
    if not api_key:
        sys.exit("REFUSED: UPLIFTAI_API_KEY not in .env.local (human task H3).")

    from livekit.plugins import upliftai

    async def synth() -> tuple[bytes, int]:
        tts = upliftai.TTS(
            voice_id=args.voice, output_format=args.format, api_key=api_key
        )
        pcm = bytearray()
        sr = 22050
        try:
            async for ev in tts.synthesize(args.text):
                sr = ev.frame.sample_rate
                pcm += bytes(ev.frame.data)
                if len(pcm) / (2 * sr) > args.max_seconds:
                    raise SystemExit(
                        f"ABORT: produced audio exceeded the {args.max_seconds}s cap."
                    )
        finally:
            await tts.aclose()
        return bytes(pcm), sr

    pcm, sr = asyncio.run(synth())
    duration = len(pcm) / (2 * sr)
    wav = pcm_to_wav(pcm, sr)

    meta = {
        "ms": round(duration * 1000),
        "bytes": len(wav),
        "sample_rate": sr,
        "output_format": args.format,
        "recorded_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    fixture = store(args.voice, args.text, wav, meta)

    ledger_path = ROOT / "state" / "usage_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["uplift_tts_sec"] = ledger.get("uplift_tts_sec", 0) + round(duration)
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

    print("RECORDED fixture:")
    print(f"  file:       {fixture}")
    print(f"  hash:       {key(args.voice, args.text)}")
    print(f"  voice:      {args.voice}   format: {args.format}")
    print(f"  duration:   {duration:.2f}s   sample_rate: {sr} Hz   bytes: {len(wav)}")
    print(
        f"  usage:      uplift_tts_sec += {round(duration)}  (now {ledger['uplift_tts_sec']}/600)"
    )
    print(
        "\n  Next: play the wav, confirm audible Urdu, and record the sample rate in docs/40-ADR.md."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
