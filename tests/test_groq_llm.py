"""Phase 6b gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

Groq LLM, `enabled` for `en` (2026-08-01). Package/API verified live against PyPI + the installed
package's own inspect.signature before any code was written
(worker/providers/llm/groq.py's docstring records the evidence), then confirmed with a real
human-approved live call — coherent, contextually appropriate replies, independently re-verified
from the DB transcript (see worker/providers/capabilities.py's docstring and the plan's Phase 6b
changelog entry for the full account).
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
from worker.providers.llm.groq import build as build_groq_llm  # noqa: E402


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


def test_groq_llm_constructs_for_english():
    """Real construction, not a mock — proves the adapter actually produces a working Groq LLM
    object with the right model, not just that the code compiles."""
    if not os.getenv("GROQ_API_KEY"):
        pytest.skip(
            "GROQ_API_KEY not set — the plugin itself requires it even to construct an LLM "
            "instance, not only to make a live call. Add it to .env.local to run this."
        )
    llm = build_groq_llm("llama-3.3-70b-versatile")
    assert llm.model == "llama-3.3-70b-versatile"


def test_groq_llm_layer_validates_successfully_now_enabled(conn):
    """Updated 2026-08-01: groq is now `enabled` for en, confirmed by a real live call. The llm
    layer must no longer be what rejects this combination — the function should get past it and
    fail (if at all) only at a later layer (tts). Updated 2026-08-02 (Phase 6d): elevenlabs is now
    enabled too, so this uses fish_audio (still genuinely `planned`) to keep exercising the gap."""
    with pytest.raises(ProviderValidationError) as exc:
        resolve_agent_provider_fields(
            conn,
            agent_language="en",
            stt_provider="gladia",
            stt_model="default",
            stt_options=None,
            llm_provider="groq",
            llm_model="llama-3.3-70b-versatile",
            llm_options=None,
            # uplift would instead fail with unsupported_provider_for_language (not listed for en
            # at all).
            tts_provider="fish_audio",
            tts_voice_id=None,
            tts_options=None,
            voice_id="v_meklc281",
            current=None,
        )
    assert exc.value.code == "provider_not_enabled"
    assert "tts" in exc.value.reason


def test_groq_still_never_selectable_for_urdu(conn):
    """Re-confirms Groq is still never selectable for `ur` regardless of `en`'s rollout state —
    the guide's explicit rule, enforced structurally (groq absent from ur's llm dict entirely)."""
    with pytest.raises(ProviderValidationError) as exc_ur:
        resolve_agent_provider_fields(
            conn,
            agent_language="ur",
            stt_provider="gladia",
            stt_model="default",
            stt_options=None,
            llm_provider="groq",
            llm_model="llama-3.3-70b-versatile",
            llm_options=None,
            tts_provider="uplift",
            tts_voice_id=None,
            tts_options=None,
            voice_id="v_meklc281",
            current=None,
        )
    assert exc_ur.value.code == "unsupported_provider_for_language"
