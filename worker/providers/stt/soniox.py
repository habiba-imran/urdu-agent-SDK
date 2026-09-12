"""Soniox STT adapter — moved from worker/factories.py::make_stt()'s soniox branch
(Phase 2, docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036).

NOT in requirements.txt as of this phase (Phase 0 audit finding #3) — moved as-is, not fixed here.
No language parameter in the original (ADR-002: blocked on funding/402, never wired up) — preserved
exactly, pure relocation.
"""

from __future__ import annotations

from typing import Any


def build() -> Any:
    from livekit.plugins import soniox

    return soniox.STT()
