#!/usr/bin/env python3
"""Measure Gemini free-tier throttling for the worker LLM (P3-T06). LIVE — human-approved only.

Old-repo D14: Groq's free tier throttled to TTFB 13-30s at ~4 turns. Same risk class for Gemini's
free tier — MEASURE, don't assume. This makes N sequential Gemini calls, records per-turn latency +
token usage, and flags the turn where throttling (429 / RESOURCE_EXHAUSTED / quota) or a latency
spike first appears. It records nothing to the ADR itself — you paste the measured table into
docs/40-ADR.md (P3-T06).

Requires --confirm-live to actually call Gemini (a quota-consuming call). Without it, prints the plan
and exits with ZERO network — so the script can be reviewed safely before you approve the live run.

    python scripts/measure_gemini_tpm.py --turns 8 --confirm-live
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=8)
    ap.add_argument("--model", default=None, help="override GEMINI_LLM_MODEL")
    ap.add_argument(
        "--confirm-live",
        action="store_true",
        help="actually call Gemini (consumes quota)",
    )
    args = ap.parse_args()

    cfg = dotenv_values(ROOT / ".env.local")
    key = cfg.get("GOOGLE_API_KEY")
    model = args.model or cfg.get("GEMINI_LLM_MODEL") or "gemini-2.5-flash"
    print(f"model: {model}   turns: {args.turns}")
    if not key:
        sys.exit("REFUSED: GOOGLE_API_KEY not in .env.local (human task H5).")
    if not args.confirm_live:
        print(
            "DRY RUN — pass --confirm-live to make the (live, quota-consuming) Gemini calls. Nothing called."
        )
        return 0

    from google import genai

    client = genai.Client(api_key=key)
    prompt = "Reply in one short Urdu sentence: welcome the caller to a laptop shop."
    print(f"{'turn':>4} {'latency_ms':>11} {'in_tok':>7} {'out_tok':>8}  status")
    latencies: list[float] = []
    throttle_turn: int | None = None
    for i in range(1, args.turns + 1):
        t0 = time.monotonic()
        try:
            r = client.models.generate_content(model=model, contents=prompt)
            ms = (time.monotonic() - t0) * 1000
            um = getattr(r, "usage_metadata", None)
            in_tok = getattr(um, "prompt_token_count", "-") if um else "-"
            out_tok = getattr(um, "candidates_token_count", "-") if um else "-"
            latencies.append(ms)
            print(f"{i:>4} {ms:>11.0f} {str(in_tok):>7} {str(out_tok):>8}  OK")
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            msg = str(e)
            throttled = (
                "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower()
            )
            if throttled and throttle_turn is None:
                throttle_turn = i
            status = "THROTTLED" if throttled else "ERROR"
            print(f"{i:>4} {ms:>11.0f} {'-':>7} {'-':>8}  {status}: {msg[:70]}")

    print("\n--- summary ---")
    if latencies:
        print(
            f"turns OK: {len(latencies)}/{args.turns}   "
            f"min={min(latencies):.0f}ms  max={max(latencies):.0f}ms  last={latencies[-1]:.0f}ms"
        )
    print(
        f"throttle onset: {'turn ' + str(throttle_turn) if throttle_turn else f'none in {args.turns} turns'}"
    )
    print(
        "\nPaste this table + throttle onset into docs/40-ADR.md (P3-T06 Gemini TPM measurement)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
