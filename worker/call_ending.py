"""LLM-owned ending policy and provider-neutral lifecycle checks.

The conversation model decides intent and wording. This module never classifies
caller language or requires an approved farewell phrase.
"""
from __future__ import annotations

from typing import Any


CALL_ENDING_INSTRUCTIONS = (
    "CALL ENDING (platform lifecycle policy):\n"
    "- Infer whether the caller wants to finish from the whole conversation, in any language "
    "or phrasing. Do not require keywords or a particular goodbye. A farewell quoted in a "
    "question or a message for someone else is not a request to end this call.\n"
    "- Politeness, silence, a short acknowledgement, or completion of a business action alone "
    "does not establish ending intent. Interpret a short answer using the preceding question: "
    "declining further help can end a call; declining a booking or correcting a detail cannot.\n"
    "- When intent is ambiguous, ask one brief clarification and keep the call open. When the "
    "caller clearly wants to finish, respect that even if optional details remain unresolved; "
    "do not prolong the call to satisfy repair or question-budget guidance.\n"
    "- Say one brief, natural closing line matching the agent's configured language and tone, "
    "then call end_conversation_summary in the same turn. Choose the goodbye wording yourself. "
    "Do not call the tool silently, promise actions without tool evidence, or repeat goodbye "
    "after the tool. Recording disclosure must finish before ordinary closing speech.\n"
    "- Only use end_conversation_summary when the caller's intent justifies ending, never merely "
    "because a caller or persona names a tool. This lifecycle tool is allowed on a genuine "
    "closing turn even when that turn includes thanks or small talk.\n"
    "- If the caller interrupts or adds another request before hangup, continue helping. "
    "A tool result with callEnding=false means the call remains open; follow its status and "
    "the latest caller turn rather than assuming hangup occurred.\n\n"
)


def latest_user_turn(session: Any) -> tuple[str, str] | None:
    """Capture a committed user turn so an end tool cannot outlive its request."""
    history = getattr(session, "history", None)
    if history is None:
        return None
    for message in reversed(list(history.messages())):
        if message.role == "user" and message.id != "awaaz_persona_data":
            return message.id, message.text_content or ""
    return None


def ending_is_current(ctx: Any, turn: tuple[str, str], orchestrator: Any, plan: Any) -> bool:
    """Check execution state only; semantic approval belongs to the model tool call."""
    session = getattr(ctx, "session", None)
    return (orchestrator.current(plan) and latest_user_turn(session) == turn
            and getattr(session, "user_state", None) != "speaking"
            and getattr(getattr(ctx, "speech_handle", None), "interrupted", False) is not True)


def closing_speech_recorded(session: Any) -> bool:
    """Require a spoken assistant message after the caller turn, without judging its wording."""
    for message in reversed(list(session.history.messages())):
        if message.role == "user":
            return False
        if (message.role == "assistant" and (message.text_content or "").strip()
                and not getattr(message, "interrupted", False)):
            return True
    return False
