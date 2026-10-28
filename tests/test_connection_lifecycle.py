"""Failure interleavings and actual adapter boundaries, with no provider network."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace as NS

import pytest
from livekit.agents import APIConnectionError, APIStatusError
from worker.lifecycle import SessionLifecycle, duration_limit
from worker.provider_retries import fail_session, wire_provider_failure


@pytest.mark.parametrize("value", [True, 0, 59, 7201, 1.5, "1800"])
def test_duration_rejects_invalid_limits(value):
    with pytest.raises(ValueError):
        duration_limit(value)


def test_duration_default_and_ceiling():
    assert duration_limit() == 1800
    assert duration_limit(7200) == 7200
    assert duration_limit(60) == 60


@pytest.mark.parametrize("channel", ["web", "inbound", "outbound"])
def test_duration_ends_transport_for_each_call_channel(monkeypatch, channel):
    from worker import lifecycle as module
    async def run():
        events, shutdowns, packets = asyncio.Event(), [], []
        participant = NS(kind=0, attributes={} if channel == "web" else {"sip.callStatus": "active"})
        async def publish(data, **kwargs): packets.append(data)
        room = NS(name="room", remote_participants={"caller": participant}, on=lambda *_: None,
                  local_participant=NS(publish_data=publish))
        session = NS(shutdown=lambda **kw: shutdowns.append(kw))
        lifecycle = SessionLifecycle(NS(room=room))
        lifecycle.session_id = "session"
        async def stop(reason): events.set()
        lifecycle.stop_transport = stop
        real_sleep = asyncio.sleep
        async def sleep(seconds):
            assert seconds == 60
            await real_sleep(0)
        monkeypatch.setattr(module.asyncio, "sleep", sleep)
        lifecycle.stt_ready.set()
        await lifecycle.pipeline_ready(session, NS(tenant_id="tenant", max_call_duration_seconds=60))
        await asyncio.wait_for(events.wait(), .5)
        assert lifecycle.reason == "max_duration_reached"
        assert shutdowns == [{"drain": False}]
        assert any(b'max_duration_reached' in packet for packet in packets)
        await lifecycle.close()
    asyncio.run(run())


def test_cancelling_prewarm_joins_child_tasks():
    from worker.latency import prewarm_greeting_providers
    async def run():
        entered, closed = asyncio.Event(), asyncio.Event()
        async def warm():
            entered.set()
            try: await asyncio.Event().wait()
            finally: closed.set()
        task = asyncio.create_task(prewarm_greeting_providers(tts=NS(prewarm=warm), stt=None))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert closed.is_set()
    asyncio.run(run())


def test_failure_packet_is_sent_before_shutdown_and_only_once():
    async def run():
        order = []
        async def publish(*args, **kwargs):
            await asyncio.sleep(0)
            order.append("published")
        session = NS(userdata=NS(humanization_runtime=None), shutdown=lambda **kwargs: order.append("shutdown"))
        room = NS(local_participant=NS(publish_data=publish))
        first = fail_session(session, "LLM", room=room, code="provider_quota_exhausted")
        assert fail_session(session, "TTS", room=room) is first
        await session._awaaz_failure_task
        assert order == ["published", "shutdown"]
        assert first["code"] == "provider_quota_exhausted"
    asyncio.run(run())


def test_quota_error_is_terminal_even_if_plugin_calls_it_recoverable():
    async def run():
        events = {}
        session = NS(userdata=NS(humanization_runtime=None),
                     on=lambda name, callback: events.setdefault(name, callback), shutdown=lambda **_: None)
        room = NS(local_participant=NS(publish_data=lambda *_, **__: asyncio.sleep(0)))
        wire_provider_failure(session, room)
        events["error"](NS(error=NS(error=NS(status_code=429), recoverable=True)))
        await session._awaaz_failure_task
        assert session._awaaz_failure_outcome["code"] == "provider_quota_exhausted"
    asyncio.run(run())


def test_provider_final_usage_survives_provider_close():
    async def run():
        callbacks = {}
        class Provider:
            def on(self, name, callback): callbacks[name] = callback
            async def aclose(self):
                callbacks["metrics_collected"](NS(type="stt_metrics", audio_duration=.4,
                    request_id="last", timestamp=1))
        session = NS()
        lifecycle = SessionLifecycle(NS(room=NS(name="room")))
        lifecycle.session = session
        lifecycle.own_provider(Provider())
        final = []
        async def settle(reason): final.append(dict(session._awaaz_final_usage))
        lifecycle.finalizer = settle
        await lifecycle.close("done")
        await lifecycle.close("duplicate")
        assert final == [{"stt_sec": .4, "tts_sec": 0, "llm_tokens": 0}]
    asyncio.run(run())


def test_atomic_settlement_rolls_back_quota_and_terminal_state(monkeypatch):
    from worker.session_close import release_session_quota_slot
    class Conn:
        def __init__(self): self.closed = False; self.quota = 1
        @contextmanager
        def transaction(self):
            before = self.closed, self.quota
            try: yield
            except Exception:
                self.closed, self.quota = before
                raise
        def execute(self, sql, params):
            if "set ended_at" in sql:
                self.closed = True
                return NS(fetchone=lambda: ("session", "tenant"))
            if "from telephony_calls" in sql: return NS(fetchone=lambda: None)
            if "update quota_state" in sql: self.quota -= 1
            if "set transcript" in sql: raise RuntimeError("transcript storage unavailable")
            return NS(fetchone=lambda: None)
    conn = Conn()
    with pytest.raises(RuntimeError, match="transcript storage"):
        release_session_quota_slot(room_name="room", tenant_id="tenant", elapsed_sec=1,
                                   end_reason="normal", transcript=[], conn=conn)
    assert conn.closed is False and conn.quota == 1


def test_finalization_payload_survives_database_outage_and_replays(monkeypatch, tmp_path):
    from worker import finalization_retry as retry, session_close
    monkeypatch.setattr(retry, "directory", lambda: tmp_path)
    monkeypatch.setattr(retry.time, "sleep", lambda _: None)
    def down(**kwargs): raise OSError("database unavailable")
    monkeypatch.setattr(session_close, "release_session_quota_slot", down)
    with pytest.raises(RuntimeError, match="durable retry"):
        retry.settle_session(room_name="room", tenant_id="tenant", elapsed_sec=6, end_reason="normal")
    assert len(list(tmp_path.glob("*.json"))) == 1
    received = []
    monkeypatch.setattr(session_close, "release_session_quota_slot", lambda **kwargs: received.append(kwargs))
    assert retry.retry_pending() == 1
    assert received[0]["elapsed_sec"] == 6
    assert not list(tmp_path.glob("*.json"))


def test_reconciled_session_accepts_actual_settlement_once_without_second_quota_release(monkeypatch):
    from worker import session_close
    class Conn:
        finalized = False
        writes = []
        def execute(self, sql, params=None):
            if sql.startswith("select id, tenant_id from sessions s"):
                return NS(fetchone=lambda: None if self.finalized else ("session", "tenant"))
            self.writes.append((sql, params))
            if "set finalized_at" in sql: self.finalized = True
            return NS(fetchone=lambda: None)
    conn = Conn()
    monkeypatch.setattr(session_close, "_finalize_telephony_call", lambda *a, **kw: (None, False, None))
    monkeypatch.setattr(session_close, "_apply_retention", lambda *a, **kw: None)
    monkeypatch.setattr(session_close, "_attach_transcript", lambda *a, **kw: True)
    billed = []
    def bill(*a, **kw): billed.append(kw["elapsed_sec"]); return 1
    monkeypatch.setattr(session_close, "_record_usage_and_minutes", bill)
    for _ in range(2):
        session_close.release_session_quota_slot(room_name="room", tenant_id="tenant", elapsed_sec=42,
                                                end_reason="normal", conn=conn)
    assert billed == [42]
    assert not any("update quota_state" in sql for sql, _ in conn.writes)
    assert any("set duration_sec" in sql and params[0] == 42 for sql, params in conn.writes)


def test_uplift_error_after_partial_audio_is_not_success():
    from worker.providers.tts.uplift_transport import ReliableWebSocketClient, RequestQueue
    async def run():
        client = ReliableWebSocketClient(NS())
        queue = RequestQueue(client, "r")
        client.audio_callbacks["r"] = queue
        client.active_requests["r"] = True
        queue.put_nowait(b"partial")
        await client._on_message({"type": "error", "requestId": "r", "statusCode": 402})
        assert await queue.get() == b"partial"
        with pytest.raises(APIStatusError) as error: await queue.get()
        assert error.value.status_code == 402
        assert not client.audio_callbacks and not client.active_requests
    asyncio.run(run())


def test_uplift_concurrent_prewarm_and_synthesis_share_ready_handshake(monkeypatch):
    from worker.providers.tts import uplift_transport as module
    instances = []
    class Socket:
        def __init__(self, **_): self.handlers = {}; self.connected = False; instances.append(self)
        def on(self, name, callback, **_): self.handlers[name] = callback
        async def connect(self, *_, **__):
            await asyncio.sleep(0)
            self.connected = True
            await self.handlers["message"]({"type": "ready"})
        async def disconnect(self): self.connected = False
        async def emit(self, *_, **__): pass
    monkeypatch.setattr(module.socketio, "AsyncClient", Socket)
    async def run():
        client = module.ReliableWebSocketClient(NS(base_url="https://fixture", api_key="fixture",
            voice_settings=NS(voice_id="voice", output_format="PCM_22050_16"), phrase_replacement_config_id=None))
        await asyncio.gather(client.connect(), client.synthesize("hello", "r"))
        assert len(instances) == 1 and client.connected
        await client.cancel("r")
        assert not client.audio_callbacks and not instances[0].connected
    asyncio.run(run())


def test_gladia_remote_close_while_input_open_raises_and_closes_socket():
    from worker.providers.stt.gladia_transport import ReliableSpeechStream
    async def run():
        stream = object.__new__(ReliableSpeechStream)
        stream._conn_options = NS(timeout=.1)
        stream._reconnect_event = asyncio.Event()
        stream._audio_duration_collector = NS(flush=lambda: None)
        closed = []
        socket = NS(close=lambda: close())
        async def close(): closed.append(True)
        async def initialize(): return {"url": "wss://fixture", "id": "r"}
        async def connect(url): return socket
        async def sending(): await asyncio.Event().wait()
        async def receiving(): return
        stream._init_live_session = initialize
        stream._session = NS(ws_connect=connect)
        stream._report_connection_acquired = lambda *_: None
        stream._send_audio_task = sending
        stream._recv_messages_task = receiving
        with pytest.raises(APIConnectionError, match="input was still open"):
            await stream._run()
        assert closed == [True]
    asyncio.run(run())


def test_startup_failure_closes_an_attempt_before_session_exists(monkeypatch):
    from worker import main, lifecycle, finalization_retry, stale_jobs
    async def run():
        callbacks, ended, notified, settled = [], [], [], []
        async def publish(data, **kwargs): notified.append(data)
        ctx = NS(room=NS(name="room", remote_participants={}, local_participant=NS(publish_data=publish)),
            job=NS(metadata='{"tenant_id":"tenant","agent_id":"agent","session_id":"session"}'),
            add_shutdown_callback=callbacks.append, shutdown=lambda **kwargs: ended.append(kwargs))
        async def connect(): return None
        ctx.connect = connect
        async def build(*args, **kwargs): raise ValueError("bad provider configuration")
        async def fresh(*args, **kwargs): return False
        async def cleanup(*args): return None
        monkeypatch.setattr(main, "build_session", build)
        monkeypatch.setattr(main, "abandon_stale_job_if_needed", fresh)
        monkeypatch.setattr(stale_jobs, "cleanup_livekit_room", cleanup)
        monkeypatch.setattr(lifecycle, "heartbeat", lambda _: ("session", False))
        monkeypatch.setattr(finalization_retry, "retry_pending", lambda: 0)
        monkeypatch.setattr(finalization_retry, "settle_session", lambda **kwargs: settled.append(kwargs))
        with pytest.raises(ValueError, match="bad provider"):
            await main.entrypoint(ctx)
        await callbacks[0]("startup_failed")
        assert ended == [{"reason": "startup_failed"}]
        assert len(notified) == 1
        assert settled[0]["tenant_id"] == "tenant"
    asyncio.run(run())


def test_tail_stt_usage_survives_closed_framework_event_channel():
    from worker.providers.stt.lifecycle import metered
    from livekit.plugins.gladia._utils import PeriodicCollector
    async def run():
        handlers, native = {}, []
        class Provider:
            def on(self, event, callback): handlers[event] = callback
            def emit(self, event, metric): handlers[event](metric)
            def stream(self):
                result = NS(_event_ch=NS(closed=False), _session=NS())
                result._audio_duration_collector = PeriodicCollector(native.append, duration=100)
                async def close(): result._event_ch.closed = True
                result.aclose = close
                return result
        provider = metered(Provider())
        owner = SessionLifecycle(NS(room=NS(name="room")))
        owner.own_provider(provider)
        stream = provider.stream()
        stream._audio_duration_collector.push(.125)
        await stream.aclose()
        assert owner.usage["stt_sec"] == .125 and native == []
    asyncio.run(run())


def test_active_call_keeps_expired_lease_from_being_reconciled(monkeypatch):
    from test_reconcile_sessions import FakeReconcileDb
    from scripts.reconcile_sessions import reconcile_sessions
    monkeypatch.setattr("worker.room_presence.room_is_active", lambda _: True)
    db = FakeReconcileDb(tenants=["tenant"], open_sessions=[{"id":"s", "tenant_id":"tenant"}],
        stale_sessions=[("s", "tenant", "room", "2026-01-01")], quota={"tenant":1})
    result = reconcile_sessions(conn=db)
    assert result["stale_sessions_closed"] == 0
    assert not any("update sessions" in sql.lower() for sql, _ in db.executed)


def test_ambiguous_outbound_failure_retains_failed_attempt_for_idempotent_retry(monkeypatch):
    from test_telephony_client_calling_simulation import ClientCallingSimulationDb
    from tenant_portal_api.telephony_service import TelephonyService
    from tenant_portal_api import telephony_queries
    db = ClientCallingSimulationDb()
    compensated, completed = [], []
    class Client:
        def create_agent_dispatch(self, room, **kwargs): return {}
        def create_sip_participant(self, **kwargs): raise TimeoutError("lost provider response")
        def end_room(self, room): compensated.append(room)
    real_complete = telephony_queries.complete_idempotency_key
    def complete(conn, tenant, key, action, response):
        completed.append(response)
        return real_complete(conn, tenant, key, action, response)
    monkeypatch.setattr(telephony_queries, "complete_idempotency_key", complete)
    service = TelephonyService(db_conn=db, livekit_client_factory=lambda **_: Client())
    with pytest.raises(TimeoutError):
        service.create_outbound_call(tenant_id="tenant_client_1", agent_id="agent_voice_1",
            from_number_id="num_client_1", to_number="+14155550199", idempotency_key="ambiguous")
    assert compensated == [db.calls[0]["room_name"]]
    assert completed[-1]["platform_status"] == "failed"
    assert completed[-1]["error_code"] == "call_setup_failed"
