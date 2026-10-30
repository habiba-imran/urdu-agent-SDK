"""Offline, real-framework interruption tests; no provider or phone calls."""
from __future__ import annotations

import asyncio
from itertools import product
import time
from types import SimpleNamespace

import pytest
from livekit import rtc
from livekit.agents import Agent, AgentSession
from livekit.agents.voice import io

from worker.interruption import (
    aec_warmup_duration, interruption_min_duration, wire_interruption_output_stop,
)
from worker.humanization.turn import build_turn_profile, turn_profile_to_livekit_options
from worker.providers.capabilities import CAPABILITIES
from test_humanization_observability_framework import SyntheticTTS


LANES = [
    (language, channel, stt, llm, tts)
    for language, layers in CAPABILITIES.items()
    for channel in ('webrtc', 'telephony')
    for stt, llm, tts in product(*[
        [name for name, entry in layers[layer].items() if entry['state'] == 'enabled']
        for layer in ('stt', 'llm', 'tts')
    ])
]


@pytest.mark.parametrize('language,channel,stt,llm,tts', LANES)
def test_every_selectable_provider_lane_uses_fast_local_interruption(monkeypatch, language, channel, stt, llm, tts):
    monkeypatch.delenv('UVA_INTERRUPTION_MIN_DURATION', raising=False)
    monkeypatch.setenv('UVA_INTERRUPTION_MODE', 'vad')
    profile = build_turn_profile(audio_channel=channel, stt_provider=stt,
                                 llm_provider=llm, agent_language=language)
    options = turn_profile_to_livekit_options(profile)
    assert options['interruption']['min_words'] == 0  # no STT/provider word gate
    assert .25 <= options['interruption']['min_duration'] <= .35
    assert options['interruption']['mode'] == 'vad'
    assert options['interruption']['enabled'] is True
    # Free-tier speculation policy and provider choice are independent of barge-in.
    assert profile.stt_provider == stt and profile.llm_provider == llm
    if llm == 'groq':
        assert not profile.preemptive_generation_enabled


@pytest.mark.parametrize('raw', ['nan', 'inf', '-1', '4', 'invalid', ''])
def test_invalid_timing_overrides_are_bounded(monkeypatch, raw):
    monkeypatch.setenv('UVA_INTERRUPTION_MIN_DURATION', raw)
    monkeypatch.setenv('UVA_AEC_WARMUP_SECONDS', raw)
    assert interruption_min_duration('webrtc') == .35
    assert aec_warmup_duration('webrtc') == .25


def test_timing_overrides_and_channel_specific_startup_guard(monkeypatch):
    monkeypatch.delenv('UVA_AEC_WARMUP_SECONDS', raising=False)
    assert aec_warmup_duration('telephony') == 0
    assert aec_warmup_duration('webrtc') == .25
    monkeypatch.setenv('UVA_INTERRUPTION_MIN_DURATION', '.65')
    monkeypatch.setenv('UVA_AEC_WARMUP_SECONDS', '3')
    assert interruption_min_duration('webrtc') == .65
    assert aec_warmup_duration('telephony') == 3


@pytest.mark.parametrize('mode,channel,llm', product(['nova', 'flux'], ['webrtc', 'telephony'], ['groq', 'gemini', 'anthropic']))
def test_deepgram_nova_and_flux_keep_the_same_local_interruption_gate(mode, channel, llm):
    profile = build_turn_profile(audio_channel=channel, agent_language='en', stt_provider='deepgram',
                                 llm_provider=llm, stt_options={'stt_mode': mode})
    options = turn_profile_to_livekit_options(profile)
    assert options['interruption']['min_words'] == 0
    assert options['interruption']['min_duration'] <= .35
    if mode == 'flux':
        assert options['endpointing']['min_delay'] == 0  # semantic EOT is still owned by Flux


class PausableSink(io.AudioOutput):
    def __init__(self, *, pause_supported=True):
        super().__init__(label='synthetic_pausable_output', sample_rate=16000,
                         capabilities=io.AudioOutputCapabilities(pause=pause_supported))
        self.started = asyncio.Event()
        self.paused = asyncio.Event()
        self.cleared = asyncio.Event()
        self.enabled = asyncio.Event()
        self.enabled.set()
        self.pause_at = None
        self.resumes = 0
        self.active = False

    async def capture_frame(self, frame):
        await self.enabled.wait()
        await super().capture_frame(frame)
        if not self.active:
            self.active = True
            self.on_playback_started(created_at=time.time())
        self.started.set()

    def pause(self):
        self.pause_at = time.monotonic()
        self.enabled.clear()
        self.paused.set()

    def resume(self):
        self.resumes += 1
        self.enabled.set()

    def flush(self):
        super().flush()
        self.active = False
        # Buffered output remains queued until clear, like a room sink that has
        # received audio ahead of real-time. Ending input does not end playout.

    def clear_buffer(self):
        self.active = False
        self.cleared.set()
        self.on_playback_finished(playback_position=.05, interrupted=True)


class SlowCleanupAgent(Agent):
    def __init__(self):
        super().__init__(instructions='Synthetic slow provider cleanup test.')
        self.cleaning = asyncio.Event()
        self.release_cleanup = asyncio.Event()

    async def tts_node(self, text, model_settings):
        async for frame in self.audio_source():
            yield frame

    async def audio_source(self):
        # Model network streaming with cancellation cleanup held separately from
        # playback. No real provider/model is contacted by this fixture.
        try:
            for _ in range(500):
                yield rtc.AudioFrame(data=bytes(640), sample_rate=16000,
                                     num_channels=1, samples_per_channel=320)
                await asyncio.sleep(.02)
        finally:
            self.cleaning.set()
            await self.release_cleanup.wait()


@pytest.mark.parametrize('fast_output,pause_supported,native_resume', [
    (False, True, False), (True, True, False), (True, False, False), (True, True, True),
])
def test_native_interruption_stops_output_before_slow_provider_cleanup(monkeypatch, fast_output, pause_supported, native_resume):
    """Reproduce old delay and verify output pause before provider cleanup completes."""
    monkeypatch.setenv('UVA_FAST_INTERRUPTION_OUTPUT', '1' if fast_output else '0')
    async def run():
        session = AgentSession(tts=SyntheticTTS(), aec_warmup_duration=0,
                               turn_handling={'interruption': {'mode': 'vad', 'resume_false_interruption': native_resume}})
        sink, agent = PausableSink(pause_supported=pause_supported), SlowCleanupAgent()
        session.output.audio = sink
        wire_interruption_output_stop(session)
        await session.start(agent, record=False)
        try:
            # Public direct-audio path: the framework's forwarding task closes
            # this source before clearing its buffered media. Normal TTS node
            # cleanup is in a separate task and is covered by the other tests.
            handle = session.say('The caller interrupts this old reply.', audio=agent.audio_source(), allow_interruptions=True)
            await asyncio.wait_for(sink.started.wait(), 3)
            sink.cleared.clear()  # output attachment may clear an empty sink
            start = time.monotonic()
            completion = session.interrupt()
            await asyncio.wait_for(agent.cleaning.wait(), 3)
            if fast_output and pause_supported and not native_resume:
                await asyncio.wait_for(sink.paused.wait(), .3)
                assert sink.pause_at - start < .3
            else:
                assert not sink.paused.is_set()
            # The original framework clear is waiting for provider cleanup.
            assert not sink.cleared.is_set()
            assert not completion.done()
            agent.release_cleanup.set()
            await asyncio.wait_for(completion, 3)
            await asyncio.wait_for(handle.wait_for_playout(), 3)
            await asyncio.sleep(0)
            assert sink.cleared.is_set() and sink.enabled.is_set()
            assert handle.interrupted
        finally:
            agent.release_cleanup.set()
            await session.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('channel', ['webrtc', 'telephony'])
def test_real_framework_ignores_brief_noise_but_yields_to_sustained_voice_without_stt(monkeypatch, channel):
    monkeypatch.delenv('UVA_INTERRUPTION_MIN_DURATION', raising=False)
    async def run():
        profile = build_turn_profile(audio_channel=channel)
        session = AgentSession(tts=SyntheticTTS(), aec_warmup_duration=0,
                               turn_handling=turn_profile_to_livekit_options(profile))
        sink, agent = PausableSink(), SlowCleanupAgent()
        session.output.audio = sink
        wire_interruption_output_stop(session)
        await session.start(agent, record=False)
        try:
            handle = session.say('Interruptible speech.', allow_interruptions=True)
            await asyncio.wait_for(sink.started.wait(), 3)
            activity = session._activity  # Test seam into the installed runtime's VAD hooks.
            activity.on_start_of_speech(None, time.time())
            activity.on_vad_inference_done(SimpleNamespace(speech_duration=.1, raw_accumulated_silence=0, speaking=True))
            assert not handle.interrupted and not sink.paused.is_set()
            activity.on_vad_inference_done(SimpleNamespace(speech_duration=profile.interruption_min_duration+.01, raw_accumulated_silence=0, speaking=True))
            await asyncio.wait_for(sink.paused.wait(), .3)
            assert handle.interrupted
            agent.release_cleanup.set()
            await asyncio.wait_for(handle.wait_for_playout(), 3)
        finally:
            agent.release_cleanup.set()
            await session.aclose()
    asyncio.run(run())


def test_required_disclosure_and_native_pause_ownership_are_preserved(monkeypatch):
    monkeypatch.setenv('UVA_FAST_INTERRUPTION_OUTPUT', '1')
    async def run():
        session = AgentSession(tts=SyntheticTTS(), aec_warmup_duration=0)
        sink, agent = PausableSink(), SlowCleanupAgent()
        session.output.audio = sink
        wire_interruption_output_stop(session)
        await session.start(agent, record=False)
        try:
            locked = session.say('Required disclosure.', allow_interruptions=False)
            await asyncio.wait_for(sink.started.wait(), 3)
            session._activity.on_vad_inference_done(SimpleNamespace(speech_duration=1, raw_accumulated_silence=0, speaking=True))
            assert not locked.interrupted and not sink.paused.is_set()
        finally:
            agent.release_cleanup.set()
            await session.aclose()
    asyncio.run(run())


def test_one_word_interim_can_interrupt_without_waiting_for_a_final_transcript(monkeypatch):
    from livekit.agents import stt
    monkeypatch.setenv('UVA_FAST_INTERRUPTION_OUTPUT', '1')
    async def run():
        session = AgentSession(tts=SyntheticTTS(), aec_warmup_duration=0,
                               turn_handling={'interruption': {'mode': 'vad', 'min_words': 0,
                                                              'resume_false_interruption': False}})
        sink, agent = PausableSink(), SlowCleanupAgent()
        session.output.audio = sink
        wire_interruption_output_stop(session)
        await session.start(agent, record=False)
        try:
            handle = session.say('Old reply.', audio=agent.audio_source())
            await asyncio.wait_for(sink.started.wait(), 3)
            session._activity.on_interim_transcript(stt.SpeechEvent(
                type=stt.SpeechEventType.INTERIM_TRANSCRIPT,
                alternatives=[stt.SpeechData(language='en', text='stop')]), speaking=True)
            await asyncio.wait_for(sink.paused.wait(), .3)
            assert handle.interrupted
            agent.release_cleanup.set()
            await asyncio.wait_for(handle.wait_for_playout(), 3)
        finally:
            agent.release_cleanup.set()
            await session.aclose()
    asyncio.run(run())


def test_real_room_output_repeated_interruptions_clear_then_play_next_reply(monkeypatch, caplog):
    """Use the installed room sink and PCM queue, without a room/server/network."""
    from unittest.mock import AsyncMock
    from livekit.agents.voice.room_io._output import _ParticipantAudioOutput
    monkeypatch.setenv('UVA_FAST_INTERRUPTION_OUTPUT', '1')
    async def run():
        room = SimpleNamespace(local_participant=SimpleNamespace(publish_track=AsyncMock(
            return_value=SimpleNamespace(wait_for_subscription=AsyncMock()))))
        sink = _ParticipantAudioOutput(room, sample_rate=16000, num_channels=1,
                                       track_publish_options=rtc.TrackPublishOptions())
        await sink.start()
        paused = asyncio.Event()
        original_pause = sink.pause
        def pause():
            original_pause()
            paused.set()
        sink.pause = pause
        session = AgentSession(tts=SyntheticTTS(), aec_warmup_duration=0,
                               turn_handling={'interruption': {'mode': 'vad', 'resume_false_interruption': False}})
        session.output.audio = sink
        agent = SlowCleanupAgent()
        wire_interruption_output_stop(session)
        await session.start(agent, record=False)
        try:
            for _ in range(3):
                paused.clear()
                agent.cleaning.clear()
                agent.release_cleanup.clear()
                handle = session.say('Old reply.', audio=agent.audio_source())
                async with asyncio.timeout(3):
                    while session.agent_state != 'speaking':
                        await asyncio.sleep(.01)
                completion = session.interrupt()
                await asyncio.wait_for(paused.wait(), .5)
                agent.release_cleanup.set()
                await asyncio.wait_for(completion, 3)
                await asyncio.wait_for(handle.wait_for_playout(), 3)
                async def short_audio():
                    yield rtc.AudioFrame(data=bytes(3200), sample_rate=16000,
                                         num_channels=1, samples_per_channel=1600)
                next_reply = session.say('Fresh reply.', audio=short_audio())
                await asyncio.wait_for(next_reply.wait_for_playout(), 3)
                assert not next_reply.interrupted and next_reply.exception() is None
        finally:
            agent.release_cleanup.set()
            await session.aclose()
            await sink.aclose()
            await asyncio.sleep(.01)
            assert not [task for task in asyncio.all_tasks()
                        if task.get_name() == 'interruption_output_stop' and not task.done()]
    asyncio.run(run())
    assert 'on_playback_started called after start_fut is set' not in caplog.text
    assert 'speech not done in time' not in caplog.text
