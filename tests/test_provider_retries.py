"""Unit tests for F-H10 Phase D provider retry settings (no network)."""

from __future__ import annotations

import logging

import pytest

from worker.provider_retries import (
    build_session_connect_options,
    read_provider_retry_settings,
)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UVA_PROVIDER_MAX_RETRY", raising=False)
    monkeypatch.delenv("UVA_PROVIDER_RETRY_INTERVAL", raising=False)
    monkeypatch.delenv("UVA_PROVIDER_CONNECT_TIMEOUT", raising=False)
    s = read_provider_retry_settings()
    assert s.max_retry == 2
    assert s.retry_interval == 2.0
    assert s.timeout == 30.0


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_PROVIDER_MAX_RETRY", "1")
    monkeypatch.setenv("UVA_PROVIDER_RETRY_INTERVAL", "0.5")
    monkeypatch.setenv("UVA_PROVIDER_CONNECT_TIMEOUT", "15")
    s = read_provider_retry_settings()
    assert s.max_retry == 1
    assert s.retry_interval == 0.5
    assert s.timeout == 15.0


def test_invalid_and_out_of_range_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_PROVIDER_MAX_RETRY", "nope")
    monkeypatch.setenv("UVA_PROVIDER_RETRY_INTERVAL", "999")
    monkeypatch.setenv("UVA_PROVIDER_CONNECT_TIMEOUT", "-1")
    s = read_provider_retry_settings()
    assert s.max_retry == 2
    assert s.retry_interval == 2.0
    assert s.timeout == 30.0


def test_zero_retry_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_PROVIDER_MAX_RETRY", "0")
    assert read_provider_retry_settings().max_retry == 0


def test_build_session_connect_options_applies_settings(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("UVA_PROVIDER_MAX_RETRY", "3")
    monkeypatch.setenv("UVA_PROVIDER_RETRY_INTERVAL", "1.5")
    monkeypatch.setenv("UVA_PROVIDER_CONNECT_TIMEOUT", "20")
    with caplog.at_level(logging.INFO, logger="worker.provider_retries"):
        opts = build_session_connect_options()
    assert opts.llm_conn_options.max_retry == 3
    assert opts.tts_conn_options.max_retry == 3
    assert opts.stt_conn_options.max_retry == 3
    assert opts.llm_conn_options.retry_interval == 1.5
    assert opts.llm_conn_options.timeout == 20.0
    assert any("provider_retries max_retry=3" in r.message for r in caplog.records)


def test_main_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UVA_PROVIDER_MAX_RETRY", "1")
    from worker.main import build_session_connect_options as main_build

    opts = main_build()
    assert opts.llm_conn_options.max_retry == 1
    assert opts.tts_conn_options.max_retry == 1
    assert opts.stt_conn_options.max_retry == 1
