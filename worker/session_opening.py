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


def apply_session_opening(session: Any, cfg: AgentConfig, logger: Any) -> SessionOpening:
    opening = resolve_session_opening(cfg)
    if opening.mode == "wait":
        logger.info("session opening first_speaker=user — waiting for caller")
        return opening
    if opening.mode == "say":
        logger.info(
            "session opening first_speaker=agent custom_greeting_chars=%s",
            len(opening.text or ""),
        )
        session.say(opening.text)
        return opening
    logger.info("session opening first_speaker=agent generated_greeting")
    session.generate_reply(instructions=opening.instructions)
    return opening
