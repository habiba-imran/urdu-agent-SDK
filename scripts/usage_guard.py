#!/usr/bin/env python3
"""Free-tier ledger. Fails `make gate` before you blow a quota blind (audit gap #12)."""

import json
import sys
import pathlib

LEDGER = pathlib.Path("state/usage_ledger.json")
BUDGETS = {  # docs/30-GUIDE-FREE-TIER.md §3-4. HARD limits from vendor free tiers.
    "uplift_tts_sec": {"limit": 600, "note": "Uplift free = 10 MINUTES TOTAL, forever"},
    "livekit_agent_min": {
        "limit": 1000,
        "note": "LiveKit Build HARD CAP — calls FAIL past it",
    },
    "gladia_stt_sec": {"limit": 36000, "note": "Gladia free tier"},
    # Paid provider (limit None): tracked for visibility, never fails the gate (ADR-005 / paid Pro).
    "supabase_db_mb": {
        "limit": None,
        "note": "Supabase Pro (PAID) — tracked, no free-tier cap",
    },
    # NOT instrumented (limit None): the real quota is on record, but "used" is not a real
    # per-call count — nothing in worker/main.py increments it yet. Tracked here so this stops
    # being an unquantified flag, per ADR-008's open item, not because it's paid/uncapped.
    "livekit_adaptive_interruption_req": {
        "limit": None,
        "note": (
            "LiveKit Adaptive Interruption Detector, LOCAL DEV mode only: 40,000 free inference "
            "req/month per plan (docs.livekit.io/agents/logic/turns/adaptive-interruption-"
            "handling/, verified live 2026-07-17 — exact quote: 'For local development and "
            "testing, every plan includes 40,000 free inference requests per month.'). Free AND "
            "UNLIMITED instead for agents deployed to LiveKit Cloud — this quota is specific to "
            "`python -m worker.main dev`/`console` runs (ADR-008). What happens past 40,000/mo "
            "(hard block vs overage billing) is NOT stated on that page — unverified, flagged."
        ),
    },
}


def load():
    if not LEDGER.exists():
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps({k: 0 for k in BUDGETS}, indent=2))
    return json.loads(LEDGER.read_text())


def main():
    u = load()
    report = "--report" in sys.argv
    bad = False
    print(f"{'provider':<20}{'used':>10}{'limit':>10}{'left':>10}  note")
    for k, b in BUDGETS.items():
        used = u.get(k, 0)
        if b["limit"] is None:  # paid/uncapped provider — tracked, never fails the gate
            print(f"{k:<20}{used:>10}{'paid':>10}{'-':>10}  {b['note']}")
            continue
        left = b["limit"] - used
        flag = "" if left > 0 else "  <-- EXHAUSTED"
        if left <= 0:
            bad = True
        print(f"{k:<20}{used:>10}{b['limit']:>10}{left:>10}  {b['note']}{flag}")
    if bad and not report:
        print("\nGATE FAIL: a free-tier budget is exhausted.", file=sys.stderr)
        print(
            "Do NOT rotate accounts (ToS + it risks the Uplift relationship you need for H9).",
            file=sys.stderr,
        )
        print("Use fixtures: docs/30-GUIDE-FREE-TIER.md §2", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
