"""ElevenLabs TTS adapter (Phase 6d, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py (provider level) AND
the specific voice row's own `rollout_state`/`enabled` in the `voices` table are both the real
gates, not this file. `voice_id`/`language` constructor args verified directly against the
installed livekit-plugins-elevenlabs==1.6.5 package (inspect.signature), not assumed from docs:
real keyword-only params (note the kwarg is `voice_id`, not `voice` like Cartesia's). The seeded
voice (migration 0019) uses the plugin's own baked-in default voice ID
(`hpp4J3VqNfWAUOO0d1Us`, `DEFAULT_VOICE_ID` in the package's own tts.py), not an invented one.

Requires ELEVEN_API_KEY (env var, or api_key= kwarg) — the plugin itself raises a clear ValueError
if neither is set, checked eagerly at construction (same pattern as every other provider adapter
in this repo).
"""

from __future__ import annotations

from typing import Any


def build(voice_id: str, language: str) -> Any:
    from livekit.plugins import elevenlabs

    return elevenlabs.TTS(voice_id=voice_id, language=language)
