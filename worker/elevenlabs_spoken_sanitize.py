"""Pre-TTS sanitizer for ElevenLabs — strip Cartesia/Fish markup and markdown.

Phase 5C: when ``spoken_style=audio_tags`` is active on a v3-capable plugin, keep a
small set of ``[tag]`` audio cues; otherwise strip all brackets.
"""

from __future__ import annotations

import re

from worker.plain_spoken_sanitize import (
    BRACKET_CUE_RE,
    strip_foreign_tts_markup,
    strip_markdown_emoji_bullets,
)
from worker.providers.tts.elevenlabs_options import elevenlabs_audio_tags_enabled

# Restrained ElevenLabs-style audio tags (research §9). Not Cartesia/Fish stage directions.
_ELEVEN_AUDIO_TAG_ALLOWLIST = frozenset(
    {
        "laughs",
        "laugh",
        "sighs",
        "sigh",
        "exhales",
        "clears throat",
    }
)


def _keep_eleven_audio_tags(match: re.Match[str]) -> str:
    inner = (match.group(0)[1:-1] or "").strip().lower()
    if inner in _ELEVEN_AUDIO_TAG_ALLOWLIST:
        return match.group(0)
    return ""


def sanitize_spoken_text(text: str, *, tts_options: dict | None = None) -> str:
    if not text:
        return text
    if elevenlabs_audio_tags_enabled(tts_options):
        out = strip_foreign_tts_markup(text, strip_brackets=False)
        out = BRACKET_CUE_RE.sub(_keep_eleven_audio_tags, out)
    else:
        out = strip_foreign_tts_markup(text, strip_brackets=True)
    return strip_markdown_emoji_bullets(out).strip()
