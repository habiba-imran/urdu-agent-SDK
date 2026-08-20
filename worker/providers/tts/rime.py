"""Rime TTS adapter (Phase 6f, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only. `speaker`/`lang` constructor args verified against
livekit-plugins-rime==1.6.5: the voice kwarg is `speaker` (not `voice`), and `lang` uses
3-letter codes. Only `en` -> `"eng"` is mapped; any other language raises.

Phase B humanization defaults (model=coda, use_websocket, speed_alpha) and Phase C audio
profiles (webrtc 16 kHz / telephony 8 kHz PCM) live in rime_options.py.
Extra kwargs are filtered against inspect.signature so an older plugin without `use_websocket`
or `segment` still constructs. The installed plugin hardcodes ``audioFormat=pcm``; we do not
pass Cartesia-style ``encoding=pcm_mulaw``.

Requires RIME_API_KEY (env var, or api_key= kwarg). WebSocket streaming defaults live in
rime_options.py (use_websocket=True).
"""

from __future__ import annotations

import inspect
from typing import Any

from .rime_options import resolve_rime_tts_kwargs

_LANG_CODES = {"en": "eng"}


def build(
    voice_id: str,
    language: str,
    tts_options: dict | None = None,
    *,
    audio_channel: str = "webrtc",
) -> Any:
    from livekit.plugins import rime

    if language not in _LANG_CODES:
        raise ValueError(
            f"no Rime language code mapping for agent_language={language!r}"
        )

    kwargs = resolve_rime_tts_kwargs(
        voice_id, _LANG_CODES[language], tts_options, audio_channel=audio_channel
    )
    allowed = set(inspect.signature(rime.TTS).parameters)
    return rime.TTS(**{k: v for k, v in kwargs.items() if k in allowed})
