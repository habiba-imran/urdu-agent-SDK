#!/usr/bin/env python3
"""Record + upload + sign a preview clip for every enabled `en` voice on cartesia/elevenlabs/rime
that doesn't have one yet (voices.preview_url IS NULL). These three providers were added later
(ADR-036, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md) and never got a preview pipeline of
their own -- only Uplift (`ur`) has one (scripts/record_voice_previews.py +
scripts/upload_voice_previews.py). fish_audio is deliberately excluded here: its account is
unfunded and every synthesize call 402s (state/BLOCKERS.md::BLOCK-FISHAUDIO).

Unlike the Uplift pair (record all -> write local .wav files -> separate upload pass), this does
record -> upload -> sign -> DB update per voice, one at a time, so a failure partway through
leaves every already-finished voice fully done (bucket object + signed preview_url committed)
instead of stuck in an intermediate local-only state that needs a second pass to finish.

Reuses the exact adapters the live worker uses (worker/providers/tts/{cartesia,elevenlabs,rime}.py
`build()`), and the same `voices.provider_voice_id` translation worker/main.py's
`_resolve_provider_voice_id()` does -- our internal `voices.id` slug is NOT the vendor's real
voice ID for these three providers (unlike Uplift, where Phase 1 backfilled them to match).

Same signed-URL bucket/TTL as scripts/upload_voice_previews.py (`voice-previews`, 7 days) -- these
rows will be picked up by the existing scripts/resign_voice_previews.py re-sign job automatically
(it selects `WHERE preview_url IS NOT NULL` across every provider, not just uplift).

    # 1. preview the exact plan -- zero network, zero cost:
    python scripts/record_provider_voice_previews.py --dry-run

    # 2. record + upload + sign for every enabled provider (human-approved only):
    RECORD_PROVIDER_PREVIEWS=1 python scripts/record_provider_voice_previews.py

    # 3. or scope to one provider:
    RECORD_PROVIDER_PREVIEWS=1 python scripts/record_provider_voice_previews.py --provider cartesia
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dbconn import conn_kwargs  # noqa: E402
from usage_guard import increment  # noqa: E402
from services.tts_cache import pcm_to_wav  # noqa: E402

BUCKET_ID = "voice-previews"
SIGNED_URL_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days -- matches upload_voice_previews.py
CACHE_CONTROL = f"public, max-age={SIGNED_URL_TTL_SECONDS}"
MAX_SECONDS = 10.0  # safety cap per line -- these are short greetings, not paragraphs

# English previews don't need gender-matched grammar the way Urdu does (no verb-gender marking
# on "I can help" in English) -- one line for every voice.
PREVIEW_TEXT = "Hi there! I'm here to help. What can I do for you today?"

# Providers this script covers. fish_audio excluded: BLOCK-FISHAUDIO, account unfunded, 402s.
PROVIDERS = ("cartesia", "elevenlabs", "rime")


def _build_tts(provider: str, provider_voice_id: str):
    if provider == "cartesia":
        from worker.providers.tts.cartesia import build
    elif provider == "elevenlabs":
        from worker.providers.tts.elevenlabs import build
    elif provider == "rime":
        from worker.providers.tts.rime import build
    else:
        raise ValueError(f"unhandled provider {provider!r}")
    return build(provider_voice_id, "en")


def fetch_voices(conn, provider: str) -> list[dict]:
    rows = conn.execute(
        """
        select id, provider_voice_id
        from voices
        where provider = %s and language = 'en' and enabled = true
          and rollout_state = 'enabled' and preview_url is null
        order by id
        """,
        (provider,),
    ).fetchall()
    missing = [r[0] for r in rows if not r[1]]
    if missing:
        sys.exit(
            f"REFUSED: {len(missing)} {provider} voice(s) have no provider_voice_id set "
            f"(e.g. {missing[0]!r}) -- cannot call the vendor API without their real voice ID."
        )
    return [{"id": r[0], "provider_voice_id": r[1]} for r in rows]


async def synth_one(provider: str, provider_voice_id: str, text: str) -> tuple[bytes, int]:
    # cartesia/elevenlabs/rime's plugins pull their aiohttp session from livekit-agents'
    # job-scoped http_context, which only exists inside a real running agent worker. Running
    # them standalone here (not via `python -m worker.main`) needs this explicit context --
    # without it every call raises "Attempted to use an http session outside of a job context"
    # (wrapped by the plugin into a generic APIConnectionError("Connection error.")).
    from livekit.agents.utils import http_context

    async with http_context.open():
        tts = _build_tts(provider, provider_voice_id)
        pcm = bytearray()
        sr = 22050
        try:
            async for ev in tts.synthesize(text):
                sr = ev.frame.sample_rate
                pcm += bytes(ev.frame.data)
                if len(pcm) / (2 * sr) > MAX_SECONDS:
                    break
        finally:
            await tts.aclose()
    return bytes(pcm), sr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show the plan; no network, no writes")
    ap.add_argument(
        "--provider", choices=PROVIDERS, help="scope to one provider instead of all three"
    )
    args = ap.parse_args()

    providers = [args.provider] if args.provider else list(PROVIDERS)

    import psycopg

    with psycopg.connect(**conn_kwargs(), prepare_threshold=None) as conn:
        plan: dict[str, list[dict]] = {}
        for provider in providers:
            plan[provider] = fetch_voices(conn, provider)

    total = sum(len(v) for v in plan.values())
    est_chars_per_voice = len(PREVIEW_TEXT)
    print(f"Preview line ({est_chars_per_voice} chars): {PREVIEW_TEXT!r}\n")
    for provider, voices in plan.items():
        print(f"{provider:12s} {len(voices):4d} voice(s) need a preview")
    print(f"\n{total} total voices to record across {len(providers)} provider(s).")

    if args.dry_run:
        for provider, voices in plan.items():
            for v in voices[:3]:
                print(f"  would record+upload+sign [{provider}] {v['id']} (pvid={v['provider_voice_id']})")
            if len(voices) > 3:
                print(f"  ... and {len(voices) - 3} more {provider} voices")
        print("\nDRY RUN -- no synthesis, no upload, no DB writes.")
        return 0

    if total == 0:
        print("Nothing to do -- every voice already has a preview_url.")
        return 0

    if os.environ.get("RECORD_PROVIDER_PREVIEWS") != "1":
        sys.exit(
            "REFUSED: set RECORD_PROVIDER_PREVIEWS=1 to actually record+upload+sign "
            "(human-approved only, spends real provider TTS budget). Use --dry-run to preview."
        )

    # The TTS plugins (cartesia.TTS/elevenlabs.TTS/rime.TTS) read their API keys straight from
    # os.environ themselves -- no api_key= kwarg is passed by worker/providers/tts/*.py's
    # build(), matching the live worker's own setup. override=False so a real deployed env var
    # always wins over the file, same pattern as tenant_portal_api/app.py.
    load_dotenv(ROOT / ".env.local", override=False)
    env = dotenv_values(ROOT / ".env.local")
    url = os.environ.get("SUPABASE_URL") or env.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE") or env.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        sys.exit(
            "REFUSED: SUPABASE_URL / SUPABASE_SERVICE_ROLE not set "
            "(checked os.environ, then .env.local)."
        )

    from supabase import create_client

    client = create_client(url, service_role)
    bucket = client.storage.from_(BUCKET_ID)

    recorded = 0
    failed: list[str] = []

    for provider, voices in plan.items():
        for v in voices:
            voice_id = v["id"]
            try:
                pcm, sr = asyncio.run(synth_one(provider, v["provider_voice_id"], PREVIEW_TEXT))
                if not pcm:
                    raise RuntimeError("empty audio returned")
                wav = pcm_to_wav(pcm, sr)
                duration = len(pcm) / (2 * sr)

                path = f"{voice_id}.wav"
                bucket.upload(
                    path,
                    wav,
                    file_options={
                        "content-type": "audio/wav",
                        "cache-control": CACHE_CONTROL,
                        "upsert": "true",
                    },
                )
                signed = bucket.create_signed_url(path, SIGNED_URL_TTL_SECONDS)
                signed_url = signed.get("signedURL") or signed.get("signedUrl")
                if not signed_url:
                    raise RuntimeError(f"sign failed: no URL in response {signed!r}")

                with psycopg.connect(**conn_kwargs(), prepare_threshold=None) as conn:
                    conn.execute(
                        "update voices set preview_url = %s where id = %s",
                        (signed_url, voice_id),
                    )
                    conn.commit()

                increment(f"{provider}_tts_sec", round(duration, 2))
                recorded += 1
                print(f"  [{provider}] {voice_id}: recorded {duration:.2f}s, uploaded, signed, committed")
            except Exception as e:
                failed.append(voice_id)
                print(f"  [{provider}] {voice_id}: FAILED - {e}")

    print(f"\nDone: {recorded}/{total} recorded+uploaded+signed+committed.")
    if failed:
        print(f"{len(failed)} failed: {failed}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
