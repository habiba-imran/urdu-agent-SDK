"""Session-owned, exclusive leases for clients with identical delivery settings."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)


class DeliveryClientPool:
    def __init__(self, *, max_idle: int = 4):
        if max_idle < 1:
            raise ValueError('delivery client pool must retain at least one idle client')
        self.max_idle = max_idle
        self._idle = OrderedDict()
        self._clients = {}
        self._closed = False

    def prepare(self, key, factory):
        """Keep an idle client available for transport warm-up, without a lease.

        Active generations remain exclusive. Do not evict or grow the idle cache
        for speculative preparation; synthesis can still acquire normally.
        """
        if self._closed:
            return None, False
        if key in self._idle:
            return self._idle[key], False
        if len(self._idle) >= self.max_idle:
            return None, False
        client = factory()
        self._clients[id(client)] = client
        self._idle[key] = client
        return client, True

    def acquire(self, key, factory):
        if self._closed:
            raise RuntimeError('delivery client pool is closed')
        client = self._idle.pop(key, None)
        reused = client is not None
        if client is None:
            client = factory()
            self._clients[id(client)] = client
        return client, reused

    async def _retire(self, client):
        if self._clients.pop(id(client), None) is not None:
            await client.aclose()

    async def release(self, key, client, *, healthy: bool):
        if id(client) not in self._clients:
            return  # Session shutdown already owns this client's cleanup.
        if self._closed or not healthy or key in self._idle:
            await self._retire(client)
            return
        oldest = None
        if len(self._idle) >= self.max_idle:
            _, oldest = self._idle.popitem(last=False)
        # Finish all cache mutations before awaiting cleanup, so concurrent
        # releases cannot overwrite an idle lease or exceed the idle bound.
        self._idle[key] = client
        if oldest is not None:
            await self._retire(oldest)

    async def aclose(self):
        self._closed = True
        clients = list(self._clients.values())
        self._clients.clear()
        self._idle.clear()
        results = await asyncio.gather(*(client.aclose() for client in clients), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning('delivery client close failed error_type=%s', type(result).__name__)
