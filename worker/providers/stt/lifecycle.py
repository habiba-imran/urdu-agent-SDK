"""Retain final STT usage after framework listeners detach; do not time out silence."""
from typing import Any


class _HeartbeatSession:
    def __init__(self, session): self._session = session
    def __getattr__(self, name): return getattr(self._session, name)
    def ws_connect(self, *args, **kwargs):
        kwargs.setdefault("heartbeat", 10.0)
        return self._session.ws_connect(*args, **kwargs)


def metered(provider: Any) -> Any:
    original_stream = getattr(provider, "stream", None)
    if not callable(original_stream):
        return provider
    provider._awaaz_direct_stt_usage = True
    def stream(*args, **kwargs):
        result = original_stream(*args, **kwargs)
        collector = getattr(result, "_audio_duration_collector", None)
        if collector is None or not hasattr(collector, "_callback"):
            raise RuntimeError("Unsupported STT plugin usage collector; check the pinned LiveKit version")
        callback = collector._callback
        def collect(duration):
            provider.emit("awaaz_stt_usage", duration)
            if not result._event_ch.closed:
                callback(duration)
        collector._callback = collect
        original_close = result.aclose
        async def close():
            try:
                await original_close()
            finally:
                collector.flush()
        result.aclose = close
        result._session = _HeartbeatSession(result._session)
        return result
    provider.stream = stream
    return provider
