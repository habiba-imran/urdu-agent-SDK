"""F-M24 Phase C — prompt dump + transcript log defaults (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from worker.prompt_dump import dump_prompts_enabled, dump_session_prompt
from worker.transcript_logging import (
    format_transcript_for_log,
    log_transcripts_enabled,
    transcript_log_max_chars,
)


@pytest.fixture(autouse=True)
def _clear_fm24_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UVA_DUMP_PROMPTS", raising=False)
    monkeypatch.delenv("UVA_DUMP_PROMPTS_PATH", raising=False)
    monkeypatch.delenv("UVA_LOG_TRANSCRIPTS", raising=False)
    monkeypatch.delenv("UVA_LOG_TRANSCRIPT_CHARS", raising=False)


def test_dump_prompts_disabled_by_default() -> None:
    assert dump_prompts_enabled() is False


def test_dump_prompts_explicit_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_DUMP_PROMPTS", "0")
    assert dump_prompts_enabled() is False
    monkeypatch.setenv("UVA_DUMP_PROMPTS", "false")
    assert dump_prompts_enabled() is False


def test_dump_prompts_explicit_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_DUMP_PROMPTS", "1")
    assert dump_prompts_enabled() is True


def test_dump_session_prompt_default_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = tmp_path / "last_session_prompt.txt"
    monkeypatch.setenv("UVA_DUMP_PROMPTS_PATH", str(out))
    # unset dump flag → default off
    path = dump_session_prompt(
        agent_id="a1",
        llm_provider="groq",
        llm_model="openai/gpt-oss-20b",
        system_instructions="SYS_SECRET",
        persona_raw="PERSONA_RAW_PII",
        persona_effective="PERSONA_EFF",
        tools_registered=["lookup"],
        compacted=False,
    )
    assert path is None
    assert not out.exists()


def test_dump_session_prompt_on_writes_markers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = tmp_path / "last_session_prompt.txt"
    monkeypatch.setenv("UVA_DUMP_PROMPTS", "1")
    monkeypatch.setenv("UVA_DUMP_PROMPTS_PATH", str(out))
    path = dump_session_prompt(
        agent_id="a1",
        llm_provider="groq",
        llm_model="openai/gpt-oss-20b",
        system_instructions="SYS_SECRET",
        persona_raw="PERSONA_RAW_PII",
        persona_effective="PERSONA_EFF",
        tools_registered=["lookup"],
        compacted=True,
    )
    assert path == out
    body = out.read_text(encoding="utf-8")
    assert "SYS_SECRET" in body
    assert "PERSONA_RAW_PII" in body
    assert "PERSONA_EFF" in body
    assert "agent_id=a1" in body


def test_log_transcripts_disabled_by_default() -> None:
    assert log_transcripts_enabled() is False


def test_format_transcript_default_omits_text() -> None:
    snippet, chars = format_transcript_for_log("Hello caller phone 555-0100")
    assert snippet == ""
    assert chars == len("Hello caller phone 555-0100")


def test_format_transcript_enabled_truncates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UVA_LOG_TRANSCRIPTS", "1")
    monkeypatch.setenv("UVA_LOG_TRANSCRIPT_CHARS", "10")
    assert transcript_log_max_chars() == 10
    snippet, chars = format_transcript_for_log("ABCDEFGHIJKLMNOP")
    assert snippet == "ABCDEFGHIJ"
    assert chars == 16


def test_default_prompt_dump_is_ignored_and_local(monkeypatch, tmp_path):
    import subprocess
    from worker import prompt_dump

    expected = prompt_dump._ROOT / "tmp" / "debug" / "last_session_prompt.txt"
    assert prompt_dump._DEFAULT_DUMP == expected
    for relative in ("tmp/debug/last_session_prompt.txt", "docs/last_session_prompt.txt"):
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", relative],
            cwd=prompt_dump._ROOT, capture_output=True,
        )
        assert result.returncode == 0
    monkeypatch.setenv("UVA_DUMP_PROMPTS", "1")
    monkeypatch.delenv("UVA_DUMP_PROMPTS_PATH", raising=False)
    target = tmp_path / "debug" / "last_session_prompt.txt"
    monkeypatch.setattr(prompt_dump, "_DEFAULT_DUMP", target)
    actual = dump_session_prompt(
        agent_id="fixture-agent", llm_provider="fixture", llm_model="fixture",
        system_instructions="fixture system", persona_raw="fixture persona",
        persona_effective="fixture effective", tools_registered=[], compacted=False,
    )
    assert actual == target
    assert target.exists()
