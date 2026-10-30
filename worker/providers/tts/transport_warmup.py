"""Owned, single-flight transport preparation. Never sends synthesis text."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class TransportWarmupMixin:
    _voice_transport_task = None
    _voice_transport_closed = False

    def prepare_transport(self):
        if self._voice_transport_closed:
            return
        if self._voice_transport_task is not None and not self._voice_transport_task.done():
            return
        async def warm():
            try:
                async with asyncio.timeout(4):
                    await self._prepare_voice_transport()
            except Exception as error:
                logger.warning('TTS transport preparation failed provider=%s error_type=%s',
                               self.__class__.__name__, type(error).__name__)
        self._voice_transport_task = asyncio.create_task(warm(), name='tts_transport_prepare')

    def prewarm_after_interruption(self):
        self.prepare_transport()

    def cancel_interruption_prewarm(self):
        if self._voice_transport_task is not None and not self._voice_transport_task.done():
            self._voice_transport_task.cancel()

    async def aclose(self):
        self._voice_transport_closed = True
        self.cancel_interruption_prewarm()
        if self._voice_transport_task is not None:
            await asyncio.gather(self._voice_transport_task, return_exceptions=True)
        await super().aclose()
