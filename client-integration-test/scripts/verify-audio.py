"""Automated real-provider WebRTC probe; measures received PCM, not browser audibility.

Uses this demo's host/session endpoints and configured test agent. Audio stays in
memory. Only synthetic input clips, transcripts and diagnostic timings are used.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave
from pathlib import Path

import httpx
import numpy as np
from dotenv import dotenv_values
from livekit import rtc

CLIENT_ROOT = Path(__file__).resolve().parent.parent


async def wait_until(predicate, timeout: float):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise TimeoutError("Expected audio/event did not arrive within the probe window")


async def run_probe(args, client, agent, public_key, index):
    result = {
        "run": index,
        "measurement": "automated client received PCM; not browser playback or first useful word",
        "pipeline": {key: agent.get(key) for key in ["agent_language", "stt_provider", "stt_model", "llm_provider", "llm_model", "tts_provider", "tts_voice_id"]},
        "timings_ms": {}, "transcripts": {}, "metrics": [], "turns": [], "errors": [],
        "audio": {"frames": 0, "active_frames": 0, "rms_threshold_int16": 120},
    }
    room = rtc.Room()
    source = None
    tasks = []
    active_at = []
    first_audio = asyncio.Event()
    disconnected = asyncio.Event()
    provider_failed = asyncio.Event()
    input_queue = asyncio.Queue()
    t0 = time.perf_counter()
    def now_ms():
        return round((time.perf_counter() - t0) * 1000, 1)

    async def receive(track):
        stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1, frame_size_ms=20)
        try:
            async for event in stream:
                result["audio"]["frames"] += 1
                samples = np.frombuffer(event.frame.data, dtype=np.int16).astype(np.float64)
                rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0
                if rms > 120:
                    stamp = now_ms()
                    active_at.append(stamp)
                    result["audio"]["active_frames"] += 1
                    if not first_audio.is_set():
                        result["timings_ms"]["workflow_to_first_active_pcm"] = stamp
                        first_audio.set()
                        print(f"run {index}: first non-silent received PCM at {stamp}ms", flush=True)
        finally:
            await stream.aclose()

    @room.on("track_subscribed")
    def subscribed(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            result["timings_ms"].setdefault("remote_audio_track_subscribed", now_ms())
            tasks.append(asyncio.create_task(receive(track)))

    @room.on("transcription_received")
    def transcript(segments, participant, publication):
        speaker = "user" if participant and participant.identity == room.local_participant.identity else "agent"
        for segment in segments:
            result["transcripts"][segment.id] = {"speaker": speaker, "text": segment.text, "final": segment.final, "received_ms": now_ms()}

    @room.on("data_received")
    def data(packet):
        try:
            value = json.loads(packet.data)
        except (ValueError, UnicodeError):
            return
        if not isinstance(value, dict):
            return
        if packet.topic in ("turn_latency", "metrics_updated") or value.get("type") in ("turn_latency", "metrics_updated"):
            result["metrics"].append({"received_ms": now_ms(), "topic": packet.topic, "payload": value})
        if value.get("type") == "awaaz_session_failure":
            result["errors"].append({"stage": value.get("stage"), "outcome": value.get("outcome")})
            provider_failed.set()

    @room.on("disconnected")
    def closed(reason):
        result["disconnected_reason"] = str(reason)
        disconnected.set()

    async def send_clip(name):
        path = Path(args.input_dir) / f"{name}.wav"
        with wave.open(str(path), "rb") as audio:
            assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 16000)
            pcm = audio.readframes(audio.getnframes())
        finished = asyncio.get_running_loop().create_future()
        for offset in range(0, len(pcm), 640):
            frame = pcm[offset:offset + 640].ljust(640, b"\x00")
            marker = finished if offset + 640 >= len(pcm) else None
            input_queue.put_nowait((frame, marker))
        return await asyncio.wait_for(finished, len(pcm) / 32000 + 10)

    async def microphone():
        # A browser microphone remains open through silence. Stopping frames at
        # clip EOF can defer STT endpointing until a provider idle timeout, which
        # makes synthetic reply measurements misleadingly slow.
        next_frame = time.perf_counter()
        silence = bytes(640)
        while room.isconnected():
            try:
                pcm, marker = input_queue.get_nowait()
            except asyncio.QueueEmpty:
                pcm, marker = silence, None
            await source.capture_frame(rtc.AudioFrame(pcm, 16000, 1, 320))
            if marker is not None:
                def mark(done=marker):
                    if not done.done():
                        done.set_result(now_ms())
                asyncio.get_running_loop().call_later(source.queued_duration, mark)
            next_frame = max(next_frame + .02, time.perf_counter())
            await asyncio.sleep(max(0, next_frame - time.perf_counter()))

    async def wait_quiet():
        await wait_until(lambda: active_at and now_ms() - active_at[-1] >= 1300, 35)

    async def turn(name):
        if disconnected.is_set() or provider_failed.is_set():
            raise RuntimeError('Session ended or provider failed before the next synthetic turn')
        await wait_quiet()
        row = {"input_clip": name, "input_start_ms": now_ms()}
        result["turns"].append(row)
        end = await send_clip(name)
        row["input_end_ms"] = end
        try:
            await wait_until(lambda: disconnected.is_set() or provider_failed.is_set() or any(stamp > end for stamp in active_at), 35)
            if not any(stamp > end for stamp in active_at):
                row['error'] = 'Session ended or provider failed before reply audio'
                raise RuntimeError(row['error'])
            first = next(stamp for stamp in active_at if stamp > end)
            row["input_end_to_reply_active_pcm_ms"] = round(first - end, 1)
            await wait_quiet()
        except TimeoutError:
            row["error"] = "No reply PCM within 35 seconds after synthetic input"
            result['errors'].append({"stage": "reply", "input_clip": name, "message": row['error']})

    try:
        # Unchanged demo connects mint with saved server configuration. Apply the
        # selection only when explicitly requested for a pipeline comparison.
        selection = {
            "agentLanguage": agent["agent_language"], "sttProvider": agent["stt_provider"],
            "sttModel": agent["stt_model"], "llmProvider": agent["llm_provider"],
            "llmModel": agent["llm_model"], "ttsProvider": agent["tts_provider"],
            "ttsVoiceId": agent.get("tts_voice_id") or agent["voice_id"],
        }
        if args.apply_pipeline:
            prepared = await client.post(f"/api/agents/{agent['id']}/pipeline", json=selection)
            prepared.raise_for_status()
        result['pipeline_mode'] = 'explicit_apply' if args.apply_pipeline else 'saved_agent_configuration'
        result["timings_ms"]["pipeline_prepare"] = now_ms()
        print(f"run {index}: pipeline checked at {now_ms()}ms", flush=True)
        mint_start = now_ms()
        response = await client.post("/api/voice/session", json={"publishableKey": public_key, "agentId": agent["id"]}, headers={"Origin": "http://localhost:5174"})
        if not response.is_success:
            result["errors"].append({"stage": "mint", "status": response.status_code, "body": response.json()})
            return result
        session = response.json()
        result["room"] = session["roomName"]
        result["timings_ms"]["session_mint"] = round(now_ms() - mint_start, 1)
        print(f"run {index}: minted in {result['timings_ms']['session_mint']}ms", flush=True)
        join_start = now_ms()
        await asyncio.wait_for(room.connect(session["wsUrl"], session["token"]), 30)
        result["timings_ms"]["livekit_join"] = round(now_ms() - join_start, 1)
        result["timings_ms"]["room_connected"] = now_ms()
        print(f"run {index}: room connected at {now_ms()}ms", flush=True)
        source = rtc.AudioSource(16000, 1, queue_size_ms=200)
        track = rtc.LocalAudioTrack.create_audio_track("synthetic-microphone", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await room.local_participant.publish_track(track, options)
        tasks.append(asyncio.create_task(microphone()))
        result['input_transport'] = 'continuous_16khz_pcm_with_silence_between_clips'

        async def readiness():
            # This indicates an active automated receiver, not a real speaker device.
            while room.isconnected():
                await room.local_participant.publish_data(json.dumps({"type": "awaaz_playback_state", "ready": True}), reliable=True)
                await asyncio.sleep(.5)
        tasks.append(asyncio.create_task(readiness()))
        audio_wait = asyncio.create_task(first_audio.wait())
        close_wait = asyncio.create_task(disconnected.wait())
        failure_wait = asyncio.create_task(provider_failed.wait())
        tasks.extend([audio_wait, close_wait, failure_wait])
        await asyncio.wait([audio_wait, close_wait, failure_wait], timeout=65, return_when=asyncio.FIRST_COMPLETED)
        if not first_audio.is_set():
            if provider_failed.is_set():
                raise RuntimeError('Provider failed before greeting audio')
            raise RuntimeError('Room closed before greeting audio' if disconnected.is_set() else 'No greeting audio received within 65 seconds')
        await wait_quiet()
        await turn("identity")
        await turn("arithmetic")
        if args.interruption:
            await wait_quiet()
            end = await send_clip("long")
            await wait_until(lambda: active_at and active_at[-1] > end, 35)
            await asyncio.sleep(.5)
            row = {"input_clip": "stop", "input_start_ms": now_ms(), "agent_audio_active_at_start": now_ms() - active_at[-1] < 100}
            result["turns"].append(row)
            row["input_end_ms"] = await send_clip("stop")
            await wait_quiet()
            row["last_agent_active_pcm_ms"] = active_at[-1]
            row["stop_timing_valid"] = False
            row["stop_timing_limit"] = "Silence/acknowledgement requires generation alignment; no acoustic barge-in stop claim"
        await turn("close")
        await asyncio.sleep(2)
    except Exception as exc:
        result["errors"].append({"type": type(exc).__name__, "message": str(exc)[:300]})
    finally:
        if room.isconnected():
            await room.disconnect()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if source:
            await source.aclose()
        result["duration_ms"] = now_ms()
        result["transcripts"] = list(result["transcripts"].values())
        result["status"] = "failed" if result["errors"] or any(turn.get("error") for turn in result["turns"]) else "completed_probe"
    return result


async def main(args):
    frontend = dotenv_values(CLIENT_ROOT / 'frontend/.env')
    async with httpx.AsyncClient(base_url=args.backend, timeout=60) as client:
        prep_started = time.perf_counter()
        readiness = await client.get('/api/demo/ready')
        readiness.raise_for_status()
        service_preparation_ms = round((time.perf_counter() - prep_started) * 1000, 1)
        print(json.dumps({'service_preparation_ms_before_connect': service_preparation_ms}), flush=True)
        response = await client.get('/api/agents')
        response.raise_for_status()
        agent = next(item for item in response.json()['agents'] if item['id'] == frontend.get('VITE_UVA_AGENT_ID'))
        if agent['agent_language'] != 'en':
            raise RuntimeError('These synthetic clips only validate the English lane')
        if not any(word in agent.get('name', '').lower() for word in ('demo', 'test')):
            raise RuntimeError('The configured agent must be a dedicated demo/test agent')
        config = (await client.get('/api/demo/config')).json()
        results = []
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        for index in range(1, args.runs + 1):
            result = await run_probe(args, client, agent, frontend.get('VITE_UVA_PUBLISHABLE_KEY') or config['publishableKey'], index)
            results.append(result)
            output.write_text(json.dumps({"service_preparation_ms_before_connect": service_preparation_ms, "runs": results}, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({"run": index, "timings_ms": result['timings_ms'], "turns": result['turns'], "audio": result['audio'], "metric_packets": len(result['metrics']), "errors": result['errors']}, ensure_ascii=False), flush=True)
            await asyncio.sleep(3)
        return bool(results) and all(result['status'] == 'completed_probe' for result in results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default='http://localhost:3100')
    parser.add_argument('--input-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--runs', type=int, default=2)
    parser.add_argument('--interruption', action='store_true')
    parser.add_argument('--apply-pipeline', action='store_true', help='Apply configuration explicitly; unchanged demo connects skip this step')
    raise SystemExit(0 if asyncio.run(main(parser.parse_args())) else 1)
