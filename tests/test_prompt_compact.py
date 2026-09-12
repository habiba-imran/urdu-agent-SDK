"""Unit tests for worker.prompt_compact — Groq free-tier prompt shrink."""

from worker.prompt_compact import compact_prompt_for_groq


def test_compact_keeps_business_sections_and_drops_platform_rule_dupes(monkeypatch):
    monkeypatch.setenv("GROQ_PROMPT_SOFT_CHARS", "100")

    prompt = (
        """
### SECTION 1: BUSINESS IDENTITY
We are Lena Clinic. Hours Mon-Fri 9-5. Phone 555-0100.

### SECTION 2: SAFETY
Never give medical advice.
4. 911 EMERGENCY PROTOCOL:
   Say: hang up and call 911.
EMERGENCY TRIAGE RULES (follow immediately when triggers match):
   1. Life-Threatening Emergency
      Trigger keywords: chest pain, shortness of breath
      Immediate action: call 911 again (duplicate of protocol above).

### SECTION 3: VOICE & CONVERSATION RULES (STRICT VOICE DISCIPLINE)
"""
        + ("long rule text. " * 80)
        + """

### SECTION 4: ACCURACY, SPELLING & READ-BACK DISCIPLINE
"""
        + ("more rules. " * 80)
        + """

### SECTION 5: SECURITY & ANTI-INJECTION DIRECTIVES (OWASP TOP-1 DEFENSE)
"""
        + ("security. " * 80)
        + """

### SECTION 8: APPOINTMENT INTAKE (VOICE)
When the caller wants to schedule collect many verbose fields and explanations.
"""
        + ("intake padding. " * 40)
        + """

### SECTION 8A: APPOINTMENT TIMING RULES
"""
        + ("timing padding. " * 40)
        + """

### FINAL AUTHORITY: INVARIANT CORE ENFORCEMENT
"""
        + ("final authority padding. " * 40)
        + """

### KNOWLEDGE DIGEST
FAQ: parking is free behind the building.

### SECTION 10: CUSTOM INSTRUCTIONS
Always mention we accept walk-ins after 3pm.
"""
    ).strip()

    out, changed = compact_prompt_for_groq(prompt)
    assert changed is True
    assert "Lena Clinic" in out
    assert "Never give medical advice" in out
    assert "call 911" in out.lower()
    assert "EMERGENCY TRIAGE RULES" not in out
    assert "parking is free" in out
    assert "walk-ins after 3pm" in out
    assert "SECTION 3" not in out
    assert "FINAL AUTHORITY" not in out
    assert "APPOINTMENT INTAKE" in out
    assert "intake padding" not in out
    assert len(out) < len(prompt)


def test_compact_skips_small_prompts():
    small = "### SECTION 1: BUSINESS IDENTITY\nShort clinic prompt."
    out, changed = compact_prompt_for_groq(small)
    assert changed is False
    assert out == small
