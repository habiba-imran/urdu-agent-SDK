"""Gladia STT adapter — moved from worker/factories.py::make_stt()'s default branch
(Phase 2, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

`language` was hardcoded to "ur" in the original; here it's a parameter, but for every existing
agent (agent_language defaults to 'ur' per migration 0016) `build("ur")` produces the exact same
`languages=["ur"]` call as before — zero behavior change for the current Urdu path.
"""

from __future__ import annotations

from typing import Any


def build(language: str) -> Any:
    from livekit.plugins import gladia

    # code_switching EXPLICIT False — the livekit-plugins-gladia STT() constructor default is
    # actually True (gladia/stt.py L211); it's functionally moot here since Gladia's own API
    # docs say a single-element `languages` list makes the setting ignored server-side, but
    # leaving it implicit was fragile: if this ever grows a second language, the plugin default
    # would silently re-enable code_switching. D19 (ported DECISIONS.md) measured CER 0.14
    # ur-only vs 0.43 with ur+en code_switching=True on the OLD raw-Gladia-WebSocket
    # integration — checked 2026-07-17 against Gladia's current docs/changelog for a material
    # change since: none found for Urdu specifically (Solaria-3, June 2026, and the Hebrew
    # upgrade, March 2026, are the only recent model-accuracy changelog entries, both unrelated
    # to Urdu; docs.gladia.io/chapters/language/code-switching still warns broad language sets
    # cause "frequent misdetections"). See docs/40-ADR.md ADR-009.
    return gladia.STT(languages=[language], code_switching=False)
