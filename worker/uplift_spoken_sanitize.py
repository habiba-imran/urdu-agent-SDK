"""Pre-TTS sanitizer for Uplift — light markdown/emoji cleanup; no English SSML kept."""

from __future__ import annotations

from worker.plain_spoken_sanitize import (
    strip_foreign_tts_markup,
    strip_markdown_emoji_bullets,
)


def sanitize_spoken_text(text: str) -> str:
    if not text:
        return text
    out = strip_foreign_tts_markup(text, strip_brackets=True)
    return strip_markdown_emoji_bullets(out).strip()
