"""F-M15 Phase D — provider/model honesty (no network / no live LLM keys)."""

from __future__ import annotations

import logging
import sys
import types
from unittest.mock import MagicMock

import pytest

from worker.providers.capabilities import (
    CAPABILITIES,
    allowed_llm_models,
    llm_capability,
)
from worker.providers.llm.gemini import resolve_gemini_model
from worker.providers.llm.groq import resolve_groq_model


def test_groq_runtime_models_exclude_dead_ids() -> None:
    cap = llm_capability("en", "groq")
    assert cap is not None
    assert "openai/gpt-oss-20b" in cap["models"]
    assert "llama-3.3-70b-versatile" not in cap["models"]
    assert "llama-3.3-70b-versatile" in cap["legacy_aliases"]
    assert "llama-3.3-70b-versatile" in allowed_llm_models(cap)


def test_gemini_runtime_models_exclude_deprecated() -> None:
    for lang in ("en", "ur"):
        cap = llm_capability(lang, "gemini")
        assert cap is not None
        assert cap["models"] == ["gemini-3.6-flash"]
        assert "gemini-2.5-flash" in cap["legacy_aliases"]
        assert "gemini-2.5-flash" in allowed_llm_models(cap)


def test_resolve_groq_dead_and_live() -> None:
    effective, reason = resolve_groq_model("llama-3.3-70b-versatile")
    assert reason == "dead_model"
    assert effective == "openai/gpt-oss-20b"
    live, live_reason = resolve_groq_model("openai/gpt-oss-20b")
    assert live == "openai/gpt-oss-20b"
    assert live_reason is None
    empty, empty_reason = resolve_groq_model("")
    assert empty_reason == "empty_model"


def test_resolve_gemini_deprecated() -> None:
    effective, reason = resolve_gemini_model("gemini-2.5-flash")
    assert reason == "deprecated_id"
    assert effective  # live default
    live, live_reason = resolve_gemini_model("gemini-3.6-flash")
    assert live == "gemini-3.6-flash"
    assert live_reason is None


def _install_fake_groq_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLLM:
        def __init__(self, **kwargs: object) -> None:
            self.model = kwargs["model"]  # type: ignore[index]
            self.kwargs = kwargs

    groq_mod = types.ModuleType("livekit.plugins.groq")
    groq_mod.LLM = FakeLLM  # type: ignore[attr-defined]
    plugins = types.ModuleType("livekit.plugins")
    plugins.groq = groq_mod  # type: ignore[attr-defined]
    livekit = types.ModuleType("livekit")
    livekit.plugins = plugins  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "livekit", livekit)
    monkeypatch.setitem(sys.modules, "livekit.plugins", plugins)
    monkeypatch.setitem(sys.modules, "livekit.plugins.groq", groq_mod)


def test_groq_build_logs_remap(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import worker.providers.llm.groq as groq_mod

    _install_fake_groq_plugin(monkeypatch)
    with caplog.at_level(logging.INFO, logger="worker.providers.llm.groq"):
        llm = groq_mod.build("qwen/qwen3.6-27b")
    assert llm.model == "openai/gpt-oss-20b"
    assert any(
        "llm model remapped provider=groq" in r.message
        and "reason=dead_model" in r.message
        for r in caplog.records
    )


def _install_fake_gemini_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeThinkingConfig:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeHttpOptions:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeTypes:
        ThinkingConfig = FakeThinkingConfig
        HttpOptions = FakeHttpOptions

    class FakeLLM:
        def __init__(self, **kwargs: object) -> None:
            self.model = kwargs["model"]  # type: ignore[index]
            self.kwargs = kwargs

    google_genai = types.ModuleType("google.genai")
    google_genai.types = FakeTypes()  # type: ignore[attr-defined]
    google_plugin = types.ModuleType("livekit.plugins.google")
    google_plugin.LLM = FakeLLM  # type: ignore[attr-defined]
    plugins = types.ModuleType("livekit.plugins")
    plugins.google = google_plugin  # type: ignore[attr-defined]
    livekit = types.ModuleType("livekit")
    livekit.plugins = plugins  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.genai", google_genai)
    monkeypatch.setitem(sys.modules, "livekit", livekit)
    monkeypatch.setitem(sys.modules, "livekit.plugins", plugins)
    monkeypatch.setitem(sys.modules, "livekit.plugins.google", google_plugin)


def test_gemini_build_logs_remap(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import worker.providers.llm.gemini as gemini_mod

    _install_fake_gemini_plugin(monkeypatch)
    with caplog.at_level(logging.INFO, logger="worker.providers.llm.gemini"):
        llm = gemini_mod.build("gemini-2.5-flash")
    assert llm.model  # remapped default
    assert any(
        "llm model remapped provider=gemini" in r.message
        and "reason=deprecated_id" in r.message
        for r in caplog.records
    )


def test_public_capabilities_picker_excludes_dead_groq() -> None:
    from tenant_portal_api.provider_capabilities import get_public_capabilities

    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = []
    result = get_public_capabilities(conn)
    groq = result["languages"]["en"]["llm"]["groq"]
    assert "llama-3.3-70b-versatile" not in groq["models"]
    assert "openai/gpt-oss-20b" in groq["models"]
    assert "llama-3.3-70b-versatile" in groq["legacyAliases"]
    gemini = result["languages"]["en"]["llm"]["gemini"]
    assert gemini["models"] == ["gemini-3.6-flash"]
    assert "gemini-2.5-flash" in gemini["legacyAliases"]


def test_capabilities_table_has_no_dead_ids_in_models() -> None:
    dead = {
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen/qwen3.6-27b",
    }
    for lang, layers in CAPABILITIES.items():
        for provider, cap in layers.get("llm", {}).items():
            overlap = dead.intersection(cap.get("models") or [])
            assert not overlap, f"{lang}/{provider} models still list {overlap}"


def test_adapter_dead_sets_match_legacy_aliases() -> None:
    """Keep capabilities.legacy_aliases in sync with adapter remap tables."""
    from worker.providers.llm import gemini as gemini_mod
    from worker.providers.llm import groq as groq_mod

    groq_cap = llm_capability("en", "groq")
    assert groq_cap is not None
    assert set(groq_cap["legacy_aliases"]) == set(groq_mod._DEAD_GROQ_MODELS)

    for lang in ("en", "ur"):
        gem_cap = llm_capability(lang, "gemini")
        assert gem_cap is not None
        assert set(gem_cap["legacy_aliases"]) == set(gemini_mod._DEPRECATED_GEMINI_MODELS)
