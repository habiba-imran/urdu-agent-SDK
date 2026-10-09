#!/usr/bin/env python3
"""Reconcile sessions and repair tenant quota_state.concurrent_now counters.

Usage:
    python scripts/reconcile_sessions.py [--max-age-minutes 30] [--dry-run]

What it does:
1. Identifies open sessions (ended_at is null) older than --max-age-minutes (default: 30m),
   skipping sessions that belong to a telephony call which is still live (A-01.5: the
   call's own lifecycle — webhook, worker close, telephony_reconcile's 2h sweep — ends it).
2. Closes stale sessions with end_reason='reconciled_stale' (duration_sec stays 0).
3. P3-H4: writes capped agent_sec usage_events for closed sessions that never flushed usage.
4. Re-calculates the true slot count per tenant and updates quota_state.concurrent_now to
   match. Browser sessions count while open; telephony calls count through their ledger
   (telephony_calls.quota_reserved_at set, quota_released_at null) and their linked
   sessions row is excluded so a call is never counted twice. Terminal-but-unreleased
   calls stay counted until scripts/reconcile_telephony.py (same workflow, runs after
   this script) releases them — the ledger is corrected, never bypassed.

Runbook: docs/WAVE2-SESSION-RECONCILE.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from dbconn import conn_kwargs
except ImportError:
    from scripts.dbconn import conn_kwargs  # type: ignore # noqa: E402


def reconcile_sessions(
    max_age_minutes: int = 30,
    dry_run: bool = False,
    conn: Any | None = None,
) -> dict[str, int]:
    """Reconcile stale sessions and synchronize quota_state.concurrent_now.

    If ``conn`` is provided (unit tests), it is used and not closed by this function.
    Returns summary stats dict.
    """
    stats = {
        "stale_sessions_closed": 0,
        "usage_events_written": 0,
        "tenants_reconciled": 0,
        "total_open_sessions_remaining": 0,
    }

    owns_conn = conn is None
    if owns_conn:
        conn = psycopg.connect(
            **conn_kwargs(), connect_timeout=10, autocommit=not dry_run
        )

    try:
        return _reconcile_on_conn(
            conn, max_age_minutes=max_age_minutes, dry_run=dry_run, stats=stats
        )
    finally:
        if owns_conn and conn is not None:
            conn.close()


# A-01.5: a sessions row that belongs to a live telephony call is not an orphan — the
# call's lifetime is governed by telephony_calls (webhook / worker close / the 2h stale
# sweep in telephony_reconcile.py), not by the browser max-age. Closing it here after
# 30 minutes made the worker's real close miss the row (transcript lost, usage replaced
# by the capped estimate). Once the call is terminal or released the predicate is false
# and the session is reconciled like any other.
_NOT_LIVE_TELEPHONY_SESSION = """
              AND NOT EXISTS (
                  SELECT 1 FROM telephony_calls tc
                  WHERE tc.session_id = s.id
                    AND tc.quota_reserved_at IS NOT NULL
                    AND tc.quota_released_at IS NULL
                    AND tc.platform_status IN ('queued', 'dialing', 'ringing', 'in_progress')
              )
"""


def _reconcile_on_conn(
    conn: Any,
    *,
    max_age_minutes: int,
    dry_run: bool,
    stats: dict[str, int],
) -> dict[str, int]:
    with conn.cursor() as cur:
        # 1. Close stale open sessions (browser sessions, and telephony sessions whose
        #    call has already ended)
        cur.execute(
            f"""
            SELECT id, tenant_id, room_name, started_at
            FROM sessions s
            WHERE ended_at IS NULL
              AND started_at < NOW() - (INTERVAL '1 minute' * %s)
              {_NOT_LIVE_TELEPHONY_SESSION}
            """,
            (max_age_minutes,),
        )
        stale_rows = cur.fetchall()
        stats["stale_sessions_closed"] = len(stale_rows)

        if stale_rows:
            print(
                f"[reconcile] Found {len(stale_rows)} stale session(s) > {max_age_minutes}m old:"
            )
            for s_id, t_id, r_name, s_at in stale_rows:
                print(
                    f"  - Session {s_id} (tenant {t_id}, room {r_name}, started {s_at})"
                )

            if not dry_run:
                cur.execute(
                    f"""
                    UPDATE sessions s
                    SET ended_at = NOW(),
                        -- duration_sec stays 0: Sessions UI must not show multi-day
                        -- wall-clock ages. Billing truth is usage_events.agent_sec below.
                        duration_sec = 0,
                        end_reason = 'reconciled_stale'
                    WHERE ended_at IS NULL
                      AND started_at < NOW() - (INTERVAL '1 minute' * %s)
                      {_NOT_LIVE_TELEPHONY_SESSION}
                    """,
                    (max_age_minutes,),
                )
                print(
                    f"[reconcile] Marked {cur.rowcount} session(s) as closed ('reconciled_stale')."
                )
                # P3-H4: crash/kill never reached shutdown usage flush. Cap estimate at
                # max_age so a long-orphaned row cannot bill days of wall clock.
                cap_sec = float(max_age_minutes * 60)
                for s_id, t_id, _r_name, s_at in stale_rows:
                    if not t_id:
                        continue
                    cur.execute(
                        """
                        SELECT 1 FROM usage_events
                        WHERE session_id = %s AND kind = 'agent_sec'
                        LIMIT 1
                        """,
                        (s_id,),
                    )
                    if cur.fetchone():
                        continue
                    cur.execute(
                        """
                        INSERT INTO usage_events (tenant_id, session_id, kind, qty)
                        VALUES (
                            %s,
                            %s,
                            'agent_sec',
                            LEAST(
                                %s,
                                GREATEST(
                                    EXTRACT(EPOCH FROM (NOW() - %s::timestamptz)),
                                    0
                                )
                            )
                        )
                        """,
                        (t_id, s_id, cap_sec, s_at),
                    )
                    minutes = cap_sec / 60.0
                    # Prefer true elapsed when we can; fall back to cap minutes.
                    cur.execute(
                        """
                        UPDATE quota_state
                        SET minutes_this_month = minutes_this_month + LEAST(
                            %s,
                            GREATEST(EXTRACT(EPOCH FROM (NOW() - %s::timestamptz)) / 60.0, 0)
                        )
                        WHERE tenant_id = %s
                        """,
                        (minutes, s_at, t_id),
                    )
                    stats["usage_events_written"] += 1
                if stats["usage_events_written"]:
                    print(
                        f"[reconcile] Wrote {stats['usage_events_written']} "
                        "estimated agent_sec usage event(s) for crash recovery."
                    )
        else:
            print(f"[reconcile] No stale sessions > {max_age_minutes}m old found.")

        # 2. Re-align quota_state.concurrent_now to match true open session count.
        # A-01.2/3: telephony calls hold their slot on telephony_calls (reserve_call_quota
        # stamps quota_reserved_at, every exit stamps quota_released_at). Their sessions
        # row is for transcript/usage only, so count each call once via the ledger and
        # exclude its linked session. Counting only sessions here used to zero every
        # live phone call's reservation.
        cur.execute(
            """
            SELECT t.id,
                   COALESCE(s.open_count, 0) + COALESCE(c.open_count, 0) AS true_open_count,
                   q.concurrent_now
            FROM tenants t
            LEFT JOIN (
                SELECT s.tenant_id, COUNT(*) AS open_count
                FROM sessions s
                WHERE s.ended_at IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM telephony_calls tc
                      WHERE tc.session_id = s.id
                        AND tc.quota_reserved_at IS NOT NULL
                  )
                GROUP BY s.tenant_id
            ) s ON t.id = s.tenant_id
            LEFT JOIN (
                SELECT tenant_id, COUNT(*) AS open_count
                FROM telephony_calls
                WHERE quota_reserved_at IS NOT NULL
                  AND quota_released_at IS NULL
                GROUP BY tenant_id
            ) c ON t.id = c.tenant_id
            LEFT JOIN quota_state q ON t.id = q.tenant_id
            """
        )
        tenant_rows = cur.fetchall()

        to_update = []
        for t_id, true_open, current_quota in tenant_rows:
            current_val = current_quota if current_quota is not None else 0
            if true_open != current_val:
                to_update.append((t_id, true_open, current_val))

        stats["tenants_reconciled"] = len(to_update)
        stats["total_open_sessions_remaining"] = sum(r[1] for r in tenant_rows)

        if to_update:
            print(
                f"[reconcile] Found {len(to_update)} tenant(s) with mismatched concurrency counts:"
            )
            for t_id, true_open, current_val in to_update:
                print(
                    f"  - Tenant {t_id}: quota_state={current_val} -> corrected to {true_open}"
                )

            if not dry_run:
                for t_id, true_open, _ in to_update:
                    cur.execute(
                        """
                        INSERT INTO quota_state (tenant_id, concurrent_now)
                        VALUES (%s, %s)
                        ON CONFLICT (tenant_id) DO UPDATE
                        SET concurrent_now = EXCLUDED.concurrent_now
                        """,
                        (t_id, true_open),
                    )
                print(
                    f"[reconcile] Successfully updated {len(to_update)} quota_state record(s)."
                )
        else:
            print(
                "[reconcile] All tenant quota_state.concurrent_now values are up to date."
            )

    if dry_run:
        print("[reconcile] DRY RUN complete — no changes were committed.")
    else:
        print("[reconcile] Reconciliation complete and committed.")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile stale sessions and quota_state concurrent_now."
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=30,
        help="Max age in minutes for open sessions before marking them stale (default: 30).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview stale sessions and quota updates without committing DB changes.",
    )
    args = parser.parse_args()

    reconcile_sessions(max_age_minutes=args.max_age_minutes, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
