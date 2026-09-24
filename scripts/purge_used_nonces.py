#!/usr/bin/env python3
"""Delete expired replay-protection nonces (F-M11).

``used_nonces`` gains one row per successful mint and nothing ever removed them. The
``used_nonces_used_at_idx`` index in 0004_nonces.sql implies a cleanup that was never
written, so the table grows for the life of the deployment.

A nonce only has to be remembered for the mint's replay window
(``control_plane/mint.py::REPLAY_WINDOW_SEC``, 60s) — after that the timestamp check rejects
the request before the nonce is even consulted. This deletes rows older than a wide safety
margin over that window.

Scheduled by .github/workflows/reconcile.yml. Safe to run concurrently with minting: it only
removes rows that can no longer take part in a replay decision.

Usage:
    python scripts/purge_used_nonces.py [--dry-run] [--older-than-minutes N] [--limit N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from dbconn import conn_kwargs
except ImportError:  # pragma: no cover - import shim, same pattern as sibling scripts
    from scripts.dbconn import conn_kwargs  # type: ignore # noqa: E402

# The mint rejects anything older than REPLAY_WINDOW_SEC (60s) on the timestamp alone. An
# hour is ~60x that, so clock skew or a long transaction cannot make a still-relevant nonce
# eligible for deletion.
DEFAULT_OLDER_THAN_MINUTES = 60


def purge_used_nonces(
    *, older_than_minutes: int = DEFAULT_OLDER_THAN_MINUTES, dry_run: bool = True,
    limit: int = 50_000,
) -> dict[str, int]:
    with psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        total = conn.execute("select count(*) from used_nonces").fetchone()[0]
        expired = conn.execute(
            "select count(*) from used_nonces where used_at < now() - (%s || ' minutes')::interval",
            (older_than_minutes,),
        ).fetchone()[0]

        deleted = 0
        if not dry_run and expired:
            # Bounded delete so a first run on a long-neglected table cannot hold a long
            # transaction against the mint path.
            result = conn.execute(
                "delete from used_nonces where ctid in ("
                "  select ctid from used_nonces"
                "  where used_at < now() - (%s || ' minutes')::interval"
                "  limit %s"
                ")",
                (older_than_minutes, limit),
            )
            deleted = result.rowcount or 0

    stats = {"total": total, "expired": expired, "deleted": deleted}
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(
        f"[nonces] {mode} total={total} expired(>{older_than_minutes}m)={expired} deleted={deleted}"
    )
    if not dry_run and expired > deleted:
        print(f"[nonces] {expired - deleted} still expired — run again to continue")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count expired nonces without deleting them",
    )
    parser.add_argument(
        "--older-than-minutes",
        type=int,
        default=DEFAULT_OLDER_THAN_MINUTES,
        help=f"Age at which a nonce is expired (default: {DEFAULT_OLDER_THAN_MINUTES})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50_000,
        help="Maximum rows to delete in one run (default: 50000)",
    )
    args = parser.parse_args()
    # The replay window is 60s; refuse a value that could delete a live nonce.
    if args.older_than_minutes < 5:
        parser.error("--older-than-minutes must be at least 5 (mint replay window is 60s)")
    purge_used_nonces(
        older_than_minutes=args.older_than_minutes,
        dry_run=args.dry_run,
        limit=max(1, args.limit),
    )


if __name__ == "__main__":
    main()
