"""Fish Audio TTS adapter (Phase 6e + Phase 3 humanization options).

Enabled for `en` only. Constructor has no ``language`` param — ``build`` takes voice_id +
optional ``tts_options``. Verified against livekit-plugins-fishaudio==1.6.5.

Requires FISH_API_KEY (env var, or api_key= kwarg).
"""

from __future__ import annotations

import inspect
from typing import Any

from .fish_audio_options import resolve_fish_tts_kwargs


def build(voice_id: str, tts_options: dict | None = None) -> Any:
    from livekit.plugins import fishaudio

    kwargs = resolve_fish_tts_kwargs(voice_id, tts_options)
    sig = inspect.signature(fishaudio.TTS)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return fishaudio.TTS(**kwargs)
    allowed = set(sig.parameters)
    return fishaudio.TTS(**{k: v for k, v in kwargs.items() if k in allowed})
