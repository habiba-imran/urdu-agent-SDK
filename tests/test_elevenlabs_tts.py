"""Phase 6d gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

ElevenLabs TTS, `en` only, `enabled` as of 2026-08-02. Package/API verified live against PyPI +
the installed package's own inspect.signature before any code was written
(worker/providers/tts/elevenlabs.py's docstring records the evidence), then confirmed with a real
human-approved live call (real Deepgram transcripts, coherent Gemini replies, ElevenLabs audio the
human confirmed sounded clear and correct; see worker/providers/capabilities.py's docstring and
the plan's Phase 6d changelog entry for the full account).
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
from worker.providers.tts.elevenlabs import build as build_elevenlabs_tts  # noqa: E402

_ELEVENLABS_VOICE_SLUG = "elevenlabs-default"
_ELEVENLABS_REAL_VOICE_ID = "hpp4J3VqNfWAUOO0d1Us"


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


def test_elevenlabs_tts_constructs_for_english():
    """Real construction, not a mock — proves the adapter actually produces a working ElevenLabs
    TTS object with the right voice/language, not just that the code compiles."""
    if not os.getenv("ELEVEN_API_KEY"):
        pytest.skip(
            "ELEVEN_API_KEY not set — the plugin itself requires it even to construct a TTS "
            "instance, not only to make a live call. Add it to .env.local to run this."
        )
    tts = build_elevenlabs_tts(_ELEVENLABS_REAL_VOICE_ID, "en")
    assert tts._opts.voice_id == _ELEVENLABS_REAL_VOICE_ID
    assert tts._opts.language == "en"


def test_elevenlabs_now_validates_successfully_end_to_end(conn):
    """Updated 2026-08-02: elevenlabs is now `enabled` for en, confirmed by a real human-approved
    live call (real audio, human-confirmed clear and correct). A full en+elevenlabs agent must now
    resolve with NO error at all."""
    resolved = resolve_agent_provider_fields(
        conn,
        agent_language="en",
        stt_provider="gladia",
        stt_model="default",
        stt_options=None,
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_options=None,
        tts_provider="elevenlabs",
        tts_voice_id=_ELEVENLABS_VOICE_SLUG,
        tts_options=None,
        voice_id=None,
        current=None,
    )
    assert resolved["tts_provider"] == "elevenlabs"
    assert resolved["tts_voice_id"] == _ELEVENLABS_VOICE_SLUG
