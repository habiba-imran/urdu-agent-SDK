"""Fish Audio TTS adapter (Phase 6e, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py (provider level) AND
the specific voice row's own `rollout_state`/`enabled` in the `voices` table are both the real
gates, not this file. `voice_id` constructor arg verified directly against the installed
livekit-plugins-fishaudio==1.6.5 package (inspect.signature), not assumed from docs: a real
keyword-only param. Unlike Cartesia/ElevenLabs, this plugin's constructor has NO `language`
parameter at all — Fish Audio's voice models are not language-parameterized the same way, so
`build()` intentionally takes only `voice_id`. The seeded voice (migration
0020_seed_fish_audio_voice.sql) uses the plugin's own baked-in default voice ID
(`933563129e564b19a115bedd57b7406a`, `DEFAULT_VOICE_ID` in the package's own tts.py), not an
invented one.

Requires FISH_API_KEY (env var, or api_key= kwarg) — the plugin itself raises a clear ValueError
if neither is set, checked eagerly at construction (same pattern as every other provider adapter
in this repo).
"""

from __future__ import annotations

from typing import Any


def build(voice_id: str) -> Any:
    from livekit.plugins import fishaudio

    return fishaudio.TTS(voice_id=voice_id)
