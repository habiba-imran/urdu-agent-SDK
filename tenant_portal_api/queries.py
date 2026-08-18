"""Tenant-safe query layer for the tenant portal API."""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

_UNSET = object()


_AGENT_COLUMNS = (
    "id, name, prompt, voice_id, llm_model, created_at, "
    "agent_language, stt_provider, stt_model, stt_options, "
    "llm_provider, llm_options, tts_provider, tts_voice_id, tts_options, "
    "greeting, first_speaker"
)


def _agent_row_to_dict(row) -> dict:
    return {
        "id": str(row[0]),
        "name": row[1],
        "prompt": row[2],
        "voice_id": row[3],
        "llm_model": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
        "agent_language": row[6],
        "stt_provider": row[7],
        "stt_model": row[8],
        "stt_options": row[9],
        "llm_provider": row[10],
        "llm_options": row[11],
        "tts_provider": row[12],
        "tts_voice_id": row[13],
        "tts_options": row[14],
        "greeting": row[15],
        "first_speaker": row[16],
    }


def list_agents(conn: psycopg.Connection, tenant_id: str) -> list[dict]:
    rows = conn.execute(
        """
        select a.id, a.name, a.prompt, a.voice_id, a.llm_model, a.created_at,
               a.agent_language, a.stt_provider, a.stt_model, a.stt_options,
               a.llm_provider, a.llm_options, a.tts_provider, a.tts_voice_id, a.tts_options,
               a.greeting, a.first_speaker,
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
    out = []
    for r in rows:
        d = _agent_row_to_dict(r[:17])
        d["total_agent_sec"] = float(r[17])
        out.append(d)
    return out


def get_agent(conn: psycopg.Connection, tenant_id: str, agent_id: str) -> dict | None:
    """Current resolved provider fields for one agent — used by update_agent to supply
    `resolve_agent_provider_fields`'s `current` (defaults for fields omitted on a PATCH)."""
    row = conn.execute(
        f"select {_AGENT_COLUMNS} from agents where id = %s and tenant_id = %s",
        (agent_id, tenant_id),
    ).fetchone()
    return _agent_row_to_dict(row) if row is not None else None


def create_agent(
    conn: psycopg.Connection,
    tenant_id: str,
    *,
    name: str,
    prompt: str,
    voice_id: str,
    llm_model: str,
    agent_language: str,
    stt_provider: str,
    stt_model: str,
    stt_options: dict,
    llm_provider: str,
    llm_options: dict,
    tts_provider: str,
    tts_voice_id: str,
    tts_options: dict,
    greeting: str | None = None,
    first_speaker: str = "agent",
) -> dict:
    row = conn.execute(
        f"""
        insert into agents (
            tenant_id, name, prompt, voice_id, llm_model,
            agent_language, stt_provider, stt_model, stt_options,
            llm_provider, llm_options, tts_provider, tts_voice_id, tts_options,
            greeting, first_speaker
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning {_AGENT_COLUMNS}
        """,
        (
            tenant_id,
            name,
            prompt,
            voice_id,
            llm_model,
            agent_language,
            stt_provider,
            stt_model,
            Jsonb(stt_options),
            llm_provider,
            Jsonb(llm_options),
            tts_provider,
            tts_voice_id,
            Jsonb(tts_options),
            greeting,
            first_speaker,
        ),
    ).fetchone()
    return _agent_row_to_dict(row)


def update_agent(
    conn: psycopg.Connection,
    tenant_id: str,
    agent_id: str,
    *,
    name: str | None = None,
    prompt: str | None = None,
    voice_id: str | None = None,
    llm_model: str | None = None,
    agent_language: str | None = None,
    stt_provider: str | None = None,
    stt_model: str | None = None,
    stt_options: dict | None = None,
    llm_provider: str | None = None,
    llm_options: dict | None = None,
    tts_provider: str | None = None,
    tts_voice_id: str | None = None,
    tts_options: dict | None = None,
    greeting=_UNSET,
    first_speaker=_UNSET,
) -> dict:
    current = get_agent(conn, tenant_id, agent_id)
    if current is None:
        raise ValueError("agent not found")

    row = conn.execute(
        f"""
        update agents
        set name = %s,
            prompt = %s,
            voice_id = %s,
            llm_model = %s,
            agent_language = %s,
            stt_provider = %s,
            stt_model = %s,
            stt_options = %s,
            llm_provider = %s,
            llm_options = %s,
            tts_provider = %s,
            tts_voice_id = %s,
            tts_options = %s,
            greeting = %s,
            first_speaker = %s
        where id = %s and tenant_id = %s
        returning {_AGENT_COLUMNS}
        """,
        (
            name if name is not None else current["name"],
            prompt if prompt is not None else current["prompt"],
            voice_id if voice_id is not None else current["voice_id"],
            llm_model if llm_model is not None else current["llm_model"],
            agent_language if agent_language is not None else current["agent_language"],
            stt_provider if stt_provider is not None else current["stt_provider"],
            stt_model if stt_model is not None else current["stt_model"],
            Jsonb(stt_options if stt_options is not None else current["stt_options"]),
            llm_provider if llm_provider is not None else current["llm_provider"],
            Jsonb(llm_options if llm_options is not None else current["llm_options"]),
            tts_provider if tts_provider is not None else current["tts_provider"],
            tts_voice_id if tts_voice_id is not None else current["tts_voice_id"],
            Jsonb(tts_options if tts_options is not None else current["tts_options"]),
            current["greeting"] if greeting is _UNSET else greeting,
            current["first_speaker"] if first_speaker is _UNSET else first_speaker,
            agent_id,
            tenant_id,
        ),
    ).fetchone()
    return _agent_row_to_dict(row)


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


def get_raw_secret(conn: psycopg.Connection, tenant_id: str) -> str:
    """The tenant's own raw HMAC secret (tenants.hmac_secret), for the credentials-tab reveal
    action. Scoped by tenant_id from the caller's own verified portal JWT — same trust boundary
    as get_credentials above, just returning the real value instead of the masked placeholder.
    """
    row = conn.execute(
        "select hmac_secret from tenants where id = %s",
        (tenant_id,),
    ).fetchone()
    if row is None:
        raise ValueError("tenant not found")
    if not row[0]:
        raise ValueError("no secret provisioned")
    return row[0]


# An open session (ended_at IS NULL) older than this is NOT live — it leaked.
#
# The mint opens a `sessions` row; only worker/main.py's `_release_quota_slot` shutdown callback
# closes it. Any ungraceful worker exit (Ctrl-C in dev, crash, OOM, dispatch that never lands)
# leaves the row open forever, so `ended_at IS NULL` alone means "not known to have ended", NOT
# "currently on a call". Treating it as live made the dashboard report 13 live calls against a
# tenant whose oldest "live" session was 96 hours old.
#
# 30 minutes is not a new invention: it is scripts/reconcile_sessions.py's own
# `--max-age-minutes` default, i.e. the staleness bound this repo already uses when it decides a
# session is dead. Reusing that number keeps ONE definition of stale instead of two that can
# disagree. Evaluated in Postgres against now(), so no app-server clock skew enters into it.
LIVE_SESSION_MAX_AGE_MIN = 30


def list_recent_sessions(
    conn: psycopg.Connection, tenant_id: str, *, limit: int = 50
) -> list[dict]:
    rows = conn.execute(
        """
        select s.id, s.agent_id, a.name, s.room_name, s.started_at, s.ended_at,
               s.duration_sec, s.end_reason,
               (
                 s.ended_at is null
                 and s.started_at > now() - (%s || ' minutes')::interval
               ) as live,
               s.summary, s.transcript
        from sessions s
        join agents a on a.id = s.agent_id
        where s.tenant_id = %s
        order by s.started_at desc
        limit %s
        """,
        (LIVE_SESSION_MAX_AGE_MIN, tenant_id, limit),
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
            "live": r[8],
            # Open but past the staleness bound: never closed, and reconciliation has not
            # swept it yet. Surfaced rather than silently folded into "Ended" so a leaked
            # session stays diagnosable from the dashboard instead of looking like a clean call.
            "stale": r[5] is None and not r[8],
            # Both set by the worker at session end (worker/tools.py::end_conversation_summary
            # for summary, worker/main.py::_release_quota_slot for transcript) — null for any
            # session that never reached a clean agent-initiated or shutdown-callback close.
            "summary": r[9],
            "transcript": r[10],
        }
        for r in rows
    ]


def usage_summary(conn: psycopg.Connection, tenant_id: str) -> dict:
    """Usage for the CURRENT CALENDAR MONTH — 1st through the last day, not a rolling window.

    Matches `quota_state.minutes_this_month`, which worker/main.py's shutdown callback already
    rolls over on `date_trunc('month', now())` (the monthly cap the mint enforces). Before this,
    the two disagreed: the cap reset on the calendar month while this view showed a rolling
    "last 30 days" — a tenant could be capped mid-month while the dashboard still showed room, or
    see last month's tail-end usage bleeding into "this month"'s totals.

    Bounds are computed in ONE query (`period` CTE) so `period_start`/`period_end` returned to the
    caller are read from the exact same `now()` the WHERE clauses filtered on — a second query or
    a Python-side `datetime.now()` could observe a different moment and label the data wrong,
    especially right at a month boundary. `period_end` is the exclusive start of next month, not
    "the last day" — deliberately, so there's no ambiguity about whether the last instant of the
    month is included.
    """
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

    period = conn.execute(
        """
        select date_trunc('month', now())::date,
               (date_trunc('month', now()) + interval '1 month')::date
        """
    ).fetchone()
    period_start, period_end = period[0], period[1]

    totals = conn.execute(
        """
        select kind, coalesce(sum(qty), 0) as total_qty
        from usage_events
        where tenant_id = %s
          and at >= %s and at < %s
        group by kind
        order by kind
        """,
        (tenant_id, period_start, period_end),
    ).fetchall()

    daily = conn.execute(
        """
        select date_trunc('day', at)::date as day, kind, coalesce(sum(qty), 0) as total_qty
        from usage_events
        where tenant_id = %s
          and at >= %s and at < %s
        group by day, kind
        order by day desc, kind
        """,
        (tenant_id, period_start, period_end),
    ).fetchall()

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
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
