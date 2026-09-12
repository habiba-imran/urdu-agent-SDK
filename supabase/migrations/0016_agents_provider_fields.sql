-- 0016_agents_provider_fields.sql — Phase 1 of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md
-- (ADR-036). Additive only, idempotent (ADD COLUMN IF NOT EXISTS, matching 0009's convention) —
-- no destructive statements, safe to run against live data.
--
-- Every existing agent row backfills to `ur + gladia + gemini + uplift`, matching current runtime
-- behavior exactly (worker/factories.py today). Postgres backfills a NOT NULL column with a
-- constant DEFAULT for existing rows without a separate UPDATE (fast, no full table rewrite,
-- PG 11+). `tts_voice_id` is the one exception — its backfill value varies per row (= that row's
-- own voice_id), so it needs an explicit UPDATE below.
--
-- `tts_voice_id` is deliberately left NULLABLE here, not NOT NULL. Nothing in the application layer
-- writes it yet (Phase 3 of the plan adds that, with the tts_voice_id-over-voice_id priority rule
-- the guide specifies). Adding a NOT NULL constraint now, before Phase 3 ships, would break agent
-- creation through the CURRENT /portal/agents and /machine/agents routes, which only ever supply
-- voice_id. `voice_id` stays the authoritative, FK'd, trigger-protected column
-- (agents_voice_enabled_check, 0006) — untouched by this migration.
--
-- CONSEQUENCE FOR PHASE 2 (confirmed by test_provider_registry_schema.py, not just asserted here):
-- any agent created between this migration and Phase 3 landing (i.e. through today's still-live
-- /portal/agents or /machine/agents) has tts_voice_id = NULL. Phase 2's provider registry MUST
-- read `tts_voice_id or voice_id` (fallback), never assume tts_voice_id is always populated.

alter table agents
  add column if not exists agent_language text not null default 'ur',
  add column if not exists stt_provider   text not null default 'gladia',
  add column if not exists stt_model      text not null default 'default',
  add column if not exists stt_options    jsonb not null default '{}'::jsonb,
  add column if not exists llm_provider   text not null default 'gemini',
  add column if not exists llm_options    jsonb not null default '{}'::jsonb,
  add column if not exists tts_provider   text not null default 'uplift',
  add column if not exists tts_voice_id   text,
  add column if not exists tts_options    jsonb not null default '{}'::jsonb;

-- Backfill tts_voice_id to match each row's existing voice_id (varies per row, not a constant
-- default). WHERE clause makes this safe to re-run (idempotent).
update agents set tts_voice_id = voice_id where tts_voice_id is null;
