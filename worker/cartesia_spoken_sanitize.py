"""Pre-TTS spoken-text sanitizer for Cartesia (Phase D).

Safety net if the LLM still emits markdown or emoji. Cartesia SSML-like tags
(``<break>``, ``<emotion>``, ``<spell>``, ``<speed>``, ``<volume>``) and ``[laughter]``
are preserved — LiveKit's default ``filter_markdown`` can strip angle-bracket tags,
so Cartesia sessions must use this transform instead of the built-in pair.
"""

from __future__ import annotations

import re

_SSML_TAG_RE = re.compile(
    r"</?(?:break|emotion|spell|speed|volume)\b[^>]*>",
    re.IGNORECASE,
)
_MARKDOWN_RE = re.compile(r"[*_`#]+")
_BULLET_RE = re.compile(r"(?m)^\s*[-•]\s+")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+"
)
_PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")
_LAUGHTER_TOKEN = "[laughter]"
_LAUGHTER_PLACEHOLDER = "\x00LAUGH\x00"


def sanitize_spoken_text(text: str) -> str:
    """Strip markdown and emoji; keep Cartesia SSML tags and [laughter]."""
    if not text:
        return text

    held: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        held.append(match.group(0))
        return f"\x00{len(held) - 1}\x00"

    out = _SSML_TAG_RE.sub(_stash, text)
    out = out.replace(_LAUGHTER_TOKEN, _LAUGHTER_PLACEHOLDER)
    out = _MARKDOWN_RE.sub("", out)
    out = _BULLET_RE.sub("", out)
    out = _EMOJI_RE.sub("", out)
    out = out.replace(_LAUGHTER_PLACEHOLDER, _LAUGHTER_TOKEN)

    def _restore(match: re.Match[str]) -> str:
        return held[int(match.group(1))]

    out = _PLACEHOLDER_RE.sub(_restore, out)
    return re.sub(r"[ \t]{2,}", " ", out)
