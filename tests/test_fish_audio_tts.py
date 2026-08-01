"""Phase 6e gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

Fish Audio TTS, `en` only. Package/API verified live against PyPI + the installed package's own
inspect.signature before any code was written (worker/providers/tts/fish_audio.py's docstring
records the evidence, including the real finding that this plugin's constructor has NO `language`
parameter, unlike Cartesia/ElevenLabs). rollout_state is `testing`
(worker/providers/capabilities.py) until a human-approved live smoke test confirms it for real.
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
    ProviderValidationError,
    resolve_agent_provider_fields,
)
from worker.providers.tts.fish_audio import build as build_fish_audio_tts  # noqa: E402

_FISH_AUDIO_VOICE_SLUG = "fish-audio-default"
_FISH_AUDIO_REAL_VOICE_ID = "933563129e564b19a115bedd57b7406a"


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


def test_fish_audio_tts_constructs_for_english():
    """Real construction, not a mock — proves the adapter actually produces a working Fish Audio
    TTS object with the right voice, not just that the code compiles."""
    if not os.getenv("FISH_API_KEY"):
        pytest.skip(
            "FISH_API_KEY not set — the plugin itself requires it even to construct a TTS "
            "instance, not only to make a live call. Add it to .env.local to run this."
        )
    tts = build_fish_audio_tts(_FISH_AUDIO_REAL_VOICE_ID)
    assert tts._opts.voice_id == _FISH_AUDIO_REAL_VOICE_ID


def test_fish_audio_still_rejected_via_tenant_routes_while_testing(conn):
    """`testing` behaves exactly like `planned` for every tenant-facing route today (no
    internal/admin bypass exists) — must still be cleanly rejected, not silently allowed through
    just because rollout_state advanced past `planned`."""
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
            tts_provider="fish_audio",
            tts_voice_id=_FISH_AUDIO_VOICE_SLUG,
            tts_options=None,
            voice_id=None,
            current=None,
        )
    assert exc.value.code == "provider_not_enabled"
