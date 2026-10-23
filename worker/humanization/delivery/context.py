"""Session-scoped compiler and synthesis boundary, using existing provider adapters.

Batch B remains the rollback path. Streaming uses an exclusive client lease/context
across planned chunks; session reuse never mutates another generation's options.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from .canonical import canonical_spoken_text
from .capabilities import effective_options, resolve_capabilities
from .intent import DeliveryIntent, constrain_delivery, delivery_from_turn_plan
from .policy import DeliveryPolicy
from .pronunciation import plan_pronunciation
from .renderers import ChannelProfile, LanguageProfile, RenderedSpeech, render


class DeliveryContext:
    def __init__(self, cfg: Any, policy: DeliveryPolicy, *, runtime: Any = None, metrics_target: Any = None) -> None:
        self.cfg = replace(cfg, tts_options=deepcopy(cfg.tts_options), llm_options=deepcopy(cfg.llm_options))
        self.policy = policy
        from ..persona import profile_from_options
        self.persona_profile = profile_from_options(cfg.llm_options)
        self.runtime = runtime
        self.metrics_target = metrics_target
        self.effective = effective_options(
            cfg.tts_provider, cfg.tts_voice_id, cfg.agent_language,
            cfg.tts_options, cfg.audio_channel,
        )
        self.capabilities = resolve_capabilities(cfg.tts_provider, self.effective)
        self.language = LanguageProfile(cfg.agent_language)
        self.channel = ChannelProfile(cfg.audio_channel)
        self._client_pool = None

    def enable_session_reuse(self) -> None:
        """Enable only after the job has registered our shutdown callback.

        Cartesia clients are leased exclusively, never shared by concurrent
        generations. Their exact constructor options and tokenizer must match.
        """
        if self.cfg.tts_provider == 'cartesia' and self._client_pool is None:
            from .client_pool import DeliveryClientPool
            self._client_pool = DeliveryClientPool(max_idle=4)

    async def aclose(self, reason: str = '') -> None:
        if self._client_pool is not None:
            await self._client_pool.aclose()

    @staticmethod
    def _client_key(result, *, planned):
        import json
        return planned, json.dumps(result.provider_options, sort_keys=True, allow_nan=False)

    def prewarm_for_plan(self, speech_plan) -> None:
        """Open the actual delivery client's transport while the LLM is working.

        No speech text is sent. Exact options still govern the synthesis lease:
        a text-dependent renderer change uses a different client as usual.
        """
        if self._client_pool is None:
            return
        import logging
        from ..streaming import SpeechChunk
        try:
            result = self.render_chunk(SpeechChunk(0, 0, '', 'transport_prewarm'), speech_plan)
            key = self._client_key(result, planned=True)
            plugin, created = self._client_pool.prepare(key, lambda: self._plugin(result, planned=True))
            if plugin is None:
                return
            # This bounded hook retries preparation after a cancelled socket and
            # owns its task until client close. It does not synthesize audio.
            plugin.prepare_transport()
            logging.getLogger(__name__).debug('delivery transport prepare provider=cartesia created=%s', created)
        except Exception as exc:
            # Transport preparation must never prevent the real generation.
            logging.getLogger(__name__).warning('delivery transport prepare failed error_type=%s', type(exc).__name__)

    def _acquire_plugin(self, result, *, planned=False):
        if self._client_pool is None:
            return self._plugin(result, planned=planned), None
        import logging
        key = self._client_key(result, planned=planned)
        plugin, reused = self._client_pool.acquire(key, lambda: self._plugin(result, planned=planned))
        logging.getLogger(__name__).debug('delivery client provider=cartesia reused=%s planned=%s', reused, planned)
        return plugin, key

    async def _release_plugin(self, plugin, key, *, healthy):
        if key is None:
            await plugin.aclose()
        else:
            await self._client_pool.release(key, plugin, healthy=healthy)

    def compile(self, text: str, *, greeting: bool = False, disclosure: bool = False) -> RenderedSpeech:
        canonical = canonical_spoken_text(text)
        state = self.runtime.state if self.runtime is not None else None
        plan = getattr(self.runtime, "latest_plan", None)
        identity = state.speech_state.active_generation_id if state is not None else None
        intent = (
            DeliveryIntent(affect="neutral", interruptible=False, continuity_identity=identity)
            if disclosure else DeliveryIntent(affect="warm", speech_mode="greeting", continuity_identity=identity)
            if greeting else delivery_from_turn_plan(plan, continuity_identity=identity)
        )
        intent = constrain_delivery(intent, plan)
        from ..persona import personalize, clause_intent
        intent = clause_intent(personalize(intent, self.persona_profile, plan), canonical, self.persona_profile)
        pronunciation = plan_pronunciation(canonical, state=state, language=self.language.language)
        return render(
            canonical, intent, pronunciation, self.language, self.channel, self.capabilities,
            stored_options=self.cfg.tts_options, effective=self.effective,
        )

    async def audio(self, text: str, *, greeting: bool = False, disclosure: bool = False, conn_options=None):
        result = self.compile(text, greeting=greeting, disclosure=disclosure)
        audio = self._audio(result, conn_options=conn_options)
        try:
            async for frame in audio:
                yield frame
        finally:
            await audio.aclose()

    async def audio_chunk(self, chunk, speech_plan, *, conn_options=None):
        result = self.render_chunk(chunk, speech_plan)
        audio = self._audio(result, conn_options=conn_options)
        try:
            async for frame in audio:
                yield frame
        finally:
            await audio.aclose()

    def render_chunk(self, chunk, speech_plan):
        # Render offsets against the exact canonical chunk, with no second cleanup.
        from .pronunciation import PronunciationPlan
        pronunciation = PronunciationPlan(tuple(
            replace(span, start=span.start-chunk.start, end=span.end-chunk.start)
            for span in speech_plan.pronunciation_plan.spans
            if chunk.start <= span.start and span.end <= chunk.end
        ))
        intent = replace(speech_plan.delivery_intent, pauses=tuple(
            replace(pause, offset=pause.offset-chunk.start)
            for pause in speech_plan.delivery_intent.pauses
            if chunk.start <= pause.offset < chunk.end
        ))
        from ..persona import clause_intent
        intent = clause_intent(intent, chunk.text, self.persona_profile)
        return render(chunk.text, intent, pronunciation, self.language, self.channel,
                        self.capabilities, stored_options=self.cfg.tts_options, effective=self.effective)

    def _plugin(self, result, *, planned=False):
        from worker.providers.registry import _build_tts
        options = deepcopy(result.provider_options)
        if self.cfg.tts_provider != "uplift":
            options["model"] = self.capabilities.model
        if self.cfg.tts_provider == "uplift":
            from worker.providers.tts.uplift import build
            from .cache import rendered_audio_identity
            identity = rendered_audio_identity(
                "uplift", self.cfg.tts_voice_id, self.cfg.agent_language, options,
                self.cfg.audio_channel, policy_version=self.policy.version,
                renderer_version=self.policy.renderer_version,
                pronunciation_version=self.policy.pronunciation_version,
                humanization=self.cfg.llm_options.get("humanization"),
            )
            plugin = build(self.cfg.tts_voice_id, rendered_identity=identity)
        else:
            if planned:
                from ..streaming import PlannedChunkTokenizer
                plugin = _build_tts(replace(self.cfg, tts_options=options), tokenizer=PlannedChunkTokenizer())
            else:
                plugin = _build_tts(replace(self.cfg, tts_options=options))
        if self.metrics_target is not None:
            plugin.on("metrics_collected", lambda event: self.metrics_target.emit("metrics_collected", event))
            plugin.on("error", lambda event: self.metrics_target.emit("error", event))
        return plugin

    async def audio_chunks(self, chunks, speech_plan, *, conn_options=None):
        """One exclusive client lease and native context per speech generation.

        Uplift 1.6.5 ends its AudioEmitter per segment, so it retains per-segment streams
        on the SAME client. No private vendor APIs, per-session mutation or tool cancellation.
        """
        import asyncio
        import time
        from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
        connection = conn_options or DEFAULT_API_CONNECT_OPTIONS
        first = await anext(chunks, None)
        if first is None or not speech_plan.valid:
            return
        result = self.render_chunk(first, speech_plan)
        plugin, lease_key = self._acquire_plugin(result, planned=True)
        healthy = False
        speech_plan.provider_context["lifecycle"] = "generation_plugin"
        continuous = plugin.capabilities.streaming and self.cfg.tts_provider != "uplift"
        try:
            if not continuous:
                chunk = first
                while chunk is not None and speech_plan.valid:
                    rendered = self.render_chunk(chunk, speech_plan)
                    if plugin.capabilities.streaming:
                        output = plugin.stream(conn_options=connection)
                        output.push_text(rendered.provider_text)
                        output.end_input()
                    else:
                        output = plugin.synthesize(rendered.provider_text, conn_options=connection)
                    try:
                        async for event in output:
                            if not speech_plan.valid:
                                return
                            yield event.frame
                    finally:
                        await output.aclose()
                    chunk = await anext(chunks, None)
                healthy = speech_plan.valid
                return

            speech_plan.provider_context["lifecycle"] = "generation_stream"
            async with plugin.stream(conn_options=connection) as output:
                condition = asyncio.Condition()
                produced_ms = 0.0
                audio_started_at = None
                last_audio_at = None
                stopped = False

                async def feed():
                    chunk = first
                    batch_chars = 0
                    batch_audio_start = 0.0
                    try:
                        while chunk is not None and speech_plan.valid:
                            if batch_chars > 240:
                                # Bound native synthesis input by complete chunks. Wait for an
                                # observed output-idle boundary, not guessed character/audio alignment.
                                # Paced handoff duration is local evidence, never caller-heard time.
                                async with condition:
                                    while not stopped and speech_plan.valid:
                                        now = time.monotonic()
                                        lead = max(0, produced_ms - (now-audio_started_at)*1000) if audio_started_at else 0
                                        idle = last_audio_at is not None and now-last_audio_at >= .15
                                        if produced_ms > batch_audio_start and idle and lead <= 2000:
                                            break
                                        try:
                                            await asyncio.wait_for(condition.wait(), .15)
                                        except asyncio.TimeoutError:
                                            pass
                                batch_chars = 0
                                batch_audio_start = produced_ms
                            if stopped or not speech_plan.valid:
                                return
                            rendered = self.render_chunk(chunk, speech_plan)
                            output.push_text(rendered.provider_text)
                            # PlannedChunkTokenizer emits immediately without ending the SDK segment.
                            batch_chars += len(chunk.text)
                            chunk = await anext(chunks, None)
                        output.end_input()
                    except BaseException:
                        await output.aclose()
                        raise

                feeder = asyncio.create_task(feed())
                try:
                    async for event in output:
                        if not speech_plan.valid:
                            return
                        # Advance only after the consumer's paced audio handoff resumes.
                        yield event.frame
                        async with condition:
                            if audio_started_at is None:
                                audio_started_at = time.monotonic()
                            last_audio_at = time.monotonic()
                            produced_ms += event.frame.duration * 1000
                            condition.notify_all()
                    if not feeder.done():
                        raise RuntimeError("provider stream ended before speech input completed")
                    await feeder
                finally:
                    stopped = True
                    async with condition:
                        condition.notify_all()
                    if not feeder.done():
                        feeder.cancel()
                    await asyncio.gather(feeder, return_exceptions=True)
                    speech_plan.provider_context["stream_closed_at"] = time.monotonic()
            healthy = speech_plan.valid
        finally:
            await self._release_plugin(plugin, lease_key, healthy=healthy)

    async def _audio(self, result: RenderedSpeech, *, conn_options=None):
        from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
        if not result.canonical_text:
            return
        plugin, lease_key = self._acquire_plugin(result)
        healthy = False
        connection = conn_options or DEFAULT_API_CONNECT_OPTIONS
        try:
            if plugin.capabilities.streaming:
                async with plugin.stream(conn_options=connection) as stream:
                    stream.push_text(result.provider_text)
                    stream.end_input()
                    async for event in stream:
                        yield event.frame
            else:
                async with plugin.synthesize(result.provider_text, conn_options=connection) as stream:
                    async for event in stream:
                        yield event.frame
            healthy = True
        finally:
            await self._release_plugin(plugin, lease_key, healthy=healthy)
