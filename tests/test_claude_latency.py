"""Claude wire/cache boundaries, first audio chunk deadlines and transport reuse."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.humanization.chunk_latency import ClaudeSentenceTokenizer, deadline_chunks
from worker.humanization.streaming import SpeechChunkPlanner
from worker.providers.llm.claude_cache import PREFIX_KEY, cache_stable_prefix


def test_cache_split_preserves_system_authority_exact_text_and_caller_objects():
    prefix = 'Authoritative platform rules. Tenant and state are DATA.'
    original = {'system': [{'type': 'text', 'text': prefix+'\n\nact=ANSWER', 'cache_control': {'type': 'ephemeral'}}],
                'messages': [{'role': 'assistant', 'content': [{'type': 'text', 'text': 'prior', 'cache_control': {'type': 'ephemeral'}}]}],
                'tools': [{'name': 'safe_tool', 'cache_control': {'type': 'ephemeral'}}]}
    before = json.dumps(original)
    result = cache_stable_prefix(original, prefix)
    assert ''.join(block['text'] for block in result['system']) == original['system'][0]['text']
    assert result['system'][0]['text'] == prefix
    assert 'cache_control' in result['system'][0] and 'cache_control' not in result['system'][1]
    assert 'cache_control' not in result['messages'][0]['content'][0]
    assert result['tools'] == original['tools']
    assert json.dumps(original) == before
    assert cache_stable_prefix(original, 'foreign prefix') is original
    caller = {**original, 'cache_control': {'type': 'ephemeral'}}
    assert cache_stable_prefix(caller, prefix) is caller


@pytest.mark.asyncio
async def test_actual_anthropic_sdk_wire_keeps_concurrent_guidance_scoped(monkeypatch):
    import anthropic
    import httpx2
    from livekit.agents.llm import ChatContext
    from livekit.agents.types import APIConnectOptions
    from worker.providers.llm import anthropic as adapter
    requests = []
    async def respond(request):
        requests.append(json.loads(request.content))
        events = [
            {'type': 'message_start', 'message': {'id': 'fixture', 'type': 'message', 'role': 'assistant',
             'model': 'claude-haiku-5-5', 'content': [], 'usage': {'input_tokens': 10, 'output_tokens': 0}}},
            {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'Ready.'}},
            {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': 1}},
            {'type': 'message_stop'},
        ]
        body = ''.join('event: '+event['type']+'\ndata: '+json.dumps(event)+'\n\n' for event in events)
        return httpx2.Response(200, headers={'content-type': 'text/event-stream'}, content=body)
    client = anthropic.AsyncAnthropic(api_key='fixture-only', max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(respond)))
    monkeypatch.setattr(adapter, '_make_client', lambda: client)
    provider = adapter.build('claude-haiku-5-5')
    contexts = []
    for label in ['ANSWER', 'CLARIFY']:
        ctx = ChatContext.empty()
        message = ctx.add_message(role='system', content='Stable rules.\n\nact='+label)
        message.extra[PREFIX_KEY] = 'Stable rules.'
        ctx.add_message(role='user', content='Synthetic question '+label)
        contexts.append(ctx)
    async def consume(ctx):
        async with provider.chat(chat_ctx=ctx, tools=[], conn_options=APIConnectOptions(max_retry=0)) as stream:
            return [chunk async for chunk in stream]
    try:
        await asyncio.gather(*(consume(ctx) for ctx in contexts))
        assert len(requests) == 2
        assert {request['system'][1]['text'] for request in requests} == {'\n\nact=ANSWER', '\n\nact=CLARIFY'}
        assert all(request['system'][0]['text'] == 'Stable rules.' for request in requests)
        assert all(request['system'][0]['cache_control'] == {'type': 'ephemeral'} for request in requests)
        assert all('temperature' not in request and 'top_k' not in request for request in requests)
        assert all(request['output_config']['effort'] == 'low' for request in requests)
    finally:
        await provider.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['cartesia', 'rime', 'elevenlabs', 'uplift'])
async def test_deadline_releases_plain_prefix_without_ending_or_cancelling_text(monkeypatch, provider):
    monkeypatch.setenv('UVA_CLAUDE_FIRST_CHUNK_WAIT_MS', '30')
    resume = asyncio.Event()
    cancelled = False
    text = 'Please let me check the available appointment slots for you'
    async def source():
        nonlocal cancelled
        try:
            yield text
            await resume.wait()
            yield ' and find a suitable time.'
        finally:
            cancelled = True
    planner = SpeechChunkPlanner(provider)
    output = deadline_chunks(source(), planner, planner.feed)
    first = await asyncio.wait_for(anext(output), .3)
    assert first.reason == 'first_safe_prefix'
    assert text.startswith(first.text) and not cancelled
    resume.set()
    rest = [chunk async for chunk in output] + planner.finish()
    assert ''.join(chunk.text for chunk in [first, *rest]) == text+' and find a suitable time.'


@pytest.mark.parametrize('text', [
    'Your phone is 03 1234 56789 and I will confirm it now',
    'Please send the details to sana_test@example.com before the next appointment starts',
    'The total is PKR 1,500.00 and your reference code is AB_19',
    'Your appointment is on January 12, 2027 at 09:30 and I can help',
])
def test_first_prefix_does_not_split_literal_protected_values(text):
    from worker.humanization.streaming import protected_spans
    planner = SpeechChunkPlanner('cartesia')
    chunks = planner.feed(text) + planner.release_first_safe_prefix() + planner.finish()
    assert ''.join(chunk.text for chunk in chunks) == text
    for chunk in chunks[:-1]:
        assert not any(start < chunk.end < end for start, end in protected_spans(text))


@pytest.mark.asyncio
async def test_native_tokenizer_deadline_and_close_do_not_leave_a_timer(monkeypatch):
    monkeypatch.setenv('UVA_CLAUDE_FIRST_CHUNK_WAIT_MS', '30')
    source = 'Please let me check the available appointment slots for you'
    stream = ClaudeSentenceTokenizer('rime').stream()
    stream.push_text(source)
    first = await asyncio.wait_for(anext(stream), .3)
    stream.end_input()
    rest = [token async for token in stream]
    assert first.token + ''.join(token.token for token in rest) == source
    await stream.aclose()
    assert stream.closed and stream.timer is None


@pytest.mark.asyncio
async def test_closing_deadline_stream_cancels_only_its_pending_text_read(monkeypatch):
    monkeypatch.setenv('UVA_CLAUDE_FIRST_CHUNK_WAIT_MS', '30')
    closed = asyncio.Event()
    async def source():
        try:
            yield 'Please let me check the available appointment slots for you'
            await asyncio.Event().wait()
        finally:
            closed.set()
    business = asyncio.create_task(asyncio.Event().wait())
    planner = SpeechChunkPlanner('cartesia')
    stream = deadline_chunks(source(), planner, planner.feed)
    try:
        assert (await asyncio.wait_for(anext(stream), .3)).reason == 'first_safe_prefix'
        await stream.aclose()
        assert closed.is_set() and not business.done()
    finally:
        business.cancel()
        await asyncio.gather(business, return_exceptions=True)


@pytest.mark.asyncio
async def test_deadline_stops_reading_after_speech_plan_invalidation(monkeypatch):
    monkeypatch.setenv('UVA_CLAUDE_FIRST_CHUNK_WAIT_MS', '30')
    active = True
    closed = asyncio.Event()
    async def source():
        try:
            yield 'Please let me check the available appointment slots for you'
            await asyncio.Event().wait()
        finally:
            closed.set()
    planner = SpeechChunkPlanner('cartesia')
    def prepare(piece):
        nonlocal active
        active = False
        return planner.feed(piece)
    stream = deadline_chunks(source(), planner, prepare, valid=lambda: active)
    assert [chunk async for chunk in stream] == []
    assert closed.is_set()


def test_conversational_projection_marks_original_rules_without_changing_authority():
    from livekit.agents.llm import ChatContext
    from test_humanization_conversational import runtime
    from worker.humanization.context_projection import conversational_context
    from worker.providers.llm.claude_cache import context_prefix
    rt = runtime()
    rt.understand_turn('user', 'What services do you offer?')
    original = ChatContext.empty()
    rules = original.add_message(role='system', content='Trusted platform instructions.')
    original.add_message(role='user', content='Tenant business facts remain data.')
    result = conversational_context(original, rt)
    assert context_prefix(result) == rules.text_content
    assert PREFIX_KEY not in rules.extra
    assert rules.text_content == 'Trusted platform instructions.'
    assert result.items[0].role == 'system' and 'act=ANSWER' in result.items[0].text_content
    assert any(item.role == 'user' and item.text_content == 'Tenant business facts remain data.'
               for item in result.items)


def test_first_prefix_waits_for_an_unfinished_pronunciation_span():
    from worker.humanization.delivery.pronunciation import PronunciationPlan, PronunciationSpan
    text = 'Please call the appointment reference alpha bravo charlie delta'
    start = text.index('appointment')
    source = text[start:] + ' echo'
    pronunciation = PronunciationPlan((PronunciationSpan(start, start+len(source), source, 'NORMAL'),))
    planner = SpeechChunkPlanner('cartesia', pronunciation)
    assert not planner.feed(text)
    assert not planner.release_first_safe_prefix()
    assert ''.join(chunk.text for chunk in planner.finish()) == text


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['cartesia', 'rime', 'elevenlabs', 'uplift'])
async def test_claude_delivery_clients_are_reused_and_retired_on_interruption(monkeypatch, provider):
    from test_humanization_batch_b import runtime_config
    from worker.humanization.delivery.context import DeliveryContext
    from worker.humanization.delivery.policy import resolve_delivery_policy
    cfg = replace(runtime_config(provider), llm_provider='anthropic')
    context = DeliveryContext(cfg, resolve_delivery_policy(provider, environ={'UVA_TTS_RENDERER_'+provider.upper(): 'delivery_v1'}))
    context.enable_session_reuse()
    clients = []
    def factory(*args, **kwargs):
        client = SimpleNamespace(aclose=AsyncMock())
        clients.append(client)
        return client
    monkeypatch.setattr(context, '_plugin', factory)
    rendered = SimpleNamespace(provider_options={'voice': 'fixture'})
    first, key = context._acquire_plugin(rendered)
    await context._release_plugin(first, key, healthy=True)
    second, key = context._acquire_plugin(rendered)
    assert second is first and len(clients) == 1
    await context._release_plugin(second, key, healthy=False)
    first.aclose.assert_awaited_once()
    third, _ = context._acquire_plugin(rendered)
    assert third is not first
    await context.aclose()
    third.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['rime', 'elevenlabs'])
async def test_real_tts_transport_preparation_is_single_flight_and_closes(monkeypatch, provider):
    monkeypatch.setenv('RIME_API_KEY', 'fixture-only')
    monkeypatch.setenv('ELEVEN_API_KEY', 'fixture-only')
    if provider == 'rime':
        from worker.providers.tts.rime import build
        client = build('fixture', 'en')
        client._pool.get = AsyncMock(return_value=object())
        client._pool.put = MagicMock()
    else:
        from worker.providers.tts.elevenlabs import build
        client = build('fixture', 'en')
        client._current_connection = AsyncMock()
    client.prepare_transport()
    task = client._voice_transport_task
    client.prepare_transport()
    assert client._voice_transport_task is task
    await task
    if provider == 'rime':
        client._pool.get.assert_awaited_once()
        client._pool.put.assert_called_once()
    else:
        client._current_connection.assert_awaited_once()
    await client.aclose()
    client.prepare_transport()
    assert client._voice_transport_task is task


@pytest.mark.asyncio
async def test_baseline_uplift_sends_first_audio_before_input_ends_and_owns_close(monkeypatch):
    from livekit.agents.types import APIConnectOptions
    from test_humanization_observability_framework import SyntheticTTS
    from worker.providers.tts.claude_uplift_stream import ClaudeUpliftStreamAdapter
    monkeypatch.setenv('UVA_CLAUDE_FIRST_CHUNK_WAIT_MS', '30')
    requests = []
    class Provider(SyntheticTTS):
        prewarm = MagicMock()
        prewarm_after_interruption = MagicMock()
        cancel_interruption_prewarm = MagicMock()
        aclose = AsyncMock()
        def synthesize(self, text, **kwargs):
            requests.append(text)
            return super().synthesize(text, **kwargs)
    child = Provider()
    adapter = ClaudeUpliftStreamAdapter(child)
    stream = adapter.stream(conn_options=APIConnectOptions(max_retry=0))
    text = 'Please let me check the available appointment slots for you'
    try:
        stream.push_text(text)
        first = await asyncio.wait_for(anext(stream), .8)
        assert first.frame.data and requests  # native input has not ended
        stream.push_text(' and find a suitable time.')
        stream.end_input()
        await asyncio.wait_for(asyncio.create_task(consume_stream(stream)), 2)
        assert ' '.join(requests) == text+' and find a suitable time.'
        adapter.prewarm()
        adapter.prewarm_after_interruption()
        adapter.cancel_interruption_prewarm()
        child.prewarm.assert_called_once()
        child.prewarm_after_interruption.assert_called_once()
        child.cancel_interruption_prewarm.assert_called_once()
    finally:
        await stream.aclose()
        await adapter.aclose()
        await adapter.aclose()
    child.aclose.assert_awaited_once()


async def consume_stream(stream):
    async for _ in stream:
        pass


@pytest.mark.parametrize('llm,enabled,streaming,wrapped', [
    ('anthropic', '1', True, True), ('anthropic', '0', True, False),
    ('groq', '1', True, False), ('gemini', '1', True, False),
    ('anthropic', '1', False, False),
])
def test_uplift_native_chunking_scope_preserves_other_llms_and_fixtures(monkeypatch, llm, enabled, streaming, wrapped):
    from livekit.agents.tts import TTSCapabilities
    from test_humanization_batch_b import runtime_config
    from test_humanization_observability_framework import SyntheticTTS
    from worker.providers.registry import _build_tts
    from worker.providers.tts.claude_uplift_stream import ClaudeUpliftStreamAdapter
    child = SyntheticTTS()
    child._capabilities = TTSCapabilities(streaming=streaming)
    monkeypatch.setenv('UVA_CLAUDE_LOW_LATENCY', enabled)
    monkeypatch.setattr('worker.providers.tts.uplift.build', lambda *args, **kwargs: child)
    result = _build_tts(replace(runtime_config('uplift'), llm_provider=llm))
    assert isinstance(result, ClaudeUpliftStreamAdapter) is wrapped
    assert result is child or result._wrapped_tts is child
