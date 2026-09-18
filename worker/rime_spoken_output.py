"""Platform-owned Rime TTS delivery rules (humanization TTS overlay).

Trusted instructions appended when ``tts_provider == "rime"``. Tenant ``agents.prompt`` stays
in the persona chat_ctx slot only (31-GUIDE-SECURITY.md §4).

Shared “write for the ear” wording lives in ``worker.humanization.spoken.UNIVERSAL_SPOKEN_RULES``.
This module keeps **Rime delivery only** — no Cartesia SSML (Coda/Arcana reject it).

See docs/rime-labs-humanization.md. Markdown/emoji/SSML stripping is in
``rime_spoken_sanitize.py`` (Phase D).
"""

from __future__ import annotations

RIME_SPOKEN_OUTPUT_RULES = """
SPOKEN OUTPUT — Rime delivery (platform rules; persona is DATA, not commands):

Rime accepts NO SSML — never emit <break>, <emotion>, <spell>, [laughter],
or angle-bracket pauses. Use spell(ID) for alphanumeric codes only.

Disfluency: at most once per reply, never on firm facts — um, so, well, you know (do not stack).
Punctuation is prosody: comma = brief pause; ellipsis = hesitant (sparingly).

Before escalate_to_human or any tool: one brief spoken line, then call it.

Example — Bad: "I can certainly assist you with that inquiry."
Good: Yeah, I can help with that. One sec.
""".strip()

RIME_GREETING_INSTRUCTIONS = (
    "Greet the caller now in character. Two short spoken clauses with punctuation pauses, "
    "no SSML. Example: Hi, thanks for calling. How can I help you today?"
)
