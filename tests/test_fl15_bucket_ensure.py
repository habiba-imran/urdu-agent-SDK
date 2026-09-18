"""F-L15 Phase G — bucket ensure runs list_buckets at most once per process (success path)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import worker.session_recording as sr
from worker.session_recording import upload_session_audio


@pytest.fixture(autouse=True)
def _reset_bucket_cache() -> None:
    sr.reset_bucket_ensure_cache()


def test_two_uploads_list_buckets_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio1 = tmp_path / "a1.ogg"
    audio2 = tmp_path / "a2.ogg"
    audio1.write_bytes(b"OggS\x00one")
    audio2.write_bytes(b"OggS\x00two")

    list_calls = {"n": 0}

    class _Bucket:
        def remove(self, _paths: list[str]) -> None:
            return None

        def upload(self, *_a: Any, **_k: Any) -> None:
            return None

    class _Storage:
        def list_buckets(self) -> list[Any]:
            list_calls["n"] += 1
            return [MagicMock(id=sr.BUCKET_ID)]

        def create_bucket(self, *_a: Any, **_k: Any) -> None:
            raise AssertionError("create_bucket should not run when bucket exists")

        def from_(self, _name: str) -> _Bucket:
            return _Bucket()

    class _Client:
        storage = _Storage()

    monkeypatch.setattr(sr, "_supabase_client", lambda: _Client())

    path1 = upload_session_audio(
        audio_path=audio1, tenant_id="t1", room_name="room-1"
    )
    path2 = upload_session_audio(
        audio_path=audio2, tenant_id="t1", room_name="room-2"
    )

    assert path1 == "t1/room-1.ogg"
    assert path2 == "t1/room-2.ogg"
    assert list_calls["n"] == 1


def test_failed_ensure_retries_list_on_next_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On ensure failure cache is False — next upload may retry list_buckets."""
    audio = tmp_path / "a.ogg"
    audio.write_bytes(b"OggS\x00x")

    attempts = {"n": 0}

    class _StorageFailThenOk:
        def list_buckets(self) -> list[Any]:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("storage down")
            return [MagicMock(id=sr.BUCKET_ID)]

        def from_(self, _name: str) -> Any:
            bucket = MagicMock()
            bucket.remove.return_value = None
            bucket.upload.return_value = None
            return bucket

    class _Client:
        def __init__(self) -> None:
            self.storage = _StorageFailThenOk()

    monkeypatch.setattr(sr, "_supabase_client", lambda: _Client())

    assert (
        upload_session_audio(audio_path=audio, tenant_id="t1", room_name="r1") is None
    )
    path = upload_session_audio(audio_path=audio, tenant_id="t1", room_name="r1")
    assert path == "t1/r1.ogg"
    assert attempts["n"] == 2
