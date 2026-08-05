"""Parameterized database repository queries for telephony resources.

Provides repository functions for Telnyx connections, numbers, orders, SIP connections,
LiveKit trunk records, calls, idempotency keys, events, and quota transactions.

Uses parameterized SQL (%s) and explicit transaction/row-lock handling.
Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import json
from typing import Any, Protocol


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


# Idempotency Repository
def get_idempotency_key(
    conn: DbConnection, tenant_id: str, idempotency_key: str, action: str
) -> dict[str, Any] | None:
    """Check idempotency key table for matching key and action."""
    row = conn.execute(
        """
        select request_hash, response_body, platform_status
        from telephony_idempotency_keys
        where tenant_id = %s and idempotency_key = %s and action = %s
        """,
        (tenant_id, idempotency_key, action),
    ).fetchone()
    if not row:
        return None
    return {
        "request_hash": row[0],
        "response_body": row[1] if isinstance(row[1], dict) else json.loads(row[1]),
        "platform_status": row[2],
    }


def save_idempotency_key(
    conn: DbConnection,
    tenant_id: str,
    idempotency_key: str,
    action: str,
    request_hash: str,
    response_body: dict[str, Any],
) -> None:
    """Save completed idempotency payload."""
    body_json = (
        json.dumps(response_body)
        if not isinstance(response_body, str)
        else response_body
    )
    conn.execute(
        """
        insert into telephony_idempotency_keys (
            tenant_id, idempotency_key, action, request_hash, response_body, platform_status, completed_at
        ) values (%s, %s, %s, %s, %s::jsonb, 'completed', now())
        on conflict (tenant_id, idempotency_key, action) do nothing
        """,
        (tenant_id, idempotency_key, action, request_hash, body_json),
    )


# Call & Quota Repository
def reserve_call_quota(conn: DbConnection, tenant_id: str) -> bool:
    """Atomically reserve quota for a call in quota_state."""
    tenant_row = conn.execute(
        "select max_concurrent from tenants where id = %s",
        (tenant_id,),
    ).fetchone()
    if not tenant_row:
        return True
    max_conc = tenant_row[0]
    conn.execute(
        """
        insert into quota_state (tenant_id, concurrent_now)
        values (%s, 0)
        on conflict (tenant_id) do nothing
        """,
        (tenant_id,),
    )
    quota_row = conn.execute(
        "select concurrent_now from quota_state where tenant_id = %s for update",
        (tenant_id,),
    ).fetchone()
    curr = quota_row[0] if quota_row else 0
    if curr >= max_conc:
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
    """Release quota for a call exactly once."""
    row = conn.execute(
        "select quota_released_at from telephony_calls where id = %s for update",
        (call_id,),
    ).fetchone()
    if not row or row[0] is not None:
        return False  # Already released or invalid call
    conn.execute(
        "update telephony_calls set quota_released_at = now() where id = %s",
        (call_id,),
    )
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


def transition_call_status(
    conn: DbConnection,
    call_id: str,
    new_status: str,
    raw_participant_status: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update call public platform status."""
    conn.execute(
        """
        update telephony_calls
        set platform_status = %s,
            raw_livekit_sip_participant_status = coalesce(%s, raw_livekit_sip_participant_status),
            error_code = coalesce(%s, error_code),
            error_message = coalesce(%s, error_message),
            updated_at = now()
        where id = %s
        """,
        (new_status, raw_participant_status, error_code, error_message, call_id),
    )


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
