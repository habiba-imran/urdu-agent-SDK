"""Bound the first ordinary speech chunk's punctuation wait for Claude only."""
from __future__ import annotations

import asyncio
import math
import os

from livekit.agents import tokenize
from .streaming import SpeechChunkPlanner


def first_chunk_wait_seconds():
    try:
        value = float(os.getenv('UVA_CLAUDE_FIRST_CHUNK_WAIT_MS', '120'))
        return value / 1000 if math.isfinite(value) and 30 <= value <= 500 else .12
    except ValueError:
        return .12


async def deadline_chunks(source, planner, prepare, *, valid=None):
    """A timeout never cancels an in-flight text read or ends the TTS context."""
    iterator = source.__aiter__()
    pending = None
    deadline = None
    expired = False
    try:
        while True:
            pending = asyncio.create_task(anext(iterator))
            while True:
                timeout = max(0, deadline-asyncio.get_running_loop().time()) if deadline is not None and not expired else None
                done, _ = await asyncio.wait([pending], timeout=timeout)
                if done:
                    break
                expired = True
                if valid is not None and not valid():
                    return
                for chunk in planner.release_first_safe_prefix():
                    yield chunk
            try:
                piece = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            if valid is not None and not valid():
                return
            if deadline is None and piece:
                deadline = asyncio.get_running_loop().time() + first_chunk_wait_seconds()
            for chunk in prepare(piece):
                yield chunk
            if expired:
                for chunk in planner.release_first_safe_prefix():
                    yield chunk
    finally:
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


class ClaudeSentenceTokenizer(tokenize.SentenceTokenizer):
    def __init__(self, provider):
        self.provider = provider

    def tokenize(self, text, *, language=None):
        planner = SpeechChunkPlanner(self.provider)
        return [chunk.text for chunk in [*planner.feed(text), *planner.finish()]]

    def stream(self, *, language=None):
        return ClaudeSentenceStream(self.provider)


class ClaudeSentenceStream(tokenize.SentenceStream):
    def __init__(self, provider):
        super().__init__()
        self.provider = provider
        self.planner = SpeechChunkPlanner(provider)
        self.timer = None
        self.expired = False

    def emit(self, chunks):
        for chunk in chunks:
            self._event_ch.send_nowait(tokenize.TokenData(segment_id='claude_clause', token=chunk.text))

    def release(self):
        self.expired = True
        if not self.closed:
            self.emit(self.planner.release_first_safe_prefix())

    def push_text(self, text):
        self._check_not_closed()
        if text and self.timer is None:
            self.timer = asyncio.get_running_loop().call_later(first_chunk_wait_seconds(), self.release)
        self.emit(self.planner.feed(text))
        if self.expired:
            self.emit(self.planner.release_first_safe_prefix())

    def flush(self):
        self._check_not_closed()
        if self.timer is not None:
            self.timer.cancel()
        self.emit(self.planner.finish())
        self.planner = SpeechChunkPlanner(self.provider)
        self.timer = None
        self.expired = False

    def end_input(self):
        self.flush()
        self._do_close()

    async def aclose(self):
        if self.timer is not None:
            self.timer.cancel()
        self.planner.clear()
        self._do_close()
