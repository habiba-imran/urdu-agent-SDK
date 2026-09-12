-- 0017_voices_provider_fields.sql — Phase 1 of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md
-- (ADR-036). Additive only, idempotent — no destructive statements.
--
-- Every existing voice row (the 82 seeded in 0005) backfills to provider='uplift', language='ur',
-- rollout_state='enabled' — matching current reality exactly, nothing changes behavior.
--
-- `rollout_state` gets a CHECK constraint (matches this repo's existing convention, e.g.
-- tenants.status, usage_events.kind) since the guide defines a closed, fixed set of 3 states.
-- `provider` deliberately does NOT get a CHECK constraint restricting it to a fixed vendor list —
-- the whole point of this phase's registry work is that adding a new TTS vendor (Phase 6+) must
-- not require a schema migration to loosen an enum. Same reasoning for not indexing
-- (language, provider, rollout_state) here: the table is 82 rows, the capabilities API that will
-- actually query by these columns doesn't exist until Phase 4 — added then, against a real query
-- pattern, not speculatively now.

alter table voices
  add column if not exists provider          text not null default 'uplift',
  add column if not exists provider_voice_id text,
  add column if not exists language          text not null default 'ur',
  add column if not exists rollout_state     text not null default 'enabled'
    check (rollout_state in ('planned', 'testing', 'enabled'));

-- Backfill provider_voice_id to match each row's own id (varies per row).
update voices set provider_voice_id = id where provider_voice_id is null;
