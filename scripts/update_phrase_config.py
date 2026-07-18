"""Create (or recreate) the Uplift phrase-replacement config for this repo's persona (ADR-006
Layer 2). Config CRUD only — no TTS synthesis, zero Uplift audio-minute budget (ADR-006).

Writes the resulting configId to .uplift_phrase_config so worker/factories.py picks it up.
Run: python scripts/update_phrase_config.py
"""

import json
import os
import urllib.request

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

KEY = os.environ["UPLIFTAI_API_KEY"]
BASE = "https://api.upliftai.org/v1/synthesis/phrase-replacement-config"
OUT = os.path.join(os.path.dirname(__file__), "..", ".uplift_phrase_config")

# ADR-006's actual rule (quoted, not paraphrased): "Mappings from the old repo's D42 list were
# removed — they were ported on assumption, not measured. Layer 1 (Latin-script convention) may
# be sufficient on its own. When a real mispronunciation is heard in a recording, the specific
# problem phrase goes here as a tested correction, not a guessed one."
#
# CORRECTION (2026-07-18): an earlier version of this file had a comment here claiming the old
# D42 list (16 entries) was "human-verified... heard-correct in a recording." That was wrong —
# ADR-006 says the opposite: those entries were removed specifically because they were ported on
# assumption, never measured against this product's own recordings. Do not trust that old
# comment's framing if you find it referenced elsewhere (e.g. state/PROGRESS.md's Phase-3
# history) — ADR-006's own text is the authority, and it is quoted above, not summarized.
#
# Only ONE entry has real listening evidence behind it as of 2026-07-18: RAM, confirmed
# mispronounced by ear in a real recording. Every other candidate term (from the old D42 list,
# and every new term persona.py's OUTPUT rule names) is HELD — not written here, not reused,
# not assumed correct just because it sounds plausible — until it is independently heard
# mispronounced in a real recording and the specific fix is confirmed, per ADR-006's rule. Add
# entries to this list ONE AT A TIME, each with a one-line note of which recording it was heard
# in, as that evidence actually accumulates. Do not batch-add speculative entries again.
PHRASE_REPLACEMENTS = [
    {"phrase": "RAM", "replacement": "ریم"},  # heard mispronounced, confirmed by ear
]


def api(method: str, url: str, body: dict | None = None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else None


def main():
    replacements = PHRASE_REPLACEMENTS

    # Remove the stale empty config (ADR-006: 38949e76-... currently has 0 entries) and any
    # others, same cleanup pattern as the old repo's script.
    for cfg in api("GET", BASE) or []:
        cid = cfg.get("configId")
        try:
            api("DELETE", f"{BASE}/{cid}")
            print(f"deleted old config {cid}")
        except Exception as e:
            print(f"could not delete {cid}: {e}")

    created = api(
        "POST", BASE, {"name": "uva-persona-terms", "phraseReplacements": replacements}
    )
    config_id = created["configId"]

    # Verify round-trip encoding (same assertion as the old repo's script).
    all_cfgs = api("GET", BASE)
    mine = next(c for c in all_cfgs if c["configId"] == config_id)
    sample = mine["phraseReplacements"][0]["replacement"]
    assert "?" not in sample and any("؀" <= ch <= "ۿ" for ch in sample), (
        f"replacement text not stored as Urdu: {sample!r}"
    )

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(config_id)
    ok_sample = sample.encode("ascii", "backslashreplace").decode()
    print(
        f"OK configId={config_id} replacements={len(replacements)} sample={ok_sample}"
    )


if __name__ == "__main__":
    main()
