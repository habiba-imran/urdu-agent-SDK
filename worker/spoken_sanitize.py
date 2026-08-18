"""Dispatch the provider-correct pre-TTS sanitizer.

Cartesia keeps SSML; Rime strips SSML and keeps spell(). Never cross-apply.
"""

from __future__ import annotations

from collections.abc import Callable


def sanitizer_for_provider(tts_provider: str) -> Callable[[str], str] | None:
    if tts_provider == "cartesia":
        from .cartesia_spoken_sanitize import sanitize_spoken_text

        return sanitize_spoken_text
    if tts_provider == "rime":
        from .rime_spoken_sanitize import sanitize_spoken_text

        return sanitize_spoken_text
    return None
