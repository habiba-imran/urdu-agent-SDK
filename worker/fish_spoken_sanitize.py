"""Pre-TTS sanitizer for Fish Audio — strip Cartesia XML; bracket policy by spoken_style.

Default (plain): strip all ``[...]`` cues so leaked tags are never spoken.
Phase 5D restrained: keep only ``FISH_RESTRAINED_BRACKET_ALLOWLIST`` bodies.
"""

from __future__ import annotations

import re

from worker.plain_spoken_sanitize import (
    BRACKET_CUE_RE,
    strip_foreign_tts_markup,
    strip_markdown_emoji_bullets,
)
from worker.providers.tts.fish_audio_options import (
    FISH_RESTRAINED_BRACKET_ALLOWLIST,
    fish_restrained_spoken_enabled,
)


def _keep_restrained_brackets(match: re.Match[str]) -> str:
    inner = (match.group(0)[1:-1] or "").strip().lower()
    # Allow exact allowlist tokens or "laughing nervously"-style if first word allowlisted.
    head = inner.split()[0] if inner else ""
    if inner in FISH_RESTRAINED_BRACKET_ALLOWLIST or head in FISH_RESTRAINED_BRACKET_ALLOWLIST:
        return match.group(0)
    return ""


def sanitize_spoken_text(text: str, *, tts_options: dict | None = None) -> str:
    if not text:
        return text
    if fish_restrained_spoken_enabled(tts_options):
        out = strip_foreign_tts_markup(text, strip_brackets=False)
        out = BRACKET_CUE_RE.sub(_keep_restrained_brackets, out)
    else:
        out = strip_foreign_tts_markup(text, strip_brackets=True)
    return strip_markdown_emoji_bullets(out).strip()
