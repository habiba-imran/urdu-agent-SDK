"""Cartesia TTS adapter (Phase 6c, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py (provider level) AND
the specific voice row's own `rollout_state`/`enabled` in the `voices` table are both the real
gates, not this file. `voice`/`language` constructor args verified directly against the installed
livekit-plugins-cartesia==1.6.5 package (inspect.signature), not assumed from docs: real
keyword-only params. The seeded voice (migration 0018) uses the plugin's own baked-in default
voice ID (`f786b574-daa5-4673-aa0c-cbe3e8534c02`), not an invented one.

Requires CARTESIA_API_KEY (env var, or api_key= kwarg) — the plugin itself raises a clear
ValueError if neither is set, checked eagerly at construction (same pattern as every other
provider adapter in this repo).
"""

from __future__ import annotations

from typing import Any


def build(voice_id: str, language: str) -> Any:
    from livekit.plugins import cartesia

    return cartesia.TTS(voice=voice_id, language=language)
