"""Emit usage_events for a session (P3-T07). The billing truth — append-only.

A call writes stt_sec / tts_sec / llm_tokens / agent_sec rows. Written as the DB owner (a trusted
billing write that crosses tenants by design, ADR-005), not through RLS.

Sync on purpose (psycopg async cannot use Windows' ProactorEventLoop); the async worker calls this
via asyncio.to_thread.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dbconn import conn_kwargs  # noqa: E402

KINDS = ("stt_sec", "tts_sec", "llm_tokens", "agent_sec")


def record_usage(tenant_id: str, session_id: str | None, kind: str, qty: float) -> None:
    if kind not in KINDS:
        raise ValueError(f"bad usage kind {kind!r}; must be one of {KINDS}")
    with psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        conn.execute(
            "insert into usage_events (tenant_id, session_id, kind, qty) values (%s, %s, %s, %s)",
            (tenant_id, session_id, kind, qty),
        )


def record_usage_many(
    conn: psycopg.Connection,
    tenant_id: str,
    session_id: str | None,
    items: dict[str, float],
) -> int:
    """Write several usage kinds on an ALREADY-OPEN connection. Returns rows written.

    Takes a connection instead of opening its own (unlike record_usage above) because the caller
    — worker/main.py's shutdown callback — already holds one and writes the session row on it. Four
    separate record_usage() calls would mean four extra connections per hung-up call, which on
    Supabase's connection budget is a real cost for something we can do in one round trip.

    Zero/negative quantities are skipped: a call with no TTS should record no tts_sec row at all,
    not a row of 0 that makes "we measured zero" indistinguishable from "we never measured".
    """
    rows = [(k, v) for k, v in items.items() if v and v > 0]
    for kind, _ in rows:
        if kind not in KINDS:
            raise ValueError(f"bad usage kind {kind!r}; must be one of {KINDS}")
    for kind, qty in rows:
        conn.execute(
            "insert into usage_events (tenant_id, session_id, kind, qty) values (%s, %s, %s, %s)",
            (tenant_id, session_id, kind, float(qty)),
        )
    return len(rows)


def collect_model_usage(session: object) -> dict[str, float]:
    """Map livekit's per-model usage onto this repo's four `usage_events.kind` values.

    Source is `AgentSession.usage.model_usage` (agent_session.py L642-644) — a list with one entry
    per provider/model combination, so entries of the same type are SUMMED rather than overwritten.
    `metrics_collected` is deliberately not used: this livekit-agents version logs a deprecation
    warning for it and points at usage tracking instead (agent_session.py L561-568).

    Defensive by design: this runs inside a shutdown callback, and losing the session row + the
    concurrency slot because a usage field moved in a livekit upgrade would be a far worse failure
    than losing one call's usage numbers. Returns {} if usage is unavailable for any reason.
    """
    out = {"stt_sec": 0.0, "tts_sec": 0.0, "llm_tokens": 0.0}
    try:
        model_usage = session.usage.model_usage  # type: ignore[attr-defined]
    except Exception:
        return {}

    for u in model_usage or []:
        kind = getattr(u, "type", "")
        if kind == "stt_usage":
            out["stt_sec"] += float(getattr(u, "audio_duration", 0.0) or 0.0)
        elif kind == "tts_usage":
            out["tts_sec"] += float(getattr(u, "audio_duration", 0.0) or 0.0)
        elif kind == "llm_usage":
            out["llm_tokens"] += float(getattr(u, "input_tokens", 0) or 0) + float(
                getattr(u, "output_tokens", 0) or 0
            )
    return out
