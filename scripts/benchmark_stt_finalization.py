"""Bounded explicit live STT timing from a synthetic PCM WAV, no transcript output.

Measures final/preflight events relative to the last voiced 20ms source window.
Does not call an LLM, synthesize replies, place calls, or access tenant state.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def measure(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env.local')
    import numpy as np
    from livekit import rtc
    from livekit.agents import stt
    from livekit.agents.types import APIConnectOptions
    from livekit.agents.utils import http_context
    with wave.open(str(args.audio)) as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1 or source.getframerate() != 16000:
            raise ValueError('Use a mono 16 kHz signed 16-bit PCM WAV.')
        pcm = source.readframes(source.getnframes())
    samples = np.frombuffer(pcm, dtype=np.int16)
    last_voice = 0
    for offset in range(0, len(samples), 320):
        window = samples[offset:offset+320].astype(np.float64)
        if np.sqrt(np.mean(window**2)) >= 100:
            last_voice = offset+len(window)
    if not last_voice:
        raise ValueError('No speech energy in the supplied synthetic fixture.')
    # Retain 100ms of post-voice audio, then send enough silence for provider EOT.
    samples = samples[:min(len(samples), last_voice+1600)]
    source_stop = None
    events = []
    async with http_context.open():
        if args.provider == 'gladia':
            from worker.providers.stt.gladia import build
            provider = build('en')
        else:
            from worker.providers.stt.deepgram import build
            provider = build('en', {'stt_mode': 'flux' if args.provider.endswith('flux') else 'nova',
                                    'flux_eager_eot': True, 'eager_eot_threshold': .5})
        stream = provider.stream(conn_options=APIConnectOptions(max_retry=0, timeout=10))
        connected = asyncio.Event()
        original_connect = getattr(stream, '_connect_ws', None)
        if original_connect is not None:
            async def connect():
                result = await original_connect()
                connected.set()
                return result
            stream._connect_ws = connect
        async def collect():
            async for event in stream:
                if event.type in {stt.SpeechEventType.PREFLIGHT_TRANSCRIPT,
                                  stt.SpeechEventType.FINAL_TRANSCRIPT,
                                  stt.SpeechEventType.END_OF_SPEECH}:
                    events.append({'event': event.type.value, 'at': time.perf_counter()})
        consumer = asyncio.create_task(collect())
        try:
            # Separate handshake cost from steady conversational finalization.
            connect_started = time.perf_counter()
            async with asyncio.timeout(10):
                while not connected.is_set() and getattr(stream, '_ws', None) is None:
                    if consumer.done():
                        consumer.result()
                    await asyncio.sleep(.01)
            connection_ms = round((time.perf_counter()-connect_started)*1000, 1)
            for offset in range(0, len(samples), 320):
                frame = samples[offset:offset+320]
                stream.push_frame(rtc.AudioFrame(data=frame.tobytes(), sample_rate=16000,
                                                 num_channels=1, samples_per_channel=len(frame)))
                await asyncio.sleep(len(frame)/16000)
                if offset < last_voice <= offset+len(frame):
                    source_stop = time.perf_counter()
            for _ in range(100):
                stream.push_frame(rtc.AudioFrame(data=bytes(640), sample_rate=16000,
                                                 num_channels=1, samples_per_channel=320))
                await asyncio.sleep(.02)
            stream.end_input()
            await asyncio.wait_for(consumer, 12)
            print(json.dumps({'provider': args.provider, 'source': 'synthetic_speech_fixture',
                              'voice_duration_seconds': round(last_voice/16000, 2),
                              'connection_ms_excluded': connection_ms,
                              'measurement': 'live_stt_event_after_last_voiced_source_window',
                              'events': [{'event': event['event'], 'after_voice_end_ms': round((event['at']-source_stop)*1000, 1)}
                                         for event in events]}, indent=2))
        except Exception as error:
            print(json.dumps({'provider': args.provider, 'error_type': type(error).__name__,
                              'status': getattr(error, 'status_code', None)}))
            raise SystemExit(1) from None
        finally:
            await stream.aclose()
            if not consumer.done():
                consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)
            await provider.aclose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--provider', choices=['deepgram-nova', 'deepgram-flux', 'gladia'], required=True)
    parser.add_argument('--audio', type=Path, required=True, help='Explicit synthetic fixture; never a private call recording.')
    args = parser.parse_args()
    if not args.live:
        parser.error('No API calls made. Pass --live to transcribe the synthetic fixture once.')
    asyncio.run(measure(args))
