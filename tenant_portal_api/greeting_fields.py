"""Validate tenant greeting / first-speaker fields (untrusted agent config).

``greeting`` is DATA, same trust class as ``agents.prompt``: spoken via TTS when the agent
opens, never merged into platform system instructions.
"""

from __future__ import annotations

ALLOWED_FIRST_SPEAKERS = frozenset({"agent", "user"})
DEFAULT_FIRST_SPEAKER = "agent"
MAX_GREETING_CHARS = 500


class GreetingConfigError(ValueError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def normalize_greeting(value: str | None) -> str | None:
    """Return stripped greeting text, or None when omitted/blank (platform-generated greeting)."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise GreetingConfigError("invalid_greeting", "greeting must be a string")
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > MAX_GREETING_CHARS:
        raise GreetingConfigError(
            "invalid_greeting",
            f"greeting must be at most {MAX_GREETING_CHARS} characters",
        )
    return stripped


def normalize_first_speaker(
    value: str | None, *, default: str = DEFAULT_FIRST_SPEAKER
) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or value not in ALLOWED_FIRST_SPEAKERS:
        raise GreetingConfigError(
            "invalid_first_speaker",
            "first_speaker must be 'agent' or 'user'",
        )
    return value
