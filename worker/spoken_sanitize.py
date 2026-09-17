"""Dispatch the provider-correct pre-TTS sanitizer.

Cartesia keeps SSML; other providers strip foreign markup. Never cross-apply Cartesia
preservation rules to Rime/ElevenLabs/Fish/Uplift.

Stream path: use ``make_stream_sanitizer`` so tags split across LLM chunks are not
spoken aloud (whole-string regexes are unsafe per-chunk).
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Callable


def sanitizer_for_provider(
    tts_provider: str,
    *,
    tts_options: dict | None = None,
    effective_model: str | None = None,
) -> Callable[[str], str] | None:
    """Return sanitizer for the *effective* TTS provider (after telephony remaps)."""
    del effective_model  # reserved if model-specific sanitizers are needed later
    provider = (tts_provider or "").strip().lower()
    options = tts_options

    if provider == "cartesia":
        from .cartesia_spoken_sanitize import sanitize_spoken_text

        return sanitize_spoken_text
    if provider == "rime":
        from .rime_spoken_sanitize import sanitize_spoken_text

        return sanitize_spoken_text
    if provider == "elevenlabs":
        from .elevenlabs_spoken_sanitize import sanitize_spoken_text

        def _eleven(text: str) -> str:
            return sanitize_spoken_text(text, tts_options=options)

        return _eleven
    if provider == "fish_audio":
        from .fish_spoken_sanitize import sanitize_spoken_text

        def _fish(text: str) -> str:
            return sanitize_spoken_text(text, tts_options=options)

        return _fish
    if provider == "uplift":
        from .uplift_spoken_sanitize import sanitize_spoken_text

        return sanitize_spoken_text
    return None


def _incomplete_markup_tail(buffer: str) -> int:
    """Index where a flush would cut an open ``<…>`` or ``[…]``; else ``len(buffer)``.

    Keeps an unclosed tag/bracket in the buffer so the next chunk can complete it
    before sanitization runs.
    """
    last_lt = buffer.rfind("<")
    last_gt = buffer.rfind(">")
    last_lb = buffer.rfind("[")
    last_rb = buffer.rfind("]")

    cut = len(buffer)
    if last_lt > last_gt:
        cut = min(cut, last_lt)
    if last_lb > last_rb:
        cut = min(cut, last_lb)
    return cut


def make_stream_sanitizer(
    sanitize_fn: Callable[[str], str],
) -> Callable[[AsyncIterable[str]], AsyncIterable[str]]:
    """Wrap a whole-string sanitizer into a stream transform that buffers incomplete tags."""

    async def _transform(text: AsyncIterable[str]) -> AsyncIterable[str]:
        buffer = ""
        async for chunk in text:
            if not chunk:
                continue
            buffer += chunk
            flush_to = _incomplete_markup_tail(buffer)
            if flush_to <= 0:
                # Cap runaway incomplete markup (malformed LLM output).
                if len(buffer) > 256:
                    yield sanitize_fn(buffer)
                    buffer = ""
                continue
            piece = buffer[:flush_to]
            buffer = buffer[flush_to:]
            if piece:
                yield sanitize_fn(piece)
        if buffer:
            yield sanitize_fn(buffer)

    return _transform
