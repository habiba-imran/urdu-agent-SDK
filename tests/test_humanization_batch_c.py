"""Phase 7 P0: stream properties, provider feed and cancellation contracts."""
from __future__ import annotations
import asyncio
import random
import pytest
from worker.humanization.delivery.canonical import canonical_spoken_text
from worker.humanization.delivery.intent import DeliveryIntent
from worker.humanization.delivery.pronunciation import PronunciationPlan, PronunciationSpan
from worker.humanization.streaming import StreamSafeNormalizer, SpeechChunkPlanner, SpeechPlan, streaming_enabled

PROVIDERS = ("cartesia", "rime", "elevenlabs", "uplift")
TEXTS = (
    "Hello there. I can help you, and then we can check.",
    "آپ کی بکنگ ہو گئی ہے۔ کیا آپ کو مزید مدد چاہیے؟",
    "آپ کا reference AB_19 ہے، Sana سے بات کریں۔",
    "  Hello \t there\n  again.  ",
    "Email test_id+tag@example.com, please.",
    "Visit https://example.com/a_b?q=1.5&ref=AB_19 then call.",
    "Call +92 (300) 123-4567, or 0300 1234567.",
    "Your ID is AB_19 and ref ZX-91. Keep both.",
    "It costs PKR 1,500.25, or $12.50. Yes.",
    "Café é — नमस्ते — 你好. Unicode stays.",
    "Hello 👩🏽‍💻 😊 world!",
    '<emotion value="calm"/> Hello <spell>AB_19</spell> **there** [laughs].',
    "Use [website label](https://example.com/a_b). Or spell(S A N A).",
    "3 < 5 and 5 > 3. [AB_19] stays.",
    "Your code is AB_19. <emotion_value=broken",
    "Your code is AB_19. [unsupported cue",
    "spell (S A N A) says a name. <bad>safe</bad>",
)


def partitions(text):
    yield [text]
    yield list(text)
    for i in range(len(text)+1):
        yield [text[:i], text[i:]]
    rng = random.Random(7)
    for _ in range(75):
        cuts = sorted({0, len(text), *(rng.randrange(len(text)+1) for _ in range(12))})
        yield [text[a:b] for a,b in zip(cuts,cuts[1:])]


@pytest.mark.parametrize("text", TEXTS)
def test_arbitrary_boundaries_equal_whole_text(text):
    expected = canonical_spoken_text(text)
    for pieces in partitions(text):
        normalizer = StreamSafeNormalizer()
        result = "".join(normalizer.feed(p) for p in pieces) + normalizer.finish()
        assert result == expected, (pieces, result, expected)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_planner_deterministic_for_transport_boundaries(provider):
    text = "I can help you, please email test_id@example.com. آپ کا کوڈ AB_19 ہے۔ Final answer."
    expected = None
    for parts in partitions(text):
        planner = SpeechChunkPlanner(provider)
        result = [c for p in parts for c in planner.feed(p)] + planner.finish()
        assert "".join(c.text for c in result) == text
        value = [(c.start,c.end,c.reason) for c in result]
        if expected is None:
            expected = value
        assert value == expected


@pytest.mark.parametrize("entity", (
    "+92 (300) 123-4567", "test_id@example.com", "https://example.com/a,b?q=1.25",
    "09/10/2026", "09:30 a.m.", "$1,500.25", "PKR 1,500.25", "AB_19", "ZX-91",
    "S-A-N-A", "S A N A", "S. A. N. A.", "October 9, 2026", "<spell>Sana, Clinic</spell>", "spell(Sana, Clinic)",
))
def test_protected_spans_remain_whole(entity):
    text = "Please use this value " + entity + ", and continue. The end."
    for parts in partitions(text):
        planner = SpeechChunkPlanner("cartesia")
        chunks = [c for p in parts for c in planner.feed(p)] + planner.finish()
        assert any(entity in c.text for c in chunks), (entity, chunks)


def test_explicit_pronunciation_span_protects_a_named_phrase():
    text = "Please speak to Sana, Clinic and wait. Okay."
    start = text.index("Sana")
    plan = PronunciationPlan((PronunciationSpan(start,start+12,"Sana, Clinic", "SPELL"),))
    planner = SpeechChunkPlanner("cartesia", plan)
    chunks = [c for p in text for c in planner.feed(p)] + planner.finish()
    assert any("Sana, Clinic" in c.text for c in chunks)


def test_cancelled_plan_rejects_text_chunk_and_audio_and_clears_buffers():
    async def run():
        from livekit import rtc
        plan = SpeechPlan("speech:1", "cartesia", DeliveryIntent())
        plan.normalizer.feed("unfinished <emotion")
        plan.planner.feed("unfinished speech")
        plan.cancel()
        assert not plan.accept_text("late text")
        assert not plan.accept_chunk(SpeechChunkPlanner("cartesia").feed("Late answer. Next.")[0])
        assert not await plan.pace_audio(rtc.AudioFrame(data=bytes(320),sample_rate=16000,num_channels=1,samples_per_channel=160))
        assert plan.rejected_audio_ms == 10
        assert plan.normalizer.buffer == plan.planner.buffer == ""
        assert plan.metrics()["caller_heard_latency_ms"] is None
    asyncio.run(run())


@pytest.mark.parametrize("provider", PROVIDERS)
def test_separate_provider_flag_default_and_rollback(provider, monkeypatch):
    from test_humanization_batch_b import context
    ctx = context(provider)
    key = "UVA_TTS_STREAMING_" + provider.upper()
    assert not streaming_enabled(ctx, environ={})
    assert streaming_enabled(ctx, environ={key:"streaming_v1"})
    assert not streaming_enabled(ctx, environ={key:"baseline"})
    for other in set(PROVIDERS)-{provider}:
        assert not streaming_enabled(ctx, environ={"UVA_TTS_STREAMING_"+other.upper():"streaming_v1"})
    with pytest.raises(ValueError):
        streaming_enabled(ctx, environ={key:"future"})
    from worker.humanization.delivery.policy import DeliveryPolicy
    ctx.policy = DeliveryPolicy()
    with pytest.raises(ValueError, match="requires delivery_v1"):
        streaming_enabled(ctx, environ={key:"streaming_v1"})


@pytest.mark.parametrize("provider", PROVIDERS)
def test_real_framework_streams_before_llm_finishes_and_keeps_canonical_history(provider, monkeypatch):
    from livekit.agents import AgentSession, llm
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
    from test_humanization_batch_b import context
    from test_humanization_observability_framework import SyntheticSink, SyntheticTTS
    from worker.humanization.agent import AwaazAgent
    import worker.providers.registry as registry
    import worker.providers.tts.uplift as uplift
    monkeypatch.setenv("UVA_TTS_STREAMING_" + provider.upper(), "streaming_v1")

    async def run():
        received, closed = [], []
        first_feed = asyncio.Event()
        remainder_sent = asyncio.Event()
        class RecordingTTS(SyntheticTTS):
            def synthesize(self, text, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):
                received.append(text)
                first_feed.set()
                return super().synthesize(text, conn_options=conn_options)
            async def aclose(self):
                closed.append(True)
                await super().aclose()
        monkeypatch.setattr(registry, "_build_tts", lambda cfg, **kwargs: RecordingTTS())
        monkeypatch.setattr(uplift, "build", lambda *a, **kw: RecordingTTS())
        class Model(llm.LLM):
            def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
                return Stream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)
        class Stream(llm.LLMStream):
            async def _run(self):
                first = 'آپ کی بکنگ ہو گئی ہے۔ اگلا حصہ ' if provider == 'uplift' else '<emotion value="calm"/>I can help you. Next part '
                for piece in first:
                    self._event_ch.send_nowait(llm.ChatChunk(id="reply", delta=llm.ChoiceDelta(content=piece)))
                await asyncio.wait_for(first_feed.wait(), 2)
                assert not remainder_sent.is_set()
                tail = 'code AB_19 اور email test_id@example.com ہے۔' if provider == 'uplift' else 'code AB_19 and email test_id@example.com.'
                for piece in tail:
                    self._event_ch.send_nowait(llm.ChatChunk(id="reply", delta=llm.ChoiceDelta(content=piece)))
                remainder_sent.set()
                self._event_ch.send_nowait(llm.ChatChunk(id="reply", usage=llm.CompletionUsage(prompt_tokens=10,completion_tokens=5,total_tokens=15)))
        session = AgentSession(llm=Model(),tts=SyntheticTTS(),tts_text_transforms=[],use_tts_aligned_transcript=False)
        session.output.audio = SyntheticSink()
        agent = AwaazAgent(instructions="plain",delivery_context=context(provider))
        await session.start(agent,record=False)
        try:
            handle = session.generate_reply(user_input="Question")
            await asyncio.wait_for(handle.wait_for_playout(), 5)
            assert handle.exception() is None
            plan = agent.speech_plans[-1]
            expected = ('آپ کی بکنگ ہو گئی ہے۔ اگلا حصہ code AB_19 اور email test_id@example.com ہے۔' if provider == 'uplift'
                        else 'I can help you. Next part code AB_19 and email test_id@example.com.')
            assert plan.canonical_text == expected
            assert ''.join(c.text for c in plan.planned_chunks) == expected
            assert [m.text_content for m in session.history.messages() if m.role=="assistant"] == [expected]
            assert [m.text_content for m in agent.chat_ctx.messages() if m.role=="assistant"] == [expected]
            assert len(received) == 2 and len(closed) == 1
            assert plan.provider_context["lifecycle"] == "generation_plugin"
            assert plan.chunk_wait_ms is not None and plan.chunk_wait_ms >= 0
            assert plan.inter_chunk_gap_ms == []  # one generation client; audio gaps require playback evidence
            assert plan.playout_completed is True and plan.heard_reference is None
            assert all('<emotion' not in c.text for c in plan.planned_chunks)
            static = session.say('<spell>ZX9</spell> is your code.', allow_interruptions=True)
            await asyncio.wait_for(static.wait_for_playout(), 5)
            assert static.exception() is None
            assert agent.speech_plans[-1].canonical_text == 'ZX9 is your code.'
            assert static.chat_items[-1].text_content == 'ZX9 is your code.'
            assert list(session.history.messages())[-1].text_content == 'ZX9 is your code.'
            assert list(agent.chat_ctx.messages())[-1].text_content == 'ZX9 is your code.'
            assert agent.speech_plans[-1].history_references == (static.chat_items[-1].id,)
            assert agent.speech_plans[-1].framework_playout_references == agent.speech_plans[-1].history_references
        finally:
            await session.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("provider", PROVIDERS)
def test_actual_provider_stream_entry_preserves_settings_and_whole_chunk(provider, monkeypatch):
    from test_humanization_batch_b import context
    monkeypatch.setenv("UPLIFT_MODE", "live")
    for key in ("CARTESIA_API_KEY","RIME_API_KEY","ELEVEN_API_KEY","UPLIFTAI_API_KEY"):
        monkeypatch.setenv(key,"synthetic-no-network")
    module_name = 'upliftai' if provider=='uplift' else provider
    import importlib
    module = importlib.import_module('livekit.plugins.'+module_name+'.tts')
    feeds, closed = [], []
    original_close = module.TTS.aclose
    async def run_stream(self, emitter):
        pieces = [piece async for piece in self._input_ch if isinstance(piece,str)]
        feeds.append((pieces,self._tts))
        emitter.initialize(request_id='fixture',sample_rate=self._tts.sample_rate,num_channels=1,mime_type='audio/pcm',stream=True)
        emitter.start_segment(segment_id='fixture')
        emitter.push(bytes(3200))
        emitter.end_segment()
        emitter.end_input()
        await emitter.join()
    async def close(self):
        closed.append(self)
        await original_close(self)
    monkeypatch.setattr(module.SynthesizeStream,'_run',run_stream)
    monkeypatch.setattr(module.TTS,'aclose',close)
    async def run():
        ctx = context(provider)
        text = 'آپ کا کوڈ AB_19 ہے۔' if provider=='uplift' else 'Your code is AB_19.'
        from worker.humanization.delivery.pronunciation import plan_pronunciation
        plan = SpeechPlan('speech:1',provider,DeliveryIntent(),plan_pronunciation(text,language=ctx.language.language))
        from worker.humanization.streaming import SpeechChunk
        frames = [f async for f in ctx.audio_chunk(SpeechChunk(0,len(text),text,'short_reply'),plan)]
        assert frames and len(feeds)==len(closed)==1
        pieces,plugin = feeds[0]
        assert len(pieces)==1  # planned text, never raw model tokens
        assert 'AB_19' in pieces[0] or ('underscore' in pieces[0] if provider!='uplift' else 'انڈر اسکور' in pieces[0])
        if provider=='cartesia':
            assert plugin.model=='sonic-3.5' and plugin.sample_rate==16000
        elif provider=='rime':
            assert plugin.model=='arcana' and plugin._segment=='immediate' and plugin.sample_rate==16000
        elif provider=='elevenlabs':
            assert plugin.model=='eleven_flash_v2_5' and plugin._opts.auto_mode is True
        else:
            assert plugin._opts.voice_settings.output_format=='PCM_22050_16'
    asyncio.run(run())


def test_audio_handoff_backpressure_is_bounded_and_cancellation_rechecked(monkeypatch):
    from livekit import rtc
    import worker.humanization.streaming as streaming
    async def run():
        now = [0.0]
        waits = []
        monkeypatch.setattr(streaming.time,'monotonic',lambda:now[0])
        async def sleep(delay):
            waits.append(delay)
            now[0] += delay
        monkeypatch.setattr(streaming.asyncio,'sleep',sleep)
        frame = rtc.AudioFrame(data=bytes(32000),sample_rate=16000,num_channels=1,samples_per_channel=16000)
        plan = SpeechPlan('speech:1','cartesia',DeliveryIntent())
        for _ in range(4):
            assert await plan.pace_audio(frame)
            assert plan.lead_estimate_ms <= 2000.01
        assert waits == [1.0,1.0]
        async def cancel_during_wait(delay):
            plan.cancel()
        monkeypatch.setattr(streaming.asyncio,'sleep',cancel_during_wait)
        assert not await plan.pace_audio(frame)
        assert plan.rejected_audio_ms == 1000
    asyncio.run(run())


@pytest.mark.parametrize("provider", PROVIDERS)
def test_interrupted_framework_generation_closes_synthesis_and_new_generation_works(provider, monkeypatch):
    from livekit.agents import AgentSession, tts
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
    from test_humanization_batch_b import context
    from test_humanization_observability_framework import SyntheticSink, SyntheticTTS
    from worker.humanization.agent import AwaazAgent
    import worker.providers.registry as registry
    import worker.providers.tts.uplift as uplift
    monkeypatch.setenv('UVA_TTS_STREAMING_'+provider.upper(),'streaming_v1')
    async def run():
        started = asyncio.Event()
        received, closed, cancelled_streams = [], [], []
        class SlowAudio(tts.ChunkedStream):
            async def _run(self, emitter):
                emitter.initialize(request_id='old',sample_rate=16000,num_channels=1,mime_type='audio/pcm')
                emitter.push(bytes(3200))
                emitter.flush()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled_streams.append(True)
        class Provider(SyntheticTTS):
            def synthesize(self,text,*,conn_options=DEFAULT_API_CONNECT_OPTIONS):
                received.append(text)
                if 'Old reply' in text:
                    return SlowAudio(tts=self,input_text=text,conn_options=conn_options)
                return super().synthesize(text,conn_options=conn_options)
            async def aclose(self):
                closed.append(True)
                await super().aclose()
        class Sink(SyntheticSink):
            async def capture_frame(self,frame):
                await super().capture_frame(frame)
                started.set()
        monkeypatch.setattr(registry,'_build_tts',lambda cfg, **kwargs:Provider())
        monkeypatch.setattr(uplift,'build',lambda *a,**kw:Provider())
        sink = Sink()
        session = AgentSession(tts=SyntheticTTS(),tts_text_transforms=[],use_tts_aligned_transcript=False)
        session.output.audio = sink
        agent = AwaazAgent(instructions='plain',delivery_context=context(provider,language='en'))
        await session.start(agent,record=False)
        try:
            old = session.say('Old reply. Second sentence.',allow_interruptions=True)
            await asyncio.wait_for(started.wait(),2)
            old.interrupt()
            await asyncio.wait_for(old.wait_for_playout(),3)
            plan = agent.speech_plans[-1]
            assert plan.cancelled and plan.playout_completed is False
            assert plan.normalizer.buffer == plan.planner.buffer == ''
            assert cancelled_streams and closed == [True]
            assert len(received)==1  # second sentence was never fed after interruption
            count = sink.frames
            from livekit import rtc
            late = rtc.AudioFrame(data=bytes(320),sample_rate=16000,num_channels=1,samples_per_channel=160)
            assert not await plan.pace_audio(late)
            assert not plan.accept_text('zombie')
            assert sink.frames==count
            new = session.say('New answer.',allow_interruptions=True)
            await asyncio.wait_for(new.wait_for_playout(),3)
            assert new.exception() is None and sink.frames>count
            assert agent.speech_plans[-1].generation_id != plan.generation_id
            assert not agent.speech_plans[-1].cancelled
            assert not agent._active_speech_plans
        finally:
            await session.aclose()
    asyncio.run(run())


def test_speech_cancellation_owns_only_synthesis_not_business_task():
    async def run():
        business_committed = asyncio.Event()
        complete = asyncio.Event()
        async def write():
            business_committed.set()
            await complete.wait()
            return 'committed result'
        task = asyncio.create_task(write())
        await business_committed.wait()
        synthesis = asyncio.create_task(asyncio.Event().wait())
        plan = SpeechPlan('speech:1','cartesia',DeliveryIntent())
        plan.synthesis_task = synthesis
        plan.cancel()
        await asyncio.gather(synthesis,return_exceptions=True)
        assert synthesis.cancelled() and not task.cancelled()
        complete.set()
        assert await task == 'committed result'
    asyncio.run(run())


def test_streamed_llm_tool_identity_usage_and_text_are_preserved():
    from livekit.agents import llm
    from worker.humanization.agent import AwaazAgent
    async def source():
        for part in ('<emo','tion value="calm"/> Checking',' now.'):
            yield llm.ChatChunk(id='reply',delta=llm.ChoiceDelta(content=part))
        yield llm.ChatChunk(id='reply',delta=llm.ChoiceDelta(tool_calls=[llm.FunctionToolCall(
            name='business_write',arguments='{"ref":"AB_19"}',call_id='tool-distinct')]))
        yield llm.ChatChunk(id='reply',usage=llm.CompletionUsage(prompt_tokens=10,completion_tokens=5,total_tokens=15))
    async def run():
        plan = SpeechPlan('speech:1','cartesia',DeliveryIntent())
        agent = AwaazAgent(instructions='plain')
        chunks = [c async for c in agent._streaming_llm_stream(source(),plan)]
        assert ''.join(c.delta.content or '' for c in chunks if c.delta) == 'Checking now.'
        tools = [call for c in chunks if c.delta for call in c.delta.tool_calls or []]
        assert len(tools)==1 and tools[0].call_id=='tool-distinct'
        assert tools[0].arguments=='{"ref":"AB_19"}'
        assert sum(c.usage.total_tokens for c in chunks if c.usage)==15
        assert plan.canonical_text=='Checking now.'
    asyncio.run(run())


def test_seeded_malformed_composition_property():
    # Cross-construct cases matter: cleanup can expose an incomplete suffix.
    atoms = ['hello',' ','  ','<emo','tion value="calm"/>','[laugh','s]','spell(',
             'Sana',')','[label]','(',')','<bad','/>','_','*','\n','AB_19','@',
             ',',']','[','<','>','</spell>','3.50','آپ']
    rng = random.Random(17)
    for _ in range(4000):
        text = ''.join(rng.choices(atoms,k=15))
        normalizer = StreamSafeNormalizer()
        actual = ''.join(normalizer.feed(c) for c in text) + normalizer.finish()
        assert actual == canonical_spoken_text(text), text


def test_unknown_installed_version_fails_closed(monkeypatch):
    import importlib.metadata
    from test_humanization_batch_b import context
    ctx = context('cartesia')
    monkeypatch.setattr(importlib.metadata,'version',lambda name:'future')
    with pytest.raises(ValueError,match='audited'):
        streaming_enabled(ctx,environ={'UVA_TTS_STREAMING_CARTESIA':'streaming_v1'})


def test_explicit_pronunciation_offsets_survive_chunk_rendering(monkeypatch):
    from test_humanization_batch_b import context
    from worker.humanization.agent import AwaazAgent
    async def run():
        ctx = context('cartesia')
        received = []
        from test_humanization_observability_framework import SyntheticTTS
        original_render = ctx.render_chunk
        def render_chunk(chunk, plan):
            result = original_render(chunk, plan)
            received.append(result)
            return result
        monkeypatch.setattr(ctx, 'render_chunk', render_chunk)
        monkeypatch.setattr(ctx, '_plugin', lambda result, **kwargs: SyntheticTTS())
        full = 'First answer. Please speak to Sana, Clinic and wait.'
        start = full.index('Sana')
        plan = SpeechPlan('speech:1','cartesia',DeliveryIntent(),PronunciationPlan((
            PronunciationSpan(start,start+12,'Sana, Clinic','ALIAS',alias='Saa na clinic'),)))
        plan.llm_started=True
        async def text():
            for c in full:
                yield c
        agent = AwaazAgent(instructions='plain',delivery_context=ctx)
        _ = [frame async for frame in agent._streaming_tts(text(),plan,None)]
        assert 'Saa na clinic' in received[-1].provider_text
        assert 'Sana, Clinic' in received[-1].canonical_text
    asyncio.run(run())
