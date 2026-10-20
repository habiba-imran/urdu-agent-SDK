"""Cartesia TTS adapter (Phase 6c, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py (provider level) AND
the specific voice row's own `rollout_state`/`enabled` in the `voices` table are both the real
gates, not this file. Constructor args verified against livekit-plugins-cartesia==1.6.5:
`model`, `voice`, `language`, `speed`, `emotion`, `volume` (see upstream tts.py).

Phase B humanization defaults (sonic-3.5, speed 0.95, emotion calm+content) and Phase C audio
profiles (webrtc pcm_s16le 16kHz / telephony pcm_mulaw 8kHz) live in cartesia_options.py.

Requires CARTESIA_API_KEY (env var, or api_key= kwarg) — the plugin itself raises a clear
ValueError if neither is set, checked eagerly at construction (same pattern as every other
provider adapter in this repo).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .cartesia_options import low_latency_cartesia_tokenizer, resolve_cartesia_tts_kwargs

logger = logging.getLogger(__name__)


def build(voice_id: str, language: str, tts_options: dict | None = None, *, audio_channel: str = "webrtc", tokenizer=None) -> Any:
    from livekit.plugins import cartesia

    class InterruptionReadyCartesia(cartesia.TTS):
        _interruption_warm_task: asyncio.Task | None = None
        _closing = False

        def prewarm_after_interruption(self) -> None:
            if self._closing or (self._interruption_warm_task is not None and not self._interruption_warm_task.done()):
                return

            async def warm() -> None:
                try:
                    # Pinned plugin 1.6.5 removes cancelled sockets from its pool.
                    # ConnectionPool.prewarm's retained one-shot task prevents a
                    # second warm-up. Borrow/return through the same pool instead;
                    # never reuse the cancelled stream or consume stale audio.
                    async def acquire() -> None:
                        connection = await self._pool.get(timeout=4.0)
                        self._pool.put(connection)
                    await asyncio.wait_for(acquire(), timeout=4.0)
                    logger.debug("Cartesia interruption transport prepared")
                except Exception as exc:
                    logger.warning("Cartesia interruption prewarm unavailable error_type=%s", type(exc).__name__)

            self._interruption_warm_task = asyncio.create_task(warm(), name="cartesia_interruption_prewarm")

        def cancel_interruption_prewarm(self) -> None:
            task = self._interruption_warm_task
            if task is not None and not task.done():
                task.cancel()

        async def aclose(self) -> None:
            self._closing = True
            self.cancel_interruption_prewarm()
            if self._interruption_warm_task is not None:
                await asyncio.gather(self._interruption_warm_task, return_exceptions=True)
            await super().aclose()

    return InterruptionReadyCartesia(
        **resolve_cartesia_tts_kwargs(
            voice_id, language, tts_options, audio_channel=audio_channel
        ),
        # Default blingfire SentenceTokenizer buffers ~10 chars + full sentences before
        # websocket send — adds multi-second dead air during in-call turns (UVA-4).
        tokenizer=tokenizer if tokenizer is not None else low_latency_cartesia_tokenizer(),
        word_timestamps=False,
    )
