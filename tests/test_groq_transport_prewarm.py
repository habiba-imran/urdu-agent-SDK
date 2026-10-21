"""Connection warm-up uses the same public client as chat, without completions."""
import asyncio
import sys
from types import SimpleNamespace

import httpx
import openai
import pytest
from worker.providers.llm import groq
from worker.latency import prewarm_llm


@pytest.mark.parametrize("status", [200, 503])
def test_transport_warmup_never_generates_or_retries(monkeypatch, status):
    async def run():
        requests = []
        async def respond(request):
            requests.append((request.method, request.url.path))
            if status != 200:
                return httpx.Response(status, json={"error": {"message": "unavailable"}})
            return httpx.Response(200, json={"object": "list", "data": []})
        client = openai.AsyncClient(api_key="fixture-not-a-secret", base_url="https://api.groq.com/openai/v1",
            max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        monkeypatch.setenv("GROQ_API_KEY", "fixture-not-a-secret")
        monkeypatch.setattr(groq, "_make_transport_client", lambda: client)
        provider = groq.build("openai/gpt-oss-20b")
        try:
            if status == 200:
                await prewarm_llm(provider)
                await prewarm_llm(provider)
            else:
                with pytest.raises(openai.APIStatusError):
                    await provider.prewarm()
            assert requests == [("GET", "/openai/v1/models")]
            assert provider.model == "openai/gpt-oss-20b"
        finally:
            await provider.aclose()
        assert client.is_closed()
    asyncio.run(run())


def test_qwen_models_never_request_an_unsupported_reasoning_effort(monkeypatch):
    """Groq rejects reasoning_effort="none" with HTTP 400 (L-07).

    Verified against the live API on 2026-10-21:
      `reasoning_effort` must be one of `low`, `medium`, or `high`

    Every qwen id resolves away through _DEAD_GROQ_MODELS today, so the old branch was
    unreachable. This pins the value so a future live qwen id cannot 400 every turn.
    """
    import worker.providers.llm.groq as groq_adapter

    captured: dict = {}

    class FakeLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_plugin = SimpleNamespace(LLM=FakeLLM)
    monkeypatch.setitem(sys.modules, "livekit.plugins.groq", fake_plugin)
    # `from livekit.plugins import groq` reads the package attribute, not sys.modules.
    import livekit.plugins

    monkeypatch.setattr(livekit.plugins, "groq", fake_plugin, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fixture-key")
    # Bypass the dead-model remap so the qwen branch is actually exercised.
    monkeypatch.setattr(groq_adapter, "resolve_groq_model",
                        lambda model: ("qwen/qwen-future-99b", None))

    groq_adapter.build("qwen/qwen-future-99b")

    assert captured.get("reasoning_effort") in {"low", "medium", "high"}, (
        f"Groq rejects reasoning_effort={captured.get('reasoning_effort')!r} with HTTP 400"
    )
