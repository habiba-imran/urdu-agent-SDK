"""F-M1 Phase B — Habiba worker silent-handler logging (no network)."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.latency import (
    is_telephony_job,
    load_session_identity,
    parse_dispatch_metadata,
    prewarm_llm,
)
from worker.session_recording import upload_session_audio


def test_load_session_identity_logs_warning_on_db_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    @contextmanager
    def _boom(*_a: Any, **_k: Any):
        raise RuntimeError("no db")
        yield  # pragma: no cover

    monkeypatch.setattr("worker.db_pool.worker_db_connection", _boom)
    with caplog.at_level(logging.WARNING, logger="worker.latency"):
        assert load_session_identity("missing-room") is None
    assert any("stage=load_session_identity failed" in r.message for r in caplog.records)


def test_parse_dispatch_metadata_logs_on_bad_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="worker.latency"):
        assert parse_dispatch_metadata("{not-json") is None
    assert any("stage=parse_dispatch_metadata failed" in r.message for r in caplog.records)


def test_is_telephony_job_logs_on_bad_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="worker.latency"):
        assert is_telephony_job(job_metadata="{bad") is False
    assert any("stage=telephony_meta_parse failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_prewarm_llm_logs_on_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _BadLlm:
        __module__ = "fake.gemini"

        def chat(self, **_k: Any) -> Any:
            raise RuntimeError("llm down")

    with caplog.at_level(logging.WARNING, logger="worker.latency"):
        await prewarm_llm(_BadLlm())
    assert any("stage=prewarm_llm failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_tools_http_aclose_failure_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import worker.tools as tools_mod

    bad = MagicMock()
    bad.is_closed = False
    bad.aclose = AsyncMock(side_effect=RuntimeError("close failed"))

    tools_mod._http_client = bad
    # Different loop id forces recreate → aclose of the old client.
    tools_mod._http_client_loop_id = -1

    with caplog.at_level(logging.WARNING, logger="worker.tools"):
        client = await tools_mod._shared_http_client()
    assert client is not bad
    assert any("stage=http_client_aclose failed" in r.message for r in caplog.records)
    # Avoid leaking clients across tests.
    tools_mod._http_client = None
    tools_mod._http_client_loop_id = None


def test_recording_prior_remove_failure_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Any,
) -> None:
    from worker import session_recording as sr

    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"OggS\x00fake")

    class _Bucket:
        def remove(self, _paths: list[str]) -> None:
            raise RuntimeError("remove denied")

        def upload(self, *_a: Any, **_k: Any) -> None:
            return None

    class _Storage:
        def list_buckets(self) -> list[Any]:
            return [MagicMock(id=sr.BUCKET_ID)]

        def from_(self, _name: str) -> _Bucket:
            return _Bucket()

    class _Client:
        storage = _Storage()

    monkeypatch.setattr(sr, "_supabase_client", lambda: _Client())
    sr.reset_bucket_ensure_cache()

    with caplog.at_level(logging.WARNING, logger="worker.session_recording"):
        path = upload_session_audio(
            audio_path=audio, tenant_id="t1", room_name="room-1"
        )
    assert path == "t1/room-1.ogg"
    assert any("prior object remove failed" in r.message for r in caplog.records)
