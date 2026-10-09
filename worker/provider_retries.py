"""F-H10 Phase D: bounded LiveKit provider connect retries (env-tunable).

P0 defaults settle within five seconds without retries. LLM/TTS retain explicit
legacy retry settings plus a separate six-second useful-progress bound. STT
connections always settle within five seconds; idle microphone silence is valid.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("worker.provider_retries")

_DEFAULT_MAX_RETRY = 0
_DEFAULT_RETRY_INTERVAL = 1.0
_DEFAULT_TIMEOUT = 5.0


@dataclass(frozen=True)
class ProviderRetrySettings:
    max_retry: int
    retry_interval: float
    timeout: float


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r — using default %s",
            name,
            raw,
            default,
        )
        return default
    if value < minimum or value > maximum:
        logger.warning(
            "%s=%s out of range [%s,%s] — using default %s",
            name,
            value,
            minimum,
            maximum,
            default,
        )
        return default
    return value


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r — using default %s",
            name,
            raw,
            default,
        )
        return default
    if value < minimum or value > maximum:
        logger.warning(
            "%s=%s out of range [%s,%s] — using default %s",
            name,
            value,
            minimum,
            maximum,
            default,
        )
        return default
    return value


def read_provider_retry_settings() -> ProviderRetrySettings:
    """Read bounded retry knobs from env.

    Caps are intentional: unbounded retries recreate the Wave 1 dead-air problem.
    """
    return ProviderRetrySettings(
        max_retry=_env_int(
            "UVA_PROVIDER_MAX_RETRY",
            _DEFAULT_MAX_RETRY,
            minimum=0,
            maximum=5,
        ),
        retry_interval=_env_float(
            "UVA_PROVIDER_RETRY_INTERVAL",
            _DEFAULT_RETRY_INTERVAL,
            minimum=0.1,
            maximum=30.0,
        ),
        timeout=_env_float(
            "UVA_PROVIDER_CONNECT_TIMEOUT",
            _DEFAULT_TIMEOUT,
            minimum=1.0,
            maximum=120.0,
        ),
    )


def build_session_connect_options() -> Any:
    """LiveKit ``SessionConnectOptions`` for LLM/TTS/STT connect retries."""
    from livekit.agents.types import APIConnectOptions
    from livekit.agents.voice.agent_session import SessionConnectOptions

    settings = read_provider_retry_settings()
    conn = APIConnectOptions(
        max_retry=settings.max_retry,
        retry_interval=settings.retry_interval,
        timeout=settings.timeout,
    )
    logger.info(
        "provider_retries max_retry=%s retry_interval=%s timeout=%s "
        "(env UVA_PROVIDER_MAX_RETRY / UVA_PROVIDER_RETRY_INTERVAL / "
        "UVA_PROVIDER_CONNECT_TIMEOUT)",
        settings.max_retry,
        settings.retry_interval,
        settings.timeout,
    )
    return SessionConnectOptions(
        llm_conn_options=conn,
        tts_conn_options=conn,
        # A missing speech recognizer cannot hide behind a legacy 30s override.
        # Its first connection attempt must settle within the P0 silence budget.
        stt_conn_options=APIConnectOptions(max_retry=0, retry_interval=settings.retry_interval,
                                          timeout=min(settings.timeout, 5.0)),
    )


# Bounds conversational progress independently of plugin retries and explicit
# legacy env overrides. Idle STT is not timed out: silence is valid microphone input.
PROGRESS_TIMEOUT = 6.0


def session_runtime(session: Any) -> Any:
    try:
        userdata = getattr(session, "userdata", None)
    except ValueError:
        return None
    return getattr(userdata, "humanization_runtime", None)


def fail_session(session: Any, stage: str, *, room: Any = None) -> dict:
    outcome = {"type": "awaaz_session_failure", "stage": stage,
               "outcome": "PROVIDER_UNAVAILABLE", "spokenFallback": False}
    runtime = session_runtime(session)
    if runtime is not None:
        if runtime.failure_outcome is not None:
            return runtime.failure_outcome
        runtime.failure_outcome = outcome
    logger.error("bounded_provider_failure stage=%s spoken_fallback=false", stage)
    if room is not None:
        import asyncio
        import json
        async def publish():
            try:
                await room.local_participant.publish_data(json.dumps(outcome).encode(), reliable=True)
            except Exception:
                logger.debug("failure outcome publish unavailable")
        task = asyncio.create_task(publish())
        task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    session.shutdown(drain=False)
    return outcome


async def bounded_provider_stream(stream: Any, agent: Any, stage: str, *, timeout: float = PROGRESS_TIMEOUT):
    import asyncio
    import time
    # TTS may wait for LLM text; that wait is bounded by the LLM node separately.
    # Only useful output resets this deadline; usage-only/empty LLM chunks cannot.
    deadline = time.monotonic() + timeout
    useful = False
    try:
        while True:
            try:
                item = await asyncio.wait_for(anext(stream), timeout=max(.001, deadline-time.monotonic()))
            except StopAsyncIteration:
                if not useful:
                    raise RuntimeError(stage + " returned no useful output")
                return
            delta = getattr(item, "delta", None)
            progress = (stage == "TTS" and getattr(item, "duration", 0) > 0) or (
                stage == "LLM" and (isinstance(item, str) and bool(item.strip()) or bool(
                    (getattr(delta, "content", None) or "").strip() or getattr(delta, "tool_calls", None))))
            if progress:
                useful = True
                deadline = time.monotonic()+timeout
            yield item
    except Exception:
        runtime = getattr(agent, "humanization_runtime", None)
        callback = getattr(runtime, "failure_callback", None)
        if callback is not None:
            callback(stage)
        else:
            fail_session(agent.session, stage)
        raise
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            await close()


def wire_provider_failure(session: Any, room: Any) -> None:
    def on_error(ev: Any) -> None:
        err = getattr(ev, "error", ev)
        name = type(err).__name__.upper()
        stage = next((stage for stage in ("STT", "LLM", "TTS") if stage in name), "PIPELINE")
        fail_session(session, stage, room=room)
    runtime = session_runtime(session)
    if runtime is not None:
        runtime.failure_callback = lambda stage: fail_session(session, stage, room=room)
    session.on("error", on_error)
