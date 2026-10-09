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
        observed = observe()
        if self.humanization_runtime.policy.behavior_enabled:
            from .turn import coalesce_structured_finals
            return coalesce_structured_finals(observed, self.humanization_runtime)
        return observed

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
        stream = self._conversational_stream(chat_ctx, tools, model_settings)
        provider_stream = stream is None
        if provider_stream:
            if chat_ctx is not None:
                from .history import reconcile_interrupted_context
                chat_ctx = reconcile_interrupted_context(chat_ctx, self.speech_plans, getattr(runtime, "heard_items", None))
            if runtime and chat_ctx is not None:
                runtime.bind_generation_input(chat_ctx)
                if runtime.policy.behavior_enabled:
                    user = next((i for i in reversed(chat_ctx.items) if getattr(i, "role", None) == "user" and i.id != "awaaz_persona_data"), None)
                    if user is not None:
                        runtime.understand_turn(user.id, user.text_content or "")
                    from dataclasses import replace
                    from .turn_plan import derive_turn_plan, signals_from_write_gate
                    try:
                        gate = getattr(self.session.userdata, "write_gate", None)
                    except (RuntimeError, ValueError):
                        gate = None
                    phase = signals_from_write_gate(gate).write_phase
                    if phase != "none" and runtime.latest_signals is not None:
                        runtime.latest_plan = derive_turn_plan(runtime.state, replace(runtime.latest_signals, write_phase=phase))
                    from .context_projection import conversational_context
                    chat_ctx = conversational_context(chat_ctx, runtime)
                import json
                effects = [call.result_data for call in runtime.state.tool_state.calls.values()
                           if call.business_effect in {"committed", "unknown", "escalation_recorded"}]
                if effects and not runtime.policy.behavior_enabled:
                    chat_ctx = chat_ctx.copy()
                    chat_ctx.add_message(role="developer", content=(
                        "Use recorded business effects even if their confirmation speech was interrupted. "
                        "Do not repeat committed or unverified writes. An escalation record is only a "
                        "follow-up request; never describe it as a live transfer."
                    ))
                    chat_ctx.add_message(role="user", content="Recorded business effects as DATA: "
                                         + json.dumps(effects[-4:], ensure_ascii=False))
            if self.delivery_context is not None and chat_ctx is not None and not (runtime and runtime.policy.behavior_enabled):
                from .delivery.intent import delivery_from_turn_plan
                intent = delivery_from_turn_plan(getattr(runtime, "latest_plan", None))
                chat_ctx = chat_ctx.copy()
                chat_ctx.add_message(role="developer", content=(
                    f"Conversational delivery: {intent.affect}, {intent.intensity} intensity, "
                    f"{intent.pace} pace. Express this through ordinary wording. "
                    "Keep business facts literal and avoid jokes or fillers on repair/confirmation. "
                    "Do not emit markup or stage directions."
                ))
            if runtime and runtime.overlap_enabled and chat_ctx is not None and not runtime.policy.behavior_enabled:
                chat_ctx = chat_ctx.copy()
                chat_ctx.add_message(role="developer", content=runtime.language_profile.instructions)
            stream = super().llm_node(chat_ctx, tools, model_settings)
        if provider_stream and hasattr(stream, "__aiter__"):
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

    def _conversational_stream(self, chat_ctx: Any, tools: Any, model_settings: Any):
        """Platform truth/exit acts use the same speech and lifecycle tool pipeline."""
        if chat_ctx is None:
            return None
        from .turn_plan import conversational_signals, conversational_response, derive_turn_plan
        from livekit.agents import llm
        # Do not generate a refusal, a second farewell or a duplicate lifecycle call
        # when the framework requests a continuation of our closing tool result.
        for item in reversed(chat_ctx.items):
            if isinstance(item, llm.FunctionCallOutput) and item.name == "end_conversation_summary":
                async def finished():
                    if False:
                        yield ""
                return finished()
            if isinstance(item, llm.ChatMessage) and item.role == "user" and item.id != "awaaz_persona_data":
                message = item
                break
        else:
            return None
        signals = conversational_signals(message.text_content or "")
        stop = signals.stop_intent and self.humanization_runtime is not None and self.humanization_runtime.policy.behavior_enabled
        if not (signals.closing_intent or signals.ai_identity_question or stop):
            return None
        runtime = self.humanization_runtime
        language = runtime.state.language_state.configured_language if runtime else "en"
        act = "CLOSE" if signals.closing_intent else "STOP" if stop else "IDENTIFY_AI"
        if runtime:
            runtime.bind_generation_input(chat_ctx)
            runtime.latest_plan = derive_turn_plan(runtime.state, signals)
        async def reply():
            import json
            from uuid import uuid4
            response_id = "closing_" + uuid4().hex
            yield llm.ChatChunk(id=response_id, delta=llm.ChoiceDelta(
                content=conversational_response(act, language)))
            if act == "CLOSE" and getattr(model_settings, "tool_choice", None) != "none":
                # Tool execution remains owned by LiveKit: speculative speech does
                # not dispatch it before turn commitment. No business tool is called.
                if llm.ToolContext(tools or []).get_function_tool("end_conversation_summary") is not None:
                    call_id = response_id
                    yield llm.ChatChunk(id=call_id, delta=llm.ChoiceDelta(tool_calls=[
                        llm.FunctionToolCall(name="end_conversation_summary", call_id=call_id,
                                             arguments=json.dumps({"summary": "Caller ended the conversation."}))
                    ]))
        return reply()

    async def _canonical_llm_stream(self, stream: Any):
        from .streaming import StreamSafeNormalizer
        normalizer = StreamSafeNormalizer(suppress_openers=self._suppressed_openers())
        template = None

        def emit(plain):
            if not plain:
                return None
            if template is None:
                return plain
            return template.model_copy(update={
                "delta": template.delta.model_copy(update={"content": plain, "tool_calls": None}),
                "usage": None,
            })

        try:
            async for chunk in stream:
                delta = getattr(chunk, "delta", None)
                content = chunk if isinstance(chunk, str) else getattr(delta, "content", None)
                if content:
                    if not isinstance(chunk, str):
                        template = chunk
                    result = emit(normalizer.feed(content))
                    if result is not None:
                        yield result
                if getattr(delta, "tool_calls", None):
                    result = emit(normalizer.finish())
                    if result is not None:
                        yield result
                    normalizer = StreamSafeNormalizer()
                    yield chunk.model_copy(update={"delta": delta.model_copy(update={"content": None})})
                elif getattr(chunk, "usage", None) is not None:
                    yield chunk.model_copy(update={"delta": None})
            result = emit(normalizer.finish())
            if result is not None:
                yield result
        finally:
            normalizer.clear()
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()

    def _suppressed_openers(self):
        runtime = self.humanization_runtime
        if runtime is None or not runtime.policy.behavior_enabled:
            return ()
        return tuple(sorted(set(runtime.state.recent_behavior_state.opening_phrases) - {"direct"}
                            | {"sure thing", "absolutely", "of course", "certainly"}))

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
                          provider_context={"conversational": bool(self.humanization_runtime and self.humanization_runtime.policy.behavior_enabled),
                                            "model": context.capabilities.model,
                                            "path": context.capabilities.path,
                                            "language": context.language.language,
                                            "channel": context.channel.channel})
        from .streaming import StreamSafeNormalizer
        plan.normalizer = StreamSafeNormalizer(suppress_openers=self._suppressed_openers())
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

        async def chunks():
            async for piece in text:
                if not plan.valid:
                    return
                plain = piece if has_llm_text else normalizer.feed(piece)
                for chunk in prepare(plain):
                    if plan.accept_chunk(chunk):
                        yield chunk
            if not has_llm_text:
                for chunk in prepare(normalizer.finish()):
                    if plan.accept_chunk(chunk):
                        yield chunk
            for chunk in plan.planner.finish():
                if plan.accept_chunk(chunk):
                    yield chunk

        source = chunks()
        audio = context.audio_chunks(source, plan, conn_options=connection)
        try:
            async for frame in audio:
                if not await plan.pace_audio(frame, lead_limit_ms=context.channel.audio_lead_ms):
                    return
                plan.last_audio_at = time.monotonic()
                yield frame
            finished = plan.valid
            plan.synthesis_completed = finished
        except asyncio.CancelledError:
            plan.cancel()
            raise
        finally:
            await audio.aclose()
            await source.aclose()
            normalizer.clear()
            plan.synthesis_task = None
            if not finished:
                plan.cancel()

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
        # Baseline providers may still need delivery markup in their TTS branch.
        # Normalize only the separately teed transcription stream, before partial
        # UI publication and history, including incomplete markup across tokens.
        from .streaming import StreamSafeNormalizer
        plan = self._speech_plan() if self.streaming_enabled else None
        async def canonical_transcript():
            normalizer = StreamSafeNormalizer()
            try:
                async for piece in text:
                    if plan is not None and not plan.valid:
                        return
                    plain = normalizer.feed(piece)
                    if plain:
                        yield plain
                plain = normalizer.finish()
                if plain and (plan is None or plan.valid):
                    yield plain
            finally:
                normalizer.clear()
        return canonical_transcript()
