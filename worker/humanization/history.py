"""Conversation history / prompt-cache hygiene (Phase 7).

Policy (research §21–22; API-safe vs pinned livekit-agents 1.6.5):

1. **Static platform rules first** — ``compose_system_instructions`` keeps SYSTEM_INSTRUCTIONS_BASE
   then overlays; tenant persona stays in a separate chat_ctx DATA message (never delivery markup).
2. **Plain assistant text in history** — when an assistant item is added, strip TTS-only markup
   (Cartesia SSML / Fish brackets / Mist pauses) so later LLM turns are not poisoned by tags.
   TTS already received the tagged stream via ``tts_text_transforms`` / generation path.
3. **Windowing** — ``ChatContext.truncate(max_items=…)`` default **48** via ``UVA_CHAT_HISTORY_MAX_ITEMS``
   (set ``0`` / ``off`` to disable).
4. **DB transcript** — same plain-text helper so stored transcripts are readable.

Do not invent AgentSession history APIs that are not on the pinned build — only
``session.history.truncate`` / mutable ``ChatMessage.content`` (verified).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from worker.plain_spoken_sanitize import (
    CARTESIA_SPELL_TAG_RE,
    strip_foreign_tts_markup,
    strip_markdown_emoji_bullets,
)

logger = logging.getLogger("worker.humanization.history")

# Wave 1 default: cap ChatContext growth on long calls (disable with UVA_CHAT_HISTORY_MAX_ITEMS=0).
_DEFAULT_CHAT_HISTORY_MAX_ITEMS = 48


def resolve_chat_history_max_items() -> int | None:
    """Max ChatContext items to retain, or None when windowing is off.

    Default ``48`` when unset. Set ``UVA_CHAT_HISTORY_MAX_ITEMS=0`` (or ``off``) to disable.
    """
    raw = (os.getenv("UVA_CHAT_HISTORY_MAX_ITEMS") or "").strip()
    if not raw:
        return _DEFAULT_CHAT_HISTORY_MAX_ITEMS
    if raw in {"0", "off", "false", "no"}:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value < 8:
        # Too small risks dropping tool pairs / persona-adjacent context.
        logger.warning(
            "UVA_CHAT_HISTORY_MAX_ITEMS=%s too small; using 8 minimum",
            value,
        )
        return 8
    return value


def plain_text_for_history(text: str) -> str:
    """Strip TTS delivery markup for LLM history / DB transcript.

    Always strips Cartesia/ElevenLabs/Fish/Mist delivery tags — history and the
    Sessions UI must stay provider-agnostic (tags were for audio only).
    """
    if not text:
        return text
    # Unwrap <spell>…</spell> first so inner words survive, then drop all markup.
    out = CARTESIA_SPELL_TAG_RE.sub(r"\1", text)
    out = strip_foreign_tts_markup(out, strip_brackets=True)
    out = strip_markdown_emoji_bullets(out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def sanitize_transcript_turns(
    turns: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Return a copy of transcript turns with TTS markup stripped from ``text``."""
    if turns is None:
        return None
    cleaned: list[dict[str, Any]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            cleaned.append(turn)
            continue
        row = dict(turn)
        raw = row.get("text")
        if isinstance(raw, str) and raw:
            row["text"] = plain_text_for_history(raw)
        cleaned.append(row)
    return cleaned


def apply_history_hygiene(
    session: Any,
    *,
    item: Any,
    room_name: str = "",
) -> None:
    """Mutate assistant history text to plain + optionally truncate session history."""
    role = getattr(item, "role", None)
    if role == "assistant":
        raw = getattr(item, "text_content", None) or ""
        if raw and hasattr(item, "content"):
            plain = plain_text_for_history(raw)
            if plain != raw:
                try:
                    item.content = [plain]
                    logger.info(
                        "history plain-assistant room=%s stripped_markup chars %s→%s",
                        room_name,
                        len(raw),
                        len(plain),
                    )
                except Exception as exc:
                    logger.warning(
                        "history plain-assistant mutate failed room=%s: %s",
                        room_name,
                        exc,
                    )

    max_items = resolve_chat_history_max_items()
    if max_items is None:
        return
    history = getattr(session, "history", None)
    if history is None or not hasattr(history, "truncate"):
        return
    before = len(getattr(history, "items", []) or [])
    if before <= max_items:
        return
    try:
        history.truncate(max_items=max_items)
        after = len(getattr(history, "items", []) or [])
        logger.info(
            "history truncated room=%s max_items=%s before=%s after=%s",
            room_name,
            max_items,
            before,
            after,
        )
    except Exception as exc:
        logger.warning("history truncate failed room=%s: %s", room_name, exc)


def system_instructions_static_prefix_ok(system_instructions: str, base: str) -> bool:
    """Groq cache friendliness: trusted system blob must start with the static base."""
    return (system_instructions or "").startswith(base or "")
