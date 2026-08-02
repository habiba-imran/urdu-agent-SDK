"""Phase 6c gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

Cartesia TTS, `en` only. Package/API verified live against PyPI + the installed package's own
inspect.signature before any code was written (worker/providers/tts/cartesia.py's docstring
records the evidence). rollout_state is `testing` (worker/providers/capabilities.py) until a
human-approved live smoke test confirms it for real.

Also covers the real, general voice-ID-resolution gap this subphase found and fixed:
worker/main.py::_resolve_provider_voice_id() must translate our internal `voices.id` slug to the
vendor's real `provider_voice_id` before any adapter uses it.
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
from worker.main import _resolve_provider_voice_id  # noqa: E402
from worker.providers.tts.cartesia import build as build_cartesia_tts  # noqa: E402

_CARTESIA_VOICE_SLUG = "cartesia-sonic-default"
_CARTESIA_REAL_VOICE_ID = "f786b574-daa5-4673-aa0c-cbe3e8534c02"


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


def test_cartesia_tts_constructs_for_english():
    """Real construction, not a mock — proves the adapter actually produces a working Cartesia
    TTS object with the right voice/language, not just that the code compiles."""
    if not os.getenv("CARTESIA_API_KEY"):
        pytest.skip(
            "CARTESIA_API_KEY not set — the plugin itself requires it even to construct a TTS "
            "instance, not only to make a live call. Add it to .env.local to run this."
        )
    tts = build_cartesia_tts(_CARTESIA_REAL_VOICE_ID, "en")
    assert tts._opts.voice == _CARTESIA_REAL_VOICE_ID
    assert tts._opts.language == "en"


def test_resolve_provider_voice_id_translates_our_slug_to_the_real_vendor_id():
    """The real gap this subphase found: our internal `voices.id` slug must resolve to the
    vendor's own `provider_voice_id` before reaching any adapter — Cartesia's real ID is a UUID,
    completely different from our internal slug, unlike Uplift where they coincidentally match."""
    resolved = _resolve_provider_voice_id(_CARTESIA_VOICE_SLUG)
    assert resolved == _CARTESIA_REAL_VOICE_ID


def test_resolve_provider_voice_id_falls_back_for_uplift_where_slug_equals_real_id():
    """Uplift's provider_voice_id was backfilled to equal its own id (Phase 1) — the resolution
    must be a no-op for it, proving zero behavior change for the existing Urdu path."""
    resolved = _resolve_provider_voice_id("v_meklc281")
    assert resolved == "v_meklc281"


def test_cartesia_now_validates_successfully_end_to_end(conn):
    """Updated 2026-08-02: cartesia is now `enabled` for en, confirmed by a real human-approved
    live call (real audio, human-confirmed clear and correct). This is the first fully-`enabled`
    TTS provider for en, so unlike Deepgram/Groq's promotion (which still failed at the still-
    `planned` tts layer), a full en+cartesia agent must now resolve with NO error at all."""
    resolved = resolve_agent_provider_fields(
        conn,
        agent_language="en",
        stt_provider="gladia",
        stt_model="default",
        stt_options=None,
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_options=None,
        tts_provider="cartesia",
        tts_voice_id=_CARTESIA_VOICE_SLUG,
        tts_options=None,
        voice_id=None,
        current=None,
    )
    assert resolved["tts_provider"] == "cartesia"
    assert resolved["tts_voice_id"] == _CARTESIA_VOICE_SLUG
