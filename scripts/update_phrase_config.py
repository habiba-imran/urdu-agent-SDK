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

# Every Latin-script term persona.py's OUTPUT rule explicitly calls out (brand names,
# technical terms, product names, units). Multi-word phrases listed before their sub-tokens
# so they win the match (same convention as the old repo's D42 config).
#
# REUSED verbatim from the old repo's scripts/create_phrase_config.py (D42; human-verified —
# the script round-trip-asserts the stored replacement is real Urdu script, and D42 recorded
# it as heard-correct in a recording). Not re-guessed.
_REUSED_FROM_D42 = [
    {"phrase": "TechZone", "replacement": "ٹیک زون"},
    {"phrase": "MacBook", "replacement": "میک بُک"},
    {"phrase": "ThinkPad", "replacement": "تھنک پیڈ"},
    {"phrase": "Lenovo", "replacement": "لینووو"},
    {"phrase": "Dell", "replacement": "ڈیل"},
    {"phrase": "XPS", "replacement": "ایکس پی ایس"},
    {"phrase": "Air", "replacement": "ایئر"},
    {"phrase": "Pro", "replacement": "پرو"},
    {"phrase": "SSD", "replacement": "ایس ایس ڈی"},
    {"phrase": "RAM", "replacement": "ریم"},
    {"phrase": "GB", "replacement": "جی بی"},
    {"phrase": "TB", "replacement": "ٹی بی"},
    {"phrase": "USB", "replacement": "یو ایس بی"},
    {"phrase": "warranty", "replacement": "وارنٹی"},
    {"phrase": "battery", "replacement": "بیٹری"},
    {"phrase": "laptop", "replacement": "لیپ ٹاپ"},
]

# NEW — not in the old config, needed because persona.py's current term list adds them.
# My transliteration, following the SAME letter-by-letter-acronym / phonetic convention as
# the reused entries above, but NOT human-verified by ear. FLAGGED for human confirmation
# before this is committed live, per the task instructions:
#   - "Bluetooth" -> "بلوٹوتھ": lowest confidence of this batch: multiple plausible Urdu
#     spellings exist for this loanword and I have no prior human-verified reference for it.
#   - "M2" -> "ایم ٹو": high confidence — exact same pattern as the old config's verified
#     M1/M3/M4 entries ("ایم ون"/"ایم تھری"/"ایم فور"), just the missing number in the series.
#   - "battery health" -> "بیٹری ہیلتھ": compound phrase, listed before the bare "battery"
#     entry above so it wins the match on the full phrase; "بیٹری" half is reused/verified,
#     "ہیلتھ" half is new.
#   - "WiFi" -> "وائی فائی", "HDMI" -> "ایچ ڈی ایم آئی", "charger" -> "چارجر",
#     "processor" -> "پروسیسر", "display" -> "ڈسپلے": moderate confidence, common
#     transliterations, but not human-verified in this product's own recordings.
_NEW_PROPOSED = [
    {"phrase": "battery health", "replacement": "بیٹری ہیلتھ"},
    {"phrase": "WiFi", "replacement": "وائی فائی"},
    {"phrase": "Bluetooth", "replacement": "بلوٹوتھ"},
    {"phrase": "HDMI", "replacement": "ایچ ڈی ایم آئی"},
    {"phrase": "charger", "replacement": "چارجر"},
    {"phrase": "processor", "replacement": "پروسیسر"},
    {"phrase": "display", "replacement": "ڈسپلے"},
    {"phrase": "M2", "replacement": "ایم ٹو"},
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
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--reused-only",
        action="store_true",
        help="write only the 16 D42-verified entries; skip the 8 new unconfirmed ones",
    )
    args = ap.parse_args()
    replacements = _REUSED_FROM_D42 if args.reused_only else _NEW_PROPOSED + _REUSED_FROM_D42

    # Remove the stale empty config (ADR-006: 38949e76-... currently has 0 entries) and any
    # others, same cleanup pattern as the old repo's script.
    for cfg in api("GET", BASE) or []:
        cid = cfg.get("configId")
        try:
            api("DELETE", f"{BASE}/{cid}")
            print(f"deleted old config {cid}")
        except Exception as e:
            print(f"could not delete {cid}: {e}")

    created = api("POST", BASE, {"name": "uva-persona-terms", "phraseReplacements": replacements})
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
    print(f"OK configId={config_id} replacements={len(replacements)} sample={ok_sample}")


if __name__ == "__main__":
    main()
