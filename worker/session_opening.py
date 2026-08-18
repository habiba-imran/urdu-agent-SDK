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


async def _await_opening_speech(handle: Any, logger: Any, *, label: str) -> None:
    """Wait for opening TTS to finish; log interruption/errors for live debugging."""
    try:
        await handle.wait_for_playout()
    except Exception as exc:
        logger.warning("session opening %s playout failed: %s", label, exc)
        return
    if getattr(handle, "interrupted", False):
        logger.warning("session opening %s was interrupted before playout finished", label)
    elif getattr(handle, "exception", None):
        logger.warning(
            "session opening %s finished with error: %s",
            label,
            handle.exception(),
        )


async def apply_session_opening(session: Any, cfg: AgentConfig, logger: Any) -> SessionOpening:
    opening = resolve_session_opening(cfg)
    if opening.mode == "wait":
        logger.info("session opening first_speaker=user — waiting for caller")
        return opening
    if opening.mode == "say":
        logger.info(
            "session opening first_speaker=agent custom_greeting_chars=%s",
            len(opening.text or ""),
        )
        # Mic echo/noise during connect was falsely interrupting the greeting (client heard
        # silence while STT still worked). Opening speech must not be interruptible.
        handle = session.say(opening.text, allow_interruptions=False)
        await _await_opening_speech(handle, logger, label="custom_greeting")
        return opening
    logger.info("session opening first_speaker=agent generated_greeting")
    handle = session.generate_reply(
        instructions=opening.instructions,
        allow_interruptions=False,
    )
    await _await_opening_speech(handle, logger, label="generated_greeting")
    return opening
