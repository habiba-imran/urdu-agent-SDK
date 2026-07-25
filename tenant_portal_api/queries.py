"""Tenant-safe query layer for the tenant portal API."""

from __future__ import annotations

import psycopg


def list_agents(conn: psycopg.Connection, tenant_id: str) -> list[dict]:
    rows = conn.execute(
        """
        select a.id, a.name, a.prompt, a.voice_id, a.llm_model, a.created_at,
               coalesce(u.total_agent_sec, 0) as total_agent_sec
        from agents a
        left join (
            select s.agent_id, sum(ue.qty) as total_agent_sec
            from sessions s
            join usage_events ue on ue.session_id = s.id and ue.kind = 'agent_sec'
            where s.tenant_id = %s
            group by s.agent_id
        ) u on u.agent_id = a.id
        where a.tenant_id = %s
        order by a.created_at desc
        """,
        (tenant_id, tenant_id),
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "prompt": r[2],
            "voice_id": r[3],
            "llm_model": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
            "total_agent_sec": float(r[6]),
        }
        for r in rows
    ]


def create_agent(
    conn: psycopg.Connection,
    tenant_id: str,
    *,
    name: str,
    prompt: str,
    voice_id: str,
    llm_model: str,
) -> dict:
    row = conn.execute(
        """
        insert into agents (tenant_id, name, prompt, voice_id, llm_model)
        values (%s, %s, %s, %s, %s)
        returning id, name, prompt, voice_id, llm_model, created_at
        """,
        (tenant_id, name, prompt, voice_id, llm_model),
    ).fetchone()
    return {
        "id": str(row[0]),
        "name": row[1],
        "prompt": row[2],
        "voice_id": row[3],
        "llm_model": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
    }


def update_agent(
    conn: psycopg.Connection,
    tenant_id: str,
    agent_id: str,
    *,
    name: str | None = None,
    prompt: str | None = None,
    voice_id: str | None = None,
    llm_model: str | None = None,
) -> dict:
    current = conn.execute(
        """
        select id, name, prompt, voice_id, llm_model, created_at
        from agents
        where id = %s and tenant_id = %s
        """,
        (agent_id, tenant_id),
    ).fetchone()
    if current is None:
        raise ValueError("agent not found")

    row = conn.execute(
        """
        update agents
        set name = %s,
            prompt = %s,
            voice_id = %s,
            llm_model = %s
        where id = %s and tenant_id = %s
        returning id, name, prompt, voice_id, llm_model, created_at
        """,
        (
            name if name is not None else current[1],
            prompt if prompt is not None else current[2],
            voice_id if voice_id is not None else current[3],
            llm_model if llm_model is not None else current[4],
            agent_id,
            tenant_id,
        ),
    ).fetchone()
    return {
        "id": str(row[0]),
        "name": row[1],
        "prompt": row[2],
        "voice_id": row[3],
        "llm_model": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
    }


def get_credentials(conn: psycopg.Connection, tenant_id: str) -> dict:
    row = conn.execute(
        """
        select id, name, allowed_origins, hmac_secret_hash, status
        from tenants
        where id = %s
        """,
        (tenant_id,),
    ).fetchone()
    if row is None:
        raise ValueError("tenant not found")

    return {
        "publishable_key": str(row[0]),
        "tenant_id": str(row[0]),
        "name": row[1],
        "allowed_origins": row[2] or [],
        "hmac_secret_hash": row[3],
        "secret_masked": "masked",
        "status": row[4],
    }


def list_recent_sessions(
    conn: psycopg.Connection, tenant_id: str, *, limit: int = 50
) -> list[dict]:
    rows = conn.execute(
        """
        select s.id, s.agent_id, a.name, s.room_name, s.started_at, s.ended_at,
               s.duration_sec, s.end_reason
        from sessions s
        join agents a on a.id = s.agent_id
        where s.tenant_id = %s
        order by s.started_at desc
        limit %s
        """,
        (tenant_id, limit),
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "agent_id": str(r[1]),
            "agent_name": r[2],
            "room_name": r[3],
            "started_at": r[4].isoformat() if r[4] else None,
            "ended_at": r[5].isoformat() if r[5] else None,
            "duration_sec": r[6],
            "end_reason": r[7],
            "live": r[5] is None,
        }
        for r in rows
    ]


def usage_summary(
    conn: psycopg.Connection, tenant_id: str, *, days: int = 30
) -> dict:
    quota = conn.execute(
        """
        select t.max_concurrent, t.max_minutes_month,
               coalesce(q.concurrent_now, 0) as concurrent_now,
               coalesce(q.minutes_this_month, 0) as minutes_this_month
        from tenants t
        left join quota_state q on q.tenant_id = t.id
        where t.id = %s
        """,
        (tenant_id,),
    ).fetchone()
    if quota is None:
        raise ValueError("tenant not found")

    totals = conn.execute(
        """
        select kind, coalesce(sum(qty), 0) as total_qty
        from usage_events
        where tenant_id = %s
          and at >= now() - (%s || ' days')::interval
        group by kind
        order by kind
        """,
        (tenant_id, days),
    ).fetchall()

    daily = conn.execute(
        """
        select date_trunc('day', at)::date as day, kind, coalesce(sum(qty), 0) as total_qty
        from usage_events
        where tenant_id = %s
          and at >= now() - (%s || ' days')::interval
        group by day, kind
        order by day desc, kind
        """,
        (tenant_id, days),
    ).fetchall()

    return {
        "window_days": days,
        "quota": {
            "max_concurrent": quota[0],
            "max_minutes_month": quota[1],
            "concurrent_now": quota[2],
            "minutes_this_month": float(quota[3]),
        },
        "totals": [{"kind": r[0], "total_qty": float(r[1])} for r in totals],
        "daily": [
            {"day": r[0].isoformat(), "kind": r[1], "total_qty": float(r[2])}
            for r in daily
        ],
    }
