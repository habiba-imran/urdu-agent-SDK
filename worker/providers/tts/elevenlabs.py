"""ElevenLabs TTS adapter (Phase 6d + Phase 3 humanization options).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py (provider level) AND
the specific voice row's own `rollout_state`/`enabled` in the `voices` table are both the real
gates, not this file. Constructor kwargs verified against livekit-plugins-elevenlabs==1.6.5.

Requires ELEVEN_API_KEY (env var, or api_key= kwarg).
"""

from __future__ import annotations

import inspect
from typing import Any

from .elevenlabs_options import resolve_elevenlabs_tts_kwargs


def build(
    voice_id: str,
    language: str,
    tts_options: dict | None = None,
) -> Any:
    from livekit.plugins import elevenlabs

    kwargs = resolve_elevenlabs_tts_kwargs(voice_id, language, tts_options)
    sig = inspect.signature(elevenlabs.TTS)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return elevenlabs.TTS(**kwargs)
    allowed = set(sig.parameters)
    return elevenlabs.TTS(**{k: v for k, v in kwargs.items() if k in allowed})
