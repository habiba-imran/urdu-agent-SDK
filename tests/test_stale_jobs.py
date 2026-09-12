"""Stale LiveKit job rejection for orphaned browser sessions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import psycopg
import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from dbconn import conn_kwargs  # noqa: E402
from worker.stale_jobs import (  # noqa: E402
    abandon_stale_job_if_needed,
    close_open_session,
    evaluate_session_for_job,
    reject_stale_job_request,
    stale_job_max_age_sec,
)


def _kw():
    try:
        return conn_kwargs()
    except SystemExit:
        pytest.skip("SUPABASE_DB_URL not configured")


@pytest.fixture
def tenant_with_session():
    conn = psycopg.connect(**_kw(), autocommit=True)
    tenant_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    room_name = str(uuid.uuid4())
    conn.execute(
        "insert into tenants (id,name,hmac_secret_hash) values (%s,'stale-test','x')",
        (tenant_id,),
    )
    conn.execute(
        "insert into agents (id,tenant_id,name,prompt,voice_id,llm_model) "
        "values (%s,%s,'agent','prompt','v_meklc281','gemini-2.5-flash')",
        (agent_id, tenant_id),
    )
    conn.execute(
        "insert into quota_state (tenant_id, concurrent_now) values (%s, 1)",
        (tenant_id,),
    )
    conn.execute(
        "insert into sessions (tenant_id, agent_id, room_name) values (%s,%s,%s)",
        (tenant_id, agent_id, room_name),
    )
    yield {"tenant_id": tenant_id, "room_name": room_name, "conn": conn}
    for table in ("usage_events", "sessions", "quota_state", "agents"):
        conn.execute(f"delete from {table} where tenant_id = %s", (tenant_id,))
    conn.execute("delete from tenants where id = %s", (tenant_id,))
    conn.close()


def test_evaluate_rejects_closed_session(tenant_with_session):
    room = tenant_with_session["room_name"]
    conn = tenant_with_session["conn"]
    conn.execute(
        "update sessions set ended_at = now(), end_reason = 'participant_disconnected' "
        "where room_name = %s",
        (room,),
    )
    reject, reason = evaluate_session_for_job(room)
    assert reject is True
    assert reason == "session_already_closed"


def test_evaluate_rejects_old_open_session(tenant_with_session):
    room = tenant_with_session["room_name"]
    conn = tenant_with_session["conn"]
    conn.execute(
        "update sessions set started_at = now() - interval '10 minutes' where room_name = %s",
        (room,),
    )
    reject, reason = evaluate_session_for_job(room, max_age_sec=180)
    assert reject is True
    assert reason == "stale_orphan_dispatch"


def test_evaluate_accepts_fresh_open_session(tenant_with_session):
    room = tenant_with_session["room_name"]
    reject, reason = evaluate_session_for_job(
        room,
        now=datetime.now(UTC),
        max_age_sec=stale_job_max_age_sec(),
    )
    assert reject is False
    assert reason == ""


def test_close_open_session_releases_concurrency(tenant_with_session):
    room = tenant_with_session["room_name"]
    tenant_id = tenant_with_session["tenant_id"]
    conn = tenant_with_session["conn"]

    assert close_open_session(room, end_reason="stale_orphan_dispatch") is True

    ended = conn.execute(
        "select ended_at, end_reason from sessions where room_name = %s",
        (room,),
    ).fetchone()
    assert ended[0] is not None
    assert ended[1] == "stale_orphan_dispatch"

    concurrent = conn.execute(
        "select concurrent_now from quota_state where tenant_id = %s",
        (tenant_id,),
    ).fetchone()[0]
    assert concurrent == 0


@pytest.mark.asyncio
async def test_reject_stale_job_request_accepts_immediately():
    req = MagicMock()
    req.accept = AsyncMock()
    req.reject = AsyncMock()

    await reject_stale_job_request(req)

    req.accept.assert_awaited_once()
    req.reject.assert_not_called()


@pytest.mark.asyncio
async def test_abandon_stale_job_if_needed_closes_before_connect():
    ctx = MagicMock()
    ctx.room.name = "stale-room-123"
    ctx.shutdown = MagicMock()

    with (
        patch(
            "worker.stale_jobs.evaluate_session_for_job",
            return_value=(True, "session_already_closed"),
        ),
        patch("worker.stale_jobs.close_open_session", return_value=True) as close_mock,
        patch("worker.stale_jobs.cleanup_livekit_room", new_callable=AsyncMock) as cleanup_mock,
    ):
        abandoned = await abandon_stale_job_if_needed(ctx)

    assert abandoned is True
    close_mock.assert_called_once_with("stale-room-123", end_reason="session_already_closed")
    cleanup_mock.assert_awaited_once_with("stale-room-123")
    ctx.shutdown.assert_called_once_with(reason="session_already_closed")


@pytest.mark.asyncio
async def test_abandon_stale_job_if_needed_allows_fresh_sessions():
    ctx = MagicMock()
    ctx.room.name = "fresh-room-456"

    with patch(
        "worker.stale_jobs.evaluate_session_for_job",
        return_value=(False, ""),
    ):
        abandoned = await abandon_stale_job_if_needed(ctx)

    assert abandoned is False
    ctx.shutdown.assert_not_called()
