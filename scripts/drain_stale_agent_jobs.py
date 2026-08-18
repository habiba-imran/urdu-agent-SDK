#!/usr/bin/env python3
"""Drain orphaned browser sessions and their LiveKit agent dispatches.

Use when the worker was offline and minted jobs piled up in LiveKit, or to release leaked
concurrency slots for sessions that never got a participant.

Usage:
    python scripts/drain_stale_agent_jobs.py [--max-age-seconds 180] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env.local")

from worker.stale_jobs import drain_orphan_sessions, stale_job_max_age_sec  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=stale_job_max_age_sec(),
        help="Close open sessions older than this many seconds (default: WORKER_STALE_JOB_MAX_AGE_SEC or 180).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without changing DB or LiveKit state.",
    )
    args = parser.parse_args()

    stats = asyncio.run(
        drain_orphan_sessions(max_age_sec=args.max_age_seconds, dry_run=args.dry_run)
    )
    print(
        f"drain complete: sessions_closed={stats['sessions_closed']} "
        f"livekit_cleaned={stats['livekit_cleaned']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
