"""Shared helpers for the self-test suite (STEP 9)."""

# Imports intentionally follow sys.path setup + load_dotenv() below, so E402 is expected here.
# ruff: noqa: E402

import asyncio
import base64
import io
import json
import os
import re
import sys
import time
import uuid
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

import numpy as np
import socketio

import config

NAMESPACE = "/text-to-speech/multi-stream"


# --- Uplift synthesis (returns 16 kHz mono WAV bytes, ready for Whisper/pipeline) ----


async def synth_urdu(text: str, out_rate: int = 16000) -> bytes:
    """Synthesize Urdu speech with Uplift and return WAV bytes at out_rate."""
    sio = socketio.AsyncClient()
    audio = bytearray()
    done = asyncio.Event()

    @sio.on("message", namespace=NAMESPACE)
    async def on_message(data):
        t = data.get("type")
        if t == "audio":
            b64 = data.get("audio")
            if b64:
                audio.extend(base64.b64decode(b64))
        elif t in ("audio_end", "error"):
            if t == "error":
                print(f"uplift error: {data}")
            done.set()

    await sio.connect(
        "https://api.upliftai.org",
        auth={"token": config.UPLIFTAI_API_KEY},
        namespaces=[NAMESPACE],
        transports=["websocket"],
        wait_timeout=15,
    )
    await sio.emit(
        "synthesize",
        {
            "requestId": str(uuid.uuid4()),
            "text": text,
            "voiceId": config.UPLIFT_VOICE_ID,
            "outputFormat": "PCM_22050_16",
        },
        namespace=NAMESPACE,
    )
    await asyncio.wait_for(done.wait(), timeout=45)
    await sio.disconnect()

    pcm = np.frombuffer(bytes(audio), dtype=np.int16)
    if out_rate != 22050 and len(pcm):
        n_out = int(len(pcm) * out_rate / 22050)
        x_old = np.linspace(0, 1, len(pcm))
        x_new = np.linspace(0, 1, n_out)
        pcm = np.interp(x_new, x_old, pcm.astype(np.float64)).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(out_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


# --- Groq Whisper STT -----------------------------------------------------------------


async def groq_transcribe(wav_bytes: bytes) -> tuple[str, float]:
    """Transcribe WAV bytes with Groq whisper-large-v3 (ur). Returns (text, seconds)."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1"
    )
    t0 = time.monotonic()
    res = await client.audio.transcriptions.create(
        file=("audio.wav", wav_bytes, "audio/wav"),
        model=config.GROQ_STT_MODEL,
        language=config.STT_LANGUAGE,
        prompt=config.STT_PROMPT,
        response_format="json",
    )
    return res.text.strip(), time.monotonic() - t0


# --- Text-level agent conversation (LLM + real tools, no audio pipeline) ---------------


class FakeFunctionCallParams:
    """Duck-typed FunctionCallParams: tool handlers only use .arguments and .result_callback."""

    def __init__(self, name: str, arguments: dict):
        self.function_name = name
        self.arguments = arguments
        self.result: object = None

    async def result_callback(self, result):
        self.result = result


def _openai_tools() -> list[dict]:
    import tools as tz_tools

    schema = tz_tools.build_tools_schema()
    out = []
    for f in schema.standard_tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": f.name,
                    "description": f.description,
                    "parameters": {
                        "type": "object",
                        "properties": f.properties,
                        "required": f.required,
                    },
                },
            }
        )
    return out


class AgentConversation:
    """Drives Mahnoor at the text level: real system prompt, real LLM chain, real tools.

    Replies are passed through the production OutputSanitizer (sanitize_text), so
    what tests assert on is what the caller would hear. Every reply is also
    recorded in the class-level ``all_replies`` registry for transcript-wide
    checks (Roman-Urdu / Devanagari, v3 acceptance criterion 5).
    """

    all_replies: list[str] = []  # transcript-wide registry across conversations

    def __init__(self):
        import persona
        import tools as tz_tools
        from session_state import SessionState

        self.session = SessionState()
        self.messages: list[dict] = [
            {"role": "system", "content": persona.SYSTEM_PROMPT}
        ]
        self.tools_json = _openai_tools()
        self.tool_calls_made: list[tuple[str, dict]] = []
        self._handlers = {
            "search_products": tz_tools.search_products,
            "get_product_details": tz_tools.get_product_details,
            "get_shop_info": tz_tools.get_shop_info,
            "create_reservation": tz_tools.create_reservation,
            "create_support_ticket": tz_tools.create_support_ticket,
            "schedule_callback": tz_tools.schedule_callback,
            "end_conversation_summary": tz_tools.make_end_conversation_summary(
                self.session
            ),
        }

    async def _completion(self, provider: str):
        """One chat completion against the given provider (all OpenAI-compatible)."""
        from openai import AsyncOpenAI

        if provider == "gemini":
            client = AsyncOpenAI(
                api_key=config.GOOGLE_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            return await client.chat.completions.create(
                model=config.GEMINI_LLM_MODEL,
                messages=self.messages,
                tools=self.tools_json,
                temperature=config.LLM_TEMPERATURE,
                max_completion_tokens=500,
                extra_body={"reasoning_effort": "none"},  # disable 2.5-flash thinking
            )
        if provider == "cerebras":
            client = AsyncOpenAI(
                api_key=config.CEREBRAS_API_KEY, base_url="https://api.cerebras.ai/v1"
            )
            model = config.CEREBRAS_LLM_MODEL
        else:
            client = AsyncOpenAI(
                api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1"
            )
            model = config.GROQ_LLM_MODEL
        return await client.chat.completions.create(
            model=model,  # llama-3.3-70b (non-reasoning) on both
            messages=self.messages,
            tools=self.tools_json,
            temperature=config.LLM_TEMPERATURE,
            max_completion_tokens=300,
        )

    async def say(self, user_text: str, max_rounds: int = 6) -> str:
        """Send one user turn; runs the tool loop; returns the assistant's spoken reply.

        Mirrors the production pipeline's provider failover: on repeated 429s from
        the primary provider it retries once with backoff, then switches to the
        other provider (Groq ⇄ Gemini) for the rest of the conversation.
        """
        self.messages.append({"role": "user", "content": user_text})
        spoken_parts: list[str] = []
        if not hasattr(self, "_provider"):
            self._provider = (
                config.LLM_PROVIDER
                if config.LLM_PROVIDER in ("cerebras", "groq", "gemini")
                else "cerebras"
            )
            # failover chain mirrors production: cerebras → groq → gemini
            self._fallbacks = {
                "cerebras": "groq",
                "groq": "gemini",
                "gemini": "cerebras",
            }

        for _ in range(max_rounds):
            resp = None
            for attempt in range(4):
                try:
                    resp = await self._completion(self._provider)
                    break
                except Exception as e:
                    is_rate = "429" in str(e) or "rate" in str(e).lower()
                    # llama-3.3 sometimes emits a malformed tool call (args JSON
                    # glued into the function name → Groq 400 "not in request.tools",
                    # D22); production self-heals by re-running the inference —
                    # mirror that with a plain same-provider retry
                    is_bad_tool = "400" in str(e) and (
                        "request.tools" in str(e) or "tool" in str(e).lower()
                    )
                    if is_bad_tool and attempt < 3:
                        print(f"  ⚠️ malformed tool call, retrying ({str(e)[:80]})")
                        await asyncio.sleep(2)
                        continue
                    if is_rate and attempt == 0:
                        await asyncio.sleep(4)
                        continue
                    if is_rate and attempt < 3:
                        fallback = self._fallbacks[self._provider]
                        print(
                            f"  ⚠️ LLM failover: {self._provider} → {fallback} ({str(e)[:80]})"
                        )
                        self._provider = fallback
                        continue
                    raise
            msg = resp.choices[0].message
            entry = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            self.messages.append(entry)
            if msg.content:
                spoken_parts.append(msg.content)

            if not msg.tool_calls:
                break

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                self.tool_calls_made.append((name, args))
                handler = self._handlers.get(name)
                params = FakeFunctionCallParams(name, args)
                if handler:
                    await handler(params)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(
                            params.result, ensure_ascii=False, default=str
                        ),
                    }
                )

        from processors import sanitize_text

        reply = sanitize_text(" ".join(spoken_parts)).strip()
        if reply:
            AgentConversation.all_replies.append(reply)
        return reply


# --- Assertion helpers ---------------------------------------------------------------


def extract_big_numbers(text: str) -> set[int]:
    """Extract >=5-digit numbers (prices) from text, tolerating separators and Urdu digits."""
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    t = text.translate(trans)
    t = re.sub(r"(?<=\d)[,،.](?=\d{3}\b)", "", t)  # thousands separators
    return {int(m) for m in re.findall(r"\d{5,9}", t)}


async def db_prices() -> set[int]:
    import db

    client = await db.get_client()
    res = await client.table("products").select("price_pkr").execute()
    return {r["price_pkr"] for r in res.data}


class Check:
    """Tiny pass/fail collector shared by all test modules."""

    def __init__(self, name: str):
        self.name = name
        self.results: list[tuple[str, bool, str]] = []

    def ok(self, label: str, cond: bool, detail: str = ""):
        self.results.append((label, bool(cond), detail))
        mark = "PASS" if cond else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
        return cond

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.results)
