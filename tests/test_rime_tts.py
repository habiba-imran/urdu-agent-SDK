"""Phase 6f gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

Rime TTS, `en` only, `enabled` as of 2026-08-02. Package/API verified live against PyPI + the
installed package's own inspect.signature before any code was written
(worker/providers/tts/rime.py's docstring records the evidence, including two real, non-obvious
API differences: the voice kwarg is `speaker` and the language kwarg `lang` uses 3-letter codes,
not our internal 2-letter `agent_language` values), then confirmed with a real human-approved live
call (a long, 20-turn conversation, real Rime audio the human confirmed sounded clear; see
worker/providers/capabilities.py's docstring and the plan's Phase 6f changelog entry for the full
account).
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

try:
    import psycopg
except ImportError:  # pragma: no cover
    pytest.skip("psycopg not installed", allow_module_level=True)

from dbconn import conn_kwargs  # noqa: E402

from tenant_portal_api.provider_validation import (  # noqa: E402
    resolve_agent_provider_fields,
)
from worker.providers.tts.rime import build as build_rime_tts  # noqa: E402

_RIME_VOICE_SLUG = "rime-arcana-astra"
_RIME_REAL_SPEAKER = "astra"


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


def test_rime_tts_constructs_for_english():
    """Real construction, not a mock — proves the adapter actually produces a working Rime TTS
    object with the right speaker/language, not just that the code compiles."""
    if not os.getenv("RIME_API_KEY"):
        pytest.skip(
            "RIME_API_KEY not set — the plugin itself requires it even to construct a TTS "
            "instance, not only to make a live call. Add it to .env.local to run this."
        )
    tts = build_rime_tts(_RIME_REAL_SPEAKER, "en")
    assert tts._opts.speaker == _RIME_REAL_SPEAKER
    assert tts._opts.arcana_options.lang == "eng"


def test_rime_build_rejects_unmapped_language():
    """The adapter maps only `en` -> `eng` explicitly and must raise for anything else, rather
    than silently guessing a 3-letter code — this repo's "no silent fallback" rule applied to a
    language-code translation, not just a provider name."""
    with pytest.raises(ValueError):
        build_rime_tts(_RIME_REAL_SPEAKER, "ur")


def test_rime_now_validates_successfully_end_to_end(conn):
    """Updated 2026-08-02: rime is now `enabled` for en, confirmed by a real human-approved live
    call (real audio, human-confirmed clear). A full en+rime agent must now resolve with NO error
    at all."""
    resolved = resolve_agent_provider_fields(
        conn,
        agent_language="en",
        stt_provider="gladia",
        stt_model="default",
        stt_options=None,
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_options=None,
        tts_provider="rime",
        tts_voice_id=_RIME_VOICE_SLUG,
        tts_options=None,
        voice_id=None,
        current=None,
    )
    assert resolved["tts_provider"] == "rime"
    assert resolved["tts_voice_id"] == _RIME_VOICE_SLUG
