"""Unit tests: configured TTS/LLM providers stick (force_* helpers are no-ops)."""

from worker.config import AgentConfig
from worker.telephony_tts import (
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


def test_force_cartesia_never_remaps_webrtc():
    cfg, voice, forced = force_cartesia_for_telephony(
        _cfg(), "andromeda", audio_channel="webrtc"
    )
    assert forced is False
    assert cfg.tts_provider == "rime"
    assert voice == "andromeda"


def test_force_cartesia_never_remaps_rime_on_telephony():
    cfg, voice, forced = force_cartesia_for_telephony(
        _cfg(), "andromeda", audio_channel="telephony"
    )
    assert forced is False
    assert cfg.tts_provider == "rime"
    assert voice == "andromeda"


def test_force_cartesia_keeps_urdu_uplift_on_telephony():
    cfg, voice, forced = force_cartesia_for_telephony(
        _cfg(
            agent_language="ur",
            tts_provider="uplift",
            tts_voice_id="v_meklc281",
            voice_id="v_meklc281",
            llm_provider="gemini",
        ),
        "v_meklc281",
        audio_channel="telephony",
    )
    assert forced is False
    assert cfg.tts_provider == "uplift"
    assert cfg.tts_voice_id == "v_meklc281"
    assert voice == "v_meklc281"


def test_force_cartesia_keeps_elevenlabs_on_telephony():
    cfg, voice, forced = force_cartesia_for_telephony(
        _cfg(tts_provider="elevenlabs", tts_voice_id="el-voice"),
        "el-voice",
        audio_channel="telephony",
    )
    assert forced is False
    assert cfg.tts_provider == "elevenlabs"
    assert voice == "el-voice"


def test_force_groq_never_remaps_gemini_on_english_telephony(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg, forced = force_groq_for_telephony(_cfg(), audio_channel="telephony")
    assert forced is False
    assert cfg.llm_provider == "gemini"


def test_force_groq_keeps_gemini_on_webrtc(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg, forced = force_groq_for_telephony(_cfg(), audio_channel="webrtc")
    assert forced is False
    assert cfg.llm_provider == "gemini"


def test_force_groq_keeps_urdu_gemini(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    cfg, forced = force_groq_for_telephony(
        _cfg(agent_language="ur"), audio_channel="telephony"
    )
    assert forced is False
    assert cfg.llm_provider == "gemini"
