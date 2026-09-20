"""F-C4 Phase B: decide whether to start RecorderIO and whether to persist audio.

Two policies (do not conflate):

- ``may_start_recorder`` — gates ``session.start(record=…)``. Consent is NOT required.
- ``may_persist_recording`` — gates upload / DB URL writes. Requires consent ``granted``
  (Phase C sets that after disclosure; until then persist fails closed).

LiveKit: honour ``Job.enable_recording`` via ``JobContext.job.enable_recording``.
Hosted Render: env alone cannot force recording on — agent opt-in required.
Local/dev (``RENDER`` unset): ``UVA_SESSION_RECORD_AUDIO`` may force start for demos.
"""

from __future__ import annotations

import os
from typing import Any


_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Consent values written/read on the session path (Phase C expands usage).
CONSENT_NOT_APPLICABLE = "not_applicable"
CONSENT_PENDING = "pending"
CONSENT_GRANTED = "granted"
CONSENT_DECLINED = "declined"


def env_session_record_audio_requested() -> bool:
    raw = (os.environ.get("UVA_SESSION_RECORD_AUDIO") or "0").strip().lower()
    return raw in _TRUTHY


def is_hosted_render() -> bool:
    """True when running on Render (platform sets ``RENDER=true``).

    Used only to refuse env-only force-on in hosted environments. Local/dev has
    ``RENDER`` unset so demos may still use ``UVA_SESSION_RECORD_AUDIO=1``.
    """
    raw = (os.environ.get("RENDER") or "").strip().lower()
    return raw in _TRUTHY


def livekit_recording_allowed(enable_recording: bool | None) -> bool:
    """Honour LiveKit job signal: never start/persist when explicitly false.

    ``None`` means the caller could not read the field — treat as allowed (do not
    invent a disable). Explicit ``False`` always blocks.
    """
    if enable_recording is False:
        return False
    return True


def may_start_recorder(
    *,
    agent_recording_enabled: bool,
    enable_recording: bool | None = None,
    env_record_audio: bool | None = None,
    hosted_render: bool | None = None,
) -> bool:
    """Whether ``session.start`` may pass ``record={"audio": True, …}``.

    Consent is intentionally ignored here (see module docstring).
    """
    if not livekit_recording_allowed(enable_recording):
        return False

    agent_on = bool(agent_recording_enabled)
    env_on = (
        env_session_record_audio_requested()
        if env_record_audio is None
        else bool(env_record_audio)
    )
    on_render = is_hosted_render() if hosted_render is None else bool(hosted_render)

    if on_render:
        # Prod/staging on Render: agent opt-in only; env cannot force on.
        return agent_on
    # Local/dev: agent opt-in OR explicit env force for demos.
    return agent_on or env_on


def may_persist_recording(
    *,
    may_start: bool,
    consent_status: str | None,
) -> bool:
    """Whether finalize may upload audio and write recording URL columns."""
    if not may_start:
        return False
    status = (consent_status or "").strip().lower()
    return status == CONSENT_GRANTED


def read_livekit_enable_recording(job_ctx: Any) -> bool | None:
    """Read ``job_ctx.job.enable_recording`` when present; else ``None``."""
    job = getattr(job_ctx, "job", None)
    if job is None:
        return None
    if not hasattr(job, "enable_recording"):
        return None
    try:
        return bool(job.enable_recording)
    except Exception:
        return None


def session_start_record_option(*, may_start: bool) -> dict[str, bool] | bool:
    """Value for ``AgentSession.start(..., record=…)``."""
    if may_start:
        return {"audio": True, "traces": False, "logs": False, "transcript": False}
    return False
