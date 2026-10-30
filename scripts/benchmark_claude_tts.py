"""Explicit live pairing probe, synthetic text only; no tenant, tool or phone writes.

Measures text request to first worker PCM through the actual AgentSession and
humanized delivery path. STT and receiver playout are NOT included.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def measure(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env.local')
    from livekit.agents import Agent, AgentSession
    from livekit.agents.voice import io
    from livekit.agents.utils import http_context
    from worker.providers.llm.anthropic import build
    from worker.providers.registry import _build_tts
    from worker.providers.types import AgentRuntimeConfig
    from worker.humanization.agent import AwaazAgent
    from worker.humanization.delivery.context import DeliveryContext
    from worker.humanization.delivery.policy import resolve_delivery_policy
    from worker.humanization.runtime import HumanizationRuntime
    from worker.humanization.policy import resolve_humanization_policy
    from worker.humanization.persona import profile_from_options
    from worker.provider_retries import build_session_connect_options
    from worker.cartesia_spoken_output import SYSTEM_INSTRUCTIONS_BASE

    os.environ['UVA_CLAUDE_LOW_LATENCY'] = '0' if args.baseline else '1'
    provider = args.provider
    language = 'ur' if provider == 'uplift' else 'en'
    async with http_context.open():
        if provider == 'cartesia':
            from livekit.plugins.cartesia.tts import TTSDefaultVoiceId
            voice, options = TTSDefaultVoiceId, {}
        elif provider == 'elevenlabs':
            from livekit.plugins.elevenlabs.tts import DEFAULT_VOICE_ID
            voice, options = DEFAULT_VOICE_ID, {}
        elif provider == 'uplift':
            from livekit.plugins.upliftai.tts import DEFAULT_VOICE_ID
            voice, options = DEFAULT_VOICE_ID, {}
        else:
            from livekit.plugins.rime.tts import DefaultCodaVoice
            voice = DefaultCodaVoice if args.rime_model == 'coda' else 'astra'
            options = {'model': args.rime_model}
        persona = {'humanization': {'enabled': not args.native}}
        cfg = AgentRuntimeConfig(language, '', '', {}, 'anthropic', args.model, persona, provider, voice, options)
        llm, tts = build(args.model), _build_tts(cfg)
        runtime = HumanizationRuntime(tenant_id='synthetic', agent_id='synthetic', session_id='synthetic',
            language=language, channel='webrtc', persona_profile=profile_from_options(persona),
            policy=resolve_humanization_policy(environ={'UVA_HUMANIZATION_POLICY_VERSION': 'conversational_v1'}))
        context = DeliveryContext(cfg, resolve_delivery_policy(provider,
            environ={'UVA_TTS_RENDERER_'+provider.upper(): 'delivery_v1'}), runtime=runtime, metrics_target=tts)
        context.enable_session_reuse()
        runtime.delivery_context = context
        rows = []
        current = {}
        class Sink(io.AudioOutput):
            def __init__(self):
                super().__init__(label='measurement_pcm_not_receiver', sample_rate=tts.sample_rate,
                                 capabilities=io.AudioOutputCapabilities(pause=False))
                self.active = False
                self.duration = 0
            async def capture_frame(self, frame):
                await super().capture_frame(frame)
                if not self.active:
                    self.active = True
                    self.on_playback_started(created_at=time.time())
                current.setdefault('first_pcm_at', time.perf_counter())
                self.duration += frame.duration
                await asyncio.sleep(frame.duration)
            def flush(self):
                super().flush()
                self.active = False
                self.on_playback_finished(playback_position=self.duration, interrupted=False)
                self.duration = 0
            def clear_buffer(self):
                self.active = False
                self.on_playback_finished(playback_position=0, interrupted=True)
        session = AgentSession(llm=llm, tts=tts, aec_warmup_duration=0,
                               turn_handling={'interruption': {'resume_false_interruption': False}},
                               conn_options=build_session_connect_options())
        session.output.audio = Sink()
        if not args.native:
            runtime.attach_session(session)
        instructions = SYSTEM_INSTRUCTIONS_BASE + (
            '\nSynthetic test facts: booking means choosing an available time and confirming the details. '
            'Explain only this general process in two short sentences, at most 30 words total. No live availability or tools exist. '
            + ('Speak Urdu.' if language == 'ur' else 'Speak English.'))
        agent = Agent(instructions=instructions) if args.native else AwaazAgent(
            instructions=instructions, humanization_runtime=runtime, delivery_context=context)
        def metrics(event):
            if hasattr(event, 'ttft'):
                current['llm_ttft_ms'] = round(event.ttft*1000, 1)
                current['cache_read_tokens'] = getattr(event, 'prompt_cached_tokens', None)
                current['output_tokens'] = getattr(event, 'completion_tokens', None)
            elif hasattr(event, 'ttfb'):
                current.setdefault('tts_ttfb_ms', round(event.ttfb*1000, 1))
                current.setdefault('tts_connection_ms', round(event.acquire_time*1000, 1))
                current.setdefault('tts_connection_reused', event.connection_reused)
        llm.on('metrics_collected', metrics)
        tts.on('metrics_collected', metrics)
        try:
            await llm.prewarm()
            await session.start(agent, record=False)
            for index in range(args.runs):
                current = {'run': index+1}
                started = time.perf_counter()
                question = ('I am worried about getting the appointment details wrong. What should I check?'
                            if args.scenario == 'concern' else 'How do I book an appointment?') if language == 'en' else (
                            'مجھے تفصیل کی فکر ہے، وقت بک کرتے ہوئے کیا چیک کروں؟'
                            if args.scenario == 'concern' else 'میں وقت کیسے بک کروں؟')
                handle = session.generate_reply(user_input=question)
                await asyncio.wait_for(handle.wait_for_playout(), 40)
                if handle.exception() is not None:
                    raise handle.exception()
                plans = getattr(agent, 'speech_plans', [])
                plan = plans[-1] if plans else None
                first = current.pop('first_pcm_at', None)
                current['request_to_first_worker_pcm_ms'] = round((first-started)*1000, 1) if first else None
                current['chunk_wait_ms'] = round(plan.chunk_wait_ms, 1) if plan and plan.chunk_wait_ms is not None else None
                current['first_chunk_to_pcm_ms'] = round((first-plan.first_chunk_at)*1000, 1) if first and plan and plan.first_chunk_at else None
                current['first_chunk_reason'] = plan.planned_chunks[0].reason if plan and plan.planned_chunks else None
                current['worker_audio_gap_ms'] = plan.worker_audio_gap_ms if plan else None
                rows.append(current)
            print(json.dumps({'provider': provider, 'model': args.model, 'language': language,
                              'effective_tts': {key: value for key, value in context.effective.items()
                                                if key in {'model', 'voice', 'voice_id', 'speaker', 'speed', 'speed_alpha',
                                                           'sample_rate', 'encoding', 'output_format', 'use_websocket', 'voice_settings'}},
                              'policy': 'previous' if args.baseline else 'updated',
                              'pipeline': 'native_default' if args.native else 'humanized_delivery',
                              'scenario': args.scenario,
                              'measurement': 'live_text_to_worker_pcm_excludes_stt_and_receiver', 'results': rows}, indent=2))
        except Exception as error:
            print(json.dumps({'provider': provider, 'error_type': type(error).__name__,
                              'first_pcm_seen': current.get('first_pcm_at') is not None,
                              'llm_ttft_ms': current.get('llm_ttft_ms'),
                              'output_tokens': current.get('output_tokens'),
                              'status': getattr(error, 'status_code', None)}))
            raise SystemExit(1) from None
        finally:
            await session.aclose()
            await context.aclose()
            await llm.aclose()
            await tts.aclose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--provider', choices=['cartesia', 'rime', 'elevenlabs', 'uplift'], required=True)
    parser.add_argument('--runs', type=int, choices=range(1, 4), default=2)
    parser.add_argument('--model', default='claude-haiku-5-5')
    parser.add_argument('--rime-model', choices=['arcana', 'coda'], default='arcana')
    parser.add_argument('--scenario', choices=['normal', 'concern'], default='normal')
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--native', action='store_true', help='Use the default Agent path without humanization/delivery streaming.')
    args = parser.parse_args()
    if not args.live:
        parser.error('No API calls made. Pass --live to run the bounded paid-provider pairing probe.')
    asyncio.run(measure(args))
