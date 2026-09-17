"""Phase 4 humanization: Urdu language profile + Uplift phrase config resolution."""

from __future__ import annotations

from worker.config import AgentConfig
from worker.humanization.spoken import (
    URDU_SPOKEN_OUTPUT_RULES,
    compose_system_instructions,
    language_overlay_for,
)
from worker.main import _language_directive, build_agent, SYSTEM_INSTRUCTIONS
from worker.providers.tts.uplift import resolve_uplift_phrase_config_id


def _cfg(**overrides) -> AgentConfig:
    base = dict(
        agent_id="a",
        tenant_id="t",
        name="n",
        prompt="persona",
        voice_id="v_meklc281",
        llm_model="gemini-3.6-flash",
        agent_language="ur",
        llm_provider="gemini",
        tts_provider="uplift",
    )
    base.update(overrides)
    return AgentConfig(**base)


def test_urdu_overlay_present_for_ur_not_en():
    assert "Pakistani Urdu" in URDU_SPOKEN_OUTPUT_RULES
    assert "Roman Urdu" in URDU_SPOKEN_OUTPUT_RULES
    assert "<emotion" not in URDU_SPOKEN_OUTPUT_RULES
    assert language_overlay_for("ur") == URDU_SPOKEN_OUTPUT_RULES
    assert language_overlay_for("en") == ""


def test_compose_ur_includes_urdu_profile_without_cartesia_emotion():
    text = compose_system_instructions(_cfg())
    assert URDU_SPOKEN_OUTPUT_RULES in text
    assert "Uplift delivery" in text
    assert "EMOTION (required" not in text
    assert "<emotion value=" not in text


def test_compose_en_excludes_urdu_profile():
    text = compose_system_instructions(
        _cfg(
            agent_language="en",
            tts_provider="cartesia",
            llm_provider="groq",
            llm_model="openai/gpt-oss-20b",
        )
    )
    assert "LANGUAGE — Pakistani Urdu" not in text
    assert "Do NOT emit <emotion>" in text
    assert "EMOTION (required" not in text


def test_language_directive_urdu_and_english():
    ur = _language_directive("ur")
    assert "Pakistani Urdu" in ur
    assert "Roman Urdu" in ur
    en = _language_directive("en")
    assert "English" in en
    assert "Roman Urdu" not in en


def test_build_agent_ur_includes_urdu_rules():
    agent = build_agent(_cfg())
    assert agent.instructions.startswith(SYSTEM_INSTRUCTIONS)
    assert "LANGUAGE — Pakistani Urdu" in agent.instructions
    assert "Respond only in Pakistani Urdu" in agent.instructions
    assert "<emotion value=" not in agent.instructions


def test_uplift_phrase_config_env_resolution(monkeypatch, tmp_path):
    monkeypatch.delenv("UPLIFT_PHRASE_CONFIG_ID", raising=False)
    monkeypatch.delenv("UPLIFT_USE_PHRASE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("UPLIFT_DISABLE_PHRASE_CONFIG", raising=False)
    assert resolve_uplift_phrase_config_id() is None

    monkeypatch.setenv("UPLIFT_PHRASE_CONFIG_ID", "cfg-abc")
    assert resolve_uplift_phrase_config_id() == "cfg-abc"

    monkeypatch.setenv("UPLIFT_DISABLE_PHRASE_CONFIG", "1")
    assert resolve_uplift_phrase_config_id() is None

    monkeypatch.delenv("UPLIFT_DISABLE_PHRASE_CONFIG", raising=False)
    monkeypatch.setenv("UPLIFT_PHRASE_CONFIG_ID", "")
    assert resolve_uplift_phrase_config_id() is None
