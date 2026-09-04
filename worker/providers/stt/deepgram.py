"""Deepgram STT adapter (Phase 6a, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

Enabled for `en` only — `rollout_state` in worker/providers/capabilities.py is the gate, not this
file. `model`/`language` constructor args verified directly against the installed
livekit-plugins-deepgram==1.6.5 package (inspect.signature), not assumed from docs: both are real
keyword-only params, `model` defaults to "nova-3", `language` accepts a bare "en" (confirmed
against the package's own DeepgramLanguages type — "ur" is NOT in that list at all, a real,
pre-existing latent bug in this adapter's old ur-branch code that was never actually triggered
since Deepgram was never the default STT and isn't in `ur`'s capability entry; not fixed here since
Deepgram is only ever selected for `en` going forward).

Requires DEEPGRAM_API_KEY (env var, or api_key= kwarg) — the plugin itself raises a clear
ValueError if neither is set.
"""

from __future__ import annotations

from typing import Any


def build(language: str) -> Any:
    from livekit.plugins import deepgram

    # Voice-optimized Nova-3: no_delay + low endpointing_ms for streaming finals (UVA-6).
    # interim_results=True feeds partial transcripts into LiveKit preemptive generation (UVA-14).
    lang = "en-US" if language.startswith("en") else language
    return deepgram.STT(
        model="nova-3",
        language=lang,
        no_delay=True,
        endpointing_ms=10,
        interim_results=True,
        # smart_format adds post-processing latency on finals; voice path prefers speed
        # (numbers/punctuation are fine for Cartesia without it).
        smart_format=False,
    )
