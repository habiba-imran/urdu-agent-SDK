"""Anthropic (Claude) LLM adapter — request-shape contracts.

Every assertion here corresponds to something verified against the live API on 2026-10-23
(see worker/providers/llm/anthropic.py's module docstring). The adapter's whole job is to
send a request shape current Claude models accept, so these tests guard that shape rather
than the plugin's internals.
"""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest

import worker.providers.llm.anthropic as adapter


class _FakeBaseLLM:
    """Stands in for livekit.plugins.anthropic.LLM."""

    instances: list["_FakeBaseLLM"] = []

    def __init__(self, **kwargs):
        self.ctor_kwargs = kwargs
        self.chat_calls: list[dict] = []
        self.closed = False
        _FakeBaseLLM.instances.append(self)

    def chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        return SimpleNamespace(marker="stream")

    async def aclose(self):
        self.closed = True


class _FakeAsyncAnthropic:
    instances: list["_FakeAsyncAnthropic"] = []

    def __init__(self, **kwargs):
        self.ctor_kwargs = kwargs
        self.list_calls = 0
        self.closed = False
        _FakeAsyncAnthropic.instances.append(self)
        outer = self

        class _Models:
            async def list(self, timeout=None):
                outer.list_calls += 1
                return SimpleNamespace(data=[])

        self.models = _Models()

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_plugin(monkeypatch):
    _FakeBaseLLM.instances = []
    _FakeAsyncAnthropic.instances = []

    plugin = ModuleType("livekit.plugins.anthropic")
    plugin.LLM = _FakeBaseLLM
    sdk = ModuleType("anthropic")
    sdk.AsyncAnthropic = _FakeAsyncAnthropic

    class _FakeHttpxClient:
        """Stands in for anthropic.DefaultAsyncHttpxClient (httpx2-backed)."""

        def __init__(self, **kwargs):
            self.limits = kwargs.get("limits")

    sdk.DefaultAsyncHttpxClient = _FakeHttpxClient

    import livekit.plugins

    monkeypatch.setitem(sys.modules, "livekit.plugins.anthropic", plugin)
    monkeypatch.setitem(sys.modules, "anthropic", sdk)
    # `from livekit.plugins import anthropic` reads the package attribute, not sys.modules
    # (the OB-F13 trap). Both are needed or the real plugin loads instead.
    monkeypatch.setattr(livekit.plugins, "anthropic", plugin, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-key")
    monkeypatch.delenv("ANTHROPIC_LLM_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MAX_TOKENS", raising=False)
    monkeypatch.delenv("ANTHROPIC_EFFORT", raising=False)
    monkeypatch.delenv("ANTHROPIC_THINKING", raising=False)
    return plugin


def test_never_sends_sampling_params_that_current_models_reject(fake_plugin):
    """temperature / top_k return HTTP 400 on claude-opus-5-5 and claude-haiku-5-5.

    Verified live 2026-10-23. The plugin forwards whatever it is handed and its own default
    model still accepts these, so a well-meaning copy of gemini.py's temperature=0.35 would
    break every turn. This is the single most important contract in the file.
    """
    adapter.build("claude-opus-5-5")
    ctor = _FakeBaseLLM.instances[0].ctor_kwargs
    assert "temperature" not in ctor
    assert "top_k" not in ctor


def test_enables_native_prompt_caching_without_changing_output_controls(fake_plugin):
    llm = adapter.build("claude-haiku-5-5")
    ctor = _FakeBaseLLM.instances[0].ctor_kwargs
    assert ctor["caching"] == "ephemeral"
    assert llm.voice_options["caching"] == "ephemeral"
    llm.chat(chat_ctx="ctx", extra_kwargs={"user": "fixture-user"})
    request = _FakeBaseLLM.instances[0].chat_calls[0]
    assert request["extra_kwargs"]["thinking"] == {"type": "disabled"}
    assert request["extra_kwargs"]["output_config"] == {"effort": "low"}
    assert request["extra_kwargs"]["user"] == "fixture-user"


def test_injects_effort_because_the_plugin_exposes_no_thinking_control(fake_plugin):
    llm = adapter.build("claude-opus-5-5")
    llm.chat(chat_ctx="ctx")

    call = _FakeBaseLLM.instances[0].chat_calls[0]
    assert call["extra_kwargs"] == {"output_config": {"effort": "low"}}
    assert call["chat_ctx"] == "ctx"


def test_effort_is_env_tunable_and_rejects_nonsense(fake_plugin, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_EFFORT", "xhigh")
    adapter.build("claude-opus-5-5").chat(chat_ctx="c")
    assert _FakeBaseLLM.instances[-1].chat_calls[0]["extra_kwargs"]["output_config"]["effort"] == "xhigh"

    monkeypatch.setenv("ANTHROPIC_EFFORT", "turbo")
    adapter.build("claude-opus-5-5").chat(chat_ctx="c")
    assert _FakeBaseLLM.instances[-1].chat_calls[0]["extra_kwargs"]["output_config"]["effort"] == "low"


def test_caller_supplied_extra_kwargs_is_not_clobbered(fake_plugin):
    llm = adapter.build("claude-opus-5-5")
    llm.chat(chat_ctx="ctx", extra_kwargs={"output_config": {"effort": "max"}, "user": "u1"})

    extra = _FakeBaseLLM.instances[0].chat_calls[0]["extra_kwargs"]
    assert extra["output_config"] == {"effort": "max"}, "an explicit caller value must win"
    assert extra["user"] == "u1"


def test_chat_passes_through_unknown_kwargs(fake_plugin):
    """Signature is **kwargs so a plugin upgrade cannot silently drop a new parameter."""
    llm = adapter.build("claude-opus-5-5")
    llm.chat(chat_ctx="ctx", tools=["t"], parallel_tool_calls=True, some_future_arg=1)

    call = _FakeBaseLLM.instances[0].chat_calls[0]
    assert call["tools"] == ["t"]
    assert call["parallel_tool_calls"] is True
    assert call["some_future_arg"] == 1


def test_max_tokens_is_capped_tight_for_spoken_replies(fake_plugin, monkeypatch):
    adapter.build("claude-opus-5-5")
    assert _FakeBaseLLM.instances[-1].ctor_kwargs["max_tokens"] == 320

    monkeypatch.setenv("ANTHROPIC_MAX_TOKENS", "400")
    adapter.build("claude-opus-5-5")
    assert _FakeBaseLLM.instances[-1].ctor_kwargs["max_tokens"] == 400

    # Clamped at both ends: an unbounded reply would dominate the output bill.
    monkeypatch.setenv("ANTHROPIC_MAX_TOKENS", "999999")
    adapter.build("claude-opus-5-5")
    assert _FakeBaseLLM.instances[-1].ctor_kwargs["max_tokens"] == 2048

    monkeypatch.setenv("ANTHROPIC_MAX_TOKENS", "not-a-number")
    adapter.build("claude-opus-5-5")
    assert _FakeBaseLLM.instances[-1].ctor_kwargs["max_tokens"] == 320


def test_empty_model_resolves_to_the_repo_default_not_the_plugin_default(fake_plugin, monkeypatch):
    """The plugin's own default is claude-sonnet-4-6 — a different generation."""
    assert adapter.resolve_anthropic_model("") == ("claude-haiku-5-5", "empty_model")

    monkeypatch.setenv("ANTHROPIC_LLM_MODEL", "claude-opus-5-5")
    assert adapter.resolve_anthropic_model("") == ("claude-opus-5-5", "empty_model")
    # An explicit agent-row model is always honoured.
    assert adapter.resolve_anthropic_model("claude-sonnet-5-5") == ("claude-sonnet-5-5", None)


def test_missing_api_key_fails_loudly_at_construction(fake_plugin, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        adapter.build("claude-opus-5-5")


def test_prewarm_opens_the_connection_without_spending_tokens(fake_plugin):
    llm = adapter.build("claude-opus-5-5")

    async def run():
        await llm.prewarm()
        await llm.prewarm()  # inside the 30s window — must not re-dial

    asyncio.run(run())
    client = _FakeAsyncAnthropic.instances[0]
    # models.list is free; a completion would bill against the development budget.
    assert client.list_calls == 1


def test_sync_sdk_prewarm_shares_pending_task_and_close_cancels_it(fake_plugin):
    llm = adapter.build('claude-haiku-5-5')

    async def run():
        started = asyncio.Event()

        async def pending(**kwargs):
            started.set()
            await asyncio.Event().wait()

        llm._transport_client.models.list = pending
        # LiveKit calls the hook without awaiting it. It must start the work.
        task = llm.prewarm()
        assert not asyncio.iscoroutine(task)
        await started.wait()
        assert llm.prewarm() is task
        await llm.aclose()
        assert task.cancelled()

    asyncio.run(run())
    assert _FakeAsyncAnthropic.instances[0].closed


def test_client_disables_sdk_retries_so_they_cannot_stack_in_the_watchdog(fake_plugin):
    adapter.build("claude-opus-5-5")
    assert _FakeAsyncAnthropic.instances[0].ctor_kwargs["max_retries"] == 0


def test_aclose_closes_both_the_plugin_and_our_client(fake_plugin):
    llm = adapter.build("claude-opus-5-5")
    asyncio.run(llm.aclose())
    assert _FakeBaseLLM.instances[0].closed is True
    assert _FakeAsyncAnthropic.instances[0].closed is True


def test_registry_dispatches_the_anthropic_provider(fake_plugin):
    from worker.providers.registry import _build_llm

    cfg = SimpleNamespace(llm_provider="anthropic", llm_model="claude-haiku-5-5")
    _build_llm(cfg)
    assert _FakeBaseLLM.instances[-1].ctor_kwargs["model"] == "claude-haiku-5-5"


def test_capabilities_offer_anthropic_for_both_languages():
    from worker.providers.capabilities import allowed_llm_models, llm_capability

    for language in ("ur", "en"):
        cap = llm_capability(language, "anthropic")
        assert cap is not None, f"anthropic missing for {language}"
        assert cap["state"] == "enabled"
        assert cap["default_model"] == "claude-haiku-5-5"
        # Portal validation is capability-driven, so this set is what agent rows may carry.
        assert {"claude-opus-5-5", "claude-haiku-5-5"} <= set(allowed_llm_models(cap))


# --- thinking: the control that decides whether a turn produces any text at all ---------


def test_thinking_off_value_is_per_model_because_the_wrong_one_is_a_400():
    """Verified against the live API 2026-10-23:

        haiku-5-5   disabled 200   between_tools 400
        sonnet-5-5  disabled 400   between_tools 200
        opus-5-5    both 400 -- thinking cannot be switched off there

    Sending the wrong value fails the whole turn, so this is a table lookup, not a guess.
    """
    assert adapter.resolve_thinking("claude-haiku-5-5") == {"type": "disabled"}
    assert adapter.resolve_thinking("claude-sonnet-5-5") == {"type": "between_tools"}
    assert adapter.resolve_thinking("claude-opus-5-5") is None
    # An unrecognised model is left alone rather than sent a value its API may reject.
    assert adapter.resolve_thinking("claude-future-9") is None


def test_thinking_is_sent_with_effort_on_every_request(fake_plugin):
    """A thinking-only response streams no text deltas at all.

    The plugin maps a text delta to a chat chunk and drops every other event, so a turn
    that spends its whole max_tokens budget on thinking yields zero content and
    worker/provider_retries.py raises "LLM returned no useful output" -- which ends the
    call, not just the turn. That is what killed the 2026-10-23 staging sessions.
    """
    adapter.build("claude-haiku-5-5").chat(chat_ctx="ctx")
    extra = _FakeBaseLLM.instances[-1].chat_calls[0]["extra_kwargs"]
    assert extra["thinking"] == {"type": "disabled"}
    assert extra["output_config"] == {"effort": "low"}


def test_thinking_can_be_left_on_deliberately(fake_plugin, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_THINKING", "on")
    adapter.build("claude-haiku-5-5").chat(chat_ctx="ctx")
    assert "thinking" not in _FakeBaseLLM.instances[-1].chat_calls[0]["extra_kwargs"]


def test_opus_never_receives_a_thinking_field_it_would_reject(fake_plugin):
    adapter.build("claude-opus-5-5").chat(chat_ctx="ctx")
    assert "thinking" not in _FakeBaseLLM.instances[-1].chat_calls[0]["extra_kwargs"]


def test_connection_is_kept_alive_across_conversational_turns(fake_plugin):
    """keepalive_expiry defaults to 5s; turns are ~10s apart.

    Without this the pooled connection expired between every turn and each one paid a
    fresh TCP + TLS handshake -- 84ms + 88ms in the staging log.
    """
    adapter.build("claude-haiku-5-5")
    limits = _FakeAsyncAnthropic.instances[0].ctor_kwargs["http_client"].limits
    assert limits.keepalive_expiry == 120
    assert limits.max_keepalive_connections == 50
