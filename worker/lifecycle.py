"""Session-owned connection policy, lease and deterministic provider cleanup."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from contextvars import ContextVar
from typing import Any

log = logging.getLogger("worker.lifecycle")
DEFAULT_MAX_CALL_DURATION_SECONDS = 1800
MAX_CALL_DURATION_SECONDS = 7200
current_lifecycle: ContextVar[Any] = ContextVar("awaaz_lifecycle", default=None)


def duration_limit(value: Any = None) -> int:
    if value is None:
        return DEFAULT_MAX_CALL_DURATION_SECONDS
    if isinstance(value, bool) or not isinstance(value, int) or not 60 <= value <= MAX_CALL_DURATION_SECONDS:
        raise ValueError("max_call_duration_seconds must be an integer between 60 and 7200")
    return value


async def publish_outcome(room: Any, outcome: dict) -> bool:
    try:
        await asyncio.wait_for(room.local_participant.publish_data(
            json.dumps(outcome).encode(), reliable=True), timeout=1.0)
        return True
    except Exception:
        log.warning("lifecycle_notify_failed type=%s", outcome.get("type"))
        return False


def heartbeat(room_name: str) -> tuple[str | None, bool]:
    from worker.db_pool import worker_db_connection
    with worker_db_connection() as conn:
        row = conn.execute(
            "update sessions set worker_heartbeat_at = now() "
            "where room_name = %s and ended_at is null returning id, tenant_id", (room_name,)
        ).fetchone()
        from control_plane.quota_usage import monthly_exhausted
        exhausted = monthly_exhausted(conn, str(row[1])) if row else False
    return (str(row[0]) if row else None), exhausted


class SessionLifecycle:
    def __init__(self, ctx: Any):
        self.ctx = ctx
        self.started = time.monotonic()
        self.session: Any = None
        self.tenant_id = ""
        self.session_id: str | None = None
        self.ready = False
        self.stt_ready = asyncio.Event()
        self.closed = False
        self.tasks: set[asyncio.Task] = set()
        self.providers: list[Any] = []
        self.reason: str | None = None
        self.metrics: dict[str, Any] = {"establishment_attempted": True, "pipeline_ready_ms": None,
            "provider_close_failures": [], "finalization": "pending"}
        self.finalizer: Any = None
        self.before_finalize: list[Any] = []
        self.usage = {"stt_sec": 0.0, "tts_sec": 0.0, "llm_tokens": 0.0}
        self._metric_ids: set[tuple] = set()
        self._duration_task: asyncio.Task | None = None
        self._lease_task: asyncio.Task | None = None

    def own_task(self, task: asyncio.Task) -> None:
        self.tasks.add(task)
        def done(result: asyncio.Task) -> None:
            self.tasks.discard(result)
            if not result.cancelled():
                result.exception()  # retrieve exceptions; callers still await their task
        task.add_done_callback(done)

    async def stop_transport(self, reason: str) -> None:
        """Delete the call room even if a speech handle cannot drain during failure."""
        self.reason = reason
        try:
            import aiohttp
            from livekit import api
            async with api.LiveKitAPI(timeout=aiohttp.ClientTimeout(total=3.0)) as client:
                await client.room.delete_room(api.DeleteRoomRequest(room=self.ctx.room.name))
            self.metrics["transport_ended"] = True
        except Exception as error:
            if getattr(error, "code", None) == "not_found":
                self.metrics["transport_ended"] = True
            else:
                self.metrics["transport_ended"] = False
                log.exception("terminal_room_delete_failed room=%s", self.ctx.room.name)
        finally:
            self.ctx.shutdown(reason=reason)

    def start_lease(self) -> None:
        async def lease() -> None:
            while True:
                try:
                    identity, exhausted = await asyncio.to_thread(heartbeat, self.ctx.room.name)
                    if identity:
                        self.session_id = identity
                        if self.session is not None:
                            self.session.userdata.telemetry_session_id = identity
                    elif self.session_id is not None and self.session is not None:
                        self.reason = "session_closed_by_server"
                        await publish_outcome(self.ctx.room, {"type": "awaaz_session_ended",
                            "reason": self.reason, "session_id": self.session_id})
                        self.session.shutdown(drain=False)
                        await self.stop_transport(self.reason)
                        return
                    if exhausted and self.session is not None:
                        self.reason = "monthly_quota_exhausted"
                        await publish_outcome(self.ctx.room, {"type": "awaaz_session_ended",
                            "reason": self.reason, "session_id": self.session_id})
                        self.session.shutdown(drain=False)
                        await self.stop_transport(self.reason)
                        return
                except Exception:
                    log.exception("worker_lease_failed room=%s", self.ctx.room.name)
                await asyncio.sleep(20)
        self._lease_task = asyncio.create_task(lease(), name="session_lease")
        self.own_task(self._lease_task)

    def own_provider(self, provider: Any) -> None:
        if any(existing is provider for existing in self.providers):
            return
        self.providers.append(provider)
        def collected(metric: Any) -> None:
            key = (id(provider), getattr(metric, "type", ""), getattr(metric, "request_id", ""),
                   getattr(metric, "segment_id", None), getattr(metric, "timestamp", None))
            if key in self._metric_ids:
                return
            self._metric_ids.add(key)
            kind = getattr(metric, "type", "")
            if kind in ("stt_metrics", "tts_metrics"):
                if kind != "stt_metrics" or not getattr(provider, "_awaaz_direct_stt_usage", False):
                    self.usage["stt_sec" if kind == "stt_metrics" else "tts_sec"] += float(metric.audio_duration)
                if kind == "stt_metrics" and getattr(metric, "request_id", None) == "" and metric.audio_duration == 0:
                    self.stt_ready.set()
            elif kind == "llm_metrics":
                self.usage["llm_tokens"] += float(metric.total_tokens)
        if callable(getattr(provider, "on", None)):
            provider.on("metrics_collected", collected)
            if getattr(provider, "_awaaz_direct_stt_usage", False):
                def usage(duration): self.usage["stt_sec"] += float(duration)
                provider.on("awaaz_stt_usage", usage)

    async def pipeline_ready(self, session: Any, cfg: Any) -> None:
        self.session = session
        self.tenant_id = cfg.tenant_id
        limit = duration_limit(cfg.max_call_duration_seconds)
        async def send_ready() -> None:
            if not self.ready:
                return
            await publish_outcome(self.ctx.room, {"type": "awaaz_agent_ready",
                "session_id": self.session_id, "max_call_duration_seconds": limit})
        def data_received(packet: Any) -> None:
            participant = getattr(packet, "participant", None)
            if participant is None or getattr(participant, "kind", None) == 4:
                return
            try:
                if json.loads(packet.data).get("type") == "awaaz_lifecycle_request":
                    self.own_task(asyncio.create_task(send_ready()))
            except (ValueError, TypeError, AttributeError):
                return
        self.ctx.room.on("data_received", data_received)
        async def announce_ready() -> None:
            try:
                await asyncio.wait_for(self.stt_ready.wait(), 10.0)
            except TimeoutError:
                from worker.provider_retries import fail_session
                fail_session(session, "STT_CONNECT", room=self.ctx.room)
                return
            self.ready = True
            self.metrics["pipeline_ready_ms"] = round((time.monotonic() - self.started) * 1000)
            log.info("lifecycle_ready room=%s session_id=%s max_duration_s=%s",
                     self.ctx.room.name, self.session_id, limit)
            await send_ready()
        self.own_task(asyncio.create_task(announce_ready(), name="announce_pipeline_ready"))
        async def expire() -> None:
            # The budget starts when a caller is present and the pipeline is ready.
            await self.stt_ready.wait()
            def caller_present() -> bool:
                for participant in self.ctx.room.remote_participants.values():
                    attrs = getattr(participant, "attributes", {})
                    if "sip.callStatus" in attrs:
                        if attrs["sip.callStatus"] in ("active", "automation"):
                            return True
                    elif getattr(participant, "kind", None) != 4:
                        return True
                return False
            while not caller_present():
                await asyncio.sleep(.1)
            await asyncio.sleep(limit)
            self.reason = "max_duration_reached"
            await publish_outcome(self.ctx.room, {"type": "awaaz_session_ended",
                "reason": self.reason, "session_id": self.session_id})
            session.shutdown(drain=False)
            await self.stop_transport(self.reason)
        self._duration_task = asyncio.create_task(expire(), name="session_duration_limit")
        self.own_task(self._duration_task)

    async def close(self, reason: str = "") -> None:
        if self.closed:
            return
        self.closed = True
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)
        close_session = getattr(self.session, "aclose", None)
        # AgentSession serializes close with its internal lock. Awaiting it here
        # also covers job-shutdown callbacks that run concurrently with this one.
        if callable(close_session):
            try:
                await asyncio.wait_for(close_session(), 8.0)
                self.metrics["pipeline_closed"] = True
            except Exception:
                self.metrics["pipeline_closed"] = False
                log.exception("pipeline_close_failed room=%s", self.ctx.room.name)
        # Closing providers is job-owned, including the baseline (non-delivery) path.
        for provider in reversed(self.providers):
            close = getattr(provider, "aclose", None)
            if close is not None:
                try:
                    result = close()
                    if inspect.isawaitable(result):
                        await asyncio.wait_for(result, 3.0)
                except Exception:
                    self.metrics["provider_close_failures"].append(type(provider).__name__)
                    log.exception("provider_close_failed provider=%s", type(provider).__name__)
        for callback in self.before_finalize:
            try:
                await asyncio.wait_for(callback(), 10.0)
            except Exception:
                self.metrics.setdefault("finalize_callback_failures", []).append(getattr(callback, "__name__", "callback"))
                log.exception("finalize_callback_failed room=%s", self.ctx.room.name)
        self.metrics["end_reason"] = self.reason or reason
        self.metrics["elapsed_ms"] = round((time.monotonic() - self.started) * 1000)
        if self.session is not None:
            self.session._awaaz_final_usage = dict(self.usage)
            self.session._awaaz_lifecycle_metrics = dict(self.metrics)
        if self.finalizer is not None:
            await self.finalizer(self.reason or reason)
        log.info("lifecycle_closed room=%s reason=%s elapsed_s=%.3f",
                 self.ctx.room.name, self.reason or reason, time.monotonic() - self.started)
