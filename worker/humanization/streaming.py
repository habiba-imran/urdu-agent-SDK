"""Phase 7 P0: stable normalization, conservative chunks and speech-only cancellation.

Transport fragments are never speech boundaries. No business/tool task is owned here.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any

from livekit.agents import tokenize

from .delivery.canonical import canonical_spoken_text
from .delivery.intent import DeliveryIntent
from .delivery.pronunciation import PronunciationPlan, PronunciationSpan

STREAMING_VERSION = "streaming_v1"
MAX_TEXT = 32768  # fail closed on runaway output; never force-split a protected value


def streaming_enabled(context, *, environ=None):
    import os
    from .delivery.policy import ACTIVE_PROVIDERS
    env = os.environ if environ is None else environ
    provider = context.cfg.tts_provider
    value = env.get("UVA_TTS_STREAMING_" + provider.upper(), "baseline").strip()
    if value == "baseline":
        return False
    if value != STREAMING_VERSION or provider not in ACTIVE_PROVIDERS:
        raise ValueError("unsupported TTS streaming policy")
    if not context.policy.enabled:
        raise ValueError("streaming_v1 requires delivery_v1")
    # The small handle-context bridge and provider feed paths are audited at 1.6.5.
    from importlib.metadata import version
    if version("livekit-agents") != "1.6.5" or context.capabilities.plugin_version != "1.6.5":
        raise ValueError("streaming path requires an audited LiveKit version")
    return True


# The public SDK tokenizer interface accepts complete, already protected chunks.
# No stream.flush() between chunks: SDK 1.6.5 treats flush as a terminal segment.


class PlannedChunkTokenizer(tokenize.SentenceTokenizer):
    def tokenize(self, text, *, language=None):
        return [text] if text else []

    def stream(self, *, language=None):
        return PlannedChunkStream()


class PlannedChunkStream(tokenize.SentenceStream):
    def push_text(self, text):
        self._check_not_closed()
        if text:
            self._event_ch.send_nowait(tokenize.TokenData(segment_id="planned", token=text))

    def flush(self):
        pass  # chunks are complete; only end_input ends the native context

    def end_input(self):
        self._do_close()

    async def aclose(self):
        self._do_close()


def current_handle():
    # Public current_speech is playback-only and can misidentify preemptive/queued nodes.
    # Read the installed task-local handle; never patch framework cancellation or tools.
    from livekit.agents.voice.agent_activity import _SpeechHandleContextVar
    handle = _SpeechHandleContextVar.get(None)
    if handle is None:
        raise RuntimeError("streaming speech requires a task-local SpeechHandle")
    return handle


def _stable_cut(raw: str) -> int:
    """Last whitespace boundary outside constructs, with one character of lookahead."""
    cut = i = 0
    while i < len(raw):
        c = raw[i]
        if c == "<":
            end = raw.find(">", i + 1)
            if end < 0:
                break
            i = end + 1
            continue
        if c == "[":
            depth, end = 1, i + 1
            while end < len(raw) and depth:
                depth += (raw[end] == "[") - (raw[end] == "]")
                end += 1
            if depth or end == len(raw):
                break
            if raw[end] == "(":
                end = raw.find(")", end + 1)
                if end < 0:
                    break
                end += 1
            i = end
            continue
        spell = re.match(r"spell\s*\(", raw[i:], re.I) if i == 0 or not (raw[i-1].isalnum() or raw[i-1] == "_") else None
        if spell:
            end = raw.find(")", i + len(spell[0]))
            if end < 0:
                break
            i = end + 1
            continue
        if c.isspace():
            end = i + 1
            while end < len(raw) and raw[end].isspace():
                end += 1
            # spell + whitespace may still introduce a parenthesized control.
            if end < len(raw) and not (raw[end] == "(" and re.search(r"\bspell$", raw[:i], re.I)):
                cut = end
            i = end
        else:
            i += 1
    return cut


class StreamSafeNormalizer:
    def __init__(self, *, suppress_openers=()):
        self.suppress_openers = tuple(suppress_openers)
        self.opening = ""
        self.buffer = ""
        self.whitespace = ""
        self.started = False
        self.closed = False

    def _publish(self, plain, *, final=False):
        value = self.whitespace + plain
        if self.suppress_openers and not self.started:
            value = self.opening + value
            self.opening = ""
            folded = value.lstrip().casefold()
            candidates = [o for o in self.suppress_openers if o.startswith(folded) or folded.startswith(o)]
            if candidates and not final and any(
                o.startswith(folded.rstrip()) or folded.rstrip(" ,.!:-\u2014") == o for o in candidates
            ):
                self.opening = value
                self.whitespace = ""
                return ""
            for opener in sorted(candidates, key=len, reverse=True):
                match = re.match(r"^\s*" + re.escape(opener) + r"\s*[,!.:\u2014-]\s*(\S[\s\S]*)$", value, re.I)
                if match:
                    value = match.group(1)
                    break
        if not self.started:
            value = value.lstrip()
        body = value.rstrip()
        self.whitespace = value[len(body):]
        if body:
            self.started = True
        return body

    def feed(self, fragment):
        if self.closed:
            return ""
        self.buffer += fragment
        if len(self.buffer) > MAX_TEXT:
            raise ValueError("unresolved speech text exceeds P0 bound")
        cut = _stable_cut(self.buffer)
        if not cut or re.search(r"<[^>]*$|\[[^\[\]]*$|\bspell\s*\([^)]*$", self.buffer[:cut], re.I):
            return ""
        # Earlier cleanup can expose malformed markup inside a spelling/link wrapper.
        # Such a suffix must remain pending through EOS, just like raw open syntax.
        plain = canonical_spoken_text(self.buffer[:cut], strip=False, final=False)
        if re.search(r"<[^>]*$|\[[^\[\]]*$", plain):
            return ""
        self.buffer = self.buffer[cut:]
        return self._publish(plain)

    def finish(self):
        if self.closed:
            return ""
        plain = self._publish(canonical_spoken_text(self.buffer, strip=False), final=True)
        self.clear()
        return plain

    def clear(self):
        self.buffer = self.whitespace = self.opening = ""
        self.closed = True


# Deliberately conservative supersets. Overprotecting punctuation only delays a chunk.
_PROTECTED = tuple(re.compile(p, re.I) for p in (
    r"[\w.+-]+@[\w.-]+\.[\w-]+",
    r"(?:https?://|www\.)[^\s<>]+",
    r"(?<!\w)\+?\d[\d ()-]{5,}\d(?!\w)",
    r"\b\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b",
    r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.?m\.?)?",
    r"(?:[$£€]\s*|\b(?:PKR|USD|Rs\.?)\s*)\d[\d,]*(?:\.\d+)?(?:\s*(?:rupees|dollars))?",
    r"\b\d+[.,]\d+(?:[.,]\d+)*\b",
    r"\b(?=[\w-]*\d)(?=[\w-]*[a-z_])[\w]+(?:[-_.][\w]+)*\b",
    r"\b[A-Z](?:[ .-]+[A-Z]){1,}\.?",
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{1,4}\b",
    r"<spell\b[^>]*>[\s\S]*?(?:</spell>|$)|<[^>]*(?:>|$)|\[[^\]]*(?:\]|$)|\bspell\s*\([^)]*(?:\)|$)",
    r"\b(?:Dr|Mr|Mrs|Ms|Prof|Rs)\.",
))


def protected_spans(text: str, pronunciation: PronunciationPlan = PronunciationPlan()):
    spans = [(m.start(), m.end()) for pattern in _PROTECTED for m in pattern.finditer(text)]
    for span in pronunciation.spans:
        # Future explicit spans may extend beyond the currently received prefix.
        if text[span.start:min(span.end, len(text))] == span.source[:max(0, len(text)-span.start)]:
            spans.append((span.start, span.end))
    return spans


@dataclass(frozen=True)
class SpeechChunk:
    start: int
    end: int
    text: str
    reason: str


class SpeechChunkPlanner:
    def __init__(self, provider: str, pronunciation: PronunciationPlan = PronunciationPlan(), *, conversational=False):
        if provider not in {"cartesia", "rime", "elevenlabs", "uplift"}:
            raise ValueError("unselectable speech provider")
        self.provider = provider
        self.conversational = conversational
        self.pronunciation = pronunciation
        self.buffer = ""
        self.offset = 0
        self.chunks = 0
        self.closed = False

    def feed(self, text: str):
        if self.closed:
            return []
        self.buffer += text
        if len(self.buffer) > MAX_TEXT:
            raise ValueError("speech remainder exceeds P0 bound")
        result = []
        while True:
            spans = protected_spans(self.buffer, PronunciationPlan(tuple(
                PronunciationSpan(s.start-self.offset, s.end-self.offset, s.source, s.mode,
                                  s.alias, s.phoneme, s.group_sizes)
                for s in self.pronunciation.spans if s.end > self.offset
            )))
            boundary = None
            for m in re.finditer(r"[.!?؟۔,;،؛]\s+(?=\S)", self.buffer):
                punctuation_end = m.start() + 1
                if any(start < punctuation_end < end for start, end in spans):
                    continue
                sentence = self.buffer[m.start()] in ".!?؟۔"
                clause = (self.chunks == 0 and len(self.buffer[:punctuation_end].split()) >= 4
                          and (self.provider == "cartesia" or (
                              self.provider == "uplift" and self.buffer[m.start()] in "،؛")))
                if self.conversational:
                    words = len(self.buffer[:punctuation_end].split())
                    if sentence and self.chunks == 0 and words < 3:
                        continue
                    clause = self.chunks == 0 and words >= 8
                if sentence or clause:
                    boundary = (m.end(), "sentence" if sentence else "first_clause")
                    break
            if boundary is None:
                break
            end, reason = boundary
            result.append(self._take(end, reason))
        return result

    def _take(self, end, reason):
        chunk = SpeechChunk(self.offset, self.offset + end, self.buffer[:end], reason)
        self.buffer = self.buffer[end:]
        self.offset += end
        self.chunks += 1
        return chunk

    def finish(self):
        if self.closed:
            return []
        result = [self._take(len(self.buffer), "short_reply" if not self.chunks and len(self.buffer.split()) <= 6 else "remainder")] if self.buffer else []
        self.clear()
        return result

    def clear(self):
        self.buffer = ""
        self.closed = True


@dataclass
class HeardState:
    # Prefix ranges are character boundaries from real synchronized text or
    # complete chunks at a known output playout boundary. Never word timing.
    prefix: str = ""
    source: str = "UNKNOWN"
    playback_position: float | None = None

    def observe(self, canonical: str, *, synchronized_transcript: str | None = None,
                completed_chunks: tuple = (), playback_position: float | None = None) -> None:
        candidate = synchronized_transcript
        source = "synchronized_transcript"
        if candidate is None and completed_chunks:
            cursor = 0
            for chunk in completed_chunks:
                if chunk.start != cursor or chunk.end != cursor + len(chunk.text):
                    return
                cursor = chunk.end
            candidate = "".join(chunk.text for chunk in completed_chunks)
            source = "completed_chunks"
        if candidate is not None and canonical.startswith(candidate) and len(candidate) >= len(self.prefix):
            self.prefix, self.source = candidate, source
        if playback_position is not None:
            self.playback_position = max(self.playback_position or 0, playback_position)

    def context_text(self, canonical: str) -> str:
        return self.prefix if canonical.startswith(self.prefix) else ""


@dataclass
class SpeechPlan:
    generation_id: str
    provider: str
    delivery_intent: DeliveryIntent
    pronunciation_plan: PronunciationPlan = field(default_factory=PronunciationPlan)
    handle: Any = None
    provider_context: dict = field(default_factory=dict)
    canonical_text: str = ""
    heard: HeardState = field(default_factory=HeardState)
    planned_chunks: list[SpeechChunk] = field(default_factory=list)
    llm_started: bool = False
    cancelled: bool = False
    playout_completed: bool | None = None
    synthesis_completed: bool = False
    history_references: tuple[str, ...] = ()
    framework_playout_references: tuple[str, ...] = ()
    heard_reference: str | None = None  # actual output evidence; never synthesis completion
    first_useful_text_at: float | None = None
    first_chunk_at: float | None = None
    last_audio_at: float | None = None
    inter_chunk_gap_ms: list[float] = field(default_factory=list)
    synthesized_ms: float = 0
    accepted_audio_ms: float = 0
    rejected_audio_ms: float = 0
    lead_estimate_ms: float = 0
    audio_anchor: float | None = None
    synthesis_task: Any = None
    normalizer: StreamSafeNormalizer = field(default_factory=StreamSafeNormalizer)
    planner: Any = None
    watcher: Any = None

    def __post_init__(self):
        self.planner = SpeechChunkPlanner(self.provider, self.pronunciation_plan,
                                          conversational=self.provider_context.get("conversational", False))

    @property
    def valid(self):
        if self.handle is not None and self.handle.interrupted:
            self.cancel()
        return not self.cancelled

    @property
    def chunk_wait_ms(self):
        if self.first_chunk_at is None or self.first_useful_text_at is None:
            return None
        return max(0, (self.first_chunk_at-self.first_useful_text_at)*1000)

    def accept_text(self, text):
        if not self.valid:
            return False
        if len(self.canonical_text) + len(text) > MAX_TEXT:
            raise ValueError("speech generation exceeds P0 text bound")
        self.canonical_text += text
        return True

    def accept_chunk(self, chunk):
        if not self.valid:
            return False
        self.planned_chunks.append(chunk)
        if self.first_chunk_at is None:
            self.first_chunk_at = time.monotonic()
        return True

    def cancel(self):
        self.cancelled = True
        self.normalizer.clear()
        self.planner.clear()
        # Only the isolated synthesis task is owned/cancelled here, never tools/LLM.
        task = self.synthesis_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def bind(self):
        if self.handle is None or self.watcher is not None:
            return
        done = asyncio.get_running_loop().create_future()

        def completed(handle):
            self.playout_completed = not handle.interrupted and handle.exception() is None
            # Public handle-level item references; no guessed word/heard ranges.
            self.history_references = tuple(item.id for item in handle.chat_items
                                            if getattr(item, "role", None) == "assistant")
            self.framework_playout_references = self.history_references if self.playout_completed else ()
            if handle.interrupted:
                self.cancel()
            if not done.done():
                done.set_result(None)
            import logging
            logging.getLogger("worker.humanization.streaming").info("speech_stream_metrics %s", self.metrics())
        self.handle.add_done_callback(completed)

        async def watch():
            await self.handle.wait_if_not_interrupted([done])
            if self.handle.interrupted:
                self.cancel()
            # Terminal handle reference is structural; heard duration remains unknown.
        self.watcher = asyncio.create_task(watch())

    async def pace_audio(self, frame, *, lead_limit_ms=2000):
        """Bound local audio handoff against elapsed time, not caller-heard playback."""
        duration = frame.duration * 1000
        self.synthesized_ms += duration
        if not self.valid:
            self.rejected_audio_ms += duration
            return False
        now = time.monotonic()
        if self.audio_anchor is None:
            self.audio_anchor = now
        # Keep the stock framework's unbounded audio channel from running far ahead.
        delay = (self.accepted_audio_ms + duration - lead_limit_ms)/1000 - (now-self.audio_anchor)
        if delay > 0:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                self.rejected_audio_ms += duration
                raise
        if not self.valid:
            self.rejected_audio_ms += duration
            return False
        self.accepted_audio_ms += duration
        self.lead_estimate_ms = max(0, self.accepted_audio_ms - (time.monotonic()-self.audio_anchor)*1000)
        return True

    def metrics(self):
        return dict(generation_id=self.generation_id, streaming_policy_version=STREAMING_VERSION,
                    provider=self.provider, chunks=len(self.planned_chunks), cancelled=self.cancelled,
                    chunk_wait_ms=self.chunk_wait_ms, inter_chunk_gap_ms=self.inter_chunk_gap_ms,
                    audio_lead_estimate_ms=self.lead_estimate_ms,
                    synthesized_ms=self.synthesized_ms, rejected_audio_ms=self.rejected_audio_ms,
                    cancelled_synthesized_ms=self.synthesized_ms if self.cancelled else 0,
                    caller_heard_latency_ms=None, heard_reference=self.heard_reference)
