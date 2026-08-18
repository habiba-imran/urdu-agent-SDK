"""Unit tests for Cartesia pre-TTS sanitizer (Phase D). No livekit/psycopg required."""

from worker.cartesia_spoken_sanitize import sanitize_spoken_text


def test_strips_markdown_and_keeps_ssml():
    raw = '**Hello** — let me check that <break time="300ms"/> okay.'
    out = sanitize_spoken_text(raw)
    assert "**" not in out
    assert '<break time="300ms"/>' in out
    assert "Hello" in out


def test_strips_emoji_and_bullets():
    raw = "Sure 😊\n- first item\n- second"
    out = sanitize_spoken_text(raw)
    assert "😊" not in out
    assert "first item" in out
    assert not out.strip().startswith("-")


def test_preserves_spell_and_laughter():
    raw = "Your code is <spell>TKT4829</spell>. Oh, [laughter] okay."
    out = sanitize_spoken_text(raw)
    assert "<spell>TKT4829</spell>" in out
    assert "[laughter]" in out


def test_empty_passthrough():
    assert sanitize_spoken_text("") == ""
