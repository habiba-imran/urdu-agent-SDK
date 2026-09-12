"""Phase 4 gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

Direct tests of tenant_portal_api/provider_capabilities.py::get_public_capabilities — the function
both GET /portal/provider-capabilities and GET /machine/provider-capabilities return verbatim.
"""

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

try:
    import psycopg
except ImportError:  # pragma: no cover
    pytest.skip("psycopg not installed", allow_module_level=True)

from dbconn import conn_kwargs  # noqa: E402

from tenant_portal_api.provider_capabilities import get_public_capabilities  # noqa: E402


def _kw():
    try:
        return conn_kwargs()
    except SystemExit:
        pytest.skip("SUPABASE_DB_URL not configured")


@pytest.fixture
def conn():
    c = psycopg.connect(**_kw(), autocommit=True)
    yield c
    c.close()


def test_response_shape_matches_the_guide_example(conn):
    result = get_public_capabilities(conn)
    assert set(result.keys()) == {"languages"}
    ur = result["languages"]["ur"]
    assert ur["label"] == "Urdu"
    assert ur["stt"]["gladia"]["state"] == "enabled"
    assert ur["stt"]["gladia"]["models"] == ["default"]
    assert ur["stt"]["gladia"]["defaultModel"] == "default"
    assert ur["llm"]["gemini"]["state"] == "enabled"
    assert ur["tts"]["uplift"]["state"] == "enabled"
    assert "v_meklc281" in ur["tts"]["uplift"]["voices"]
    assert ur["tts"]["uplift"]["defaultVoice"] is not None


def test_english_present_with_stt_llm_and_tts_enabled(conn):
    """Updated 2026-08-01 (Phase 5): en+gladia/gemini are now genuinely `enabled` — see
    tests/test_english_language.py for the full Phase 5 gate. Updated 2026-08-02 (Phase 6c):
    cartesia is now `en`'s first enabled TTS vendor — see tests/test_cartesia_tts.py. Updated
    2026-08-02 (Phase 6d): elevenlabs is now enabled too — see tests/test_elevenlabs_tts.py.
    Updated 2026-08-02 (Phase 6f): rime is now enabled too — see tests/test_rime_tts.py."""
    result = get_public_capabilities(conn)
    en = result["languages"]["en"]
    assert en["stt"]["gladia"]["state"] == "enabled"
    assert en["llm"]["gemini"]["state"] == "enabled"
    assert en["tts"]["cartesia"]["state"] == "enabled"
    assert en["tts"]["elevenlabs"]["state"] == "enabled"
    assert en["tts"]["rime"]["state"] == "enabled"


def test_planned_and_disabled_never_leak_through(conn):
    """A disabled voice (rollout_state='enabled' but enabled=false) must never appear in the
    returned voice list, even though it'd otherwise match provider+language+rollout_state."""
    disabled_voice = f"test-capabilities-disabled-{uuid.uuid4().hex[:8]}"
    conn.execute(
        "insert into voices (id, display_name, provider, language, rollout_state, enabled) "
        "values (%s, 'Capabilities Test Disabled Voice', 'uplift', 'ur', 'enabled', false)",
        (disabled_voice,),
    )
    try:
        result = get_public_capabilities(conn)
        assert (
            disabled_voice not in result["languages"]["ur"]["tts"]["uplift"]["voices"]
        )
    finally:
        conn.execute("delete from voices where id = %s", (disabled_voice,))


def test_groq_and_elevenlabs_never_appear_for_urdu(conn):
    result = get_public_capabilities(conn)
    ur = result["languages"]["ur"]
    assert "groq" not in ur.get("llm", {})
    assert "elevenlabs" not in ur.get("tts", {})
