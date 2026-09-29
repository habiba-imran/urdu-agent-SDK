"""Tenant-safe query layer for the tenant portal API."""

from __future__ import annotations

from typing import Any

import psycopg

from control_plane.secret_crypto import decrypt_tool_secret, encrypt_tool_secret
from psycopg.types.json import Jsonb

_UNSET = object()


def _sanitize_session_transcript(raw: Any) -> Any:
    """Strip TTS delivery markup (emotion/break/audio tags) before returning to clients."""
    if raw is None:
        return None
    if not isinstance(raw, list):
        return raw
    try:
        from worker.humanization.history import sanitize_transcript_turns

        return sanitize_transcript_turns(raw)
    except Exception:
        return raw


_AGENT_COLUMNS = (
    "id, name, prompt, voice_id, llm_model, created_at, "
    "agent_language, stt_provider, stt_model, stt_options, "
    "llm_provider, llm_options, tts_provider, tts_voice_id, tts_options, "
    "greeting, first_speaker, recording_enabled, tools_base_url, tools_auth_secret"
)


def _agent_row_to_dict(row) -> dict:
    secret = row[19]
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
        "recording_enabled": bool(row[17]),
        "tools_base_url": row[18],
        # Never return the raw secret over the API — only whether one is configured.
        "tools_auth_secret_configured": bool(secret),
    }


def _agent_row_internal(row) -> dict:
    """Full row including tools_auth_secret — worker / internal use only.

    F-M8: the column may now hold ciphertext; callers want the usable value (a PATCH that
    preserves the current secret would otherwise re-encrypt a ciphertext).
    """
    d = _agent_row_to_dict(row)
    d["tools_auth_secret"] = decrypt_tool_secret(row[19])
    return d


def list_agents(conn: psycopg.Connection, tenant_id: str) -> list[dict]:
    rows = conn.execute(
        """
        select a.id, a.name, a.prompt, a.voice_id, a.llm_model, a.created_at,
               a.agent_language, a.stt_provider, a.stt_model, a.stt_options,
               a.llm_provider, a.llm_options, a.tts_provider, a.tts_voice_id, a.tts_options,
               a.greeting, a.first_speaker, a.recording_enabled, a.tools_base_url,
               a.tools_auth_secret,
               coalesce(u.total_agent_sec, 0) as total_agent_sec
        from agents a
        left join (
            select s.agent_id, sum(ue.qty) as total_agent_sec
            from sessions s
            join usage_events ue on ue.session_id = s.id and ue.kind = 'agent_sec'
            where s.tenant_id = %s
            group by s.agent_id
        ) u on u.agent_id = a.id
        where a.tenant_id = %s and a.archived_at is null
        order by a.created_at desc
        """,
        (tenant_id, tenant_id),
    ).fetchall()
    out = []
    for r in rows:
        d = _agent_row_to_dict(r[:20])
        d["total_agent_sec"] = float(r[20])
        out.append(d)
    return out


def get_agent(conn: psycopg.Connection, tenant_id: str, agent_id: str) -> dict | None:
    """Current resolved provider fields for one agent — used by update_agent to supply
    `resolve_agent_provider_fields`'s `current` (defaults for fields omitted on a PATCH)."""
    row = conn.execute(
        f"select {_AGENT_COLUMNS} from agents where id = %s and tenant_id = %s",
        (agent_id, tenant_id),
    ).fetchone()
    return _agent_row_internal(row) if row is not None else None


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
    recording_enabled: bool = False,
    tools_base_url: str | None = None,
    tools_auth_secret: str | None = None,
) -> dict:
    row = conn.execute(
        f"""
        insert into agents (
            tenant_id, name, prompt, voice_id, llm_model,
            agent_language, stt_provider, stt_model, stt_options,
            llm_provider, llm_options, tts_provider, tts_voice_id, tts_options,
            greeting, first_speaker, recording_enabled, tools_base_url, tools_auth_secret
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            bool(recording_enabled),
            tools_base_url,
            # F-M8: stored encrypted when a key is configured; unchanged otherwise.
            encrypt_tool_secret(tools_auth_secret),
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
    recording_enabled=_UNSET,
    tools_base_url=_UNSET,
    tools_auth_secret=_UNSET,
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
            first_speaker = %s,
            recording_enabled = %s,
            tools_base_url = %s,
            tools_auth_secret = %s
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
            (
                current["recording_enabled"]
                if recording_enabled is _UNSET
                else bool(recording_enabled)
            ),
            current["tools_base_url"] if tools_base_url is _UNSET else tools_base_url,
            # F-M8: current["tools_auth_secret"] is already decrypted by
            # _agent_row_internal, so both branches re-encrypt a plaintext value.
            encrypt_tool_secret(
                current["tools_auth_secret"]
                if tools_auth_secret is _UNSET
                else tools_auth_secret
            ),
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
        # Never return the raw secret here — reveal is a separate age-checked route.
        "secret_masked": "••••••••••••••••••••••••••••••••",
        "status": row[4],
        "secret_provisioned": bool(row[3]),
    }


def get_raw_secret(conn: psycopg.Connection, tenant_id: str) -> str:
    """The tenant's own raw HMAC secret (tenants.hmac_secret), for the credentials-tab reveal
    action. Scoped by tenant_id from the caller's own verified portal JWT — same trust boundary
    as get_credentials above, just returning the real value instead of the masked placeholder.
    """
    # F-C6: the secret may now be stored encrypted (tenants.hmac_secret_enc). Prefer it and
    # fall back to the plaintext column during rollout.
    try:
        row = conn.execute(
            "select hmac_secret_enc, hmac_secret from tenants where id = %s",
            (tenant_id,),
        ).fetchone()
        encrypted, plaintext = (row[0], row[1]) if row else (None, None)
    except psycopg.errors.UndefinedColumn:
        conn.rollback()
        row = conn.execute(
            "select hmac_secret from tenants where id = %s",
            (tenant_id,),
        ).fetchone()
        encrypted, plaintext = None, (row[0] if row else None)

    if row is None:
        raise ValueError("tenant not found")
    if encrypted:
        from control_plane.secret_crypto import decrypt_tenant_secret

        secret = decrypt_tenant_secret(encrypted)
        if not secret:
            raise ValueError("no secret provisioned")
        return secret
    if not plaintext:
        raise ValueError("no secret provisioned")
    return plaintext


def rotate_own_secret(conn: psycopg.Connection, tenant_id: str) -> str:
    """F-C6: self-service rotation. There was none — only an admin route (admin/app.py:206),
    so a tenant who believed their secret was exposed could not do anything about it.

    Returns the new secret ONCE. Stored encrypted when a key is configured.
    """
    import hashlib
    import secrets as _pysecrets

    from control_plane.secret_crypto import encrypt_tenant_secret

    new_secret = _pysecrets.token_urlsafe(32)
    new_hash = hashlib.sha256(new_secret.encode()).hexdigest()
    encrypted = encrypt_tenant_secret(new_secret)

    if encrypted:
        try:
            updated = conn.execute(
                "update tenants set hmac_secret_enc = %s, hmac_secret = null, "
                "hmac_secret_hash = %s where id = %s returning id",
                (encrypted, new_hash, tenant_id),
            ).fetchone()
        except psycopg.errors.UndefinedColumn:
            conn.rollback()
            updated = None
        else:
            if updated is None:
                raise ValueError("tenant not found")
            return new_secret

    updated = conn.execute(
        "update tenants set hmac_secret = %s, hmac_secret_hash = %s where id = %s returning id",
        (new_secret, new_hash, tenant_id),
    ).fetchone()
    if updated is None:
        raise ValueError("tenant not found")
    return new_secret


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


# F-M3: the route caps this too, but a helper that accepts any integer is one careless
# caller away from ?limit=1000000 returning every session with full transcripts.
MAX_SESSION_PAGE = 200


def list_recent_sessions(
    conn: psycopg.Connection,
    tenant_id: str,
    *,
    limit: int = 50,
    include_transcript: bool = False,
) -> list[dict]:
    """List recent sessions for a tenant.

    By default omits ``transcript`` (large JSON) — the sessions drawer fetches
    detail via ``get_session``. Recording re-sign is also skipped on the list
    route (see app.py); paths are not returned to clients.
    """
    limit = max(1, min(int(limit), MAX_SESSION_PAGE))
    if include_transcript:
        rows = conn.execute(
            """
            select s.id, s.agent_id, a.name, s.room_name, s.started_at, s.ended_at,
                   s.duration_sec, s.end_reason,
                   (
                     s.ended_at is null
                     and s.started_at > now() - (%s || ' minutes')::interval
                   ) as live,
                   s.summary, s.transcript,
                   (
                     select coalesce(sum(ue.qty), 0)
                     from usage_events ue
                     where ue.session_id = s.id and ue.kind = 'agent_sec'
                   ) as billable_agent_sec
            from sessions s
            join agents a on a.id = s.agent_id
            where s.tenant_id = %s
            order by s.started_at desc
            limit %s
            """,
            (LIVE_SESSION_MAX_AGE_MIN, tenant_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select s.id, s.agent_id, a.name, s.room_name, s.started_at, s.ended_at,
                   s.duration_sec, s.end_reason,
                   (
                     s.ended_at is null
                     and s.started_at > now() - (%s || ' minutes')::interval
                   ) as live,
                   s.summary, null,
                   (
                     select coalesce(sum(ue.qty), 0)
                     from usage_events ue
                     where ue.session_id = s.id and ue.kind = 'agent_sec'
                   ) as billable_agent_sec
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
            "duration_sec": int(r[6]) if r[6] is not None else None,
            "end_reason": r[7],
            "live": r[8],
            "stale": r[5] is None and not r[8],
            "summary": r[9],
            "transcript": _sanitize_session_transcript(r[10]),
            "billable_agent_sec": float(r[11] or 0),
        }
        for r in rows
    ]


def get_session(
    conn: psycopg.Connection, tenant_id: str, session_id: str
) -> dict | None:
    """Full session row for drawer/detail (includes transcript + recording path)."""
    row = conn.execute(
        """
        select s.id, s.agent_id, a.name, s.room_name, s.started_at, s.ended_at,
               s.duration_sec, s.end_reason,
               (
                 s.ended_at is null
                 and s.started_at > now() - (%s || ' minutes')::interval
               ) as live,
               s.summary, s.transcript, s.recording_url, s.recording_storage_path,
               (
                 select coalesce(sum(ue.qty), 0)
                 from usage_events ue
                 where ue.session_id = s.id and ue.kind = 'agent_sec'
               ) as billable_agent_sec
        from sessions s
        join agents a on a.id = s.agent_id
        where s.tenant_id = %s and s.id = %s
        limit 1
        """,
        (LIVE_SESSION_MAX_AGE_MIN, tenant_id, session_id),
    ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "agent_id": str(row[1]),
        "agent_name": row[2],
        "room_name": row[3],
        "started_at": row[4].isoformat() if row[4] else None,
        "ended_at": row[5].isoformat() if row[5] else None,
        "duration_sec": int(row[6]) if row[6] is not None else None,
        "end_reason": row[7],
        "live": row[8],
        "stale": row[5] is None and not row[8],
        "summary": row[9],
        "transcript": _sanitize_session_transcript(row[10]),
        "recording_url": row[11],
        "recording_storage_path": row[12],
        "billable_agent_sec": float(row[13] or 0),
    }


def get_session_by_room(
    conn: psycopg.Connection, tenant_id: str, room_name: str
) -> dict | None:
    """Tenant-scoped session lookup by LiveKit room name (includes recording fields)."""
    row = conn.execute(
        """
        select s.id, s.agent_id, s.room_name, s.started_at, s.ended_at,
               s.duration_sec, s.end_reason, s.summary, s.transcript,
               s.recording_url, s.recording_storage_path
        from sessions s
        where s.tenant_id = %s and s.room_name = %s
        limit 1
        """,
        (tenant_id, room_name),
    ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "agent_id": str(row[1]) if row[1] else None,
        "room_name": row[2],
        "started_at": row[3].isoformat() if row[3] else None,
        "ended_at": row[4].isoformat() if row[4] else None,
        "duration_sec": row[5],
        "end_reason": row[6],
        "summary": row[7],
        "transcript": _sanitize_session_transcript(row[8]),
        "recording_url": row[9],
        "recordingUrl": row[9],
        "recording_storage_path": row[10],
    }


def usage_summary(
    conn: psycopg.Connection,
    tenant_id: str,
    *,
    month: str | None = None,
) -> dict:
    """Usage for one calendar month — 1st through exclusive end (1st of next), in DB time (UTC).

    **Billable minutes** always come from `sum(usage_events.qty where kind='agent_sec') / 60`.
    That table is the append-only billing truth (see `0001_schema.sql` / `worker/usage.py`).
    `quota_state.minutes_this_month` is only what the mint enforces for the *current* month and
    can briefly diverge if a write fails mid-close; it is returned as `enforced_minutes` for
    transparency, never as the invoice figure.

    `month` is optional `YYYY-MM` (UTC calendar). When omitted, uses the current UTC month.
    """
    from datetime import date as date_cls
    from decimal import Decimal, ROUND_HALF_UP

    def billable_minutes_from_sec(agent_sec: float) -> float:
        """Seconds → minutes, half-up to 4 decimal places (invoice-safe)."""
        return float(
            (Decimal(str(agent_sec)) / Decimal(60)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        )

    quota = conn.execute(
        """
        select t.max_concurrent, t.max_minutes_month,
               coalesce(q.concurrent_now, 0) as concurrent_now,
               coalesce(q.minutes_this_month, 0) as minutes_this_month,
               q.period_start
        from tenants t
        left join quota_state q on q.tenant_id = t.id
        where t.id = %s
        """,
        (tenant_id,),
    ).fetchone()
    if quota is None:
        raise ValueError("tenant not found")

    current = conn.execute(
        """
        select date_trunc('month', now())::date,
               (date_trunc('month', now()) + interval '1 month')::date,
               to_char(date_trunc('month', now()), 'YYYY-MM')
        """
    ).fetchone()
    current_start, current_end, current_month = current[0], current[1], current[2]

    if month:
        try:
            year_s, month_s = month.split("-", 1)
            year_i, month_i = int(year_s), int(month_s)
            if month_i < 1 or month_i > 12:
                raise ValueError
            requested = date_cls(year_i, month_i, 1)
        except ValueError as e:
            raise ValueError("month must be YYYY-MM") from e
        if requested > current_start:
            raise ValueError("month cannot be in the future")
        earliest = conn.execute(
            "select (date_trunc('month', now()) - interval '36 months')::date"
        ).fetchone()[0]
        if requested < earliest:
            raise ValueError("month is older than the 36-month retention window")
        period_start = requested
        if month_i == 12:
            period_end = date_cls(year_i + 1, 1, 1)
        else:
            period_end = date_cls(year_i, month_i + 1, 1)
    else:
        period_start, period_end = current_start, current_end

    is_current = period_start == current_start

    period_start_utc = f"{period_start.isoformat()}T00:00:00+00:00"
    period_end_utc = f"{period_end.isoformat()}T00:00:00+00:00"

    totals = conn.execute(
        """
        select kind, coalesce(sum(qty), 0) as total_qty
        from usage_events
        where tenant_id = %s
          and at >= %s::timestamptz
          and at < %s::timestamptz
        group by kind
        order by kind
        """,
        (tenant_id, period_start_utc, period_end_utc),
    ).fetchall()

    daily = conn.execute(
        """
        select (timezone('UTC', at))::date as day,
               kind,
               coalesce(sum(qty), 0) as total_qty
        from usage_events
        where tenant_id = %s
          and at >= %s::timestamptz
          and at < %s::timestamptz
        group by 1, 2
        order by 1 desc, 2
        """,
        (tenant_id, period_start_utc, period_end_utc),
    ).fetchall()

    totals_list = [{"kind": r[0], "total_qty": float(r[1])} for r in totals]
    agent_sec = next((t["total_qty"] for t in totals_list if t["kind"] == "agent_sec"), 0.0)
    billable = billable_minutes_from_sec(agent_sec)

    # Sanity: daily agent_sec must reconcilable to totals (UTC day buckets).
    daily_agent = sum(float(r[2]) for r in daily if r[1] == "agent_sec")
    if abs(daily_agent - agent_sec) > 0.0001:
        raise RuntimeError(
            f"usage reconciliation failed: daily agent_sec {daily_agent} != total {agent_sec}"
        )

    enforced = float(quota[3]) if is_current else None
    concurrent_now = int(quota[2]) if is_current else 0

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "current_month": current_month,
        "is_current_period": is_current,
        "timezone": "UTC",
        "billable_minutes": billable,
        "billable_agent_sec": float(agent_sec),
        "quota": {
            "max_concurrent": quota[0],
            "max_minutes_month": quota[1],
            "concurrent_now": concurrent_now,
            # Back-compat field used by Overview / Usage UI — ALWAYS billable, not mint counter.
            "minutes_this_month": billable,
            "enforced_minutes": enforced,
        },
        "totals": totals_list,
        "daily": [
            {"day": r[0].isoformat(), "kind": r[1], "total_qty": float(r[2])}
            for r in daily
        ],
    }


# F-M13: archive rather than delete. sessions.agent_id cascades on delete (0001_schema.sql),
# so a real DELETE would take the tenant's session and usage history with it.
def archive_agent(conn: psycopg.Connection, tenant_id: str, agent_id: str) -> bool:
    """Mark an agent archived. Returns False when it does not belong to this tenant."""
    row = conn.execute(
        "update agents set archived_at = now() "
        "where id = %s and tenant_id = %s and archived_at is null "
        "returning id",
        (agent_id, tenant_id),
    ).fetchone()
    if row is None:
        return False
    # Stop PSTN traffic routing to an archived agent; the number stays with the tenant.
    try:
        conn.execute(
            "update telephony_managed_numbers set assigned_agent_id = null "
            "where tenant_id = %s and assigned_agent_id = %s",
            (tenant_id, agent_id),
        )
    except psycopg.errors.UndefinedTable:
        # Telephony tables are optional in some environments (fresh dev database).
        pass
    return True


def count_live_sessions_for_agent(
    conn: psycopg.Connection, tenant_id: str, agent_id: str
) -> int:
    row = conn.execute(
        "select count(*) from sessions "
        "where tenant_id = %s and agent_id = %s and ended_at is null",
        (tenant_id, agent_id),
    ).fetchone()
    return int(row[0]) if row else 0


# F-M12: escalations was write-only — worker/tools.py inserted rows that no API, UI or query
# could read back, so a shipped, LLM-callable feature produced records nobody could act on
# and caller phone numbers accumulated unseen.
def list_escalations(
    conn: psycopg.Connection, tenant_id: str, *, limit: int = 50
) -> list[dict]:
    limit = max(1, min(int(limit), MAX_SESSION_PAGE))
    rows = conn.execute(
        """
        select e.id, e.session_id, e.reason, e.contact_info, e.requested_at, e.status,
               s.room_name, s.agent_id, a.name
        from escalations e
        left join sessions s on s.id = e.session_id
        left join agents a on a.id = s.agent_id
        where e.tenant_id = %s
        order by e.requested_at desc
        limit %s
        """,
        (tenant_id, limit),
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "session_id": str(r[1]) if r[1] else None,
            "reason": r[2],
            "contact_info": r[3],
            "requested_at": r[4].isoformat() if r[4] else None,
            "status": r[5],
            "room_name": r[6],
            "agent_id": str(r[7]) if r[7] else None,
            "agent_name": r[8],
        }
        for r in rows
    ]


# Audit §3.1 / §7: tenants.allowed_origins defaults to '{}' and the mint only enforces it when
# it is non-empty (`if allowed_origins and origin not in allowed_origins`). The portal showed
# the list read-only and no route anywhere could set it, so every tenant was unrestricted and
# had no way to stop being unrestricted.
MAX_ALLOWED_ORIGINS = 20


def set_allowed_origins(
    conn: psycopg.Connection, tenant_id: str, origins: list[str]
) -> list[str]:
    """Replace a tenant's browser origin allowlist. An empty list means 'not enforced'."""
    conn.execute(
        "update tenants set allowed_origins = %s where id = %s",
        (origins, tenant_id),
    )
    return origins
