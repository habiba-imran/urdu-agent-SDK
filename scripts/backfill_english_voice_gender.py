#!/usr/bin/env python3
"""Backfill voices.gender for cartesia/elevenlabs/rime -- every English voice was seeded with
gender left NULL (scripts/fetch_cartesia_voices.py and scripts/fetch_elevenlabs_voices.py only
ever captured id/display_name/provider_voice_id, even though the source catalogue endpoints
return gender directly). Rime voices were seeded without any fetch script at all.

Read-only against the vendor APIs (all three are free metadata endpoints, no TTS billing) --
safe to rerun any time. fish_audio is excluded: it has no equivalent public catalogue endpoint
used here and its account is unfunded/blocked anyway (state/BLOCKERS.md::BLOCK-FISHAUDIO).

Vendor vocabularies are normalized to this table's existing convention (lowercase 'male'/'female',
NULL for anything else -- androgynous/non-binary voices are represented as NULL, not a third
string value, matching the existing `khwajasara` (uplift) precedent):
  - cartesia:   'masculine'->male, 'feminine'->female, 'gender_neutral'->NULL
  - elevenlabs: 'male'->male, 'female'->female, 'neutral'->NULL
  - rime:       'Male'->male, 'Female'->female, 'Non-binary'/''->NULL

    python scripts/backfill_english_voice_gender.py --dry-run   # show the plan, zero DB writes
    python scripts/backfill_english_voice_gender.py             # fetch + update
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dbconn import conn_kwargs  # noqa: E402

_CARTESIA_MAP = {"masculine": "male", "feminine": "female", "gender_neutral": None}
_ELEVENLABS_MAP = {"male": "male", "female": "female", "neutral": None}
_RIME_MAP = {"Male": "male", "Female": "female", "Non-binary": None, "": None}


def fetch_cartesia_genders(api_key: str) -> dict[str, str | None]:
    """provider_voice_id (Cartesia's real voice `id`) -> normalized gender."""
    out: dict[str, str | None] = {}
    starting_after = None
    while True:
        url = "https://api.cartesia.ai/voices?limit=100"
        if starting_after:
            url += f"&starting_after={starting_after}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Cartesia-Version": "2025-04-16"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        batch = data.get("data", [])
        for v in batch:
            raw = v.get("gender")
            if raw not in _CARTESIA_MAP:
                raise ValueError(f"unmapped cartesia gender {raw!r} for voice {v.get('id')!r}")
            out[v["id"]] = _CARTESIA_MAP[raw]
        if not data.get("has_more") or not batch:
            break
        starting_after = batch[-1]["id"]
    return out


def fetch_elevenlabs_genders(api_key: str) -> dict[str, str | None]:
    """provider_voice_id (ElevenLabs' real voice_id) -> normalized gender."""
    out: dict[str, str | None] = {}
    next_page_token = None
    while True:
        url = "https://api.elevenlabs.io/v2/voices?page_size=100"
        if next_page_token:
            url += f"&page_token={next_page_token}"
        req = urllib.request.Request(url, headers={"xi-api-key": api_key})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        for v in data.get("voices", []):
            raw = v.get("labels", {}).get("gender")
            if raw not in _ELEVENLABS_MAP:
                raise ValueError(
                    f"unmapped elevenlabs gender {raw!r} for voice {v.get('voice_id')!r}"
                )
            out[v["voice_id"]] = _ELEVENLABS_MAP[raw]
        if not data.get("has_more"):
            break
        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break
    return out


def fetch_rime_genders() -> dict[str, str | None]:
    """speaker (Rime's real provider_voice_id) -> normalized gender. Public data file, no auth
    needed -- covers every language, filtered to English speakers here since that's this
    project's only Rime scope."""
    req = urllib.request.Request("https://users.rime.ai/data/voices/voice_details.json")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    out: dict[str, str | None] = {}
    for d in data:
        if d.get("lang") != "eng":
            continue
        raw = d.get("gender", "")
        if raw not in _RIME_MAP:
            raise ValueError(f"unmapped rime gender {raw!r} for speaker {d.get('speaker')!r}")
        out[d["speaker"]] = _RIME_MAP[raw]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="show the plan; no DB writes")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env.local", override=False)

    import psycopg

    with psycopg.connect(**conn_kwargs(), prepare_threshold=None) as conn:
        rows = conn.execute(
            """
            select id, provider, provider_voice_id, gender
            from voices
            where provider in ('cartesia', 'elevenlabs', 'rime') and language = 'en'
            order by provider, id
            """
        ).fetchall()

    print(f"{len(rows)} en voices across cartesia/elevenlabs/rime in the DB.\n")

    cartesia_key = os.environ.get("CARTESIA_API_KEY")
    eleven_key = os.environ.get("ELEVEN_API_KEY")
    if not cartesia_key or not eleven_key:
        sys.exit("REFUSED: CARTESIA_API_KEY / ELEVEN_API_KEY not set.")

    print("fetching cartesia catalogue...")
    cartesia_genders = fetch_cartesia_genders(cartesia_key)
    print(f"  {len(cartesia_genders)} cartesia voices fetched")
    print("fetching elevenlabs catalogue...")
    eleven_genders = fetch_elevenlabs_genders(eleven_key)
    print(f"  {len(eleven_genders)} elevenlabs voices fetched")
    print("fetching rime catalogue...")
    rime_genders = fetch_rime_genders()
    print(f"  {len(rime_genders)} rime (eng) speakers fetched\n")

    by_provider = {"cartesia": cartesia_genders, "elevenlabs": eleven_genders, "rime": rime_genders}

    plan: list[tuple[str, str, str | None, str | None]] = []  # (id, provider, old, new)
    unmatched: list[tuple[str, str, str]] = []  # (id, provider, provider_voice_id)
    for row_id, provider, provider_voice_id, old_gender in rows:
        genders = by_provider[provider]
        if provider_voice_id not in genders:
            unmatched.append((row_id, provider, provider_voice_id))
            continue
        new_gender = genders[provider_voice_id]
        if new_gender != old_gender:
            plan.append((row_id, provider, old_gender, new_gender))

    from collections import Counter

    print("changes by (provider, old -> new):")
    for (provider, old, new), count in Counter(
        (p, o, n) for _, p, o, n in plan
    ).most_common():
        print(f"  {provider:12s} {str(old):8s} -> {str(new):8s}  x{count}")

    if unmatched:
        print(f"\n{len(unmatched)} DB voices had no match in the fetched catalogue (left as-is):")
        for row_id, provider, pvid in unmatched[:10]:
            print(f"  [{provider}] {row_id} (provider_voice_id={pvid})")
        if len(unmatched) > 10:
            print(f"  ... and {len(unmatched) - 10} more")

    print(f"\n{len(plan)} rows would be updated.")

    if args.dry_run:
        print("\nDRY RUN -- no DB writes.")
        return 0

    if not plan:
        print("Nothing to update.")
        return 0

    with psycopg.connect(**conn_kwargs(), prepare_threshold=None) as conn:
        for row_id, _provider, _old, new_gender in plan:
            conn.execute("update voices set gender = %s where id = %s", (new_gender, row_id))
        conn.commit()

    print(f"Committed {len(plan)} updates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
