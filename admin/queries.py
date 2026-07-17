"""Every admin dashboard number, as one real SQL query each — GATE 6 line 1.

All reads use the trusted DB-owner connection (SUPABASE_DB_URL, same as control_plane/mint.py and
worker/config.py — RLS bypass is correct here by design, per docs/26-PHASE-6-ADMIN.md: "Admin
bypasses RLS by design"). Nothing here is a client-side aggregate of a broader fetch; each
function is the literal SQL that produces the number the portal shows.

Cost estimate (P6-T04): 10-SPEC.md publishes exactly one figure, "Marginal ≈ $0.0044/min", and it
is explicitly about LiveKit agent-minutes. `usage_events.kind='agent_sec'` is the only kind that
maps to a published $/unit. stt_sec/tts_sec/llm_tokens have no published per-unit price anywhere
in this repo's docs, so no cost is invented for them (anti-hallucination rule 8.3) — `cost_usd` is
returned only for the agent_sec row of each group, `null` for the others, and that gap is real,
not a bug.
"""

from __future__ import annotations

import psycopg

AGENT_SEC_COST_PER_MIN_USD = (
    0.0044  # 10-SPEC.md "Unit economics" — the only published figure
)


def list_tenants(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """
        select t.id, t.name, t.status, t.max_concurrent, t.max_minutes_month,
               coalesce(q.concurrent_now, 0)      as concurrent_now,
               coalesce(q.minutes_this_month, 0)  as minutes_this_month
        from tenants t
        left join quota_state q on q.tenant_id = t.id
        order by t.created_at desc
        """
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "status": r[2],
            "max_concurrent": r[3],
            "max_minutes_month": r[4],
            "concurrent_now": r[5],
            "minutes_this_month": float(r[6]),
        }
        for r in rows
    ]


def list_agents(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """
        select a.id, a.tenant_id, t.name as tenant_name, a.name, a.voice_id, a.llm_model,
               coalesce(u.total_agent_sec, 0) as total_agent_sec
        from agents a
        join tenants t on t.id = a.tenant_id
        left join (
            select s2.agent_id, sum(ue.qty) as total_agent_sec
            from sessions s2
            join usage_events ue on ue.session_id = s2.id and ue.kind = 'agent_sec'
            group by s2.agent_id
        ) u on u.agent_id = a.id
        order by a.created_at desc
        """
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "tenant_id": str(r[1]),
            "tenant_name": r[2],
            "name": r[3],
            "voice_id": r[4],
            "llm_model": r[5],
            "total_agent_sec": float(r[6]),
        }
        for r in rows
    ]


def list_sessions(
    conn: psycopg.Connection, *, tenant_id: str | None = None
) -> list[dict]:
    q = """
        select s.id, s.tenant_id, s.agent_id, s.room_name, s.started_at, s.ended_at,
               s.duration_sec, s.end_reason
        from sessions s
        {where}
        order by s.started_at desc
        limit 200
    """
    if tenant_id:
        rows = conn.execute(
            q.format(where="where s.tenant_id = %s"), (tenant_id,)
        ).fetchall()
    else:
        rows = conn.execute(q.format(where="")).fetchall()
    return [
        {
            "id": str(r[0]),
            "tenant_id": str(r[1]),
            "agent_id": str(r[2]),
            "room_name": r[3],
            "started_at": r[4].isoformat() if r[4] else None,
            "ended_at": r[5].isoformat() if r[5] else None,
            "duration_sec": r[6],
            "end_reason": r[7],
            "live": r[5] is None,
        }
        for r in rows
    ]


def usage_by_tenant_day_kind(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """
        select tenant_id, date_trunc('day', at)::date as day, kind, sum(qty) as total_qty
        from usage_events
        group by tenant_id, day, kind
        order by day desc, tenant_id
        """
    ).fetchall()
    out = []
    for tenant_id, day, kind, total_qty in rows:
        total_qty = float(total_qty)
        cost_usd = (
            round((total_qty / 60.0) * AGENT_SEC_COST_PER_MIN_USD, 6)
            if kind == "agent_sec"
            else None
        )
        out.append(
            {
                "tenant_id": str(tenant_id),
                "day": day.isoformat(),
                "kind": kind,
                "total_qty": total_qty,
                "cost_usd": cost_usd,
            }
        )
    return out


def quota_near_cap(conn: psycopg.Connection, *, threshold: float = 0.8) -> list[dict]:
    """Tenants at >= `threshold` of either their concurrent or monthly-minutes cap."""
    rows = conn.execute(
        """
        select t.id, t.name, t.max_concurrent, t.max_minutes_month,
               coalesce(q.concurrent_now, 0) as concurrent_now,
               coalesce(q.minutes_this_month, 0) as minutes_this_month
        from tenants t
        left join quota_state q on q.tenant_id = t.id
        where t.max_concurrent > 0 and t.max_minutes_month > 0
          and (
                coalesce(q.concurrent_now, 0)::numeric / t.max_concurrent >= %s
             or coalesce(q.minutes_this_month, 0) / t.max_minutes_month >= %s
          )
        order by t.name
        """,
        (threshold, threshold),
    ).fetchall()
    return [
        {
            "tenant_id": str(r[0]),
            "name": r[1],
            "max_concurrent": r[2],
            "max_minutes_month": r[3],
            "concurrent_now": r[4],
            "minutes_this_month": float(r[5]),
            "concurrent_pct": round(r[4] / r[2], 4) if r[2] else None,
            "minutes_pct": round(float(r[5]) / r[3], 4) if r[3] else None,
        }
        for r in rows
    ]


def live_concurrency(conn: psycopg.Connection) -> dict:
    """Sum of quota_state.concurrent_now (OUR own per-tenant cap accounting — the number the mint
    actually enforces) against our configured caps. NOT a claim about LiveKit Build's own
    concurrent-session ceiling: ADR-014 found the documented "5 concurrent" figure was not
    reproduced at n=6 and is UNVERIFIED-BY-US — asserting a LiveKit-side number here would
    contradict that ADR and invent a figure we do not have. `livekit_cap_note` says so explicitly
    rather than silently picking a number."""
    rows = conn.execute(
        "select coalesce(sum(concurrent_now), 0), coalesce(sum(max_concurrent), 0) "
        "from quota_state right join tenants on tenants.id = quota_state.tenant_id"
    ).fetchone()
    total_concurrent, total_cap = rows
    return {
        "total_concurrent_now": int(total_concurrent),
        "total_our_cap": int(total_cap),
        "livekit_cap_note": (
            "docs/10-SPEC.md lists LiveKit Build free tier as '5 concurrent, 1,000 min' but "
            "ADR-014 measured 6/6 concurrent test connections succeeding and explicitly could "
            "not reproduce a 5-concurrent hard cap — that figure is UNVERIFIED-BY-US, not "
            "asserted here as ground truth."
        ),
    }


def blockers(conn: psycopg.Connection, *, hours: int = 24) -> list[dict]:
    """429/403 rejection rate per tenant over the trailing window — mint_rejections (0007_admin.sql),
    populated by control_plane/mint.py + control_plane/app.py's rate limiter."""
    rows = conn.execute(
        """
        select tenant_id, status, count(*) as n
        from mint_rejections
        where at >= now() - (%s || ' hours')::interval
        group by tenant_id, status
        order by n desc
        """,
        (hours,),
    ).fetchall()
    return [
        {"tenant_id": str(r[0]) if r[0] else None, "status": r[1], "count": r[2]}
        for r in rows
    ]
