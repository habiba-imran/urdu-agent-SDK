"""Shrink oversized tenant prompts for Groq free-tier TPM.

Platform system instructions already own voice brevity, anti-injection, spoken-output,
and tool discipline. Compaction therefore keeps business facts / safety / intake /
runtime / custom text, and drops (or heavily stubs) rule sections that only repeat
those platform rules.
"""

from __future__ import annotations

import os
import re

# Soft cap on the persona body. Compaction aims to land at or under this size.
def _soft_chars() -> int:
    return int(os.getenv("GROQ_PROMPT_SOFT_CHARS", "3000"))


_SECTION_RE = re.compile(
    r"(?=^[ \t]*### (?:SECTION \d+[A-Z]?:|KNOWLEDGE DIGEST|FINAL AUTHORITY))",
    re.MULTILINE,
)

# Facts the model needs from the tenant prompt. Rules-only sections are dropped —
# UVA system instructions already cover voice / accuracy / security / grounding.
_KEEP_FULL_PREFIXES = (
    "### SECTION 1:",
    "### SECTION 10:",
    "### KNOWLEDGE DIGEST",
)

_SECTION_2_PREFIX = "### SECTION 2:"
_SECTION_8_PREFIX = "### SECTION 8:"
_SECTION_8A_PREFIX = "### SECTION 8A:"
_SECTION_9_PREFIX = "### SECTION 9:"

_EMERGENCY_TRIAGE_DUP_RE = re.compile(
    r"\nEMERGENCY TRIAGE RULES \(follow immediately when triggers match\):.*"
    r"(?=\n### |\Z)",
    re.DOTALL | re.IGNORECASE,
)

_INTAKE_STUB = """### SECTION 8: APPOINTMENT INTAKE (VOICE)
When the caller wants to schedule: one question per turn. Collect name (spell back),
phone (digit read-back), DOB, insurance + member ID (spell back), reason/symptoms.
Batch-confirm every 4 details. Note the request — front desk confirms availability."""

_TIMING_STUB = """### SECTION 8A: APPOINTMENT TIMING RULES
Upcoming only vs SECTION 9 timestamp. Stay within Operating Hours. Resolve relative
dates ("next Monday") in the business timezone. Collect preferred day/time for confirmation."""


def _slim_section_2(part: str) -> str:
    """Keep clinical disclaimer + 911 script; drop duplicated triage keyword block."""
    text = part.strip()
    if "911 EMERGENCY PROTOCOL" in text.upper() or "CALL 911" in text.upper():
        text = _EMERGENCY_TRIAGE_DUP_RE.sub("", text).strip()
    return text


def _knowledge_cap(part: str, budget: int) -> str:
    text = part.strip()
    if len(text) <= budget:
        return text
    return (
        text[: max(0, budget - 80)].rstrip()
        + "\n\n[Knowledge digest truncated for free-tier token limits.]"
    )


def compact_prompt_for_groq(prompt: str) -> tuple[str, bool]:
    """Return (possibly compacted prompt, whether compaction ran)."""
    text = (prompt or "").strip()
    soft = _soft_chars()
    if not text or len(text) <= soft:
        return text, False

    parts = [p for p in _SECTION_RE.split(text) if p and p.strip()]
    if len(parts) < 3:
        # Unstructured prompt — hard truncate with a marker.
        kept = text[:soft].rstrip()
        return (
            kept
            + "\n\n[Prompt truncated for voice latency / free-tier token limits. "
            "Core business facts above still apply.]",
            True,
        )

    kept: list[str] = []
    for part in parts:
        head = part.lstrip()[:48]
        if any(head.startswith(prefix) for prefix in _KEEP_FULL_PREFIXES):
            if head.startswith("### KNOWLEDGE DIGEST"):
                # Leave room for identity + safety + intake; cap digest last.
                kept.append(part.strip())
            else:
                kept.append(part.strip())
        elif head.startswith(_SECTION_2_PREFIX):
            kept.append(_slim_section_2(part))
        elif head.startswith(_SECTION_8_PREFIX) and not head.startswith(
            _SECTION_8A_PREFIX
        ):
            kept.append(_INTAKE_STUB)
        elif head.startswith(_SECTION_8A_PREFIX):
            kept.append(_TIMING_STUB)
        elif head.startswith(_SECTION_9_PREFIX):
            kept.append(part.strip())
        # SECTION 3–7 and FINAL AUTHORITY: drop — platform instructions already own them.

    # If still over soft (usually a huge knowledge digest), trim digest last.
    compacted = "\n\n".join(kept).strip()
    if len(compacted) > soft:
        trimmed: list[str] = []
        other_len = 0
        digest: str | None = None
        for block in kept:
            if block.lstrip().startswith("### KNOWLEDGE DIGEST"):
                digest = block
            else:
                trimmed.append(block)
                other_len += len(block) + 2
        if digest is not None:
            budget = max(200, soft - other_len - 20)
            trimmed.append(_knowledge_cap(digest, budget))
            compacted = "\n\n".join(trimmed).strip()

    if not compacted or len(compacted) >= len(text):
        return text, False
    return compacted, True
