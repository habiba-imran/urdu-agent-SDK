"""Phase 5 gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

English STT + LLM, zero new vendors: Gladia was already language-parameterized in Phase 2, Gemini
needed no code change at all (prompt-driven, not language-specific). This phase only flips
capability rollout states and proves both actually work for `en`.

Updated 2026-08-02 (Phase 6c): cartesia is now `en`'s first enabled TTS vendor (see
tests/test_cartesia_tts.py) — a full English agent IS creatable end-to-end now. Updated
2026-08-02 (Phase 6d): elevenlabs is now enabled too (live test passed — see
tests/test_elevenlabs_tts.py). Updated 2026-08-02 (Phase 6f): rime is now enabled too (see
tests/test_rime_tts.py). The remaining "still rejected" test below documents fish_audio
specifically — genuinely still `testing`/not-enabled, blocked on account funding
(state/BLOCKERS.md::BLOCK-FISHAUDIO), not "no TTS at all" (that gap closed in Phase 6c).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

try:
    import psycopg
except ImportError:  # pragma: no cover
    pytest.skip("psycopg not installed", allow_module_level=True)

from dbconn import conn_kwargs  # noqa: E402

from tenant_portal_api.provider_capabilities import get_public_capabilities  # noqa: E402
from tenant_portal_api.provider_validation import (  # noqa: E402
    ProviderValidationError,
    resolve_agent_provider_fields,
)
from worker.providers.registry import build_components  # noqa: E402
from worker.providers.types import AgentRuntimeConfig  # noqa: E402


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


def test_gladia_stt_builds_for_english():
    """The adapter itself needed no change (parameterized in Phase 2) — this proves it actually
    produces an English-configured STT, not just that the language string flows through somewhere."""
    cfg = AgentRuntimeConfig(
        agent_language="en",
        stt_provider="gladia",
        stt_model="default",
        stt_options={},
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_options={},
        tts_provider="uplift",  # irrelevant to this test; only stt is inspected
        tts_voice_id="v_meklc281",
        tts_options={},
    )
    stt = build_components(cfg).stt
    assert stt._opts.language_config.languages == ["en"]
    assert stt._opts.language_config.code_switching is False


def test_capabilities_api_shows_english_stt_llm_and_tts_enabled(conn):
    result = get_public_capabilities(conn)
    en = result["languages"]["en"]
    assert en["stt"]["gladia"]["state"] == "enabled"
    assert en["llm"]["gemini"]["state"] == "enabled"
    # Updated 2026-08-01 (Phase 6a): deepgram is now enabled too — see tests/test_deepgram_stt.py.
    assert en["stt"]["deepgram"]["state"] == "enabled"
    # Updated 2026-08-01 (Phase 6b): groq is now enabled too — see tests/test_groq_llm.py.
    assert en["llm"]["groq"]["state"] == "enabled"
    # Updated 2026-08-02 (Phase 6c): cartesia is now enabled — the first en TTS vendor. See
    # tests/test_cartesia_tts.py.
    assert en["tts"]["cartesia"]["state"] == "enabled"
    # Updated 2026-08-02 (Phase 6d): elevenlabs is now enabled too. See tests/test_elevenlabs_tts.py.
    assert en["tts"]["elevenlabs"]["state"] == "enabled"
    # Updated 2026-08-02 (Phase 6f): rime is now enabled too. See tests/test_rime_tts.py.
    assert en["tts"]["rime"]["state"] == "enabled"


def test_english_agent_with_still_planned_tts_vendor_rejected_cleanly(conn):
    """Proves stt+llm validate successfully for en (no error raised at those layers) and the
    function only stops at tts when the chosen TTS vendor (fish_audio) is still `planned` — not a
    generic failure, the exact documented gap. Updated 2026-08-02 (Phase 6c/6d): cartesia and
    elevenlabs are both enabled now, see the tests above — swapped to fish_audio, still
    genuinely `planned`."""
    with pytest.raises(ProviderValidationError) as exc:
        resolve_agent_provider_fields(
            conn,
            agent_language="en",
            stt_provider="gladia",
            stt_model="default",
            stt_options=None,
            llm_provider="gemini",
            llm_model="gemini-2.5-flash",
            llm_options=None,
            # fish_audio EXISTS in en's capability table (documents the confirmed target scope)
            # but is still `planned` — the real case this test targets. `uplift` would instead
            # hit unsupported_provider_for_language (it isn't listed for en at all), a different,
            # already-covered case.
            tts_provider="fish_audio",
            tts_voice_id=None,
            tts_options=None,
            voice_id="v_meklc281",
            current=None,
        )
    assert exc.value.code == "provider_not_enabled"
    assert "tts" in exc.value.reason
