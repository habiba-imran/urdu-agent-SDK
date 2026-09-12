"""Phase 2 gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

Provider registry refactor: worker/factories.py's STT/LLM/TTS logic moved to worker/providers/,
called via worker/main.py::build_session(). Must be zero behavior change for the existing
ur+gladia+gemini+uplift path — these tests prove that, not just assert it.

SAFETY NOTE: this environment's .env.local sets UPLIFT_MODE=live (for real dev-session work
elsewhere). Every test here that touches the Uplift TTS adapter explicitly monkeypatches
UPLIFT_MODE=fixture — os.environ.setdefault() (what conftest.py itself uses) does NOT override an
already-set var, so relying on the default would silently build a LIVE upliftai.TTS client. That
is exactly what an early draft of this file did; it was caught only by the pre-existing offline
network guard blocking the resulting connection attempts, not by this file's own design. Fixed by
never relying on the default here.
"""

import asyncio
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

from worker.config import load_agent_config  # noqa: E402
from worker.factories import make_llm, make_stt, make_tts  # noqa: E402
from worker.providers.registry import UnsupportedProviderError, build_components  # noqa: E402
from worker.providers.types import AgentRuntimeConfig  # noqa: E402

# Real fixture cache entry (tests/fixtures/tts/manifest.json), same one the worked/approved Urdu
# demo agent uses — canonical, human-listened + approved (see manifest's own status field).
_VOICE_ID = "v_meklc281"
_TEXT = (
    "السلام علیکم، TechZone Laptops میں خوش آمدید۔ میں مہ نور بات کر رہی ہوں، "
    "میں آپ کی کیا مدد کر سکتی ہوں؟"
)


def _kw():
    try:
        return conn_kwargs()
    except SystemExit:
        pytest.skip("SUPABASE_DB_URL not configured")


def _default_runtime_cfg(**overrides) -> AgentRuntimeConfig:
    base = dict(
        agent_language="ur",
        stt_provider="gladia",
        stt_model="default",
        stt_options={},
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_options={},
        tts_provider="uplift",
        tts_voice_id=_VOICE_ID,
        tts_options={},
    )
    base.update(overrides)
    return AgentRuntimeConfig(**base)


async def _collect_pcm(tts) -> bytes:
    pcm = bytearray()
    async for ev in tts.synthesize(_TEXT):
        pcm += bytes(ev.frame.data)
    return bytes(pcm)


def test_registry_and_legacy_factory_produce_same_component_types(monkeypatch):
    """worker/factories.py now delegates to worker/providers/ — both paths must still exist and
    agree, since scripts/probe_soniox_402.py and scratch/test_tts_resilient.py still import
    factories.py directly."""
    monkeypatch.setenv("UPLIFT_MODE", "fixture")
    tts_old, stt_old, llm_old = (
        make_tts(_VOICE_ID),
        make_stt(),
        make_llm("gemini-2.5-flash"),
    )
    components = build_components(_default_runtime_cfg())
    # FixtureTTS is defined as a fresh local class inside build() on every call (same pattern the
    # original factories.py::make_tts() used) — `is` identity will never match across two separate
    # calls, so compare by name instead. STT/LLM are real importable classes (gladia.STT,
    # google.LLM), not locally redefined, so `is` is the right check for those.
    assert type(tts_old).__name__ == type(components.tts).__name__ == "FixtureTTS"
    assert type(stt_old) is type(components.stt)
    assert type(llm_old) is type(components.llm)


def test_uplift_fixture_synthesis_matches_the_committed_fixture_exactly(monkeypatch):
    """The real Urdu-regression proof: fixture-mode synthesis through the (now the only) code
    path must still return exactly the cached wav's PCM data — not just construct without error.

    Asserts startswith(), not ==: LiveKit's ChunkedStream base class emits fixed 10ms frames
    (220 samples * 2 bytes = 440 bytes at 22050Hz) and zero/silence-pads the final partial frame
    to a full frame boundary — verified directly (the two buffers are byte-identical for their
    entire overlapping length; the synthesized one is exactly one 440-byte frame longer). This is
    a LiveKit audio-pipeline characteristic, not something worker/providers/tts/uplift.py controls
    or something this refactor changed — the original factories.py used the exact same base
    classes and would pad identically.
    """
    monkeypatch.setenv("UPLIFT_MODE", "fixture")
    from services.tts_cache import require

    expected_wav = require(_VOICE_ID, _TEXT)
    expected_pcm = expected_wav[
        44:
    ]  # same header-strip _FixtureChunkedStream._run does

    tts = build_components(_default_runtime_cfg()).tts
    got_pcm = asyncio.run(_collect_pcm(tts))

    assert got_pcm.startswith(expected_pcm)
    frame_bytes = 440  # 10ms @ 22050Hz, 16-bit mono
    assert len(got_pcm) - len(expected_pcm) <= frame_bytes


def test_gladia_stt_language_defaults_to_ur_unchanged():
    """agent_language='ur' (Phase 1's default for every existing agent) must produce the exact
    same languages=["ur"] Gladia STT construction as the pre-refactor hardcoded call."""
    stt = build_components(_default_runtime_cfg(agent_language="ur")).stt
    assert stt._opts.language_config.languages == ["ur"]
    assert stt._opts.language_config.code_switching is False


def test_unsupported_provider_raises_typed_error_not_silent_fallback():
    with pytest.raises(UnsupportedProviderError):
        build_components(_default_runtime_cfg(tts_provider="not-a-real-provider"))
    with pytest.raises(UnsupportedProviderError):
        build_components(_default_runtime_cfg(stt_provider="not-a-real-provider"))
    with pytest.raises(UnsupportedProviderError):
        build_components(_default_runtime_cfg(llm_provider="not-a-real-provider"))


@pytest.fixture
def tenant_and_agents():
    """Two agents: one with tts_voice_id explicitly set to simulate a pre-Phase-1/already-synced
    row, one left NULL to simulate a row inserted through the still-live old API path (0016's own
    documented gap) — proves build_session's fallback actually engages only when needed."""
    conn = psycopg.connect(**_kw(), autocommit=True)
    tenant_id = str(uuid.uuid4())
    agent_synced, agent_null = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute(
        "insert into tenants (id, name, hmac_secret_hash) values (%s, 'p2-test', 'x')",
        (tenant_id,),
    )
    conn.execute(
        "insert into agents (id, tenant_id, name, prompt, voice_id, llm_model) "
        "values (%s, %s, 'p2-synced', 'PROMPT', %s, 'gemini-2.5-flash')",
        (agent_synced, tenant_id, _VOICE_ID),
    )
    conn.execute(
        "insert into agents (id, tenant_id, name, prompt, voice_id, llm_model) "
        "values (%s, %s, 'p2-null-tts-voice-id', 'PROMPT', %s, 'gemini-2.5-flash')",
        (agent_null, tenant_id, _VOICE_ID),
    )
    # A plain INSERT leaves tts_voice_id NULL for BOTH rows (no column default — 0016's own
    # documented behavior, confirmed by Phase 1's tests). Explicitly set it on the "synced" one
    # so the two fixture rows actually represent the two distinct scenarios their names claim.
    conn.execute(
        "update agents set tts_voice_id = %s where id = %s", (_VOICE_ID, agent_synced)
    )
    yield {
        "conn": conn,
        "tenant_id": tenant_id,
        "agent_synced": agent_synced,
        "agent_null": agent_null,
    }
    conn.execute("delete from agents where tenant_id = %s", (tenant_id,))
    conn.execute("delete from tenants where id = %s", (tenant_id,))
    conn.close()


def test_agent_config_new_fields_load_correctly(tenant_and_agents):
    """Catches the off-by-one column-order risk flagged in the Phase 0 audit (finding #9) —
    every new AgentConfig field must line up with the column it's actually meant to hold."""
    cfg = load_agent_config(
        tenant_and_agents["agent_synced"], tenant_and_agents["tenant_id"]
    )
    assert cfg.agent_language == "ur"
    assert cfg.stt_provider == "gladia"
    assert cfg.stt_model == "default"
    assert cfg.stt_options == {}
    assert cfg.llm_provider == "gemini"
    assert cfg.llm_options == {}
    assert cfg.tts_provider == "uplift"
    assert cfg.tts_voice_id == _VOICE_ID
    assert cfg.tts_options == {}
    assert cfg.greeting is None
    assert cfg.first_speaker == "agent"


def test_agent_config_tts_voice_id_is_null_for_the_unsynced_row(tenant_and_agents):
    """Sanity check that the fixture's "null" agent genuinely represents the NULL scenario before
    the next test relies on it."""
    cfg = load_agent_config(
        tenant_and_agents["agent_null"], tenant_and_agents["tenant_id"]
    )
    assert cfg.tts_voice_id is None
    assert cfg.voice_id == _VOICE_ID


def test_build_session_falls_back_to_voice_id_when_tts_voice_id_is_null(
    tenant_and_agents, monkeypatch
):
    """The exact scenario Phase 1 flagged: an agent whose tts_voice_id is NULL must still get a
    correctly-voiced TTS component via the voice_id fallback in build_session()."""
    monkeypatch.setenv("UPLIFT_MODE", "fixture")
    from worker.main import build_session

    md = {
        "tenant_id": tenant_and_agents["tenant_id"],
        "agent_id": tenant_and_agents["agent_null"],
    }
    session, cfg, _greeting_prewarm = asyncio.run(build_session(md, room_name="test-room-p2"))
    assert cfg.tts_voice_id is None  # confirms the NULL scenario was actually exercised
    got_pcm = asyncio.run(_collect_pcm(session.tts))
    from services.tts_cache import require

    # startswith(), not == — see the frame-padding note in
    # test_uplift_fixture_synthesis_matches_the_committed_fixture_exactly above.
    assert got_pcm.startswith(require(_VOICE_ID, _TEXT)[44:])
