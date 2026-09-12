"""Unit tests for telephony Cartesia / Groq force-remap."""

from worker.config import AgentConfig
from worker.telephony_tts import (
    TELEPHONY_CARTESIA_PROVIDER_VOICE_ID,
    TELEPHONY_CARTESIA_VOICE_ID,
    TELEPHONY_GROQ_MODEL,
    force_cartesia_for_telephony,
    force_groq_for_telephony,
)


def _cfg(**overrides) -> AgentConfig:
    base = dict(
        agent_id="a",
        tenant_id="t",
        name="n",
        prompt="persona",
        voice_id="rime-arcana-andromeda",
        llm_model="gemini-2.5-flash",
        tts_provider="rime",
        tts_voice_id="rime-arcana-andromeda",
        agent_language="en",
        llm_provider="gemini",
    )
    base.update(overrides)
    return AgentConfig(**base)


def test_force_cartesia_skips_webrtc():
    cfg, voice, forced = force_cartesia_for_telephony(
        _cfg(), "andromeda", audio_channel="webrtc"
    )
    assert forced is False
    assert cfg.tts_provider == "rime"
    assert voice == "andromeda"


def test_force_cartesia_skips_already_cartesia():
    cfg, voice, forced = force_cartesia_for_telephony(
        _cfg(tts_provider="cartesia", tts_voice_id="cartesia-katie-friendly-fixer"),
        "f786b574-daa5-4673-aa0c-cbe3e8534c02",
        audio_channel="telephony",
    )
    assert forced is False
    assert cfg.tts_provider == "cartesia"
    assert voice == "f786b574-daa5-4673-aa0c-cbe3e8534c02"


def test_force_cartesia_remaps_rime_on_telephony():
    cfg, voice, forced = force_cartesia_for_telephony(
        _cfg(), "andromeda", audio_channel="telephony"
    )
    assert forced is True
    assert cfg.tts_provider == "cartesia"
    assert cfg.tts_voice_id == TELEPHONY_CARTESIA_VOICE_ID
    assert voice == TELEPHONY_CARTESIA_PROVIDER_VOICE_ID


def test_force_groq_remaps_gemini_on_english_telephony(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg, forced = force_groq_for_telephony(_cfg(), audio_channel="telephony")
    assert forced is True
    assert cfg.llm_provider == "groq"
    assert cfg.llm_model == TELEPHONY_GROQ_MODEL


def test_force_groq_skips_webrtc(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg, forced = force_groq_for_telephony(_cfg(), audio_channel="webrtc")
    assert forced is False
    assert cfg.llm_provider == "gemini"


def test_force_groq_skips_urdu(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg, forced = force_groq_for_telephony(
        _cfg(agent_language="ur"), audio_channel="telephony"
    )
    assert forced is False
    assert cfg.llm_provider == "gemini"


def test_force_groq_skips_without_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cfg, forced = force_groq_for_telephony(_cfg(), audio_channel="telephony")
    assert forced is False
    assert cfg.llm_provider == "gemini"
