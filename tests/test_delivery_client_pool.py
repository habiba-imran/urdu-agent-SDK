"""Delivery transport reuse must preserve settings, generation isolation and cleanup."""
from types import SimpleNamespace as NS

import pytest

from worker.humanization.delivery.client_pool import DeliveryClientPool


class Client:
    def __init__(self):
        self.closes = 0

    async def aclose(self):
        self.closes += 1


@pytest.mark.asyncio
async def test_prepared_client_is_available_exclusively_and_preparation_is_bounded():
    pool = DeliveryClientPool(max_idle=1)
    prepared, created = pool.prepare('normal', Client)
    assert created
    assert pool.prepare('normal', Client) == (prepared, False)
    assert pool.prepare('slower', Client) == (None, False)
    leased, reused = pool.acquire('normal', Client)
    assert leased is prepared and reused
    replacement, created = pool.prepare('normal', Client)
    assert created and replacement is not leased
    await pool.release('normal', leased, healthy=False)
    assert leased.closes == 1 and replacement.closes == 0
    next_client, reused = pool.acquire('normal', Client)
    assert next_client is replacement and reused
    await pool.aclose()
    assert replacement.closes == 1
    assert pool.prepare('closed', Client) == (None, False)


@pytest.mark.asyncio
async def test_plan_preparation_warms_matching_client_without_speech_or_option_mutation(monkeypatch):
    from test_humanization_batch_b import context
    from worker.humanization.delivery.intent import DeliveryIntent
    from worker.humanization.streaming import SpeechChunk, SpeechPlan

    class Voice(Client):
        warms = 0

        def prepare_transport(self):
            self.warms += 1

    clients = []

    def build(*args, **kwargs):
        client = Voice()
        clients.append(client)
        return client

    monkeypatch.setattr('worker.providers.registry._build_tts', build)
    ctx = context('cartesia')
    ctx.enable_session_reuse()
    plan = SpeechPlan('readback', 'cartesia', DeliveryIntent(pace='slower'))
    ctx.prewarm_for_plan(plan)
    assert len(clients) == 1 and clients[0].warms == 1
    # No text or synthesis has occurred; the first real chunk leases the warm client.
    assert not plan.canonical_text and not plan.planned_chunks
    chunk = SpeechChunk(0, 18, 'Please confirm it.', 'sentence')
    plugin, key = ctx._acquire_plugin(ctx.render_chunk(chunk, plan), planned=True)
    assert plugin is clients[0]
    # A different pace must retain an independent transport/settings identity.
    normal = SpeechPlan('normal', 'cartesia', DeliveryIntent())
    other, other_key = ctx._acquire_plugin(ctx.render_chunk(chunk, normal), planned=True)
    assert other is not plugin and other_key != key
    await ctx._release_plugin(plugin, key, healthy=True)
    await ctx._release_plugin(other, other_key, healthy=True)
    await ctx.aclose()
    assert all(client.closes == 1 for client in clients)


@pytest.mark.asyncio
async def test_only_completed_exclusive_lease_can_be_reused():
    pool = DeliveryClientPool()
    first, reused = pool.acquire('same-settings', Client)
    assert not reused
    concurrent, reused = pool.acquire('same-settings', Client)
    assert concurrent is not first and not reused
    await pool.release('same-settings', first, healthy=True)
    again, reused = pool.acquire('same-settings', Client)
    assert again is first and reused
    # An interrupted generation is retired, never returned as a healthy lease.
    await pool.release('same-settings', concurrent, healthy=False)
    assert concurrent.closes == 1 and first.closes == 0
    await pool.aclose()
    await pool.release('same-settings', again, healthy=True)
    assert first.closes == concurrent.closes == 1


@pytest.mark.asyncio
async def test_settings_and_tokenizer_identity_are_separate_and_idle_cache_is_bounded():
    pool = DeliveryClientPool(max_idle=2)
    clients = []
    for key in [(True, 'normal'), (True, 'slower'), (False, 'normal')]:
        client, reused = pool.acquire(key, Client)
        assert not reused
        clients.append(client)
        await pool.release(key, client, healthy=True)
    assert clients[0].closes == 1
    assert clients[1].closes == clients[2].closes == 0
    await pool.aclose()
    await pool.aclose()
    assert all(client.closes == 1 for client in clients)
    with pytest.raises(RuntimeError, match='closed'):
        pool.acquire('new', Client)


@pytest.mark.asyncio
async def test_duplicate_completed_lease_is_closed_without_replacing_cached_client():
    pool = DeliveryClientPool()
    first, _ = pool.acquire('same', Client)
    second, _ = pool.acquire('same', Client)
    await pool.release('same', first, healthy=True)
    await pool.release('same', second, healthy=True)
    assert second.closes == 1
    again, reused = pool.acquire('same', Client)
    assert again is first and reused
    await pool.aclose()


@pytest.mark.asyncio
async def test_delivery_context_reuses_across_replies_and_closes_at_session_end(monkeypatch):
    from test_humanization_batch_b import context

    class Output:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def __aiter__(self):
            yield NS(frame='synthetic-frame')

    class Voice(Client):
        capabilities = NS(streaming=False)

        def synthesize(self, *args, **kwargs):
            return Output()

    clients = []

    def build(*args, **kwargs):
        client = Voice()
        clients.append(client)
        return client

    monkeypatch.setattr('worker.providers.registry._build_tts', build)
    ctx = context('cartesia')
    ctx.enable_session_reuse()
    assert [frame async for frame in ctx.audio('Hello there.')] == ['synthetic-frame']
    assert [frame async for frame in ctx.audio('Welcome back.')] == ['synthetic-frame']
    assert len(clients) == 1 and clients[0].closes == 0
    await ctx.aclose()
    assert clients[0].closes == 1
