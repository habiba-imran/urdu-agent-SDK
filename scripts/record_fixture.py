#!/usr/bin/env python3
"""Record ONE Uplift TTS fixture (P3-T01 plugin verification). HUMAN-APPROVED ONLY.

Reads the utterance from a UTF-8 ``--text-file`` checked into the repo (safer than an inline CLI
arg, which a Windows terminal can silently mangle — and this text is a permanent fixture key).
Refuses to record unless ``UPLIFT_MODE=record``. ``--dry-run`` resolves the text + shows the fixture
hash WITHOUT any network call, so the exact key can be confirmed before spending budget.

    # 1. preview the resolved text + fixture hash (no network, no budget):
    python scripts/record_fixture.py --text-file tests/fixtures/reference_greeting.txt --dry-run

    # 2. record it (human-approved):
    UPLIFT_MODE=record python scripts/record_fixture.py \
        --voice v_meklc281 --format WAV_22050_16 --max-seconds 12 \
        --text-file tests/fixtures/reference_greeting.txt
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

# Windows consoles default to cp1252, which cannot encode Urdu — force stdout to UTF-8 so printing
# the utterance (or any status line) never crashes the recording.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from services.tts_cache import key, pcm_to_wav, store  # noqa: E402

CHARS_PER_SEC = (
    20  # generous upper bound on Urdu speech rate, for the pre-call spend guard
)


def resolve_text(args: argparse.Namespace) -> str:
    if args.text_file:
        return Path(args.text_file).read_text(encoding="utf-8").strip()
    return (args.text or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="v_meklc281")
    ap.add_argument("--format", default="WAV_22050_16")
    ap.add_argument("--max-seconds", type=float, default=12.0)
    ap.add_argument(
        "--text-file", help="path to a UTF-8 file holding the utterance (preferred)"
    )
    ap.add_argument(
        "--text", help="inline utterance (discouraged for non-ASCII on Windows)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="resolve text + show hash; no network"
    )
    args = ap.parse_args()

    if bool(args.text_file) == bool(args.text):
        sys.exit("REFUSED: pass exactly one of --text-file (preferred) or --text.")
    text = resolve_text(args)
    if not text:
        sys.exit("REFUSED: resolved text is empty.")

    est = len(text) / CHARS_PER_SEC
    fixture_key = key(args.voice, text)
    print(f"voice:        {args.voice}")
    print(f"format:       {args.format}")
    print(f"text ({len(text)} chars): {text}")
    print(f"fixture key:  {fixture_key}  ->  tests/fixtures/tts/{fixture_key}.wav")
    print(f"est duration: ~{est:.1f}s (hard cap {args.max_seconds}s)")

    if len(text) > args.max_seconds * CHARS_PER_SEC:
        sys.exit(
            f"REFUSED: text ~{est:.0f}s exceeds the {args.max_seconds}s cap by length. Shorten it."
        )

    if args.dry_run:
        print("\nDRY RUN — nothing recorded, no network, no budget spent.")
        return 0

    if os.environ.get("UPLIFT_MODE") != "record":
        sys.exit(
            "REFUSED: set UPLIFT_MODE=record to actually record (human-approved only). "
            "Use --dry-run to preview without recording."
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
            async for ev in tts.synthesize(text):
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
    fixture = store(args.voice, text, wav, meta)

    ledger_path = ROOT / "state" / "usage_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["uplift_tts_sec"] = ledger.get("uplift_tts_sec", 0) + round(duration)
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

    print(f"\nRECORDED: {fixture}")
    print(f"  duration {duration:.2f}s @ {sr} Hz, {len(wav)} bytes")
    print(
        f"  usage: uplift_tts_sec += {round(duration)}  (now {ledger['uplift_tts_sec']}/600)"
    )
    print(
        "  Next: play the wav, confirm audible Urdu, record the sample rate in docs/40-ADR.md."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
