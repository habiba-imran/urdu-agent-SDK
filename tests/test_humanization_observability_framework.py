"""Actual installed AgentSession pipeline with synthetic providers and no room/network."""

import asyncio
import json
from unittest.mock import MagicMock

from livekit.agents import Agent, AgentSession, llm, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from livekit.agents.voice import io

from worker.latency import wire_turn_latency
from worker.tools import AgentUserdata, lookup_business_info


class SyntheticLLM(llm.LLM):
    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
        return SyntheticStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class SyntheticStream(llm.LLMStream):
    async def _run(self):
        has_result = any(getattr(item, "type", None) == "function_call_output" for item in self.chat_ctx.items)
        if not has_result:
            delta = llm.ChoiceDelta(tool_calls=[llm.FunctionToolCall(
                name="lookup_business_info", arguments='{"query":"synthetic hours"}', call_id="synthetic_call_1")])
        else:
            delta = llm.ChoiceDelta(content="Synthetic business hours are nine to five.")
        self._event_ch.send_nowait(llm.ChatChunk(id="response_result" if has_result else "response_tool", delta=delta))
        self._event_ch.send_nowait(llm.ChatChunk(id="response_result" if has_result else "response_tool", usage=llm.CompletionUsage(
            completion_tokens=5, prompt_tokens=10, total_tokens=15)))


class SyntheticTTS(tts.TTS):
    def __init__(self):
        super().__init__(capabilities=tts.TTSCapabilities(streaming=False), sample_rate=16000, num_channels=1)

    def synthesize(self, text, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):
        return SyntheticAudio(tts=self, input_text=text, conn_options=conn_options)


class SyntheticAudio(tts.ChunkedStream):
    async def _run(self, output_emitter):
        output_emitter.initialize(request_id="synthetic_audio", sample_rate=16000, num_channels=1, mime_type="audio/pcm")
        output_emitter.push(bytes(3200))
        output_emitter.flush()
        output_emitter.end_input()
        await output_emitter.join()


class SyntheticSink(io.AudioOutput):
    def __init__(self):
        super().__init__(label="synthetic_sink", capabilities=io.AudioOutputCapabilities(pause=False), sample_rate=16000)
        self.frames = 0

    async def capture_frame(self, frame):
        await super().capture_frame(frame)
        self.frames += 1

    def flush(self):
        super().flush()
        self.on_playback_finished(playback_position=.1, interrupted=False)

    def clear_buffer(self):
        self.on_playback_finished(playback_position=0, interrupted=True)


def test_real_framework_user_tool_llm_tts_terminal_trace(monkeypatch):
    async def run():
        import worker.ssrf_guard as ssrf
        import worker.tools as tools
        from types import SimpleNamespace
        async def post(*args, **kwargs):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"success": True, "result": "synthetic hours"})
        async def client():
            return SimpleNamespace(post=post)
        monkeypatch.setattr(tools, "_shared_http_client", client)
        monkeypatch.setattr(ssrf, "prepare_tools_post_url", lambda url: (url, {}))
        monkeypatch.setenv("UVA_PUBLISH_TURN_LATENCY", "1")
        monkeypatch.setenv("UVA_LOG_TRANSCRIPTS", "0")
        userdata = AgentUserdata("synthetic_tenant", "synthetic_agent", "synthetic_room",
                                 tools_base_url="https://synthetic.example", tools_auth_secret="SECRET_SENTINEL")
        session = AgentSession(llm=SyntheticLLM(), tts=SyntheticTTS(), userdata=userdata)
        sink = SyntheticSink()
        session.output.audio = sink
        room, logger = MagicMock(), MagicMock()
        agent = Agent(instructions="synthetic test", tools=[lookup_business_info])
        tracker = wire_turn_latency(session, room, logger, agent=agent)
        userdata.latency_tracker = tracker
        await session.start(agent, record=False)
        try:
            handle = session.generate_reply(user_input="synthetic user turn")
            await asyncio.wait_for(handle.wait_for_playout(), timeout=5)
            await asyncio.sleep(0)
            assert handle.exception() is None
            assert sink.frames > 0
            assert tracker._tools["synthetic_call_1"]["outcome"] == "completed"
            assert tracker._tools["synthetic_call_1"]["duration_ms"] is not None
            rows = [json.loads(c.args[0]) for c in room.local_participant.publish_data.call_args_list if c.kwargs["topic"] == "turn_latency"]
            assert len(rows) == 1
            row = rows[0]
            assert row["user_turn_id"] is not None
            assert row["outcome"] == "completed"
            assert len(row["generations"]) == 2
            assert len(row["tools"]) == 1
            assert row["tools"][0]["generation_id"] == row["generations"][0]["generation_id"]
            assert row["stages"]["first_useful_llm_text"] is not None
            assert row["stages"]["tts_first_audio"] is not None
            assert "SECRET_SENTINEL" not in str(logger.info.call_args_list)
            assert "synthetic user turn" not in str(logger.info.call_args_list)
        finally:
            await session.aclose()
    asyncio.run(run())
