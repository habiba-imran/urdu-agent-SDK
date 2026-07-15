"""Mic-less pipeline harness: the REAL bot pipeline with audio fed programmatically.

Replaces only the WebRTC transport with an in-process source/sink; everything else
(VAD, Groq STT, LLM switcher, sanitizer, Uplift TTS, aggregators, observer) is the
same as production. The sink emulates a transport's Bot(Started|Stopped)SpeakingFrame
signaling so turn strategies and the metrics observer behave exactly as they do live.
"""

import asyncio
import os
import sys
import time
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from loguru import logger

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    ErrorFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    LLMTextFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.worker import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

import bot as bot_module
import config
import db
import persona
import tools as tz_tools
from processors import InputGuard, OutputSanitizer, TurnMetricsObserver
from services.uplift_tts import UpliftTTSService
from session_state import SessionState


class LLMTextTap(FrameProcessor):
    """Records the full sanitized LLM output (pre-TTS) per response."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.responses: list[str] = []
        self._current = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame) and not getattr(frame, "skip_tts", False):
            self._current += frame.text
        from pipecat.frames.frames import (
            LLMFullResponseEndFrame,
            LLMFullResponseStartFrame,
        )

        if isinstance(frame, LLMFullResponseStartFrame):
            self._current = ""
        elif isinstance(frame, LLMFullResponseEndFrame) and self._current.strip():
            self.responses.append(self._current.strip())
        await self.push_frame(frame, direction)


class QuotaErrorWatcher(BaseObserver):
    """Records when a provider 429/quota error crosses the pipeline (v4 A.3).

    The latency harness uses these timestamps to mark turns as quota-excluded:
    a 429 measures the provider's free-tier rate limiter, not the pipeline.
    """

    def __init__(self):
        super().__init__()
        self.times: list[float] = []
        self._seen: set[int] = set()

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        if frame.id in self._seen:
            return
        self._seen.add(frame.id)
        if isinstance(frame, ErrorFrame):
            msg = str(getattr(frame, "error", "")).lower()
            if (
                "429" in msg
                or "quota" in msg
                or "too_many_requests" in msg
                or "rate limit" in msg
            ):
                self.times.append(time.monotonic())


class TransportSink(FrameProcessor):
    """Absorbs bot audio like an output transport: emits Bot*SpeakingFrames and
    paces audio at real time, so downstream frames (TTSTextFrame → assistant
    aggregator) are released in playback order exactly like a live transport.
    InterruptionFrames are system frames: they bypass the queue and clear it,
    which drops unplayed audio + unspoken text — same as production."""

    def __init__(self, *, pace_audio: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.pace_audio = pace_audio
        self.audio = bytearray()
        self.last_audio_at: float | None = None
        self.first_audio_at: float | None = None
        self.bot_speaking = False
        self.turn_done = asyncio.Event()
        self.interrupted_at: float | None = None
        self.text_log: list[
            tuple[float, str]
        ] = []  # (time, sentence) released downstream

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        from pipecat.frames.frames import TTSTextFrame

        if isinstance(frame, TTSTextFrame) and frame.text:
            self.text_log.append((time.monotonic(), frame.text))
        if isinstance(frame, TTSAudioRawFrame):
            now = time.monotonic()
            self.last_audio_at = now
            if self.first_audio_at is None:
                self.first_audio_at = now
            self.audio.extend(frame.audio)
            if not self.bot_speaking:
                self.bot_speaking = True
                await self.push_frame(
                    BotStartedSpeakingFrame(), FrameDirection.UPSTREAM
                )
                await self.push_frame(
                    BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM
                )
            await self.push_frame(frame, direction)
            if self.pace_audio:
                await asyncio.sleep(len(frame.audio) / 2 / max(frame.sample_rate, 1))
            return
        elif isinstance(frame, TTSStoppedFrame):
            if self.bot_speaking:
                self.bot_speaking = False
                await self.push_frame(
                    BotStoppedSpeakingFrame(), FrameDirection.UPSTREAM
                )
                await self.push_frame(
                    BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM
                )
            self.turn_done.set()
        elif isinstance(frame, InterruptionFrame):
            self.interrupted_at = time.monotonic()
            if self.bot_speaking:
                self.bot_speaking = False
        await self.push_frame(frame, direction)

    def reset_turn(self):
        self.turn_done.clear()
        self.first_audio_at = None
        self.interrupted_at = None

    def played_ms(self) -> float:
        return len(self.audio) / 2 / 22.05  # ms of 22.05kHz mono s16 audio


class PipelineHarness:
    def __init__(
        self,
        turn_stop_mode: str | None = None,
        llm_provider: str | None = None,
        vad_stop_secs: float | None = None,
        stt_provider: str | None = None,
    ):
        # snapshot config so back-to-back harnesses in one process don't leak
        # overrides into each other (restored in stop())
        self._config_snapshot = {
            "TURN_STOP_MODE": config.TURN_STOP_MODE,
            "LLM_PROVIDER": config.LLM_PROVIDER,
            "VAD_STOP_SECS": config.VAD_STOP_SECS,
            "STT_PROVIDER": config.STT_PROVIDER,
        }
        if turn_stop_mode:
            config.TURN_STOP_MODE = turn_stop_mode
        if llm_provider:
            config.LLM_PROVIDER = llm_provider
        if vad_stop_secs:
            config.VAD_STOP_SECS = vad_stop_secs
        if stt_provider:
            config.STT_PROVIDER = stt_provider

        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.audio.vad.vad_analyzer import VADParams
        from pipecat.pipeline.llm_switcher import LLMSwitcher
        from pipecat.pipeline.service_switcher import ServiceSwitcherStrategyFailover
        from pipecat.processors.aggregators.llm_context import LLMContext
        from pipecat.processors.aggregators.llm_response_universal import (
            LLMContextAggregatorPair,
            LLMUserAggregatorParams,
        )
        from pipecat.processors.audio.vad_processor import VADProcessor

        self.session = SessionState()
        self.sink = TransportSink()
        self.tap = LLMTextTap()

        vad = VADProcessor(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=config.VAD_CONFIDENCE,
                    start_secs=config.VAD_START_SECS,
                    stop_secs=config.VAD_STOP_SECS,
                    min_volume=config.VAD_MIN_VOLUME,
                )
            )
        )
        stt, _stt_services = bot_module.build_stt()  # v5: (stage, services) tuple
        llms = bot_module.build_llms(self.session)
        self._llms = llms

        # Speak-during-function-call fillers, exactly as bot.py wires them (v4
        # early trigger): the filler IS the agent's first audio on tool turns.
        sanitizer = OutputSanitizer()
        bot_module.wire_tool_fillers(llms, sanitizer)
        switcher = LLMSwitcher(llms=llms, strategy_type=ServiceSwitcherStrategyFailover)
        self.tts = UpliftTTSService(
            api_key=config.UPLIFTAI_API_KEY,
            voice_id=config.UPLIFT_VOICE_ID,
            phrase_replacement_config_id=config.UPLIFT_PHRASE_CONFIG_ID,
            # v3 humanness: greeting + fillers replay from a startup PCM cache
            cached_phrases=[persona.GREETING, *persona.TOOL_FILLERS],
        )
        context = LLMContext(
            messages=[{"role": "system", "content": persona.SYSTEM_PROMPT}],
            tools=tz_tools.build_tools_schema(),
        )
        self.context = context
        from pipecat.processors.aggregators.llm_response_universal import (
            LLMAssistantAggregatorParams,
        )
        from pipecat.utils.context.llm_context_summarization import (
            LLMAutoContextSummarizationConfig,
        )

        turn_strategies = bot_module.build_turn_strategies()
        aggregators = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(user_turn_strategies=turn_strategies),
            assistant_params=LLMAssistantAggregatorParams(
                enable_auto_context_summarization=True,
                auto_context_summarization_config=LLMAutoContextSummarizationConfig(
                    max_context_tokens=1200,
                    max_unsummarized_messages=20,
                ),
            ),
        )
        self.observer = TurnMetricsObserver(self.session)
        self.quota_watcher = QuotaErrorWatcher()
        self._observers = [self.observer, self.quota_watcher]
        from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy

        if isinstance(turn_strategies.stop[0], SpeechTimeoutUserTurnStopStrategy):
            from processors import NumberDictationPatience

            self._observers.append(NumberDictationPatience(turn_strategies.stop[0]))

        # Failover retrigger, as in production: after a provider switch the
        # interrupted inference is re-run (rate-limited against ping-pong).
        from pipecat.frames.frames import LLMRunFrame

        retrigger_times: list[float] = []

        @switcher.strategy.event_handler("on_service_switched")
        async def on_service_switched(strategy, service):
            logger.warning(f"harness: LLM FAILOVER → {service.name}")
            self.session.llm_failovers += 1
            now = time.monotonic()
            retrigger_times[:] = [t for t in retrigger_times if now - t < 30]
            if len(retrigger_times) < 4:
                retrigger_times.append(now)
                await self.task.queue_frame(LLMRunFrame())

        from processors import InterimPromoter

        stt_stages = [vad, stt]
        if config.STT_PROVIDER == "gladia":
            stt_stages.append(InterimPromoter())
        pipeline = Pipeline(
            [
                *stt_stages,
                InputGuard(),
                aggregators.user(),
                switcher,
                sanitizer,
                self.tap,
                self.tts,
                self.sink,
                aggregators.assistant(),
            ]
        )
        self.task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=config.AUDIO_IN_SAMPLE_RATE,
                audio_out_sample_rate=config.AUDIO_OUT_SAMPLE_RATE,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            observers=self._observers,
            idle_timeout_secs=None,
            check_dangling_tasks=False,
            # no RTVI client in the harness; also avoids a pipecat 1.4.0 crash
            # serializing smart-turn TurnMetricsData in the RTVI observer
            enable_rtvi=False,
        )
        self.runner = PipelineRunner(handle_sigint=False)
        self._runner_task: asyncio.Task | None = None

    async def start(self):
        db.record_conversation_start(
            self.session.conversation_id, channel="latency-test"
        )
        self._runner_task = asyncio.create_task(self.runner.run(self.task))
        # pre-warm the primary LLM (mirrors bot.py's prewarm at client connect)
        try:
            from pipecat.services.google.llm import GoogleLLMService

            llm = self._llms[0]
            if isinstance(llm, GoogleLLMService):
                await llm._client.aio.models.generate_content(
                    model=config.GEMINI_LLM_MODEL,
                    contents="ok",
                    config={
                        "max_output_tokens": 1,
                        "thinking_config": {"thinking_budget": 0},
                    },
                )
            else:  # OpenAI-compatible services (Cerebras, Groq) via their own client
                await llm._client.chat.completions.create(
                    model=llm._settings.model,
                    messages=[{"role": "user", "content": "ok"}],
                    max_completion_tokens=1,
                )
        except Exception as e:
            logger.debug(f"harness LLM prewarm failed (non-fatal): {e}")
        await asyncio.sleep(2.5)  # pipeline + STT/TTS socket warm-up

    async def stop(self):
        await self.task.cancel()
        if self._runner_task:
            try:
                await asyncio.wait_for(self._runner_task, timeout=10)
            except asyncio.TimeoutError:
                pass
        for key, value in self._config_snapshot.items():
            setattr(config, key, value)

    async def feed_wav(self, wav_bytes: bytes, realtime: bool = False):
        """Push a 16 kHz WAV into the pipeline as InputAudioRawFrames + trailing silence."""
        with wave.open(__import__("io").BytesIO(wav_bytes), "rb") as w:
            rate = w.getframerate()
            pcm = w.readframes(w.getnframes())
        chunk = int(rate * 0.02) * 2  # 20 ms
        for i in range(0, len(pcm), chunk):
            await self.task.queue_frame(
                InputAudioRawFrame(
                    audio=pcm[i : i + chunk], sample_rate=rate, num_channels=1
                )
            )
            if realtime:
                await asyncio.sleep(0.018)
        silence = b"\x00" * chunk
        for _ in range(int((config.VAD_STOP_SECS + 0.7) / 0.02)):
            await self.task.queue_frame(
                InputAudioRawFrame(audio=silence, sample_rate=rate, num_channels=1)
            )
            if realtime:
                await asyncio.sleep(0.018)

    async def user_turn(
        self, wav_bytes: bytes, timeout: float = 45.0, realtime: bool = True
    ) -> bool:
        """Feed one user utterance and wait for the bot's spoken reply to finish.

        realtime=True paces the audio like a live mic — required for honest
        measurements with streaming STT (Gladia transcribes while audio flows).
        """
        self.sink.reset_turn()
        await self.feed_wav(wav_bytes, realtime=realtime)
        try:
            await asyncio.wait_for(self.sink.turn_done.wait(), timeout=timeout)
            self.observer._flush_bot_text()
            self.observer._flush_row(interrupted=False)
            return True
        except asyncio.TimeoutError:
            logger.warning("user_turn: timed out waiting for bot reply")
            return False
