#!/usr/bin/env python3
"""Record ONE preview line per voice for the Phase-5 picker (P5-T02). HUMAN-APPROVED ONLY.

Reuses record_fixture.py's safety pattern (refuses without UPLIFT_MODE=record, --dry-run shows
the exact plan with zero network calls, per-line + running-total budget check against the real
ledger). Saves audio locally to voice-picker/previews/<voice_id>.wav — uploading to a CDN and
populating voices.preview_url is P5-T03, a separate step, not done here.

Preview text is gender-matched (masculine/feminine verb form) since Urdu grammar marks the
speaker's gender on "I can help" — a single ungendered line would sound wrong for half the
catalogue. 'khwajasara' (gender NULL in the DB — the catalogue itself describes this voice as
androgynous, not a gap to fill in) gets a third, ungendered line that sidesteps the issue instead
of guessing a gender for it.

    # 1. preview the exact plan for ALL voices needing a recording -- zero network, zero budget:
    python scripts/record_voice_previews.py --dry-run

    # 2. record everything (human-approved only):
    UPLIFT_MODE=record python scripts/record_voice_previews.py
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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from services.tts_cache import pcm_to_wav  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402
from usage_guard import increment, load as load_ledger  # noqa: E402

OUT_DIR = ROOT / "voice-picker" / "previews"
CHARS_PER_SEC = 20  # same generous upper bound as record_fixture.py, for the pre-call estimate
DEFAULT_MAX_SECONDS = 6.0  # hard cap per line -- these are short greetings, not paragraphs

# Per-voice overrides. ADR-019: washroom-singer's file codename (ai_naat_p4_m_za) indicates a
# naat-style (melismatic, sung) voice model -- genuinely slower than ordinary speech on the same
# short line, not a bug. Raised to 10.0s for this voice specifically rather than raising the
# global default or trimming its line. If it still exceeds 10.0s, the run reports the real number
# reached and moves on -- the cap does not get raised again blind.
MAX_SECONDS_OVERRIDES = {
    "washroom-singer": 10.0,
}


def cap_for(voice_id: str) -> float:
    return MAX_SECONDS_OVERRIDES.get(voice_id, DEFAULT_MAX_SECONDS)

LINE_MASCULINE = "السلام علیکم، میں آپ کی کیا مدد کر سکتا ہوں؟"
LINE_FEMININE = "السلام علیکم، میں آپ کی کیا مدد کر سکتی ہوں؟"
LINE_NEUTRAL = "السلام علیکم، خوش آمدید"  # gender-unspecified voices (currently: khwajasara only)


def line_for(gender: str | None) -> str:
    if gender == "male":
        return LINE_MASCULINE
    if gender == "female":
        return LINE_FEMININE
    return LINE_NEUTRAL


# Legacy Uplift voices (different ID scheme, existing-integration voices, not the new picker
# catalogue) are explicitly excluded here -- ADR-018 left "should legacy voices appear in the
# picker" as an open, undecided design question. Only v_meklc281 exists in this table today; if
# more legacy voices are ever seeded, they should be excluded the same deliberate way, not swept
# in by an accidental pattern match.
LEGACY_VOICE_IDS = {"v_meklc281"}


def fetch_voices() -> list[dict]:
    import psycopg

    with psycopg.connect(**conn_kwargs()) as conn:
        rows = conn.execute(
            "select id, display_name, gender from voices where enabled = true order by id"
        ).fetchall()
    return [
        {"id": r[0], "display_name": r[1], "gender": r[2]}
        for r in rows
        if r[0] not in LEGACY_VOICE_IDS
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run", action="store_true", help="show the full plan; no network, no budget"
    )
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="skip voices that already have a local preview .wav (default on)",
    )
    args = ap.parse_args()

    voices = fetch_voices()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    plan = []
    for v in voices:
        out_path = OUT_DIR / f"{v['id']}.wav"
        if args.skip_existing and out_path.exists():
            continue
        text = line_for(v["gender"])
        est = len(text) / CHARS_PER_SEC
        plan.append({**v, "text": text, "est_sec": est, "out_path": out_path})

    total_est = sum(p["est_sec"] for p in plan)
    ledger = load_ledger()
    used = ledger.get("uplift_tts_sec", 0)
    remaining = 600 - used

    print(f"{len(voices)} enabled voices; {len(plan)} need a preview recorded")
    print(f"current ledger: uplift_tts_sec={used}/600 ({remaining}s remaining)")
    print(f"estimated total for this run: ~{total_est:.1f}s")
    print(f"estimated remaining after: ~{remaining - total_est:.1f}s\n")

    for p in plan[:5]:
        print(f"  [{p['id']}] gender={p['gender']} text={p['text']!r} est~{p['est_sec']:.1f}s")
    if len(plan) > 5:
        print(f"  ... and {len(plan) - 5} more (same 3 possible lines, by gender)")

    if total_est > remaining:
        sys.exit(
            f"\nREFUSED: estimated total {total_est:.1f}s exceeds the {remaining}s remaining "
            "in the Uplift budget. Do not proceed."
        )

    if args.dry_run:
        print("\nDRY RUN — nothing recorded, no network, no budget spent.")
        return 0

    if os.environ.get("UPLIFT_MODE") != "record":
        sys.exit(
            "REFUSED: set UPLIFT_MODE=record to actually record (human-approved only). "
            "Use --dry-run to preview without recording."
        )
    if not plan:
        print("Nothing to record (all voices already have a local preview).")
        return 0

    api_key = dotenv_values(ROOT / ".env.local").get("UPLIFTAI_API_KEY")
    if not api_key:
        sys.exit("REFUSED: UPLIFTAI_API_KEY not in .env.local (human task H3).")

    from livekit.plugins import upliftai

    phrase_config_id = None
    cfg_path = ROOT / ".uplift_phrase_config"
    if cfg_path.exists():
        phrase_config_id = cfg_path.read_text(encoding="utf-8").strip() or None

    class CapExceeded(Exception):
        """Raised when a voice's per-line synthesis crosses its per-voice cap (cap_for()).

        Carries the partial pcm/sample-rate that was actually streamed (and billed by Uplift)
        before the abort, so the caller can log real spend instead of losing it -- see the
        washroom-singer incident (docs/40-ADR.md ADR-019): the old SystemExit-inside-try-block
        design discarded this data and killed the whole run instead of just this one voice.
        """

        def __init__(self, pcm: bytes, sr: int, cap: float):
            self.pcm = pcm
            self.sr = sr
            self.cap = cap

    async def synth_one(voice_id: str, text: str, max_seconds: float) -> tuple[bytes, int]:
        tts = upliftai.TTS(
            voice_id=voice_id,
            output_format="WAV_22050_16",
            api_key=api_key,
            phrase_replacement_config_id=phrase_config_id,
        )
        pcm = bytearray()
        sr = 22050
        try:
            async for ev in tts.synthesize(text):
                sr = ev.frame.sample_rate
                pcm += bytes(ev.frame.data)
                if len(pcm) / (2 * sr) > max_seconds:
                    raise CapExceeded(bytes(pcm), sr, max_seconds)
        finally:
            await tts.aclose()
        return bytes(pcm), sr

    recorded = 0
    skipped = 0
    total_recorded_sec = 0.0
    for p in plan:
        current_used = load_ledger().get("uplift_tts_sec", 0)
        if 600 - current_used < p["est_sec"]:
            print(f"\nSTOPPING before {p['id']}: not enough budget remaining. Partial run saved.")
            break

        cap = cap_for(p["id"])
        try:
            pcm, sr = asyncio.run(synth_one(p["id"], p["text"], cap))
        except CapExceeded as e:
            partial_duration = len(e.pcm) / (2 * e.sr)
            increment("uplift_tts_sec", round(partial_duration))
            skipped += 1
            print(
                f"  [{p['id']}] SKIPPED: exceeded its {e.cap}s per-line cap at "
                f"{partial_duration:.2f}s (logged to ledger, no preview file written). "
                "Continuing with the next voice."
            )
            continue

        duration = len(pcm) / (2 * sr)
        wav = pcm_to_wav(pcm, sr)
        p["out_path"].write_bytes(wav)
        increment("uplift_tts_sec", round(duration))
        recorded += 1
        total_recorded_sec += duration
        print(f"  [{p['id']}] recorded {duration:.2f}s -> {p['out_path']}")

    final_used = load_ledger().get("uplift_tts_sec", 0)
    print(
        f"\nDone: {recorded}/{len(plan)} recorded, {skipped} skipped (cap exceeded), "
        f"{total_recorded_sec:.1f}s this run."
    )
    print(f"ledger: uplift_tts_sec={final_used}/600")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
