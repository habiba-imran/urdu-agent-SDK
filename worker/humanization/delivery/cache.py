"""Rendered audio identity: all acoustic/policy inputs, hashed and bounded."""

from __future__ import annotations

import hashlib
import json

from .capabilities import effective_options, resolve_capabilities
from .policy import resolve_delivery_policy


def rendered_audio_identity(
    provider: str, voice: str, language: str, options: dict, channel: str, *,
    tenant_id: str = "", policy_version: str | None = None,
    renderer_version: str | None = None, pronunciation_version: str | None = None,
) -> str:
    policy = resolve_delivery_policy(provider)
    effective = effective_options(provider, voice, language, options, channel)
    caps = resolve_capabilities(provider, effective)
    payload = {
        "provider": provider, "model": caps.model, "voice": voice,
        "language": language, "channel": channel, "tenant": tenant_id,
        "policy": policy_version or policy.version,
        "renderer": renderer_version or policy.renderer_version,
        "pronunciation": pronunciation_version or policy.pronunciation_version,
        "effective": effective, "stored": options,
        "language_profile": "language_v1" if (policy_version or policy.version) != "baseline" else "baseline",
        "channel_profile": "channel_v1" if (policy_version or policy.version) != "baseline" else "baseline",
        "static_delivery": "opening_v1" if (policy_version or policy.version) != "baseline" else "baseline",
        "plugin": caps.plugin_version, "path": caps.path, "source": caps.source_fingerprint,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()[:24]
