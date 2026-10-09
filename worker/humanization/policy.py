"""Session-scoped policy identity; Phase 2 never activates candidate behavior."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

POLICY_VERSIONS = frozenset({"baseline", "natural_v1_shadow", "natural_v1"})
LEGACY_ENV_KEYS = (
    "UVA_INTERRUPTION_MODE", "UVA_FORCE_BARGE_IN_FLUSH", "UVA_CHAT_HISTORY_MAX_ITEMS",
    "UVA_DEEPGRAM_ENDPOINTING_MS", "UVA_DEEPGRAM_STT_MODE", "UVA_DEEPGRAM_FLUX_EAGER_EOT",
    "UVA_DEEPGRAM_FLUX_EAGER_EOT_THRESHOLD", "UVA_TURN_DETECTOR",
    "UVA_PROVIDER_MAX_RETRY", "UVA_PROVIDER_RETRY_INTERVAL",
    "UVA_GREETING_INTERRUPTIBLE",
)


@dataclass(frozen=True)
class HumanizationPolicy:
    requested_version: str
    effective_version: str
    behavior_enabled: bool
    legacy_overrides: tuple[tuple[str, str], ...]


def resolve_humanization_policy(
    requested: str | None = None, *, environ: Mapping[str, str] | None = None,
) -> HumanizationPolicy:
    """Resolve after config cache lookup, so policy changes apply to new sessions.

    Precedence in Phase 2: existing per-agent provider options and existing turn,
    retry, history and preemption/channel resolvers remain authoritative over this
    version label. Explicit legacy environment values still reach those resolvers.
    The policy label itself cannot override them or enable audible behavior.
    An unconfigured agent stays baseline. natural_v1 is accepted as a request but
    resolves to shadow until later phases explicitly implement and activate it.
    """
    env = os.environ if environ is None else environ
    version = (requested or env.get("UVA_HUMANIZATION_POLICY_VERSION") or "baseline").strip()
    if version not in POLICY_VERSIONS:
        raise ValueError(f"unsupported humanization policy: {version}")
    effective = "natural_v1_shadow" if version == "natural_v1" else version
    overrides = tuple((key, env[key]) for key in LEGACY_ENV_KEYS if key in env)
    return HumanizationPolicy(version, effective, False, overrides)
