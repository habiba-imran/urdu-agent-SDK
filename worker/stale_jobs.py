"""Reject or abandon LiveKit agent jobs for dead/orphan browser sessions.

When the worker was offline, minted dispatches queue in LiveKit. Accepting them all at once
(on Windows, in THREAD executor mode) can trigger concurrent room connects and an FFI panic
(`timed out waiting for ReadyForRoomEventRequest`). We reject stale jobs in ``request_fnc``
before ``entrypoint`` connects, and time out waiting for a browser participant on fresh jobs.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from livekit.agents import JobRequest

# Mint TTL is 120s; allow a short join buffer before treating the dispatch as orphaned.
DEFAULT_STALE_JOB_MAX_AGE_SEC = 180
DEFAULT_PARTICIPANT_WAIT_TIMEOUT_SEC = 90


@dataclass(frozen=True)
class SessionJobState:
    tenant_id: str | None
    started_at: datetime
    ended_at: datetime | None


def stale_job_max_age_sec() -> int:
    raw = os.environ.get("WORKER_STALE_JOB_MAX_AGE_SEC", "")
    if raw.strip():
        return max(30, int(raw))
    return DEFAULT_STALE_JOB_MAX_AGE_SEC


def participant_wait_timeout_sec() -> int:
    raw = os.environ.get("WORKER_PARTICIPANT_WAIT_TIMEOUT_SEC", "")
    if raw.strip():
        return max(15, int(raw))
    return DEFAULT_PARTICIPANT_WAIT_TIMEOUT_SEC


def _conn_kwargs() -> dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        from scripts.dbconn import conn_kwargs
    except ImportError:
        from dbconn import conn_kwargs  # type: ignore # noqa: E402

    return conn_kwargs()


def load_session_job_state(room_name: str) -> SessionJobState | None:
    import psycopg

    with psycopg.connect(**_conn_kwargs(), connect_timeout=10) as conn:
        row = conn.execute(
            """
            select tenant_id, started_at, ended_at
            from sessions
            where room_name = %s
            order by started_at desc
            limit 1
            """,
            (room_name,),
        ).fetchone()
    if row is None:
        return None
    return SessionJobState(
        tenant_id=str(row[0]) if row[0] is not None else None,
        started_at=row[1],
        ended_at=row[2],
    )


def evaluate_session_for_job(
    room_name: str,
    *,
    now: datetime | None = None,
    max_age_sec: int | None = None,
) -> tuple[bool, str]:
    """Return ``(should_reject, reason)`` for a pending LiveKit job request."""
    state = load_session_job_state(room_name)
    if state is None:
        return False, ""

    if state.ended_at is not None:
        return True, "session_already_closed"

    max_age = max_age_sec if max_age_sec is not None else stale_job_max_age_sec()
    now = now or datetime.now(UTC)
    started = state.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    age_sec = (now - started.astimezone(UTC)).total_seconds()
    if age_sec > max_age:
        return True, "stale_orphan_dispatch"

    return False, ""


def close_open_session(
    room_name: str,
    *,
    end_reason: str,
    duration_sec: int | None = None,
) -> bool:
    """Close an open session row and release its concurrency slot when possible."""
    import psycopg

    with psycopg.connect(**_conn_kwargs(), connect_timeout=10, autocommit=True) as conn:
        if duration_sec is None:
            row = conn.execute(
                "select tenant_id, extract(epoch from (now() - started_at))::int "
                "from sessions where room_name = %s and ended_at is null",
                (room_name,),
            ).fetchone()
            if row is None:
                return False
            tenant_id, computed = row
            duration_sec = max(1, int(computed or 1))
        else:
            row = conn.execute(
                "select tenant_id from sessions where room_name = %s and ended_at is null",
                (room_name,),
            ).fetchone()
            if row is None:
                return False
            tenant_id = row[0]

        updated = conn.execute(
            """
            update sessions
            set ended_at = now(),
                duration_sec = %s,
                end_reason = %s
            where room_name = %s and ended_at is null
            returning id
            """,
            (duration_sec, end_reason, room_name),
        ).fetchone()
        if updated is None:
            return False

        if tenant_id:
            conn.execute(
                """
                update quota_state
                set concurrent_now = greatest(concurrent_now - 1, 0)
                where tenant_id = %s
                """,
                (tenant_id,),
            )
        return True


async def cleanup_livekit_room(room_name: str) -> None:
    """Best-effort delete dispatches and the LiveKit room for an abandoned session."""
    from livekit import api
    from livekit.agents.log import logger

    url = os.environ.get("LIVEKIT_URL", "")
    key = os.environ.get("LIVEKIT_API_KEY", "")
    secret = os.environ.get("LIVEKIT_API_SECRET", "")
    if not (url and key and secret):
        return

    async with api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lkapi:
        try:
            dispatches = await lkapi.agent_dispatch.list_dispatch(room_name)
            for dispatch in dispatches:
                try:
                    await lkapi.agent_dispatch.delete_dispatch(dispatch.id, room_name)
                except Exception as exc:
                    logger.warning(
                        "failed to delete dispatch %s for room %s: %s",
                        dispatch.id,
                        room_name,
                        exc,
                    )
        except Exception as exc:
            logger.warning("failed to list dispatches for room %s: %s", room_name, exc)

        try:
            await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
        except Exception as exc:
            logger.warning("failed to delete room %s: %s", room_name, exc)


async def reject_stale_job_request(req: JobRequest) -> None:
    """LiveKit ``request_fnc`` hook: accept immediately, then filter stale jobs in entrypoint.

    LiveKit expects ``accept()`` within ~10s of assignment. A synchronous DB round-trip here
    (plus cold job-runner startup on Windows THREAD mode) was causing ``AssignmentTimeoutError``
    and half-initialized sessions where STT worked but LLM never replied. Stale/orphan checks
    run in ``abandon_stale_job_if_needed()`` at entrypoint start, before ``ctx.connect()``.
    """
    await req.accept()


async def abandon_stale_job_if_needed(ctx: Any) -> bool:
    """Drop stale jobs after accept, before room connect. Returns True if abandoned."""
    from livekit.agents.log import logger

    room_name = ctx.room.name
    reject, reason = await asyncio.to_thread(evaluate_session_for_job, room_name)
    if not reject:
        return False

    logger.info("abandoning stale job for room %s (%s)", room_name, reason)
    await asyncio.to_thread(close_open_session, room_name, end_reason=reason)
    await cleanup_livekit_room(room_name)
    ctx.shutdown(reason=reason)
    return True


async def wait_for_session_participant(
    ctx: Any, *, already_connected: bool = False
) -> Any:
    """Wait for the browser/SIP participant with a bounded timeout.

    ``ctx.connect()`` must happen within ~10s of job_entry (LiveKit's own warning). Callers
    that already connected (so a slow DB stale-check cannot delay it) pass
    ``already_connected=True``.
    """
    from livekit.agents.log import logger

    timeout = participant_wait_timeout_sec()
    if not already_connected:
        await ctx.connect()
    try:
        return await asyncio.wait_for(ctx.wait_for_participant(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(
            "no participant joined room %s within %ss — abandoning job",
            ctx.room.name,
            timeout,
        )
        await asyncio.to_thread(
            close_open_session,
            ctx.room.name,
            end_reason="stale_no_participant",
            duration_sec=1,
        )
        ctx.shutdown(reason="stale_no_participant")
        raise
    except RuntimeError as exc:
        if "room disconnected" in str(exc).lower():
            logger.warning(
                "room %s disconnected before a participant joined — abandoning job",
                ctx.room.name,
            )
            await asyncio.to_thread(
                close_open_session,
                ctx.room.name,
                end_reason="stale_room_disconnected",
                duration_sec=1,
            )
            ctx.shutdown(reason="stale_room_disconnected")
            raise
        raise


async def drain_orphan_sessions(
    *,
    max_age_sec: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Close orphaned open sessions and delete their LiveKit rooms/dispatches."""
    import psycopg

    max_age = max_age_sec if max_age_sec is not None else stale_job_max_age_sec()
    stats = {"sessions_closed": 0, "livekit_cleaned": 0}

    with psycopg.connect(**_conn_kwargs(), connect_timeout=10) as conn:
        rows = conn.execute(
            """
            select room_name
            from sessions
            where ended_at is null
              and started_at < now() - (%s * interval '1 second')
            order by started_at asc
            """,
            (max_age,),
        ).fetchall()

    for (room_name,) in rows:
        if dry_run:
            print(f"[dry-run] would close orphan session room={room_name}")
            stats["sessions_closed"] += 1
            continue
        if close_open_session(room_name, end_reason="stale_orphan_dispatch"):
            stats["sessions_closed"] += 1
        await cleanup_livekit_room(room_name)
        stats["livekit_cleaned"] += 1

    return stats
