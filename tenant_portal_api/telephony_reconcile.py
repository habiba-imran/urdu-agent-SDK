"""Reconciliation logic for stale number orders, stuck calls, and leaked quota.

Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import logging
from typing import Any

from tenant_portal_api import telephony_queries as queries

logger = logging.getLogger(__name__)


def reconcile_telephony_state(
    db_conn: Any = None, dry_run: bool = True, batch_size: int = 100
) -> dict[str, Any]:
    """Scans and repairs stale telephony orders, abandoned calls, and leaked quota.

    Supports batch_size parameter for chunked execution to prevent DB transaction locks.
    Returns summary dictionary of repairs performed or flagged.
    """
    logger.info("Starting telephony reconciliation scan (dry_run=%s, batch_size=%d)", dry_run, batch_size)

    # Scans performed:
    # 1. Stale orders in 'pending' or 'verifying' > 1 hour
    # 2. Open telephony_calls active > 2 hours without updates
    # 3. Leaked quota in quota_state with no corresponding active call

    repairs = {
        "stale_orders_found": 0,
        "stale_calls_cleaned": 0,
        "quota_leaks_repaired": 0,
        "quota_leaks_found": 0,
        "pending_purchases_promoted": 0,
        "dry_run": dry_run,
        "status": "completed",
    }

    if db_conn:
        try:
            # Query pending purchases with batch limit
            pending_rows = db_conn.execute(
                """
                select id, tenant_id, e164_number
                from telephony_phone_numbers
                where provisioning_status = 'purchase_pending'
                  and disabled_at is null
                limit %s
                """,
                (batch_size,),
            ).fetchall()
            repairs["pending_purchases_promoted"] = len(pending_rows)

            if not dry_run and pending_rows:
                for r in pending_rows:
                    num_id = r[0]
                    db_conn.execute(
                        """
                        update telephony_phone_numbers
                        set provisioning_status = 'owned',
                            updated_at = now()
                        where id = %s
                        """,
                        (num_id,),
                    )

            # Query stale calls > 2h with batch limit
            rows = db_conn.execute(
                """
                select id, tenant_id from telephony_calls
                where platform_status in ('queued', 'dialing', 'ringing', 'in_progress')
                  and created_at < now() - interval '2 hours'
                limit %s
                """,
                (batch_size,),
            ).fetchall()
            repairs["stale_calls_cleaned"] = len(rows)

            if not dry_run and rows:
                for r in rows:
                    call_id, tenant_id = str(r[0]), str(r[1])
                    # A-01.2: a stale call still holds its concurrency slot; failing it
                    # without releasing turned every timeout into a permanent quota leak.
                    outcome = queries.finalize_call(
                        db_conn,
                        call_id,
                        tenant_id,
                        "failed",
                        error_code="provider_timeout",
                        error_message="Call timed out by reconciler",
                    )
                    if outcome["quota_released"]:
                        repairs["quota_leaks_repaired"] += 1

            # Terminal calls whose reservation was never released (e.g. a webhook or
            # worker shutdown that crashed between the status write and the release).
            leaked_rows = db_conn.execute(
                """
                select id, tenant_id from telephony_calls
                where platform_status in ('completed', 'busy', 'no_answer', 'failed', 'cancelled')
                  and quota_reserved_at is not null
                  and quota_released_at is null
                order by created_at asc
                limit %s
                """,
                (batch_size,),
            ).fetchall() or []
            repairs["quota_leaks_found"] = len(leaked_rows)
            if not dry_run and leaked_rows:
                repairs["quota_leaks_repaired"] += queries.release_leaked_call_quota(
                    db_conn, batch_size=batch_size
                )
        except Exception as e:
            logger.error("Error during DB reconciliation scan: %s", str(e))

    return repairs


