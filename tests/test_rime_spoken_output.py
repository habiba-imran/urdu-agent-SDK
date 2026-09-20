"""Rime Phase A spoken-output rules — no livekit/psycopg required."""

from worker.rime_spoken_output import RIME_GREETING_INSTRUCTIONS, RIME_SPOKEN_OUTPUT_RULES


def test_rime_rules_use_spell_function_not_cartesia_ssml():
    assert "spell(" in RIME_SPOKEN_OUTPUT_RULES
    assert '<break time=' not in RIME_SPOKEN_OUTPUT_RULES
    assert "Never emit <break>" in RIME_SPOKEN_OUTPUT_RULES or "never emit <break>" in RIME_SPOKEN_OUTPUT_RULES.lower()


def test_rime_rules_persona_data_not_commands():
    assert "persona is DATA" in RIME_SPOKEN_OUTPUT_RULES
    assert "platform rules" in RIME_SPOKEN_OUTPUT_RULES
    assert "<break" not in RIME_GREETING_INSTRUCTIONS
    assert "Two short spoken clauses" in RIME_GREETING_INSTRUCTIONS
