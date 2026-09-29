"""F-H10 Phase D: bounded LiveKit provider connect retries (env-tunable).

Session-level ``APIConnectOptions`` are what actually gate LLM/TTS/STT retries on the
voice path. Wave 1 set ``max_retry=0`` (fail fast / avoid dead-air loops). Phase D
re-enables a **small** bounded retry so a single 429/503 does not kill the turn.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("worker.provider_retries")

_DEFAULT_MAX_RETRY = 2
_DEFAULT_RETRY_INTERVAL = 2.0
_DEFAULT_TIMEOUT = 30.0


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
        stt_conn_options=conn,
    )
