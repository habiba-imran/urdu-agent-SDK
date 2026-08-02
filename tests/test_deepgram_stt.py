"""Phase 6a gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

Deepgram STT, `enabled` for `en` (2026-08-01). Package/API verified live against PyPI + the
installed package's own inspect.signature before any code was written
(worker/providers/stt/deepgram.py's docstring records the evidence), then confirmed with a real
human-approved live call — real Deepgram WebSocket connection, correct English transcripts, a
coherent LLM reply proving the transcript was accurate (see worker/providers/capabilities.py's
docstring and the plan's Phase 6a changelog entry for the full account, including two real bugs
the live test itself surfaced: worker/main.py::prewarm()'s STT_PROVIDER-gated import, and
scripts/mint_demo_token.py's missing explicit LiveKit agent dispatch call — both fixed).
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
from worker.providers.stt.deepgram import build as build_deepgram_stt  # noqa: E402


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


def test_deepgram_stt_constructs_for_english():
    """Real construction, not a mock — proves the adapter actually produces a working Deepgram
    STT object with the right model/language, not just that the code compiles."""
    if not os.getenv("DEEPGRAM_API_KEY"):
        pytest.skip(
            "DEEPGRAM_API_KEY not set — the plugin itself requires it even to construct an "
            "STT instance, not only to make a live call. Add it to .env.local to run this."
        )
    stt = build_deepgram_stt("en")
    assert stt._opts.model == "nova-3"
    assert stt._opts.language == "en"


def test_deepgram_stt_layer_validates_successfully_now_enabled(conn):
    """Updated 2026-08-01: deepgram is now `enabled` for en, confirmed by a real live call. The
    stt layer must no longer be what rejects this combination — the function should get past it
    and fail (if at all) only at a later layer, proving stt+deepgram itself validates cleanly."""
    with pytest.raises(ProviderValidationError) as exc:
        resolve_agent_provider_fields(
            conn,
            agent_language="en",
            stt_provider="deepgram",
            stt_model="nova-3",
            stt_options=None,
            llm_provider="gemini",
            llm_model="gemini-2.5-flash",
            llm_options=None,
            # Updated 2026-08-02 (Phase 6d): elevenlabs is now enabled — swapped to fish_audio,
            # still genuinely `planned`. uplift would instead fail with
            # unsupported_provider_for_language (not listed for en at all).
            tts_provider="fish_audio",
            tts_voice_id=None,
            tts_options=None,
            voice_id="v_meklc281",
            current=None,
        )
    assert exc.value.code == "provider_not_enabled"
    assert "tts" in exc.value.reason
