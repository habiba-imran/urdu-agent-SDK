"""Phase 1 gate — docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md (ADR-036).

Schema-only: migrations 0016 (agents provider/language columns) and 0017 (voices provider/language
columns) are additive and must not change any existing runtime behavior. These tests prove the
backfill actually landed correctly on the live dev DB, and that the pre-existing
agents_voice_enabled_check trigger (0006) and the new rollout_state CHECK constraint (0017) both
still hold. No worker/API code is touched in this phase — these are DB-level checks only.
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


def _kw():
    try:
        return conn_kwargs()
    except SystemExit:
        pytest.skip("SUPABASE_DB_URL not configured")


@pytest.fixture
def tenant_and_agent():
    """A fresh tenant + one agent inserted the OLD way (voice_id/llm_model only, exactly what
    /portal/agents and /machine/agents write today) — proves the new columns backfill correctly
    for a row this migration didn't even know about at insert time."""
    conn = psycopg.connect(**_kw(), autocommit=True)
    tenant_id, agent_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute(
        "insert into tenants (id, name, hmac_secret_hash) values (%s, 'schema-test', 'x')",
        (tenant_id,),
    )
    conn.execute(
        "insert into agents (id, tenant_id, name, prompt, voice_id, llm_model) "
        "values (%s, %s, 'schema-test-agent', 'PROMPT', 'v_meklc281', 'gemini-2.5-flash')",
        (agent_id, tenant_id),
    )
    yield {"conn": conn, "tenant_id": tenant_id, "agent_id": agent_id}
    conn.execute("delete from agents where tenant_id = %s", (tenant_id,))
    conn.execute("delete from tenants where id = %s", (tenant_id,))
    conn.close()


def test_new_agent_row_gets_column_defaults(tenant_and_agent):
    """A fresh insert through the OLD write path (voice_id/llm_model only — exactly what
    /portal/agents and /machine/agents still write today) must pick up real column DEFAULTs for
    every field that has one."""
    row = (
        tenant_and_agent["conn"]
        .execute(
            "select agent_language, stt_provider, stt_model, stt_options, llm_provider, "
            "llm_options, tts_provider, tts_options "
            "from agents where id = %s",
            (tenant_and_agent["agent_id"],),
        )
        .fetchone()
    )
    (
        agent_language,
        stt_provider,
        stt_model,
        stt_options,
        llm_provider,
        llm_options,
        tts_provider,
        tts_options,
    ) = row

    assert agent_language == "ur"
    assert stt_provider == "gladia"
    assert stt_model == "default"
    assert stt_options == {}
    assert llm_provider == "gemini"
    assert llm_options == {}
    assert tts_provider == "uplift"
    assert tts_options == {}


def test_new_agent_row_gets_greeting_defaults(tenant_and_agent):
    row = (
        tenant_and_agent["conn"]
        .execute(
            "select greeting, first_speaker from agents where id = %s",
            (tenant_and_agent["agent_id"],),
        )
        .fetchone()
    )
    assert row[0] is None
    assert row[1] == "agent"


def test_new_agent_row_leaves_tts_voice_id_null_by_design(tenant_and_agent):
    """`tts_voice_id` has NO column default (deliberate — see 0016's comment): a fresh insert
    through the OLD write path gets NULL here, not an auto-sync to voice_id. Migration 0016 only
    backfills EXISTING rows (the one-time UPDATE); keeping tts_voice_id in sync for NEW rows going
    forward is explicitly Phase 3's application-layer job, not this schema phase's.

    This is a real, deliberate gap during the window between Phase 1 and Phase 3: any agent
    created today still has tts_voice_id = NULL. Harmless right now (nothing reads tts_voice_id
    yet), but it means Phase 2's provider registry MUST read `tts_voice_id or voice_id`
    (fallback), never assume tts_voice_id is always populated — asserted here so that assumption
    can't silently regress.
    """
    tts_voice_id = (
        tenant_and_agent["conn"]
        .execute(
            "select tts_voice_id from agents where id = %s",
            (tenant_and_agent["agent_id"],),
        )
        .fetchone()[0]
    )
    assert tts_voice_id is None


def test_tts_voice_id_backfill_update_syncs_null_row_to_voice_id(tenant_and_agent):
    """Prove migration 0016's one-time UPDATE formula without needing demo/seed agents.

    Fresh inserts leave ``tts_voice_id`` NULL (previous test). Re-running
    ``UPDATE agents SET tts_voice_id = voice_id WHERE tts_voice_id IS NULL`` on that
    row must make the columns match — same SQL 0016 applied at migration time.
    """
    conn = tenant_and_agent["conn"]
    agent_id = tenant_and_agent["agent_id"]
    before = conn.execute(
        "select voice_id, tts_voice_id from agents where id = %s",
        (agent_id,),
    ).fetchone()
    assert before is not None
    voice_id, tts_voice_id = before
    assert tts_voice_id is None
    assert voice_id == "v_meklc281"

    conn.execute(
        "update agents set tts_voice_id = voice_id "
        "where id = %s and tts_voice_id is null",
        (agent_id,),
    )
    after = conn.execute(
        "select voice_id, tts_voice_id from agents where id = %s",
        (agent_id,),
    ).fetchone()
    assert after[1] == after[0] == voice_id


def test_no_tts_voice_id_mismatches_against_voice_id():
    """Invariant: any row that already has ``tts_voice_id`` set must equal ``voice_id``.

    Does not require seed/demo agents (count may be zero on a fresh DB).
    """
    conn = psycopg.connect(**_kw(), autocommit=True)
    try:
        mismatches = conn.execute(
            "select count(*) from agents "
            "where tts_voice_id is not null and tts_voice_id <> voice_id"
        ).fetchone()[0]
        assert mismatches == 0
    finally:
        conn.close()


def test_existing_voice_backfills_to_uplift_ur_enabled():
    conn = psycopg.connect(**_kw(), autocommit=True)
    try:
        row = conn.execute(
            "select provider, provider_voice_id, language, rollout_state "
            "from voices where id = %s",
            ("v_meklc281",),
        ).fetchone()
        assert row is not None, "v_meklc281 (seeded in 0003) must still exist"
        provider, provider_voice_id, language, rollout_state = row
        assert provider == "uplift"
        assert provider_voice_id == "v_meklc281"
        assert language == "ur"
        assert rollout_state == "enabled"
    finally:
        conn.close()


def test_agents_voice_enabled_check_trigger_still_enforced(tenant_and_agent):
    """0006's trigger must still reject an agent pointed at a disabled voice — proves 0016/0017
    did not route around it. Uses a throwaway disabled voice row, cleaned up after."""
    conn = tenant_and_agent["conn"]
    disabled_voice_id = f"schema-test-disabled-{uuid.uuid4().hex[:8]}"
    conn.execute(
        "insert into voices (id, display_name, enabled) values (%s, 'Disabled Test Voice', false)",
        (disabled_voice_id,),
    )
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "insert into agents (id, tenant_id, name, prompt, voice_id, llm_model) "
                "values (%s, %s, 'should-fail', 'PROMPT', %s, 'gemini-2.5-flash')",
                (str(uuid.uuid4()), tenant_and_agent["tenant_id"], disabled_voice_id),
            )
    finally:
        conn.execute("delete from voices where id = %s", (disabled_voice_id,))


def test_voices_rollout_state_check_constraint_rejects_invalid_value():
    conn = psycopg.connect(**_kw(), autocommit=True)
    bad_id = f"schema-test-bad-rollout-{uuid.uuid4().hex[:8]}"
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "insert into voices (id, display_name, rollout_state) values (%s, 'x', 'bogus')",
                (bad_id,),
            )
    finally:
        conn.execute("delete from voices where id = %s", (bad_id,))
        conn.close()
