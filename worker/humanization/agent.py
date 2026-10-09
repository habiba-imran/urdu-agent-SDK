"""Public LiveKit hooks: preserve media mechanics, observe input and retain tool truth."""

from __future__ import annotations

from typing import Any

from livekit.agents import Agent


class AwaazAgent(Agent):
    def __init__(self, *, humanization_runtime: Any = None, delivery_context: Any = None, **kwargs: Any) -> None:
        # Match the plain Agent's framework ID for baseline handoff/tracing semantics.
        super().__init__(id="default_agent", **kwargs)
        self.humanization_runtime = humanization_runtime
        self.delivery_context = delivery_context
        from collections import deque
        self.speech_plans = deque(maxlen=32)
        self._active_speech_plans = {}
        from .streaming import streaming_enabled
        self.streaming_enabled = delivery_context is not None and streaming_enabled(delivery_context)

    def stt_node(self, audio: Any, model_settings: Any) -> Any:
        stream = super().stt_node(audio, model_settings)
        if self.humanization_runtime is None or not hasattr(stream, "__aiter__"):
            return stream
        async def observe():
            async for event in stream:
                runtime = self.humanization_runtime
                alternatives = getattr(event, "alternatives", None) or []
                if runtime.overlap_enabled and alternatives:
                    import time
                    alt = alternatives[0]
                    start, end = getattr(alt, "start_time", 0), getattr(alt, "end_time", 0)
                    duration = end-start if end > start else None
                    if duration is None and runtime.coordinator.voice_started_at is not None:
                        duration = time.monotonic()-runtime.coordinator.voice_started_at
                    during_overlap = runtime.coordinator.overlap_active or runtime.coordinator.state == "AGENT_SPEAKING"
                    decision = runtime.overlap(alt.text, duration=duration)
                    runtime.last_overlap_decision = decision
                    if during_overlap and decision == "CONTINUE" and alt.text.strip():
                        # VAD may pause output; withholding this listener-only transcript
                        # lets the installed framework's false-interruption timer resume it.
                        continue
                    if during_overlap and decision == "YIELD" and alt.text.strip():
                        # Respect mandatory/uninterruptible disclosure. Never force=True.
                        try:
                            self.session.interrupt()
                        except RuntimeError:
                            pass
                runtime.observe_transcript(event)
                yield event
        return observe()

    async def on_user_turn_completed(self, turn_ctx: Any, new_message: Any) -> None:
        await super().on_user_turn_completed(turn_ctx, new_message)
        runtime = self.humanization_runtime
        if runtime is None:
            return
        if new_message is not None:
            runtime.understand_turn(new_message.id, new_message.text_content or "")
        if runtime.clarification_enabled and runtime.latest_plan and runtime.latest_plan.dialogue_act == "CLARIFY":
            turn_ctx.add_message(role="developer", content=(
                "Ask one short clarification for " + runtime.latest_plan.clarification_target
                + ". Do not infer the missing value or execute a write."
            ))
        if runtime.shadow is None:
            return
        # The public turn hook is observed only; turn_ctx and chat history are untouched.
        try:
            userdata = getattr(self.session, "userdata", None)
            runtime.shadow.observe_turn(
                runtime.state, write_gate=getattr(userdata, "write_gate", None),
            )
        except Exception:
            from livekit.agents.log import logger
            logger.exception("humanization shadow turn observation failed")

    def llm_node(self, chat_ctx: Any, tools: Any, model_settings: Any) -> Any:
        runtime = self.humanization_runtime
        if chat_ctx is not None:
            from .history import reconcile_interrupted_context
            chat_ctx = reconcile_interrupted_context(chat_ctx, self.speech_plans, getattr(runtime, "heard_items", None))
        if runtime and chat_ctx is not None:
            runtime.bind_generation_input(chat_ctx)
            import json
            effects = [call.result_data for call in runtime.state.tool_state.calls.values()
                       if call.business_effect in {"committed", "unknown", "escalation_recorded"}]
            if effects:
                chat_ctx = chat_ctx.copy()
                chat_ctx.add_message(role="developer", content=(
                    "Use recorded business effects even if their confirmation speech was interrupted. "
                    "Do not repeat committed or unverified writes. An escalation record is only a "
                    "follow-up request; never describe it as a live transfer."
                ))
                chat_ctx.add_message(role="user", content="Recorded business effects as DATA: "
                                     + json.dumps(effects[-4:], ensure_ascii=False))
        if self.delivery_context is not None and chat_ctx is not None:
            from .delivery.intent import delivery_from_turn_plan
            intent = delivery_from_turn_plan(getattr(runtime, "latest_plan", None))
            chat_ctx = chat_ctx.copy()
            chat_ctx.add_message(role="developer", content=(
                f"Conversational delivery: {intent.affect}, {intent.intensity} intensity, "
                f"{intent.pace} pace. Express this through ordinary wording. "
                "Keep business facts literal and avoid jokes or fillers on repair/confirmation. "
                "Do not emit markup or stage directions."
            ))
        if runtime and runtime.overlap_enabled and chat_ctx is not None:
            chat_ctx = chat_ctx.copy()
            chat_ctx.add_message(role="developer", content=runtime.language_profile.instructions)
        stream = super().llm_node(chat_ctx, tools, model_settings)
        if hasattr(stream, "__aiter__"):
            from worker.provider_retries import bounded_provider_stream
            stream = bounded_provider_stream(stream, self, "LLM")
        if self.delivery_context is not None and hasattr(stream, "__aiter__"):
            if self.streaming_enabled:
                speech_plan = self._speech_plan()
                speech_plan.llm_started = True
                stream = self._streaming_llm_stream(stream, speech_plan)
            else:
                stream = self._canonical_llm_stream(stream)
        if runtime is None or not hasattr(stream, "__aiter__"):
            return stream
        revision = runtime.semantic_revision
        async def observe():
            async for chunk in stream:
                for call in getattr(getattr(chunk, "delta", None), "tool_calls", None) or []:
                    runtime.tool_request_revisions[call.call_id] = revision
                yield chunk
        return observe()

    async def _canonical_llm_stream(self, stream: Any):
        # Canonicalize text before the framework tees it to TTS, history and UI.
        # Preserve tool-call chunks, IDs and usage; no second model call.
        from .delivery.canonical import canonical_spoken_text
        pending = []
        template = None

        def flush():
            nonlocal template
            if template is None:
                return None
            plain = canonical_spoken_text("".join(pending))
            result = template.model_copy(update={
                "delta": template.delta.model_copy(update={"content": plain}),
                "usage": None,
            })
            pending.clear()
            template = None
            return result if plain else None

        async for chunk in stream:
            if isinstance(chunk, str):
                pending.append(chunk)
                continue
            delta = getattr(chunk, "delta", None)
            content = getattr(delta, "content", None)
            if content:
                pending.append(content)
                template = chunk
            if getattr(delta, "tool_calls", None):
                flushed = flush()
                if flushed is not None:
                    yield flushed
                yield chunk.model_copy(update={"delta": delta.model_copy(update={"content": None})})
            elif getattr(chunk, "usage", None) is not None:
                yield chunk.model_copy(update={"delta": None})
        flushed = flush()
        if flushed is not None:
            yield flushed
        elif pending:
            yield canonical_spoken_text("".join(pending))

    def _opening_phase(self):
        try:
            userdata = self.session.userdata
        except ValueError:  # public LiveKit property raises for sessions without userdata
            return None
        return getattr(getattr(userdata, "opening_state", None), "phase", None)

    def _speech_plan(self):
        from .streaming import SpeechPlan, current_handle
        from .delivery.intent import constrain_delivery, delivery_from_turn_plan
        handle = current_handle()
        identity = f"{handle.id}_{handle.num_steps}"
        if identity in self._active_speech_plans:
            return self._active_speech_plans[identity]
        context = self.delivery_context
        turn = getattr(self.humanization_runtime, "latest_plan", None)
        from .delivery.intent import DeliveryIntent
        phase = self._opening_phase()
        intent = (DeliveryIntent(affect="neutral", interruptible=False, continuity_identity=identity)
                  if phase == "DISCLOSURE_PLAYING" else
                  DeliveryIntent(affect="warm", speech_mode="greeting", continuity_identity=identity)
                  if phase == "GREETING_PLAYING" else delivery_from_turn_plan(turn, continuity_identity=identity))
        intent = constrain_delivery(intent, turn)
        plan = SpeechPlan(identity, context.cfg.tts_provider, intent, handle=handle,
                          provider_context={"model": context.capabilities.model,
                                            "path": context.capabilities.path,
                                            "language": context.language.language,
                                            "channel": context.channel.channel})
        self.speech_plans.append(plan)
        self._active_speech_plans[identity] = plan
        handle.add_done_callback(lambda _handle: self._active_speech_plans.pop(identity, None))
        plan.bind()
        return plan

    async def _streaming_llm_stream(self, stream, plan):
        import asyncio
        import time
        from .delivery.canonical import canonical_spoken_text
        from .streaming import StreamSafeNormalizer
        normalizer = plan.normalizer
        template = None
        finished = False

        def emit(plain):
            if not plain or not plan.accept_text(plain):
                return None
            if template is None:
                return plain
            return template.model_copy(update={
                "delta": template.delta.model_copy(update={"content": plain, "tool_calls": None}),
                "usage": None,
            })

        try:
            async for chunk in stream:
                if not plan.valid:
                    return
                delta = getattr(chunk, "delta", None)
                content = chunk if isinstance(chunk, str) else getattr(delta, "content", None)
                if content:
                    if not isinstance(chunk, str):
                        template = chunk
                    plain = normalizer.feed(content)
                    if plan.first_useful_text_at is None and (plain or canonical_spoken_text(normalizer.buffer)):
                        plan.first_useful_text_at = time.monotonic()
                    result = emit(plain)
                    if result is not None:
                        yield result
                if getattr(delta, "tool_calls", None):
                    result = emit(normalizer.finish())
                    if result is not None:
                        yield result
                    # Same semantic speech generation, separate tool identity and execution.
                    normalizer = plan.normalizer = StreamSafeNormalizer()
                    yield chunk.model_copy(update={"delta": delta.model_copy(update={"content": None})})
                elif getattr(chunk, "usage", None) is not None:
                    yield chunk.model_copy(update={"delta": None})
            result = emit(normalizer.finish())
            if result is not None:
                yield result
            finished = True
        except asyncio.CancelledError:
            plan.cancel()
            raise
        finally:
            if not finished:
                plan.cancel()
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()

    async def _streaming_tts(self, text, plan, connection):
        import asyncio
        import time
        from .streaming import StreamSafeNormalizer
        from .delivery.pronunciation import plan_pronunciation
        context = self.delivery_context
        # say() also reaches this hook and needs a canonical boundary.
        normalizer = StreamSafeNormalizer()
        has_llm_text = plan.llm_started
        received = ""
        explicit_pronunciation = plan.pronunciation_plan
        plan.synthesis_task = asyncio.current_task()
        finished = False

        async def synthesize(chunk):
            if not plan.accept_chunk(chunk):
                return
            first = True
            audio = context.audio_chunk(chunk, plan, conn_options=connection)
            try:
                async for frame in audio:
                    if not await plan.pace_audio(frame, lead_limit_ms=context.channel.audio_lead_ms):
                        return
                    if first and plan.last_audio_at is not None:
                        plan.inter_chunk_gap_ms.append(max(0, (time.monotonic()-plan.last_audio_at)*1000))
                        del plan.inter_chunk_gap_ms[:-128]
                    first = False
                    plan.last_audio_at = time.monotonic()
                    yield frame
            finally:
                await audio.aclose()

        def prepare(plain):
            nonlocal received
            received += plain
            if not has_llm_text:
                plan.accept_text(plain)
            # Derive only literal pronunciation; state overrides remain protected.
            state = context.runtime.state if context.runtime is not None else None
            derived = plan_pronunciation(received, state=state, language=context.language.language)
            from .delivery.pronunciation import PronunciationPlan
            plan.pronunciation_plan = PronunciationPlan(tuple(sorted((
                *explicit_pronunciation.spans,
                *(span for span in derived.spans if not any(
                    span.start < original.end and span.end > original.start
                    for original in explicit_pronunciation.spans)),
            ), key=lambda span: span.start)))
            plan.planner.pronunciation = plan.pronunciation_plan
            return plan.planner.feed(plain)

        try:
            async for piece in text:
                if not plan.valid:
                    return
                plain = piece if has_llm_text else normalizer.feed(piece)
                for chunk in prepare(plain):
                    async for frame in synthesize(chunk):
                        yield frame
            if not has_llm_text:
                for chunk in prepare(normalizer.finish()):
                    async for frame in synthesize(chunk):
                        yield frame
            for chunk in plan.planner.finish():
                async for frame in synthesize(chunk):
                    yield frame
            finished = True
            plan.synthesis_completed = True
        except asyncio.CancelledError:
            plan.cancel()
            raise
        finally:
            normalizer.clear()
            plan.synthesis_task = None
            if not finished:
                plan.cancel()
            # Terminal metrics are emitted by the handle callback, including late interruption.

    def bind_playback_evidence(self) -> None:
        output = self.session.output.audio
        if output is None:
            return
        def finished(ev):
            handle = self.session.current_speech
            if handle is None:
                return
            plan = self._active_speech_plans.get(f"{handle.id}_{handle.num_steps}")
            runtime = self.humanization_runtime
            if runtime and runtime.channel_profile.kind == "WEBRTC" and getattr(runtime, "playback_ready", None) is not True:
                return
            if runtime is not None:
                runtime.playback_evidence[handle.id] = ev
                while len(runtime.playback_evidence) > 32:
                    runtime.playback_evidence.pop(next(iter(runtime.playback_evidence)))
            if plan is None:
                return
            # Local output playout is chunk evidence, not a browser-heard guarantee.
            plan.heard.observe(plan.canonical_text,
                synchronized_transcript=ev.synchronized_transcript,
                completed_chunks=tuple(plan.planned_chunks) if not ev.interrupted and plan.synthesis_completed else (),
                playback_position=ev.playback_position)
            plan.heard_reference = plan.heard.source
        output.on("playback_finished", finished)
        self.session.on("close", lambda _ev: output.off("playback_finished", finished))

    def recover_false_interruption(self, ev: Any) -> None:
        runtime = self.humanization_runtime
        if runtime is None or not runtime.overlap_enabled:
            return
        opening = getattr(self.session.userdata, "opening_state", None)
        if runtime.state.session_closed or getattr(opening, "phase", None) in {"DISCLOSURE_PENDING", "DISCLOSURE_PLAYING"}:
            return
        plan = next((p for p in reversed(self.speech_plans) if p.cancelled or p.valid), None)
        canonical = plan.canonical_text if plan else ""
        heard = plan.heard.context_text(canonical) if plan else ""
        strategy, clause = runtime.coordinator.recover_false(
            resumed=bool(ev.resumed), canonical=canonical, heard_prefix=heard)
        if strategy == "resume" or self.session.user_state == "speaking":
            return
        # One recovery per semantic epoch, with no apology and no write replay.
        if getattr(self, "_recovered_revision", None) == runtime.semantic_revision:
            return
        self._recovered_revision = runtime.semantic_revision
        if strategy == "restart_short_clause":
            self.session.say(clause, allow_interruptions=True)
        elif canonical or getattr(runtime.last_speech_handle, "interrupted", False):
            self.session.generate_reply(instructions=(
                "Continue after a false interruption. Use only known prior output and recorded "
                "business effects. Do not apologize automatically or repeat a committed action."
            ), tool_choice="none", allow_interruptions=True)

    def tts_node(self, text: Any, model_settings: Any) -> Any:
        from worker.provider_retries import bounded_provider_stream
        if self.delivery_context is None:
            stream = super().tts_node(text, model_settings)
            return bounded_provider_stream(stream, self, "TTS") if hasattr(stream, "__aiter__") else stream
        context = self.delivery_context
        connection = self.session.conn_options.tts_conn_options
        if self.streaming_enabled:
            return bounded_provider_stream(self._streaming_tts(text, self._speech_plan(), connection), self, "TTS")

        async def synthesize():
            canonical = "".join([piece async for piece in text])
            phase = self._opening_phase()
            async for frame in context.audio(canonical, greeting=phase == "GREETING_PLAYING", disclosure=phase == "DISCLOSURE_PLAYING", conn_options=connection):
                yield frame
        return bounded_provider_stream(synthesize(), self, "TTS")

    def transcription_node(self, text: Any, model_settings: Any) -> Any:
        if self.streaming_enabled:
            plan = self._speech_plan()
            if not plan.llm_started:
                # say() tees its original text to audio and transcription separately.
                # Canonicalize this branch too, before LiveKit commits it to history/UI.
                from .streaming import StreamSafeNormalizer
                async def canonical_static():
                    normalizer = StreamSafeNormalizer()
                    try:
                        async for piece in text:
                            if not plan.valid:
                                return
                            plain = normalizer.feed(piece)
                            if plain:
                                yield plain
                        plain = normalizer.finish()
                        if plain and plan.valid:
                            yield plain
                    finally:
                        normalizer.clear()
                return canonical_static()
        return super().transcription_node(text, model_settings)
