"""The env-seeded greeting must key the same way the runtime does.

``humanization`` joined ``make_greeting_cache_key`` when SDK personas shipped (8f9804c)
but ``seed_greeting_pcm_from_env`` was not updated, so for any agent carrying an
``llm_options.humanization`` profile the seeded key could never equal the runtime key —
the seed was dead weight and the first call of every worker process re-synthesised the
greeting. The demo agent has such a profile, which is how this surfaced.
"""

from __future__ import annotations

import json

from worker.greeting_cache import _prewarm_humanization, make_greeting_cache_key

PROFILE = {
    "pace": "normal",
    "energy": "balanced",
    "warmth": "warm",
    "enabled": True,
    "formality": "balanced",
    "adaptivePace": True,
    "expressiveness": "subtle",
}

_COMMON = dict(
    agent_id="c507b48c-0e85-4cc8-9f31-f80252482f3e",
    tts_provider="cartesia",
    provider_voice_id="voice-uuid",
    greeting_text="Hi, thanks for calling. How can I help you today?",
    audio_channel="webrtc",
    tts_options={},
    language="en",
    tenant_id="21590a56-2cf6-4943-b0b0-1c1ae69ed4fc",
)


def test_a_persona_profile_changes_the_cache_key():
    """If it did not, this whole bug class would be impossible — pin the premise."""
    without = make_greeting_cache_key(**_COMMON)
    with_profile = make_greeting_cache_key(**_COMMON, humanization=PROFILE)
    assert without != with_profile


def test_seeded_key_matches_the_runtime_key_for_a_persona_agent(monkeypatch):
    monkeypatch.setenv("UVA_PREWARM_HUMANIZATION", json.dumps(PROFILE))

    runtime_key = make_greeting_cache_key(**_COMMON, humanization=PROFILE)
    seeded_key = make_greeting_cache_key(**_COMMON, humanization=_prewarm_humanization())

    assert seeded_key == runtime_key, "seeded greeting would never be found at runtime"


def test_unset_profile_still_matches_an_agent_without_one(monkeypatch):
    monkeypatch.delenv("UVA_PREWARM_HUMANIZATION", raising=False)
    assert _prewarm_humanization() is None
    assert make_greeting_cache_key(**_COMMON, humanization=None) == make_greeting_cache_key(**_COMMON)


def test_malformed_profile_is_ignored_rather_than_raising(monkeypatch):
    """A bad env value must not break process start — the seed is best-effort."""
    for bad in ("{not json", "[1,2,3]", '"a string"', "null"):
        monkeypatch.setenv("UVA_PREWARM_HUMANIZATION", bad)
        assert _prewarm_humanization() is None


def test_profile_key_order_does_not_change_the_key(monkeypatch):
    """The portal may serialise the profile in any order; the key must not care."""
    reordered = dict(reversed(list(PROFILE.items())))
    monkeypatch.setenv("UVA_PREWARM_HUMANIZATION", json.dumps(reordered))

    assert make_greeting_cache_key(**_COMMON, humanization=_prewarm_humanization()) == \
        make_greeting_cache_key(**_COMMON, humanization=PROFILE)
