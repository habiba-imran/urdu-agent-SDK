#!/usr/bin/env python3
"""Minimal processors stub — ported from old Pipecat repo for CER harness compatibility.

In production (Phase 3), processor logic will be reimplemented on LiveKit Agents.
This file exists so the ported tests can import and run without refactoring.
"""

import re

from loguru import logger

# --- Regexes from the old repo's OutputSanitizer (processors.py) ---

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_BRACKET_DIRECTION_RE = re.compile(
    r"\[.*?\]|\(.*?\)\s*(?:click|tap|press|say).*", re.IGNORECASE
)
_EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001f1e0-\U0001f1ff"
    "\u2600-\u26ff\u2700-\u27bf"
    "]+",
    re.UNICODE,
)
_MD_SYMBOLS_RE = re.compile(r"[*_~`#>\-]")
_DEVANAGARI_WORD_RE = re.compile(r"\b[\u0900-\u097f]+\b")

# Shared counter across the module for the Devanagari strip tally (old repo convention)
devanagari_strips: int = 0


def sanitize_text(text: str) -> str:
    """Strip markdown, emojis, stage directions, URLs and Devanagari words from LLM text."""
    global devanagari_strips
    if not text:
        return ""
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = _BRACKET_DIRECTION_RE.sub("", text)
    text = _EMOJI_RE.sub("", text)
    text = _MD_SYMBOLS_RE.sub("", text)
    hits = _DEVANAGARI_WORD_RE.findall(text)
    if hits:
        devanagari_strips += len(hits)
        logger.warning(f"OutputSanitizer: stripped Devanagari word(s): {hits}")
        text = _DEVANAGARI_WORD_RE.sub("", text)
    text = text.replace("(", " ").replace(")", " ")
    return re.sub(r"[ \t]{2,}", " ", text)


# --- Placeholder classes for Phase 3 reimplementation ---


class InputGuard:
    """Placeholder — will be reimplemented on LiveKit Agents."""


class OutputSanitizer:
    """Placeholder — will be reimplemented on LiveKit Agents."""


class TurnMetricsObserver:
    """Placeholder — will be reimplemented on LiveKit Agents."""

    def __init__(self, session=None):
        self.session = session

    def _flush_bot_text(self):
        pass

    def _flush_row(self, interrupted=False):
        pass


class NumberDictationPatience:
    """Placeholder — will be reimplemented on LiveKit Agents."""

    def __init__(self, strategy=None):
        pass


class InterimPromoter:
    """Placeholder — will be reimplemented on LiveKit Agents."""


class SessionState:
    """Re-export from session_state module for test compatibility."""

    pass


# Also expose session_state's SessionState directly
try:
    from session_state import SessionState  # noqa: F811,F401  (intentional re-export)
except ImportError:
    pass
