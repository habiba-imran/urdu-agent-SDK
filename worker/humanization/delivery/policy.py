"""Independent per-provider rollout; natural_v1 never implicitly enables TTS."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

ACTIVE_PROVIDERS = frozenset({"cartesia", "rime", "elevenlabs", "uplift"})
POLICY_VERSION = "delivery_v1"
RENDERER_VERSION = "renderer_v1"
PRONUNCIATION_VERSION = "pronunciation_v1"


@dataclass(frozen=True)
class DeliveryPolicy:
    version: str = "baseline"
    renderer_version: str = "baseline"
    pronunciation_version: str = "baseline"

    @property
    def enabled(self) -> bool:
        return self.version != "baseline"


def resolve_delivery_policy(provider: str, *, environ: Mapping[str, str] | None = None) -> DeliveryPolicy:
    env = os.environ if environ is None else environ
    provider = provider.strip().lower()
    value = env.get("UVA_TTS_RENDERER_" + provider.upper(), "baseline").strip()
    if value == "baseline":
        return DeliveryPolicy()
    if provider not in ACTIVE_PROVIDERS or value != POLICY_VERSION:
        raise ValueError("unsupported TTS renderer policy")
    return DeliveryPolicy(POLICY_VERSION, RENDERER_VERSION, PRONUNCIATION_VERSION)
