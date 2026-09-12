"""Unit tests for session opening: wait vs custom say vs generated greeting."""

import asyncio
from types import SimpleNamespace

from worker.config import AgentConfig
from worker.session_opening import apply_session_opening, resolve_session_opening


def _cfg(**overrides) -> AgentConfig:
    base = dict(
        agent_id="a",
        tenant_id="t",
        name="n",
        prompt="persona",
        voice_id="v",
        llm_model="gemini-2.5-flash",
    )
    base.update(overrides)
    return AgentConfig(**base)


def test_default_opens_with_generated_greeting():
    opening = resolve_session_opening(_cfg())
    assert opening.mode == "generate_reply"
    assert opening.instructions


def test_user_first_waits_even_with_custom_greeting():
    opening = resolve_session_opening(
        _cfg(greeting="Hi, thanks for calling.", first_speaker="user")
    )
    assert opening.mode == "wait"
    assert opening.text is None


def test_custom_greeting_uses_say():
    opening = resolve_session_opening(
        _cfg(greeting="Hi, thanks for calling Acme. How can I help?")
    )
    assert opening.mode == "say"
    assert opening.text == "Hi, thanks for calling Acme. How can I help?"


def test_cartesia_custom_greeting_strips_markdown():
    opening = resolve_session_opening(
        _cfg(
            tts_provider="cartesia",
            greeting="**Hi** there, thanks for calling.",
        )
    )
    assert opening.mode == "say"
    assert "**" not in (opening.text or "")
    assert "Hi there, thanks for calling." in (opening.text or "")


def test_rime_custom_greeting_strips_cartesia_ssml():
    opening = resolve_session_opening(
        _cfg(
            tts_provider="rime",
            greeting='Hi **there** <break time="300ms"/> thanks for calling.',
        )
    )
    assert opening.mode == "say"
    assert "<break" not in (opening.text or "")
    assert "**" not in (opening.text or "")
    assert "thanks for calling" in (opening.text or "")


def test_apply_session_opening_dispatches():
    class FakeHandle:
        def __init__(self):
            self.interrupted = False
            self._exception = None
            self.waited = False

        async def wait_for_playout(self):
            self.waited = True

        def exception(self):
            return self._exception

    class FakeSession:
        def __init__(self):
            self.said = None
            self.say_kwargs = None
            self.generated = None
            self.generate_kwargs = None
            self.last_handle = None

        def say(self, text, **kwargs):
            self.said = text
            self.say_kwargs = kwargs
            self.last_handle = FakeHandle()
            return self.last_handle

        def generate_reply(self, instructions=None, **kwargs):
            self.generated = instructions
            self.generate_kwargs = kwargs
            self.last_handle = FakeHandle()
            return self.last_handle

    logger = SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None)

    wait_session = FakeSession()
    asyncio.run(apply_session_opening(wait_session, _cfg(first_speaker="user"), logger))
    assert wait_session.said is None
    assert wait_session.generated is None

    say_session = FakeSession()
    asyncio.run(apply_session_opening(say_session, _cfg(greeting="Hello there."), logger))
    assert say_session.said == "Hello there."
    assert say_session.say_kwargs == {"allow_interruptions": False}
    assert say_session.generated is None

    tel_session = FakeSession()
    asyncio.run(
        apply_session_opening(
            tel_session,
            _cfg(greeting="Hello there."),
            logger,
            allow_interruptions=True,
        )
    )
    assert tel_session.said == "Hello there."
    assert tel_session.say_kwargs == {"allow_interruptions": True}

    gen_session = FakeSession()
    asyncio.run(apply_session_opening(gen_session, _cfg(), logger))
    assert gen_session.said is None
    assert gen_session.generated
    assert gen_session.generate_kwargs == {"allow_interruptions": False}
