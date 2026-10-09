"""Conversation history / prompt-cache hygiene (Phase 7).

Policy (research §21–22; API-safe vs pinned livekit-agents 1.6.5):

1. **Static platform rules first** — ``compose_system_instructions`` keeps SYSTEM_INSTRUCTIONS_BASE
   then overlays; tenant persona stays in a separate chat_ctx DATA message (never delivery markup).
2. **Plain assistant text in history** — when an assistant item is added, strip TTS-only markup
   (Cartesia SSML / Fish brackets / Mist pauses) so later LLM turns are not poisoned by tags.
   TTS already received the tagged stream via ``tts_text_transforms`` / generation path.
3. **Legacy session-history windowing** — the configured limit applies to session.history.
   Installed LiveKit keeps a separate active Agent.chat_ctx; this does not bound model input.
   Phase 2 captures a separate full audit transcript. Active projection belongs to Phase 3.
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


class AuditTranscript:
    """Full user/assistant transcript, independent of legacy session history windowing."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def record(self, item: Any) -> None:
        role = getattr(item, "role", None)
        text = plain_text_for_history(getattr(item, "text_content", None) or "")
        item_id = getattr(item, "id", None)
        if role in {"user", "assistant"} and text and item_id:
            self._items[str(item_id)] = {
                "role": role, "text": text, "at": getattr(item, "created_at", None),
            }

    def turns(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._items.values()]

# Legacy session-history cap; the installed agent's active LLM context is separate.
_DEFAULT_CHAT_HISTORY_MAX_ITEMS = 48


def resolve_chat_history_max_items() -> int | None:
    """Max session.history items to retain, or None when windowing is off.

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
    # Rime pronunciation directives must not poison canonical assistant history.
    out = re.sub(r"\bspell\s*\(([^()]*)\)", r"\1", out, flags=re.I)
    # Preserve underscores in literal emails/IDs rather than treating them as markdown.
    protected = {}
    def hold_fact(match):
        token = f"\x00FACT{len(protected)}\x00"
        protected[token] = match.group(0)
        return token
    out = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b\w+_\w+(?:_\w+)*\b", hold_fact, out)
    out = strip_markdown_emoji_bullets(out)
    for token, value in protected.items():
        out = out.replace(token, value)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def reconcile_interrupted_context(chat_ctx: Any, speech_plans=(), heard_items=None) -> Any:
    """Ephemeral model input only. Full audit/history and tool records survive."""
    known = {ref: plan.heard.context_text(plan.canonical_text)
             for plan in speech_plans for ref in plan.history_references}
    known.update(heard_items or {})
    result = chat_ctx.copy()
    changed = False
    for index, item in enumerate(result.items):
        if getattr(item, "role", None) == "assistant" and getattr(item, "interrupted", False):
            # Installed ChatContext.copy() shares items. Isolate the message before
            # changing the ephemeral context, preserving audit and framework history.
            item = item.model_copy(deep=True)
            result.items[index] = item
            prefix = known.get(item.id, "")
            original = getattr(item, "text_content", None) or ""
            # Even an evidence reference cannot introduce text absent from this item.
            item.content = [prefix] if original.startswith(prefix) and prefix else []
            changed = True
    if changed:
        result.add_message(role="developer", content=(
            "Previous interrupted assistant messages contain only known output evidence. "
            "An omitted suffix must not be assumed understood. Recorded business effects remain authoritative."
        ))
    return result


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
    """Strip assistant markup and preserve legacy session-history windowing.

    The full audit transcript is captured separately from the item event.
    This function does not bound the active agent LLM context.
    """
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
