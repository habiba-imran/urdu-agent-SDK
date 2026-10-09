"""Plain speech boundary. Preserve emails, underscores, URLs and literal codes."""

from __future__ import annotations

import re

_TAG = re.compile(r"</?[A-Za-z][^>]*>|<\d{2,4}>")
_SPELL = re.compile(r"\bspell\s*\(([^()]*)\)", re.I)
_CUE = re.compile(
    r"\[(?:laugh\w*|soft[ _-]+laugh\w*|sigh\w*|chuckl\w*|happy|sad|"
    r"excited|whisper\w*|concerned|reassuring|warm|angry|"
    r"clears throat|exhales|pause\w*|breath\w*)\]", re.I,
)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def canonical_spoken_text(text: str, *, strip: bool = True, final: bool = True) -> str:
    # Deliberately does not apply the legacy markdown regex which deletes '_' in facts.
    out = _LINK.sub(r"\1", text)
    out = _SPELL.sub(r"\1", out)
    out = _TAG.sub("", out)
    out = _CUE.sub("", out)
    # Unexpected stage cues fail closed. Literal bracketed codes/digits survive unwrapped.
    def bracket(match):
        inner = match.group(0)[1:-1]
        return inner if (re.fullmatch(r"[A-Z0-9_-]+", inner) and any(c.isdecimal() for c in inner)) else ""
    out = re.sub(r"\[[^\[\]]{1,256}\]", bracket, out)
    out = re.sub(r"(?<!\w)[*_`]{1,3}|[*_`]{1,3}(?!\w)", "", out)
    from worker.plain_spoken_sanitize import EMOJI_RE
    out = EMOJI_RE.sub("", out)
    # Malformed trailing delivery syntax must not be spoken.
    if final:
        out = re.sub(r"<(?:/?[A-Za-z]|\d)[^>]*$", "", out)
        out = re.sub(r"\[[^\[\]]*$", "", out)
    return out.strip() if strip else out
