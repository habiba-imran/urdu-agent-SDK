"""F-M24 — gate caller/agent transcript text in application logs.

Default **off**: log only character counts (no PII in log aggregators).
Set ``UVA_LOG_TRANSCRIPTS=1`` for local debug; text is capped at
``UVA_LOG_TRANSCRIPT_CHARS`` (default 200).
"""

from __future__ import annotations

import os

_TRUTH_ON = frozenset({"1", "true", "yes", "on"})
_TRUTH_OFF = frozenset({"0", "false", "no", "off", ""})
_DEFAULT_MAX_CHARS = 200


def log_transcripts_enabled() -> bool:
    """True only when ``UVA_LOG_TRANSCRIPTS`` is explicitly on (default off)."""
    raw = (os.getenv("UVA_LOG_TRANSCRIPTS") or "").strip().lower()
    if raw in _TRUTH_OFF:
        return False
    return raw in _TRUTH_ON


def transcript_log_max_chars() -> int:
    raw = (os.getenv("UVA_LOG_TRANSCRIPT_CHARS") or "").strip()
    if not raw:
        return _DEFAULT_MAX_CHARS
    try:
        n = int(raw)
    except ValueError:
        return _DEFAULT_MAX_CHARS
    return max(0, n)


def format_transcript_for_log(text: str | None) -> tuple[str, int]:
    """Return ``(log_fragment, char_count)`` for INFO lines.

    When logging is disabled, ``log_fragment`` is empty (caller should use chars= only).
    When enabled, ``log_fragment`` is the truncated text suitable for ``text=%r``.
    """
    raw = text or ""
    n = len(raw)
    if not log_transcripts_enabled():
        return "", n
    max_chars = transcript_log_max_chars()
    if max_chars == 0:
        return "", n
    return raw[:max_chars], n
