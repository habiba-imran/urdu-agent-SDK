#!/usr/bin/env python3
"""Re-sign expired voice-preview URLs in Supabase Storage without re-uploading or re-recording
audio. The .wav files already exist in the private `voice-previews` bucket from the original
upload_voice_previews.py run -- only the signed URL's exp claim went stale, since that script
bakes a fixed 7-day TTL into voices.preview_url with nothing to refresh it afterward.

    python scripts/resign_voice_previews.py             # re-sign every voice with a non-null preview_url
    python scripts/resign_voice_previews.py --dry-run   # show the plan, zero writes
"""

from __future__ import annotations

import argparse
import os
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

BUCKET_ID = "voice-previews"
SIGNED_URL_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days -- matches upload_voice_previews.py


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run", action="store_true", help="show the plan; no signing, no DB write"
    )
    args = ap.parse_args()

    import psycopg

    with psycopg.connect(**conn_kwargs(), prepare_threshold=None) as conn:
        rows = conn.execute(
            "select id from voices where preview_url is not null order by id"
        ).fetchall()
    voice_ids = [r[0] for r in rows]

    print(f"{len(voice_ids)} voices with a (possibly expired) preview_url found.")

    if args.dry_run:
        for vid in voice_ids[:10]:
            print(f"  would re-sign {vid}.wav")
        if len(voice_ids) > 10:
            print(f"  ... and {len(voice_ids) - 10} more")
        print("\nDRY RUN -- no signing, no DB writes.")
        return 0

    # checks the real process environment first (CI/deployed) -- matches dbconn.conn_kwargs()
    _env_file = dotenv_values(ROOT / ".env.local")
    url = os.environ.get("SUPABASE_URL") or _env_file.get("SUPABASE_URL")
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE") or _env_file.get(
        "SUPABASE_SERVICE_ROLE"
    )
    if not url or not service_role:
        sys.exit(
            "REFUSED: SUPABASE_URL / SUPABASE_SERVICE_ROLE not set "
            "(checked os.environ, then .env.local)."
        )

    from supabase import create_client

    client = create_client(url, service_role)
    bucket = client.storage.from_(BUCKET_ID)

    signed_urls: dict[str, str] = {}
    missing: list[str] = []
    for vid in voice_ids:
        path = f"{vid}.wav"
        try:
            signed = bucket.create_signed_url(path, SIGNED_URL_TTL_SECONDS)
        except Exception as e:
            print(f"  [{vid}] SIGN FAILED: {e}")
            missing.append(vid)
            continue
        signed_url = signed.get("signedURL") or signed.get("signedUrl")
        if not signed_url:
            print(f"  [{vid}] SIGN FAILED: no URL in response {signed!r}")
            missing.append(vid)
            continue
        signed_urls[vid] = signed_url

    print(f"\n{len(signed_urls)}/{len(voice_ids)} re-signed.")
    if missing:
        print(f"{len(missing)} missing/failed (object not found in bucket?): {missing}")

    updated = 0
    with psycopg.connect(**conn_kwargs(), prepare_threshold=None) as conn:
        for vid, signed_url in signed_urls.items():
            conn.execute(
                "update voices set preview_url = %s where id = %s",
                (signed_url, vid),
            )
            updated += 1
        conn.commit()
    print(f"{updated}/{len(signed_urls)} voices.preview_url rows updated (committed).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
