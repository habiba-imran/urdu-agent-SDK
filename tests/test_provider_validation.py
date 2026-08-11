"""Phase 3 gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

Direct tests of tenant_portal_api/provider_validation.py::resolve_agent_provider_fields — the
single function every agent create/update route (both /portal and /machine) funnels through.
Tested directly (not only through the HTTP layer) so every error branch is cheap to exercise.
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

from tenant_portal_api.provider_validation import (  # noqa: E402
    ProviderValidationError,
    resolve_agent_provider_fields,
)


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


def _call(conn, **overrides):
    base = dict(
        agent_language=None,
        stt_provider=None,
        stt_model=None,
        stt_options=None,
        llm_provider=None,
        llm_model=None,
        llm_options=None,
        tts_provider=None,
        tts_voice_id=None,
        tts_options=None,
        voice_id="v_meklc281",  # the real seeded Uplift demo voice (ur, enabled)
        current=None,
    )
    base.update(overrides)
    return resolve_agent_provider_fields(conn, **base)


def test_defaults_resolve_to_ur_gladia_gemini_uplift(conn):
    resolved = _call(conn)
    assert resolved["agent_language"] == "ur"
    assert resolved["stt_provider"] == "gladia"
    assert resolved["stt_model"] == "default"
    assert resolved["stt_options"] == {}
    assert resolved["llm_provider"] == "gemini"
    assert resolved["llm_model"] == "gemini-2.5-flash"
    assert resolved["llm_options"] == {}
    assert resolved["tts_provider"] == "uplift"
    assert resolved["tts_options"] == {}


def test_voice_id_and_tts_voice_id_both_get_the_resolved_value(conn):
    """The sync fix this phase closes: whichever of voice_id/tts_voice_id the caller gave, BOTH
    columns must end up with the same resolved value."""
    resolved = _call(conn, voice_id="v_meklc281")
    assert resolved["voice_id"] == resolved["tts_voice_id"] == "v_meklc281"


def test_tts_voice_id_takes_priority_over_voice_id(conn):
    """Guide's explicit priority rule. Uses a throwaway second enabled ur/uplift voice so a real
    difference is observable, not just a no-op."""
    other_voice = f"test-priority-voice-{uuid.uuid4().hex[:8]}"
    conn.execute(
        "insert into voices (id, display_name, provider, language, rollout_state, enabled) "
        "values (%s, 'Priority Test Voice', 'uplift', 'ur', 'enabled', true)",
        (other_voice,),
    )
    try:
        resolved = _call(conn, voice_id="v_meklc281", tts_voice_id=other_voice)
        assert resolved["voice_id"] == resolved["tts_voice_id"] == other_voice
    finally:
        conn.execute("delete from voices where id = %s", (other_voice,))


def test_unsupported_language_rejected(conn):
    with pytest.raises(ProviderValidationError) as exc:
        _call(conn, agent_language="klingon")
    assert exc.value.code == "unsupported_language"
    assert exc.value.status == 422


def test_groq_rejected_for_urdu(conn):
    """The guide's explicit business rule: Groq must never be selectable for ur. Enforced
    structurally (groq is simply absent from ur's capability entry, not specially cased)."""
    with pytest.raises(ProviderValidationError) as exc:
        _call(conn, llm_provider="groq")
    assert exc.value.code == "unsupported_provider_for_language"


def test_elevenlabs_rejected_for_urdu(conn):
    with pytest.raises(ProviderValidationError) as exc:
        _call(conn, tts_provider="elevenlabs")
    assert exc.value.code == "unsupported_provider_for_language"


def test_english_fish_audio_rejected_as_not_yet_enabled(conn):
    """Updated 2026-08-02 (Phase 6d): elevenlabs is now `enabled` for en (live test passed — see
    tests/test_elevenlabs_tts.py), so this test's subject swapped a fourth time — fish_audio stays
    genuinely `testing`/not-enabled, blocked on account funding
    (state/BLOCKERS.md::BLOCK-FISHAUDIO), unaffected by cartesia/elevenlabs/rime's later
    promotions (Phase 6c/6d/6f). Must reject with provider_not_enabled, not
    unsupported_provider_for_language (a real, different case: the provider EXISTS for this
    language, just isn't live yet)."""
    with pytest.raises(ProviderValidationError) as exc:
        _call(conn, agent_language="en", tts_provider="fish_audio")
    assert exc.value.code == "provider_not_enabled"


def test_unsupported_model_for_provider_rejected(conn):
    with pytest.raises(ProviderValidationError) as exc:
        _call(conn, stt_model="not-a-real-model")
    assert exc.value.code == "unsupported_model_for_provider"


def test_nonempty_stt_options_rejected(conn):
    """No adapter consumes any option yet (Phase 2's own explicit scope boundary) — the only
    valid value today is {}."""
    with pytest.raises(ProviderValidationError) as exc:
        _call(conn, stt_options={"anything": "at all"})
    assert exc.value.code == "invalid_stt_options"


def test_unknown_voice_rejected(conn):
    with pytest.raises(ProviderValidationError) as exc:
        _call(conn, voice_id="not-a-real-voice-id")
    assert exc.value.code == "unsupported_voice_for_provider"


def test_disabled_voice_rejected(conn):
    disabled_voice = f"test-disabled-voice-{uuid.uuid4().hex[:8]}"
    conn.execute(
        "insert into voices (id, display_name, provider, language, rollout_state, enabled) "
        "values (%s, 'Disabled Test Voice', 'uplift', 'ur', 'enabled', false)",
        (disabled_voice,),
    )
    try:
        with pytest.raises(ProviderValidationError) as exc:
            _call(conn, voice_id=disabled_voice)
        assert exc.value.code == "unsupported_voice_for_provider"
    finally:
        conn.execute("delete from voices where id = %s", (disabled_voice,))


def test_current_supplies_defaults_for_omitted_fields_on_update(conn):
    """UPDATE semantics: fields not present in the request keep the agent's existing resolved
    values (via `current`), not the CREATE defaults. Only tts_voice_id changes here; every other
    field must be carried over from `current` unchanged."""
    other_voice = f"test-update-current-voice-{uuid.uuid4().hex[:8]}"
    conn.execute(
        "insert into voices (id, display_name, provider, language, rollout_state, enabled) "
        "values (%s, 'Update Current Test Voice', 'uplift', 'ur', 'enabled', true)",
        (other_voice,),
    )
    current = {
        "agent_language": "ur",
        "stt_provider": "gladia",
        "stt_model": "default",
        "stt_options": {},
        "llm_provider": "gemini",
        "llm_model": "gemini-2.5-flash",
        "llm_options": {},
        "tts_provider": "uplift",
        "tts_voice_id": "v_meklc281",
        "voice_id": "v_meklc281",
        "tts_options": {},
    }
    try:
        resolved = _call(conn, tts_voice_id=other_voice, voice_id=None, current=current)
        assert resolved["tts_voice_id"] == resolved["voice_id"] == other_voice
        assert resolved["llm_model"] == "gemini-2.5-flash"
        assert resolved["stt_provider"] == "gladia"
    finally:
        conn.execute("delete from voices where id = %s", (other_voice,))
