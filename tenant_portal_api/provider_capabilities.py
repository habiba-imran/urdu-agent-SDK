"""Public capabilities view — Phase 4 of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md
(ADR-036). Combines worker/providers/capabilities.py's STT/LLM data with the `voices` table's
TTS/voice data into the single JSON shape the guide's `GET .../provider-capabilities` example
specifies.

Only `state == "enabled"` entries are ever included. This repo has no admin/internal-only variant
of any agent-management route yet — every current caller of this module is tenant-facing
(`/portal/provider-capabilities`, `/machine/provider-capabilities`), so there is nothing that
should ever see a `planned`/`testing` entry through this endpoint. If an internal/admin surface is
ever built, `testing` inclusion belongs there, not here — not invented in advance of that surface
actually existing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from worker.providers.capabilities import CAPABILITIES  # noqa: E402

_LANGUAGE_LABELS = {"ur": "Urdu", "en": "English"}

# Prefer receptionist-friendly defaults over alphabetical first voice id.
_PREFERRED_DEFAULT_VOICES: dict[str, tuple[str, ...]] = {
    "cartesia": (
        "cartesia-sonic-default",
        "cartesia-katie-friendly-fixer",
        "cartesia-cindy-baker-receptionist",
        "cartesia-skylar-friendly-guide",
    ),
    "rime": ("rime-arcana-andromeda",),
}


def _pick_default_voice(voice_ids: list[str], provider: str) -> str | None:
    if not voice_ids:
        return None
    preferred = _PREFERRED_DEFAULT_VOICES.get(provider, ())
    for voice_id in preferred:
        if voice_id in voice_ids:
            return voice_id
    return voice_ids[0]


def get_public_capabilities(conn: psycopg.Connection) -> dict:
    languages: dict = {}

    for language, layers in CAPABILITIES.items():
        entry: dict = {"label": _LANGUAGE_LABELS.get(language, language)}

        for layer in ("stt", "llm"):
            enabled = {
                provider: {
                    "state": cap["state"],
                    "models": cap["models"],
                    "defaultModel": cap["default_model"],
                }
                for provider, cap in layers.get(layer, {}).items()
                if cap["state"] == "enabled"
            }
            if enabled:
                entry[layer] = enabled

        tts_enabled = {}
        for provider, cap in layers.get("tts", {}).items():
            if cap["state"] != "enabled":
                continue
            voice_rows = conn.execute(
                "select id from voices where provider = %s and language = %s "
                "and rollout_state = 'enabled' and enabled = true order by id",
                (provider, language),
            ).fetchall()
            voice_ids = [r[0] for r in voice_rows]
            tts_enabled[provider] = {
                "state": cap["state"],
                "voices": voice_ids,
                "defaultVoice": _pick_default_voice(voice_ids, provider),
            }
        if tts_enabled:
            entry["tts"] = tts_enabled

        # Only include a language if it has at least one enabled combination in some layer —
        # otherwise a language with everything still `planned` (en, today) would show up as an
        # empty shell, which is worse than not mentioning it at all.
        if "stt" in entry or "llm" in entry or "tts" in entry:
            languages[language] = entry

    return {"languages": languages}
