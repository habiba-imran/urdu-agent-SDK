"""Rime TTS adapter (Phase 6f, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py (provider level) AND
the specific voice row's own `rollout_state`/`enabled` in the `voices` table are both the real
gates, not this file. `speaker`/`lang` constructor args verified directly against the installed
livekit-plugins-rime==1.6.5 package (inspect.signature), not assumed from docs — two real, non-
obvious differences from every other TTS adapter in this repo:

1. The voice kwarg is `speaker` (not `voice`/`voice_id` like Cartesia/ElevenLabs/Fish Audio).
2. The language kwarg is `lang`, and Rime uses 3-letter codes (`livekit.plugins.rime.langs.
   TTSLangs = Literal["eng", "spa", "fra", "ger", "hin"]`) — NOT our internal 2-letter
   `agent_language` values. Only `en` -> `"eng"` is mapped here since Rime is only enabled for
   `en` in this plan's scope; any other value raises rather than silently guessing a code (this
   repo's explicit "no silent fallback" rule).

The seeded voice (migration 0021) uses the plugin's own baked-in default speaker for its default
model (`model="arcana"` -> `speaker="astra"`, both confirmed by reading the installed package's
source, not invented).

Requires RIME_API_KEY (env var, or api_key= kwarg) — the plugin itself raises a clear ValueError
if neither is set, checked eagerly at construction (same pattern as every other provider adapter
in this repo).

`use_websocket=True` — the plugin's own default is `False` (one-shot REST synthesis over
`RIME_BASE_URL`), which silently disables its real-time `.stream()` interface entirely (the
plugin raises "Rime TTS streaming requires use_websocket=True at construction time" if
AgentSession ever calls it in that mode). Left at the default during Phase 6f, this meant every
Rime turn actually went through the one-shot `.synthesize()` path — AgentSession has to wait for
a full sentence/response, fire one blocking REST call per chunk, then stitch the separate clips
together, instead of streaming audio incrementally as the LLM generates text. That reproduces
exactly the "laggy, sometimes stuttering/glitching" reports users hit live — the human-observed
"laggy start" flagged during Phase 6f's own live test (attributed then to a one-off cold start,
never actually root-caused) was this same defect. `use_websocket=True` switches to
`RIME_WS_BASE_URL` and enables the streaming path, matching how Cartesia/ElevenLabs/Uplift already
behave.
"""

from __future__ import annotations

from typing import Any

_LANG_CODES = {"en": "eng"}


def build(voice_id: str, language: str) -> Any:
    from livekit.plugins import rime

    if language not in _LANG_CODES:
        raise ValueError(
            f"no Rime language code mapping for agent_language={language!r}"
        )

    return rime.TTS(speaker=voice_id, lang=_LANG_CODES[language], use_websocket=True)
