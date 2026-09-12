"""Decide how a session opens: wait, speak a tenant greeting, or generate one.

Tenant ``greeting`` is untrusted DATA (same class as ``agents.prompt``). When present it is
spoken via ``session.say()`` — never concatenated into system instructions or generate_reply
instructions. ``first_speaker='user'`` skips the opening turn entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .cartesia_spoken_output import greeting_instructions
from .config import AgentConfig

OpeningMode = Literal["wait", "say", "generate_reply"]


@dataclass(frozen=True)
class SessionOpening:
    mode: OpeningMode
    text: str | None = None
    instructions: str | None = None


def _spoken_greeting(cfg: AgentConfig, text: str) -> str:
    from .spoken_sanitize import sanitizer_for_provider

    sanitize = sanitizer_for_provider(cfg.tts_provider)
    if sanitize is None:
        return text.strip()
    return sanitize(text).strip()


def resolve_session_opening(cfg: AgentConfig) -> SessionOpening:
    speaker = (cfg.first_speaker or "agent").strip().lower()
    if speaker != "agent":
        return SessionOpening(mode="wait")

    raw = (cfg.greeting or "").strip()
    if raw:
        spoken = _spoken_greeting(cfg, raw)
        if spoken:
            return SessionOpening(mode="say", text=spoken)

    return SessionOpening(
        mode="generate_reply",
        instructions=greeting_instructions(cfg),
    )


async def apply_session_opening(
    session: Any,
    cfg: AgentConfig,
    logger: Any,
    *,
    allow_interruptions: bool | None = None,
) -> SessionOpening:
    """Speak or generate the opening turn.

    WebRTC defaults to non-interruptible greetings (mic echo during connect).
    Telephony should pass ``allow_interruptions=True`` so barge-in does not leave
    the caller in a discarded-audio / deaf window.
    """
    opening = resolve_session_opening(cfg)
    interruptible = False if allow_interruptions is None else bool(allow_interruptions)
    if opening.mode == "wait":
        logger.info("session opening first_speaker=user — waiting for caller")
        return opening
    if opening.mode == "say":
        logger.info(
            "session opening first_speaker=agent custom_greeting_chars=%s allow_interruptions=%s",
            len(opening.text or ""),
            interruptible,
        )
        # Static greeting: TTS-only, no LLM (UVA-10).
        session.say(opening.text, allow_interruptions=interruptible)
        return opening
    logger.info(
        "session opening first_speaker=agent generated_greeting allow_interruptions=%s",
        interruptible,
    )
    session.generate_reply(
        instructions=opening.instructions,
        allow_interruptions=interruptible,
    )
    return opening
