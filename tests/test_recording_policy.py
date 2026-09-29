"""Unit tests for F-C4 Phase B recording policy (no network)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from worker.recording_policy import (
    CONSENT_DECLINED,
    CONSENT_GRANTED,
    CONSENT_NOT_APPLICABLE,
    CONSENT_PENDING,
    may_persist_recording,
    may_start_recorder,
    session_start_record_option,
)
from worker.session_recording import (
    _recording_persist_allowed,
    finalize_and_persist_session_recording,
    find_session_audio,
    reset_bucket_ensure_cache,
)


@pytest.fixture(autouse=True)
def _reset_bucket_cache() -> None:
    reset_bucket_ensure_cache()


def test_may_start_ignores_consent_inputs() -> None:
    # Consent is not a parameter of may_start — persist gate owns it.
    assert may_start_recorder(
        agent_recording_enabled=True,
        enable_recording=True,
        env_record_audio=False,
        hosted_render=True,
    )
    assert not may_start_recorder(
        agent_recording_enabled=False,
        enable_recording=True,
        env_record_audio=False,
        hosted_render=True,
    )


def test_may_start_honours_livekit_enable_recording_false() -> None:
    assert not may_start_recorder(
        agent_recording_enabled=True,
        enable_recording=False,
        env_record_audio=True,
        hosted_render=False,
    )


def test_may_start_render_requires_agent_env_cannot_force() -> None:
    assert not may_start_recorder(
        agent_recording_enabled=False,
        enable_recording=True,
        env_record_audio=True,
        hosted_render=True,
    )
    assert may_start_recorder(
        agent_recording_enabled=True,
        enable_recording=True,
        env_record_audio=False,
        hosted_render=True,
    )


def test_may_start_local_env_can_force_without_agent() -> None:
    assert may_start_recorder(
        agent_recording_enabled=False,
        enable_recording=True,
        env_record_audio=True,
        hosted_render=False,
    )
    assert not may_start_recorder(
        agent_recording_enabled=False,
        enable_recording=True,
        env_record_audio=False,
        hosted_render=False,
    )


def test_may_persist_requires_granted_consent() -> None:
    assert not may_persist_recording(may_start=True, consent_status=CONSENT_PENDING)
    assert not may_persist_recording(may_start=True, consent_status=CONSENT_DECLINED)
    assert not may_persist_recording(
        may_start=True, consent_status=CONSENT_NOT_APPLICABLE
    )
    assert not may_persist_recording(may_start=True, consent_status=None)
    assert may_persist_recording(may_start=True, consent_status=CONSENT_GRANTED)
    assert not may_persist_recording(may_start=False, consent_status=CONSENT_GRANTED)


def test_session_start_record_option() -> None:
    assert session_start_record_option(may_start=False) is False
    assert session_start_record_option(may_start=True) == {
        "audio": True,
        "traces": False,
        "logs": False,
        "transcript": False,
    }


@pytest.mark.asyncio
async def test_finalize_skips_upload_when_consent_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"OggS\x00fake")

    uploads: list[tuple[str, str]] = []

    def _fake_upload(**kwargs: object) -> str | None:
        uploads.append(("called", str(kwargs.get("room_name"))))
        return "t/r.ogg"

    monkeypatch.setattr(
        "worker.session_recording.upload_session_audio", _fake_upload
    )

    userdata = SimpleNamespace(
        recording_may_start=True,
        recording_consent_status=CONSENT_PENDING,
    )
    session = SimpleNamespace(userdata=userdata, _recorder_io=None)
    job_ctx = SimpleNamespace(
        _primary_agent_session=session,
        session_directory=tmp_path,
    )

    await finalize_and_persist_session_recording(
        job_ctx=job_ctx,
        room_name="room-1",
        tenant_id="tenant-1",
    )

    assert uploads == []
    assert not audio.exists()


@pytest.mark.asyncio
async def test_finalize_uploads_when_consent_granted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"OggS\x00fake")

    uploads: list[str] = []
    persisted: list[tuple[str, str]] = []

    def _fake_upload(*, audio_path: Path, tenant_id: str, room_name: str):
        uploads.append(room_name)
        return "tenant-1/room-1.ogg"

    def _fake_persist(*, room_name: str, storage_path: str, recording_url: str | None = None) -> None:
        persisted.append((room_name, storage_path, recording_url))

    monkeypatch.setattr(
        "worker.session_recording.upload_session_audio", _fake_upload
    )
    monkeypatch.setattr(
        "worker.session_recording.persist_recording_urls", _fake_persist
    )

    userdata = SimpleNamespace(
        recording_may_start=True,
        recording_consent_status=CONSENT_GRANTED,
    )
    session = SimpleNamespace(userdata=userdata, _recorder_io=None)
    job_ctx = SimpleNamespace(
        _primary_agent_session=session,
        session_directory=tmp_path,
    )

    await finalize_and_persist_session_recording(
        job_ctx=job_ctx,
        room_name="room-1",
        tenant_id="tenant-1",
    )

    assert uploads == ["room-1"]
    assert persisted == [("room-1", "tenant-1/room-1.ogg", None)]
    assert not audio.exists()


def test_recording_persist_allowed_reads_userdata() -> None:
    userdata = SimpleNamespace(
        recording_may_start=True,
        recording_consent_status=CONSENT_GRANTED,
    )
    session = SimpleNamespace(userdata=userdata)
    job_ctx = SimpleNamespace(_primary_agent_session=session)
    assert _recording_persist_allowed(job_ctx) is True

    userdata.recording_consent_status = CONSENT_PENDING
    assert _recording_persist_allowed(job_ctx) is False


def test_find_session_audio_still_works(tmp_path: Path) -> None:
    assert find_session_audio(None) is None
    assert find_session_audio(tmp_path) is None
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"OggS\x00fake")
    assert find_session_audio(tmp_path) == audio
