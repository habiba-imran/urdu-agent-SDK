"""Correctness/protected spans; trusted aliases never rewrite business state."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .policy import PRONUNCIATION_VERSION

PronunciationMode = Literal["NORMAL", "SPELL", "ALIAS", "DIGIT_GROUP", "PHONEME"]


@dataclass(frozen=True)
class PronunciationSpan:
    start: int
    end: int
    source: str
    mode: PronunciationMode = "NORMAL"
    alias: str | None = None
    phoneme: str | None = None
    group_sizes: tuple[int, ...] = ()


@dataclass(frozen=True)
class PronunciationPlan:
    spans: tuple[PronunciationSpan, ...] = ()
    version: str = PRONUNCIATION_VERSION

    def validate(self, text: str) -> None:
        previous = 0
        for span in sorted(self.spans, key=lambda s: s.start):
            if not 0 <= span.start < span.end <= len(text) or span.start < previous:
                raise ValueError("invalid or overlapping pronunciation spans")
            if text[span.start:span.end] != span.source:
                raise ValueError("pronunciation span does not match canonical text")
            if span.mode not in {"NORMAL", "SPELL", "ALIAS", "DIGIT_GROUP", "PHONEME"}:
                raise ValueError("unsupported pronunciation mode")
            if span.mode == "ALIAS" and (
                not span.alias or any(c in span.alias for c in "<>[]\n\r")
                or re.search(r"spell\s*\(", span.alias, re.I)
            ):
                raise ValueError("alias must be trusted plain spoken text")
            if span.mode == "DIGIT_GROUP":
                digits = [c for c in span.source if c.isdecimal()]
                if not digits or any(n <= 0 for n in span.group_sizes):
                    raise ValueError("invalid digit grouping")
                if span.group_sizes and sum(span.group_sizes) != len(digits):
                    raise ValueError("digit groups must cover every digit")
            previous = span.end


_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\w)\+?[\d][\d ()-]{5,}\d(?!\w)")
_CODE = re.compile(r"\b(?=[A-Z0-9_-]*[A-Z])(?=[A-Z0-9_-]*\d)[A-Z0-9]+(?:[-_][A-Z0-9]+)*\b")
_ENGLISH = re.compile(r"[A-Za-z]+(?:['’.-][A-Za-z]+)*")


def plan_pronunciation(text: str, *, state=None, language: str = "en") -> PronunciationPlan:
    """Protect literal facts; never guess name/brand respellings from an LLM."""
    spans: list[PronunciationSpan] = []

    def add(start: int, end: int, mode: PronunciationMode) -> None:
        if not any(start < s.end and end > s.start for s in spans):
            spans.append(PronunciationSpan(start, end, text[start:end], mode))

    for pattern, mode in ((_EMAIL, "SPELL"), (_PHONE, "DIGIT_GROUP"), (_CODE, "SPELL")):
        for match in pattern.finditer(text):
            if mode != "DIGIT_GROUP" or len([c for c in match[0] if c.isdecimal()]) >= 7:
                add(match.start(), match.end(), mode)
    if state is not None:
        for values in state.task_state.critical_values.values():
            for value in reversed(values):
                if value.status in {"heard", "confirmed"}:
                    for match in re.finditer(re.escape(value.value), text):
                        add(match.start(), match.end(), "NORMAL")
                    break
    if language.startswith("ur") or language in {"mixed", "en-ur", "ur-en"}:
        for match in _ENGLISH.finditer(text):
            add(match.start(), match.end(), "NORMAL")
    return PronunciationPlan(tuple(sorted(spans, key=lambda s: s.start)))


_DIGITS_EN = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_DIGITS_UR = ("صفر", "ایک", "دو", "تین", "چار", "پانچ", "چھ", "سات", "آٹھ", "نو")
_SYMBOLS_EN = {"@": "at", ".": "dot", "_": "underscore", "-": "dash", "+": "plus"}
_SYMBOLS_UR = {"@": "ایٹ", ".": "ڈاٹ", "_": "انڈر اسکور", "-": "ڈیش", "+": "پلس"}


def spell_plain(source: str, language: str) -> str:
    urdu = language.startswith("ur")
    digits = _DIGITS_UR if urdu else _DIGITS_EN
    symbols = _SYMBOLS_UR if urdu else _SYMBOLS_EN
    return " ".join(
        digits[int(c)] if c.isdecimal() else symbols.get(c, c)
        for c in source if not c.isspace()
    )


def digits_plain(span: PronunciationSpan, language: str) -> str:
    digits = "".join(c for c in span.source if c.isdecimal())
    groups = []
    index = 0
    for size in span.group_sizes or (len(digits),):
        groups.append(spell_plain(digits[index:index + size], language))
        index += size
    prefix = ("پلس " if language.startswith("ur") else "plus ") if span.source.startswith("+") else ""
    return prefix + ", ".join(groups)
