"""Evidence from the installed public STT stream, never guessed provider scores."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WordEvidence:
    text: str
    start: float | None = None
    end: float | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class TranscriptEvidence:
    text: str
    is_final: bool
    language: str | None = None
    start: float | None = None
    end: float | None = None
    confidence: float | None = None
    words: tuple[WordEvidence, ...] = ()
    provider_eot: bool | None = None
    provider: str | None = None
    model: str | None = None


def from_speech_event(event: Any, *, provider: str | None, model: str | None) -> TranscriptEvidence | None:
    kind = getattr(getattr(event, "type", None), "value", getattr(event, "type", None))
    if kind == "end_of_speech":
        return TranscriptEvidence("", False, provider_eot=True, provider=provider, model=model)
    if kind not in {"interim_transcript", "final_transcript"} or not event.alternatives:
        return None
    alt = event.alternatives[0]
    # Both installed plugins expose TimedString words, but drop word confidence.
    words = tuple(
        WordEvidence(str(word), word.start_time, word.end_time)
        for word in (getattr(alt, "words", None) or [])
        if word.start_time is not None and word.end_time is not None
        and word.end_time > word.start_time
    )
    # Gladia fills absent confidence with 1.0. Its public event loses provenance;
    # conservatively omit confidence rather than pass the fallback off as evidence.
    # Flux likewise does not expose Nova's alternative confidence contract.
    confidence = None
    if provider == "deepgram" and not (model or "").startswith("flux"):
        confidence = getattr(alt, "confidence", None)
    return TranscriptEvidence(
        alt.text, kind == "final_transcript", str(alt.language) if alt.language else None,
        min(w.start for w in words) if words else None,
        max(w.end for w in words) if words else None,
        confidence, words, None, provider, model,
    )
