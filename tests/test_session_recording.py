"""Unit tests for session recording helpers (no network)."""

from __future__ import annotations

from pathlib import Path

from worker.session_recording import find_session_audio


def test_find_session_audio_missing_dir(tmp_path: Path) -> None:
    assert find_session_audio(None) is None
    assert find_session_audio(tmp_path) is None


def test_find_session_audio_empty_file(tmp_path: Path) -> None:
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"")
    assert find_session_audio(tmp_path) is None


def test_find_session_audio_present(tmp_path: Path) -> None:
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"OggS\x00fake")
    found = find_session_audio(tmp_path)
    assert found == audio
