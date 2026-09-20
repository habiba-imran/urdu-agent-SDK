"""Shared plain-spoken cleanup helpers for non-Cartesia TTS sanitizers."""

from __future__ import annotations

import re

SSML_TAG_RE = re.compile(
    r"</?(?:break|emotion|spell|speed|volume)\b[^>]*>",
    re.IGNORECASE,
)
CARTESIA_SPELL_TAG_RE = re.compile(
    r"<spell>(.*?)</spell>", re.IGNORECASE | re.DOTALL
)
MIST_PAUSE_RE = re.compile(r"<\d{2,4}>")
# Fish-style bracket cues and leaked [laughter] / audio tags.
BRACKET_CUE_RE = re.compile(r"\[[^\[\]]{1,64}\]")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BARE_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
MARKDOWN_RE = re.compile(r"[*_`#]+")
BULLET_RE = re.compile(r"(?m)^\s*[-•]\s+")
ORDERED_RE = re.compile(r"(?m)^\s*\d+[.)]\s+")
BLOCKQUOTE_RE = re.compile(r"(?m)^\s*>\s+")
EMOJI_RE = re.compile(
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


def strip_markdown_emoji_bullets(text: str) -> str:
    out = MARKDOWN_LINK_RE.sub(r"\1", text)
    out = BARE_URL_RE.sub("", out)
    out = MARKDOWN_RE.sub("", out)
    out = BULLET_RE.sub("", out)
    out = ORDERED_RE.sub("", out)
    out = BLOCKQUOTE_RE.sub("", out)
    out = EMOJI_RE.sub("", out)
    return re.sub(r"[ \t]{2,}", " ", out)


def strip_foreign_tts_markup(text: str, *, strip_brackets: bool = True) -> str:
    """Remove Cartesia/Mist/Fish markup that would be read aloud by plain TTS."""
    out = CARTESIA_SPELL_TAG_RE.sub(r"\1", text)
    out = SSML_TAG_RE.sub("", out)
    out = MIST_PAUSE_RE.sub("", out)
    if strip_brackets:
        out = BRACKET_CUE_RE.sub("", out)
    return out
