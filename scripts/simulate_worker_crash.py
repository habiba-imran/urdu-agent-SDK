"""Phase 8 Failure-Recovery Drill — scripts/simulate_worker_crash.py.

Simulates a hard worker process termination mid-session, creates an unclosed session row,
and tests out-of-band reconciliation via reconcile_sessions.py to prove zero quota drift.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from dbconn import conn_kwargs
from reconcile_sessions import reconcile_sessions


def run_failure_recovery_drill() -> dict:
    """Creates a simulated stale unclosed session row (>30m old) and verifies reconciliation repairs it."""
    tenant_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    room_name = f"drill-room-{uuid.uuid4()}"

    print(f"[DRILL] Simulating stale crashed session for tenant {tenant_id}...")

    with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
        agent_id = str(uuid.uuid4())
        # 1. Setup tenant, agent, and increment concurrency
        conn.execute(
            """
            INSERT INTO tenants (id, name, hmac_secret_hash, status, max_concurrent)
            VALUES (%s, 'Drill Tenant', 'dummy_hash', 'active', 5)
            ON CONFLICT (id) DO NOTHING
            """,
            (tenant_id,),
        )
        conn.execute(
            """
            INSERT INTO agents (id, tenant_id, name, prompt, voice_id)
            VALUES (%s, %s, 'Drill Agent', 'You are a test drill agent.', 'v_meklc281')
            ON CONFLICT (id) DO NOTHING
            """,
            (agent_id, tenant_id),
        )

        conn.execute(
            """
            INSERT INTO quota_state (tenant_id, concurrent_now, minutes_this_month)
            VALUES (%s, 1, 0)
            ON CONFLICT (tenant_id) DO UPDATE SET concurrent_now = 1
            """,
            (tenant_id,),
        )

        # 2. Insert stale open session (started 45 minutes ago, ended_at IS NULL due to simulated crash)
        conn.execute(
            """
            INSERT INTO sessions (id, tenant_id, agent_id, room_name, started_at, ended_at)
            VALUES (%s, %s, %s, %s, NOW() - INTERVAL '45 minutes', NULL)
            """,
            (session_id, tenant_id, agent_id, room_name),
        )

    # 3. Execute out-of-band reconciliation
    stats = reconcile_sessions(max_age_minutes=30, dry_run=False)

    # 4. Verify post-reconciliation state
    with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
        row = conn.execute(
            "SELECT concurrent_now FROM quota_state WHERE tenant_id = %s",
            (tenant_id,),
        ).fetchone()
        final_concurrency = row[0] if row else -1

        sess_row = conn.execute(
            "SELECT end_reason FROM sessions WHERE id = %s",
            (session_id,),
        ).fetchone()
        final_end_reason = sess_row[0] if sess_row else None

        # Clean up drill rows
        conn.execute("DELETE FROM sessions WHERE tenant_id = %s", (tenant_id,))
        conn.execute("DELETE FROM agents WHERE tenant_id = %s", (tenant_id,))
        conn.execute("DELETE FROM quota_state WHERE tenant_id = %s", (tenant_id,))
        conn.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))


    drill_success = (final_concurrency == 0) and (final_end_reason in ("reconciled_stale", "stale_reconciled"))
    print(f"[DRILL RESULT] Concurrency reset to {final_concurrency}, end_reason: {final_end_reason}. Success: {drill_success}")


    return {
        "success": drill_success,
        "final_concurrency": final_concurrency,
        "end_reason": final_end_reason,
        "reconciled_stats": stats,
    }


if __name__ == "__main__":
    res = run_failure_recovery_drill()
    if not res["success"]:
        sys.exit(1)
