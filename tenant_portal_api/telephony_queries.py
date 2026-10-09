"""Parameterized database repository queries for telephony resources.

Provides repository functions for Telnyx connections, numbers, orders, SIP connections,
LiveKit trunk records, calls, idempotency keys, events, and quota transactions.

Uses parameterized SQL (%s) and explicit transaction/row-lock handling.
Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

_log = logging.getLogger("tenant_portal_api.telephony_queries")
logger = _log  # alias: both spellings are used in this module


class DbConnection(Protocol):
    def execute(self, query: str, params: tuple | list | None = ...) -> Any: ...


def get_active_telnyx_connection(
    conn: DbConnection, tenant_id: str
) -> dict[str, Any] | None:
    """Fetch active Telnyx connection for a tenant."""
    row = conn.execute(
        """
        select id, tenant_id, label, platform_status, provider_status, key_fingerprint,
               telnyx_account_id, last_verified_at, permission_last_checked_at, encrypted_api_key_ref
        from tenant_telnyx_connections
        where tenant_id = %s and platform_status in ('verifying', 'active', 'rotation_required')
        order by created_at desc
        limit 1
        """,
        (tenant_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "tenant_id": row[1],
        "label": row[2],
        "platform_status": row[3],
        "provider_status": row[4],
        "key_fingerprint": row[5],
        "telnyx_account_id": row[6],
        "last_verified_at": str(row[7]) if row[7] else None,
        "permission_last_checked_at": str(row[8]) if row[8] else None,
        "encrypted_api_key_ref": row[9],
    }


def upsert_telnyx_connection_verifying(
    conn: DbConnection,
    tenant_id: str,
    label: str | None,
    key_fingerprint: str,
    encrypted_ref: str,
) -> dict[str, Any]:
    """Create or update tenant Telnyx connection in verifying state."""
    row = conn.execute(
        """
        insert into tenant_telnyx_connections (
            tenant_id, label, platform_status, key_fingerprint, encrypted_api_key_ref
        ) values (%s, %s, 'verifying', %s, %s)
        returning id, tenant_id, label, platform_status, key_fingerprint, created_at
        """,
        (tenant_id, label, key_fingerprint, encrypted_ref),
    ).fetchone()
    return {
        "id": row[0],
        "tenant_id": row[1],
        "label": row[2],
        "platform_status": row[3],
        "key_fingerprint": row[4],
        "created_at": str(row[5]),
    }


def mark_telnyx_connection_active(
    conn: DbConnection, connection_id: str, telnyx_account_id: str
) -> None:
    """Mark connection active after verification."""
    conn.execute(
        """
        update tenant_telnyx_connections
        set platform_status = 'active',
            provider_status = 'active',
            telnyx_account_id = %s,
            last_verified_at = now(),
            permission_last_checked_at = now(),
            updated_at = now()
        where id = %s
        """,
        (telnyx_account_id, connection_id),
    )


def update_active_telnyx_connection_credential(
    conn: DbConnection,
    tenant_id: str,
    connection_id: str,
    key_fingerprint: str,
    encrypted_ref: str,
    label: str | None,
    telnyx_account_id: str | None,
    provider_status: str | None,
) -> dict[str, Any] | None:
    """Replace the stored credential on the current active Telnyx connection."""
    row = conn.execute(
        """
        update tenant_telnyx_connections
        set label = coalesce(%s, label),
            platform_status = 'active',
            provider_status = coalesce(%s, 'active'),
            key_fingerprint = %s,
            encrypted_api_key_ref = %s,
            telnyx_account_id = %s,
            last_verified_at = now(),
            permission_last_checked_at = now(),
            updated_at = now()
        where tenant_id = %s
          and id = %s
          and platform_status in ('verifying', 'active', 'rotation_required')
        returning id, tenant_id, label, platform_status, provider_status, key_fingerprint,
                  telnyx_account_id, last_verified_at, permission_last_checked_at, encrypted_api_key_ref
        """,
        (
            label,
            provider_status,
            key_fingerprint,
            encrypted_ref,
            telnyx_account_id,
            tenant_id,
            connection_id,
        ),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "tenant_id": row[1],
        "label": row[2],
        "platform_status": row[3],
        "provider_status": row[4],
        "key_fingerprint": row[5],
        "telnyx_account_id": row[6],
        "last_verified_at": str(row[7]) if row[7] else None,
        "permission_last_checked_at": str(row[8]) if row[8] else None,
        "encrypted_api_key_ref": row[9],
    }


def disconnect_telnyx_connection(conn: DbConnection, connection_id: str) -> None:
    """Soft disconnect a Telnyx connection."""
    conn.execute(
        """
        update tenant_telnyx_connections
        set platform_status = 'disconnected',
            disconnected_at = now(),
            updated_at = now()
        where id = %s
        """,
        (connection_id,),
    )


# Phone Numbers Repository
def list_managed_numbers(
    conn: DbConnection, tenant_id: str, assigned_agent_id: str | None = None
) -> list[dict[str, Any]]:
    """List managed phone numbers for a tenant."""
    query = """
        select id, tenant_id, provider_number_id, e164_number, country, number_type,
               features, provisioning_status, routing_status, assigned_agent_id, external_customer_ref
        from telephony_phone_numbers
        where tenant_id = %s and disabled_at is null
    """
    params: list[Any] = [tenant_id]
    if assigned_agent_id:
        query += " and assigned_agent_id = %s"
        params.append(assigned_agent_id)
    query += " order by created_at desc"

    rows = conn.execute(query, tuple(params)).fetchall()
    results = []
    for r in rows:
        results.append(
            {
                "id": r[0],
                "tenant_id": r[1],
                "provider_number_id": r[2],
                "e164_number": r[3],
                "country": r[4],
                "number_type": r[5],
                "features": r[6] if r[6] else [],
                "provisioning_status": r[7],
                "routing_status": r[8],
                "assigned_agent_id": r[9],
                "external_customer_ref": r[10],
            }
        )
    return results


def get_managed_number(
    conn: DbConnection, tenant_id: str, number_id: str
) -> dict[str, Any] | None:
    """Fetch a single managed phone number by id for a tenant."""
    row = conn.execute(
        """
        select id, tenant_id, provider_number_id, e164_number, country, number_type,
               features, provisioning_status, routing_status, assigned_agent_id,
               external_customer_ref, disabled_at
        from telephony_phone_numbers
        where tenant_id = %s and id = %s and disabled_at is null
        """,
        (tenant_id, number_id),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "tenant_id": row[1],
        "provider_number_id": row[2],
        "e164_number": row[3],
        "country": row[4],
        "number_type": row[5],
        "features": row[6] if row[6] else [],
        "provisioning_status": row[7],
        "routing_status": row[8],
        "assigned_agent_id": str(row[9]) if row[9] else None,
        "external_customer_ref": row[10],
        "disabled_at": str(row[11]) if row[11] else None,
    }


def assign_number_to_agent(
    conn: DbConnection, tenant_id: str, number_id: str, agent_id: str | None
) -> bool:
    """Assign or unassign a phone number to an agent."""
    if agent_id:
        # Verify agent belongs to tenant
        agent_check = conn.execute(
            "select id from agents where id = %s and tenant_id = %s",
            (agent_id, tenant_id),
        ).fetchone()
        if not agent_check:
            return False

    res = conn.execute(
        """
        update telephony_phone_numbers
        set assigned_agent_id = %s, updated_at = now()
        where id = %s and tenant_id = %s and disabled_at is null
        """,
        (agent_id, number_id, tenant_id),
    )
    return bool(res)


# NOTE: a second, shadowed definition of get_idempotency_key() used to sit here. Python bound the
# later one, so this copy was dead code that quietly disagreed with live behaviour
# (the removed save_idempotency_key did ON CONFLICT DO NOTHING; the live one upserts
# to 'completed'). Removed in Wave 2 cleanup - ruff F811 flagged both.





# Call & Quota Repository
def reserve_call_quota(conn: DbConnection, tenant_id: str) -> bool:
    """Atomically reserve quota for a call in quota_state.

    F-H17: this used to read only tenants.max_concurrent, so a tenant blocked from browser
    sessions by the monthly minutes cap could still place unlimited outbound PSTN calls —
    the one path that spends real carrier money. It also returned True for a tenant id that
    does not exist, failing OPEN on the spend path. Both now match control_plane/mint.py,
    which has always checked status, concurrency AND monthly minutes before issuing a token.
    """
    tenant_row = conn.execute(
        "select max_concurrent, max_minutes_month, status from tenants where id = %s",
        (tenant_id,),
    ).fetchone()
    if not tenant_row:
        # F-H17: unknown tenant used to be granted quota. Refuse: nothing legitimate places
        # a call for a tenant that is not in the database.
        logger.warning(
            "refusing call quota for unknown tenant %s", tenant_id
        )
        return False
    max_conc, max_minutes, status = tenant_row
    if status != "active":
        logger.warning(
            "refusing call quota for tenant %s with status=%s", tenant_id, status
        )
        return False
    conn.execute(
        """
        insert into quota_state (tenant_id, concurrent_now)
        values (%s, 0)
        on conflict (tenant_id) do nothing
        """,
        (tenant_id,),
    )
    quota_row = conn.execute(
        "select concurrent_now, minutes_this_month from quota_state "
        "where tenant_id = %s for update",
        (tenant_id,),
    ).fetchone()
    curr = quota_row[0] if quota_row else 0
    minutes_used = (quota_row[1] if quota_row else 0) or 0
    if curr >= max_conc:
        return False
    # F-H17: the monthly minutes cap applies to PSTN too.
    if max_minutes is not None and minutes_used >= max_minutes:
        logger.warning(
            "refusing call quota for tenant %s: monthly minutes cap reached (%s/%s)",
            tenant_id,
            minutes_used,
            max_minutes,
        )
        return False
    conn.execute(
        """
        update quota_state
        set concurrent_now = concurrent_now + 1
        where tenant_id = %s
        """,
        (tenant_id,),
    )
    return True


def release_call_quota_once(conn: DbConnection, call_id: str, tenant_id: str) -> bool:
    """Release quota for a call exactly once.

    The guard and the stamp are one conditional UPDATE so the function is safe on
    autocommit connections (worker) as well as inside a transaction (API/reconciler):
    concurrent callers race on the row, exactly one gets ``returning id``.
    """
    claimed = conn.execute(
        "update telephony_calls set quota_released_at = now() "
        "where id = %s and quota_released_at is null returning id",
        (call_id,),
    ).fetchone()
    if not claimed:
        return False  # Already released or invalid call
    conn.execute(
        "update quota_state set concurrent_now = greatest(0, concurrent_now - 1) where tenant_id = %s",
        (tenant_id,),
    )
    return True


def release_call_quota_unpersisted(conn: DbConnection, tenant_id: str) -> None:
    """Release quota when reservation happened before any telephony_calls row existed."""
    conn.execute(
        "update quota_state set concurrent_now = greatest(0, concurrent_now - 1) where tenant_id = %s",
        (tenant_id,),
    )


TERMINAL_CALL_STATUSES = ("completed", "busy", "no_answer", "failed", "cancelled")
ACTIVE_CALL_STATUSES = ("queued", "dialing", "ringing", "in_progress")


def transition_call_status(
    conn: DbConnection,
    call_id: str,
    new_status: str,
    raw_participant_status: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    *,
    ended: bool = False,
    answered: bool = False,
    only_from: tuple[str, ...] | list[str] | None = None,
) -> int:
    """Update call public platform status. Returns the number of rows changed.

    ``answered=True`` stamps ``answered_at`` (once). ``ended=True`` stamps ``ended_at``
    (once) and derives ``duration_sec`` as talk time (``now() - answered_at``; 0 when
    the call was never answered). ``only_from`` restricts the update to rows currently in
    one of those statuses so a late/duplicate event can never downgrade a call or
    overwrite a terminal status.
    """
    set_clauses = [
        "platform_status = %s",
        "raw_livekit_sip_participant_status = coalesce(%s, raw_livekit_sip_participant_status)",
        "error_code = coalesce(%s, error_code)",
        "error_message = coalesce(%s, error_message)",
        "started_at = coalesce(started_at, now())",
    ]
    params: list[Any] = [new_status, raw_participant_status, error_code, error_message]
    if answered:
        set_clauses.append("answered_at = coalesce(answered_at, now())")
    if ended:
        set_clauses.append("ended_at = coalesce(ended_at, now())")
        set_clauses.append(
            "duration_sec = coalesce(duration_sec, case when answered_at is not null "
            "then greatest(0, extract(epoch from (now() - answered_at)))::int else 0 end)"
        )
    set_clauses.append("updated_at = now()")

    where = ""
    if only_from:
        where = "platform_status = any(%s) and "
        params.append(list(only_from))
    params.append(call_id)

    cur = conn.execute(
        f"update telephony_calls set {', '.join(set_clauses)} where {where}id = %s",
        tuple(params),
    )
    rowcount = getattr(cur, "rowcount", None)
    return int(rowcount) if isinstance(rowcount, int) and rowcount >= 0 else 1


def find_open_call_by_room(conn: DbConnection, room_name: str) -> dict[str, Any] | None:
    """Most recent telephony_calls row for a LiveKit room (any status)."""
    if not (room_name or "").strip():
        return None
    row = conn.execute(
        """
        select id, tenant_id, platform_status, quota_reserved_at, quota_released_at
        from telephony_calls
        where room_name = %s
        order by created_at desc
        limit 1
        """,
        (room_name,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "tenant_id": str(row[1]),
        "platform_status": row[2],
        "quota_reserved_at": row[3],
        "quota_released_at": row[4],
    }


def finalize_call(
    conn: DbConnection,
    call_id: str,
    tenant_id: str,
    status: str,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
    raw_participant_status: str | None = None,
) -> dict[str, bool]:
    """Move a call to a terminal status (never downgrading one) and release its quota once.

    A-01.2: this is the single exit path used by the worker shutdown, the stale-job
    cleanup and the reconciler. The Telnyx webhook path releases through
    ``release_call_quota_once`` as well, so whichever lands first wins and the rest are
    no-ops — ``quota_released_at`` is the ledger.
    """
    if status not in TERMINAL_CALL_STATUSES:
        raise ValueError(f"finalize_call requires a terminal status, got {status!r}")
    row = conn.execute(
        "select platform_status from telephony_calls where id = %s for update",
        (call_id,),
    ).fetchone()
    if not row:
        return {"found": False, "status_changed": False, "quota_released": False}
    current = row[0]
    status_changed = False
    if current not in TERMINAL_CALL_STATUSES:
        transition_call_status(
            conn,
            call_id,
            status,
            raw_participant_status=raw_participant_status,
            error_code=error_code,
            error_message=error_message,
            ended=True,
        )
        status_changed = True
    released = release_call_quota_once(conn, call_id, tenant_id)
    return {"found": True, "status_changed": status_changed, "quota_released": released}


def release_leaked_call_quota(conn: DbConnection, batch_size: int = 100) -> int:
    """Release reservations on calls that are already terminal but never released.

    Returns the number of reservations released. Only rows that recorded a reservation
    (``quota_reserved_at``) are eligible, so rows that never reserved cannot decrement.
    """
    rows = conn.execute(
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
    released = 0
    for call_id, tenant_id in rows:
        if release_call_quota_once(conn, str(call_id), str(tenant_id)):
            released += 1
    return released


def insert_call_event(
    conn: DbConnection,
    tenant_id: str,
    telephony_call_id: str,
    source: str,
    event_type: str,
    internal_stage: str,
    payload: dict[str, Any],
) -> None:
    """Log structured telephony call event."""
    conn.execute(
        """
        insert into telephony_call_events (
            tenant_id, telephony_call_id, source, event_type, internal_stage, payload
        ) values (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            tenant_id,
            telephony_call_id,
            source,
            event_type,
            internal_stage,
            json.dumps(payload),
        ),
    )


# Idempotency Repository Functions
def get_idempotency_key(
    conn: DbConnection, tenant_id: str, idempotency_key: str, action: str
) -> dict[str, Any] | None:
    """Fetch stored idempotency key record."""
    row = conn.execute(
        """
        select tenant_id, idempotency_key, action, request_hash, response_body,
               platform_status, created_at, completed_at
        from telephony_idempotency_keys
        where tenant_id = %s and idempotency_key = %s and action = %s
        """,
        (tenant_id, idempotency_key, action),
    ).fetchone()
    if not row:
        return None
    return {
        "tenant_id": str(row[0]),
        "idempotency_key": row[1],
        "action": row[2],
        "request_hash": row[3],
        "response_body": row[4] if row[4] is not None else None,
        "platform_status": row[5],
        "created_at": str(row[6]) if row[6] else None,
        "completed_at": str(row[7]) if row[7] else None,
    }


def try_insert_idempotency_lock(
    conn: DbConnection,
    tenant_id: str,
    idempotency_key: str,
    action: str,
    request_hash: str,
    status: str = "in_progress",
) -> bool:
    """Attempt to insert in_progress idempotency record for leader election. Returns True if leader (inserted)."""
    try:
        cur = conn.execute(
            """
            insert into telephony_idempotency_keys (
                tenant_id, idempotency_key, action, request_hash, platform_status
            ) values (%s, %s, %s, %s, %s)
            on conflict (tenant_id, idempotency_key, action) do nothing
            """,
            (tenant_id, idempotency_key, action, request_hash, status),
        )
        rowcount = getattr(cur, "rowcount", None)
        if rowcount is not None:
            return rowcount > 0
        return True
    except Exception:
        # F-M1: returning False here reads to the caller as "already used", so a DB error
        # silently turns into a rejected or replayed request. Record why.
        _log.warning(
            "idempotency key reservation failed tenant=%s action=%s",
            tenant_id,
            action,
            exc_info=True,
        )
        return False


def complete_idempotency_key(
    conn: DbConnection,
    tenant_id: str,
    idempotency_key: str,
    action: str,
    response_body: dict[str, Any],
) -> None:
    """Mark idempotency key record as completed with response payload."""
    conn.execute(
        """
        update telephony_idempotency_keys
        set platform_status = 'completed',
            response_body = %s::jsonb,
            completed_at = now()
        where tenant_id = %s and idempotency_key = %s and action = %s
        """,
        (json.dumps(response_body), tenant_id, idempotency_key, action),
    )


def fail_idempotency_key(
    conn: DbConnection, tenant_id: str, idempotency_key: str, action: str
) -> None:
    """Mark idempotency record as failed or delete to allow safe retry."""
    conn.execute(
        """
        delete from telephony_idempotency_keys
        where tenant_id = %s and idempotency_key = %s and action = %s
        """,
        (tenant_id, idempotency_key, action),
    )


def save_idempotency_key(
    conn: DbConnection,
    tenant_id: str,
    idempotency_key: str,
    action: str,
    request_hash: str,
    response_body: dict[str, Any],
) -> None:
    """Save or complete idempotency key record."""
    conn.execute(
        """
        insert into telephony_idempotency_keys (
            tenant_id, idempotency_key, action, request_hash, response_body, platform_status, completed_at
        ) values (%s, %s, %s, %s, %s::jsonb, 'completed', now())
        on conflict (tenant_id, idempotency_key, action) do update
        set platform_status = 'completed',
            request_hash = excluded.request_hash,
            response_body = excluded.response_body,
            completed_at = now()
        """,
        (tenant_id, idempotency_key, action, request_hash, json.dumps(response_body)),
    )


