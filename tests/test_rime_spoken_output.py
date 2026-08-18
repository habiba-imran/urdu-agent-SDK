"""Rime Phase A spoken-output rules — no livekit/psycopg required."""

from worker.rime_spoken_output import RIME_GREETING_INSTRUCTIONS, RIME_SPOKEN_OUTPUT_RULES


def test_rime_rules_use_spell_function_not_cartesia_ssml():
    assert "spell(" in RIME_SPOKEN_OUTPUT_RULES
    assert '<break time=' not in RIME_SPOKEN_OUTPUT_RULES
    assert "<spell>" not in RIME_SPOKEN_OUTPUT_RULES.split("Never emit")[0]
    assert "Never emit <break>" in RIME_SPOKEN_OUTPUT_RULES or "never emit <break>" in RIME_SPOKEN_OUTPUT_RULES.lower()


def test_rime_rules_override_persona_and_forbid_ssml():
    assert "PERSONA VS THESE RULES" in RIME_SPOKEN_OUTPUT_RULES
    assert "This block always wins" in RIME_SPOKEN_OUTPUT_RULES
    assert "<break" not in RIME_GREETING_INSTRUCTIONS
    assert "two short clauses" in RIME_GREETING_INSTRUCTIONS
