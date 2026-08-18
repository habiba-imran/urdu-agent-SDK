"""Unit tests for greeting / first_speaker validation."""

from tenant_portal_api.greeting_fields import (
    MAX_GREETING_CHARS,
    GreetingConfigError,
    normalize_first_speaker,
    normalize_greeting,
)


def test_blank_greeting_becomes_none():
    assert normalize_greeting(None) is None
    assert normalize_greeting("") is None
    assert normalize_greeting("   ") is None


def test_greeting_is_stripped():
    assert normalize_greeting("  Hi there.  ") == "Hi there."


def test_greeting_rejects_over_max():
    try:
        normalize_greeting("x" * (MAX_GREETING_CHARS + 1))
        raise AssertionError("expected GreetingConfigError")
    except GreetingConfigError as exc:
        assert exc.code == "invalid_greeting"


def test_first_speaker_defaults_and_accepts_user():
    assert normalize_first_speaker(None) == "agent"
    assert normalize_first_speaker("user") == "user"
    assert normalize_first_speaker("agent") == "agent"


def test_first_speaker_rejects_unknown():
    try:
        normalize_first_speaker("both")
        raise AssertionError("expected GreetingConfigError")
    except GreetingConfigError as exc:
        assert exc.code == "invalid_first_speaker"
