"""Transport recovery after repeated barge-ins; no speech or business side effects."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from livekit.agents.utils.connection_pool import ConnectionPool
from worker.latency import wire_interruption_tts_prewarm, turn_handling_for_channel
from worker.providers.tts.cartesia import build


def test_only_actual_interruption_starts_transport_recovery():
    handlers = {}
    transport = SimpleNamespace(prewarm_after_interruption=MagicMock(), cancel_interruption_prewarm=MagicMock())
    session = SimpleNamespace(tts=transport, on=lambda event, callback: handlers.update({event: callback}))
    wire_interruption_tts_prewarm(session)
    callbacks = []
    handle = SimpleNamespace(interrupted=False, add_done_callback=callbacks.append)
    handlers['speech_created'](SimpleNamespace(speech_handle=handle))
    callbacks[0](handle)
    transport.prewarm_after_interruption.assert_not_called()
    handle.interrupted = True
    callbacks[0](handle)
    transport.prewarm_after_interruption.assert_called_once()
    handlers['close'](SimpleNamespace())
    callbacks[0](handle)
    transport.prewarm_after_interruption.assert_called_once()
    transport.cancel_interruption_prewarm.assert_called_once()
    options = turn_handling_for_channel('telephony', llm_provider='groq')
    assert options['interruption']['enabled'] is True
    assert options['preemptive_generation']['enabled'] is False


def test_provider_without_recovery_hook_remains_supported():
    handlers = {}
    session = SimpleNamespace(tts=object(), on=lambda event, callback: handlers.update({event: callback}))
    wire_interruption_tts_prewarm(session)
    handlers['speech_created'](SimpleNamespace(speech_handle=SimpleNamespace(
        interrupted=True, add_done_callback=lambda callback: callback(SimpleNamespace(interrupted=True)))))
    handlers['close'](SimpleNamespace())


def test_installed_session_native_interrupt_rewarms_and_next_reply_completes():
    from livekit.agents import Agent, AgentSession
    from test_humanization_observability_framework import SyntheticSink, SyntheticTTS
    class RecoveryTTS(SyntheticTTS):
        recovery_calls = 0
        def prewarm_after_interruption(self):
            self.recovery_calls += 1
    class SlowSink(SyntheticSink):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()
        async def capture_frame(self, frame):
            self.started.set()
            await self.release.wait()
            await super().capture_frame(frame)
        def clear_buffer(self):
            self.release.set()
            super().clear_buffer()
    async def run():
        provider = RecoveryTTS()
        session = AgentSession(tts=provider)
        sink = SlowSink()
        session.output.audio = sink
        wire_interruption_tts_prewarm(session)
        await session.start(Agent(instructions='Synthetic interruption check.'), record=False)
        try:
            first = session.say('The caller interrupts this reply.', allow_interruptions=True)
            await asyncio.wait_for(sink.started.wait(), timeout=5)
            await asyncio.wait_for(session.interrupt(), timeout=5)
            await asyncio.wait_for(first.wait_for_playout(), timeout=5)
            await asyncio.sleep(0)
            assert first.interrupted and provider.recovery_calls == 1
            second = session.say('The next reply completes.', allow_interruptions=True)
            await asyncio.wait_for(second.wait_for_playout(), timeout=5)
            assert not second.interrupted and second.exception() is None
            assert provider.recovery_calls == 1
        finally:
            sink.release.set()
            await session.aclose()
    asyncio.run(run())


def test_repeated_cancelled_cartesia_connections_are_warmed_single_flight(monkeypatch):
    monkeypatch.setenv('CARTESIA_API_KEY', 'fixture-not-a-secret')
    async def run():
        created, closed = [], []
        async def connect(timeout):
            await asyncio.sleep(0)
            connection = object()
            created.append(connection)
            return connection
        async def close(connection):
            closed.append(connection)
        provider = build('fixture-voice', 'en')
        provider._pool = ConnectionPool(connect_cb=connect, close_cb=close)
        try:
            # Exercise the installed pool's one-shot startup prewarm first.
            provider.prewarm()
            for _ in range(10):
                await asyncio.sleep(0)
                if provider._pool._available:
                    break
            assert len(created) == 1
            for expected_count in (2, 3, 4):
                previous = None
                try:
                    async with provider._pool.connection(timeout=1) as connection:
                        previous = connection
                        raise asyncio.CancelledError
                except asyncio.CancelledError:
                    pass
                # Startup prewarm cannot recover a socket removed by cancellation.
                provider.prewarm()
                await asyncio.sleep(0)
                assert len(created) == expected_count - 1
                provider.prewarm_after_interruption()
                task = provider._interruption_warm_task
                provider.prewarm_after_interruption()
                assert task is provider._interruption_warm_task
                await task
                assert len(created) == expected_count
                assert previous in closed
                async with provider._pool.connection(timeout=1) as connection:
                    assert connection is created[-1]
                    assert provider._pool.last_connection_reused is True
            # A committed business operation continues while transport is warmed.
            gate = asyncio.Event()
            business = asyncio.create_task(gate.wait())
            provider.prewarm_after_interruption()
            await provider._interruption_warm_task
            assert not business.done()
            gate.set()
            await business
        finally:
            await provider.aclose()
        assert len(closed) == len(created)
    asyncio.run(run())


def test_cartesia_close_cancels_pending_transport_warmup(monkeypatch):
    monkeypatch.setenv('CARTESIA_API_KEY', 'fixture-not-a-secret')
    async def run():
        entered = asyncio.Event()
        async def connect(timeout):
            entered.set()
            await asyncio.Event().wait()
        provider = build('fixture-voice', 'en')
        provider._pool = ConnectionPool(connect_cb=connect)
        provider.prewarm_after_interruption()
        task = provider._interruption_warm_task
        await entered.wait()
        await provider.aclose()
        assert task.done()
        provider.prewarm_after_interruption()
        assert provider._interruption_warm_task is task
    asyncio.run(run())


def test_transport_warmup_failure_is_bounded_diagnostic(monkeypatch, caplog):
    monkeypatch.setenv('CARTESIA_API_KEY', 'fixture-not-a-secret')
    async def run():
        async def connect(timeout):
            raise RuntimeError('transport unavailable')
        provider = build('fixture-voice', 'en')
        provider._pool = ConnectionPool(connect_cb=connect)
        try:
            provider.prewarm_after_interruption()
            await provider._interruption_warm_task
            assert 'error_type=RuntimeError' in caplog.text
        finally:
            await provider.aclose()
    asyncio.run(run())
