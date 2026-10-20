"""Connection warm-up uses the same public client as chat, without completions."""
import asyncio
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
