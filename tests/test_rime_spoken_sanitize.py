"""Unit tests for Rime pre-TTS sanitizer. No livekit/psycopg required."""

from worker.rime_spoken_sanitize import sanitize_spoken_text
from worker.spoken_sanitize import sanitizer_for_provider


def test_strips_markdown_and_cartesia_ssml():
    raw = '**Hello** — let me check that <break time="300ms"/> okay.'
    out = sanitize_spoken_text(raw)
    assert "**" not in out
    assert "<break" not in out
    assert "Hello" in out
    assert "okay" in out


def test_converts_cartesia_spell_tag_to_rime_spell():
    raw = "Your code is <spell>TKT4829</spell>."
    out = sanitize_spoken_text(raw)
    assert "<spell>" not in out
    assert "spell(TKT4829)" in out


def test_keeps_rime_spell_function():
    raw = "Your confirmation is spell(ABC123XYZ)."
    out = sanitize_spoken_text(raw)
    assert "spell(ABC123XYZ)" in out


def test_strips_mist_pause_laughter_emoji_bullets():
    raw = "Sure 😊 <750>\n- first item\n[laughter] second"
    out = sanitize_spoken_text(raw)
    assert "😊" not in out
    assert "<750>" not in out
    assert "[laughter]" not in out
    assert "first item" in out
    assert not out.strip().startswith("-")


def test_dispatcher_does_not_cross_apply():
    cartesia = sanitizer_for_provider("cartesia")
    rime = sanitizer_for_provider("rime")
    assert cartesia is not None and rime is not None
    sample = 'Hi <break time="200ms"/> spell(AB12).'
    cartesia_out = cartesia(sample)
    rime_out = rime(sample)
    assert '<break time="200ms"/>' in cartesia_out
    assert "<break" not in rime_out
    assert "spell(AB12)" in rime_out
    assert sanitizer_for_provider("uplift") is None
