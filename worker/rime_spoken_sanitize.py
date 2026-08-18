"""Pre-TTS spoken-text sanitizer for Rime Coda/Arcana.

Safety net if the LLM still emits markdown, emoji, Cartesia SSML, or Mist ``<750>`` pauses.
Coda would read those tags aloud. Rime ``spell()`` directives are preserved; Cartesia
``<spell>X</spell>`` is rewritten to ``spell(X)`` so an agent switched from Cartesia still
pronounces IDs correctly.
"""

from __future__ import annotations

import re

_SPELL_FN_RE = re.compile(r"spell\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE)
_CARTESIA_SPELL_TAG_RE = re.compile(
    r"<spell>(.*?)</spell>", re.IGNORECASE | re.DOTALL
)
_SSML_TAG_RE = re.compile(
    r"</?(?:break|emotion|spell|speed|volume)\b[^>]*>",
    re.IGNORECASE,
)
_MIST_PAUSE_RE = re.compile(r"<\d{2,4}>")
_LAUGHTER_RE = re.compile(r"\[laughter\]", re.IGNORECASE)
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


def sanitize_spoken_text(text: str) -> str:
    """Strip markdown, emoji, and Cartesia/Mist tags; keep Rime spell()."""
    if not text:
        return text

    held: list[str] = []

    def _stash(value: str) -> str:
        held.append(value)
        return f"\x00{len(held) - 1}\x00"

    out = _CARTESIA_SPELL_TAG_RE.sub(
        lambda m: f"spell({m.group(1).strip()})", text
    )

    def _stash_spell(match: re.Match[str]) -> str:
        return _stash(f"spell({match.group(1).strip()})")

    out = _SPELL_FN_RE.sub(_stash_spell, out)
    out = _SSML_TAG_RE.sub("", out)
    out = _MIST_PAUSE_RE.sub("", out)
    out = _LAUGHTER_RE.sub("", out)
    out = _MARKDOWN_RE.sub("", out)
    out = _BULLET_RE.sub("", out)
    out = _EMOJI_RE.sub("", out)

    def _restore(match: re.Match[str]) -> str:
        return held[int(match.group(1))]

    out = _PLACEHOLDER_RE.sub(_restore, out)
    return re.sub(r"[ \t]{2,}", " ", out)
