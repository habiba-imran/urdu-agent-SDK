"""Session-scoped compiler and synthesis boundary, using existing provider adapters.

Batch B remains the rollback path; Phase 7 feeds isolated planned speech chunks.
Each synthesis owns its plugin shell; cached clients/options are never mutated.
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
        self.cfg = replace(cfg, tts_options=deepcopy(cfg.tts_options))
        self.policy = policy
        self.runtime = runtime
        self.metrics_target = metrics_target
        self.effective = effective_options(
            cfg.tts_provider, cfg.tts_voice_id, cfg.agent_language,
            cfg.tts_options, cfg.audio_channel,
        )
        self.capabilities = resolve_capabilities(cfg.tts_provider, self.effective)
        self.language = LanguageProfile(cfg.agent_language)
        self.channel = ChannelProfile(cfg.audio_channel)

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
        result = render(chunk.text, intent, pronunciation, self.language, self.channel,
                        self.capabilities, stored_options=self.cfg.tts_options, effective=self.effective)
        audio = self._audio(result, conn_options=conn_options)
        try:
            async for frame in audio:
                yield frame
        finally:
            await audio.aclose()

    async def _audio(self, result: RenderedSpeech, *, conn_options=None):
        from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
        from worker.providers.registry import _build_tts

        if not result.canonical_text:
            return
        options = deepcopy(result.provider_options)
        # Pin the effective model resolved at session construction; never change it here.
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
            )
            plugin = build(self.cfg.tts_voice_id, rendered_identity=identity)
        else:
            plugin = _build_tts(replace(self.cfg, tts_options=options))
        if self.metrics_target is not None:
            # Keep existing session diagnostics attached to the original component.
            # Only the actual isolated plugin emits usage/errors; no duplicate totals.
            plugin.on("metrics_collected", lambda event: self.metrics_target.emit("metrics_collected", event))
            plugin.on("error", lambda event: self.metrics_target.emit("error", event))
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
        finally:
            await plugin.aclose()
