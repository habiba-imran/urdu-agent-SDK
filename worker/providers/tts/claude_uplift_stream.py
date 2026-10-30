"""Use the public segment adapter where native Uplift buffers until end_input."""
from livekit.agents.tts import StreamAdapter

from worker.humanization.chunk_latency import ClaudeSentenceTokenizer


class ClaudeUpliftStreamAdapter(StreamAdapter):
    def __init__(self, provider):
        super().__init__(tts=provider, sentence_tokenizer=ClaudeSentenceTokenizer('uplift'))
        self._closed = False

    def prewarm(self):
        return self._wrapped_tts.prewarm()

    def prewarm_after_interruption(self):
        self._wrapped_tts.prewarm_after_interruption()

    def cancel_interruption_prewarm(self):
        self._wrapped_tts.cancel_interruption_prewarm()

    async def aclose(self):
        if self._closed:
            return
        self._closed = True
        try:
            await super().aclose()
        finally:
            # StreamAdapter detaches its listeners but does not own client close.
            await self._wrapped_tts.aclose()
