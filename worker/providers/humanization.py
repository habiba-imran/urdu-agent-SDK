"""Dependency-free profile validation shared by the API image and voice worker.

Keep this in providers/: the tenant API image intentionally excludes the voice runtime.
"""
from __future__ import annotations

_ENUMS = {
    "warmth": {"reserved", "balanced", "warm"},
    "formality": {"casual", "balanced", "formal"},
    "energy": {"calm", "balanced", "lively"},
    "pace": {"slower", "normal", "slightly_fast"},
    "expressiveness": {"subtle", "balanced"},
}


def validate_profile(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("humanization must be an object")
    unknown = set(value) - {*_ENUMS, "enabled", "adaptivePace"}
    if unknown:
        raise ValueError("unsupported humanization settings: " + ", ".join(sorted(map(str, unknown))))
    for key, allowed in _ENUMS.items():
        if key in value and (not isinstance(value[key], str) or value[key] not in allowed):
            raise ValueError(f"humanization.{key} must be one of {', '.join(sorted(allowed))}")
    for key in ("enabled", "adaptivePace"):
        if key in value and not isinstance(value[key], bool):
            raise ValueError(f"humanization.{key} must be a boolean")
    return dict(value)
