#!/usr/bin/env python3
"""Upload recorded voice previews to Supabase Storage + populate voices.preview_url (P5-T02: pre-
render, THIS script P5-T03: CDN + signed URLs, long cache).

Supabase Storage is used as the CDN rather than a new third-party vendor: it's already a free-tier
resource this project has credentials for (SUPABASE_SERVICE_ROLE), matching CLAUDE.md #8 (dev is
free-tier only) without introducing an undocumented new stack dependency. Bucket is PRIVATE --
access is signed-URL-only, which is the actual point of "Never proxy live TTS for previews... CDN
-> signed URLs" (docs/25-PHASE-5-VOICE-PICKER.md): a public bucket would make signed URLs pointless
security theatre, since the raw path would work forever regardless of the signed token.

    python scripts/upload_voice_previews.py            # upload + sign + populate voices table
    python scripts/upload_voice_previews.py --dry-run  # show the plan, zero writes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import dotenv_values

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dbconn import conn_kwargs  # noqa: E402

PREVIEWS_DIR = ROOT / "voice-picker" / "previews"
BUCKET_ID = "voice-previews"
SIGNED_URL_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days -- matches the Cache-Control max-age below
CACHE_CONTROL = f"public, max-age={SIGNED_URL_TTL_SECONDS}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show the plan; no upload, no DB write")
    args = ap.parse_args()

    wavs = sorted(PREVIEWS_DIR.glob("*.wav"))
    if not wavs:
        sys.exit(f"REFUSED: no .wav files in {PREVIEWS_DIR} (run P5-T02 first).")

    print(f"{len(wavs)} local preview files found in {PREVIEWS_DIR}")
    for w in wavs[:5]:
        print(f"  {w.name} ({w.stat().st_size} bytes)")
    if len(wavs) > 5:
        print(f"  ... and {len(wavs) - 5} more")

    if args.dry_run:
        print(f"\nDRY RUN -- would create/verify bucket {BUCKET_ID!r} (private), upload "
              f"{len(wavs)} files, sign for {SIGNED_URL_TTL_SECONDS}s, and update "
              f"voices.preview_url for each. No network, no writes.")
        return 0

    env = dotenv_values(ROOT / ".env.local")
    url = env.get("SUPABASE_URL")
    service_role = env.get("SUPABASE_SERVICE_ROLE")
    if not url or not service_role:
        sys.exit("REFUSED: SUPABASE_URL / SUPABASE_SERVICE_ROLE not in .env.local.")

    from supabase import create_client

    client = create_client(url, service_role)
    storage = client.storage

    existing_ids = {b.id for b in storage.list_buckets()}
    if BUCKET_ID not in existing_ids:
        storage.create_bucket(BUCKET_ID, options={"public": False})
        print(f"created private bucket {BUCKET_ID!r}")
    else:
        print(f"bucket {BUCKET_ID!r} already exists")

    bucket = storage.from_(BUCKET_ID)

    uploaded = 0
    signed_urls: dict[str, str] = {}
    for wav in wavs:
        voice_id = wav.stem
        path = f"{voice_id}.wav"
        data = wav.read_bytes()
        try:
            bucket.upload(
                path,
                data,
                file_options={"content-type": "audio/wav", "cache-control": CACHE_CONTROL, "upsert": "true"},
            )
        except Exception as e:
            print(f"  [{voice_id}] UPLOAD FAILED: {e}")
            continue

        signed = bucket.create_signed_url(path, SIGNED_URL_TTL_SECONDS)
        signed_url = signed.get("signedURL") or signed.get("signedUrl")
        if not signed_url:
            print(f"  [{voice_id}] SIGN FAILED: no URL in response {signed!r}")
            continue

        signed_urls[voice_id] = signed_url
        uploaded += 1
        print(f"  [{voice_id}] uploaded + signed ({len(data)} bytes)")

    print(f"\n{uploaded}/{len(wavs)} uploaded and signed.")

    import psycopg

    updated = 0
    with psycopg.connect(**conn_kwargs()) as conn:
        for voice_id, signed_url in signed_urls.items():
            conn.execute(
                "update voices set preview_url = %s where id = %s", (signed_url, voice_id)
            )
            updated += 1
        conn.commit()
    print(f"{updated}/{len(signed_urls)} voices.preview_url rows updated (committed).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
