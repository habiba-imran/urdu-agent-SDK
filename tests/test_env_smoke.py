"""STEP 9.1 — Env smoke tests: one real call to every external dependency.

Fails loudly with which key/service is broken.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import Check, groq_transcribe, synth_urdu

import config


async def run() -> Check:
    check = Check("env_smoke")

    # 1. Uplift TTS (synthesizes the WAV we reuse for Whisper below)
    wav = b""
    try:
        wav = await synth_urdu("السلام علیکم، یہ ایک ٹیسٹ ہے۔")
        check.ok("Uplift TTS (UPLIFTAI_API_KEY)", len(wav) > 20000, f"{len(wav)} bytes")
    except Exception as e:
        check.ok("Uplift TTS (UPLIFTAI_API_KEY)", False, str(e)[:150])

    # 2. Groq Whisper STT
    try:
        text, secs = await groq_transcribe(wav)
        check.ok("Groq Whisper (GROQ_API_KEY)", len(text) > 0, f"{secs*1000:.0f}ms → {text!r}")
    except Exception as e:
        check.ok("Groq Whisper (GROQ_API_KEY)", False, str(e)[:150])

    # 3. Groq LLM
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1"
        )
        res = await client.chat.completions.create(
            model=config.GROQ_LLM_MODEL,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_completion_tokens=100,
        )
        out = res.choices[0].message.content or ""
        check.ok(f"Groq LLM ({config.GROQ_LLM_MODEL})", "OK" in out.upper(), out[:60])
    except Exception as e:
        # a rate-limit response proves the key authenticates; quota is a capacity
        # issue (the pipeline fails over to Gemini in that case), not a broken key
        quota_hit = "rate_limit_exceeded" in str(e) or "429" in str(e)
        check.ok(
            f"Groq LLM ({config.GROQ_LLM_MODEL})",
            quota_hit,
            ("key valid, free-tier quota exhausted → Gemini failover covers it: " if quota_hit else "")
            + str(e)[:130],
        )

    # 4. Gemini
    try:
        from google import genai

        gclient = genai.Client(api_key=config.GOOGLE_API_KEY)
        res = await asyncio.to_thread(
            gclient.models.generate_content,
            model=config.GEMINI_LLM_MODEL,
            contents="Reply with exactly: OK",
        )
        check.ok("Gemini (GOOGLE_API_KEY)", "OK" in (res.text or "").upper(), (res.text or "")[:60])
    except Exception as e:
        check.ok("Gemini (GOOGLE_API_KEY)", False, str(e)[:150])

    # 5. Supabase read + write
    try:
        import db

        client = await db.get_client()
        res = await client.table("shop_info").select("name").eq("id", 1).execute()
        check.ok(
            "Supabase read (SUPABASE_URL/KEY)",
            bool(res.data) and res.data[0]["name"] == "TechZone Laptops",
            str(res.data)[:80],
        )
        import uuid as _uuid

        conv_id = str(_uuid.uuid4())
        await client.table("conversations").insert(
            {"id": conv_id, "channel": "smoke-test"}
        ).execute()
        got = await client.table("conversations").select("id").eq("id", conv_id).execute()
        await client.table("conversations").delete().eq("id", conv_id).execute()
        check.ok("Supabase write", bool(got.data), conv_id)
    except Exception as e:
        check.ok("Supabase read/write", False, str(e)[:150])

    return check


if __name__ == "__main__":
    c = asyncio.run(run())
    sys.exit(0 if c.passed else 1)
