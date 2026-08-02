-- 0021_seed_rime_voice.sql — Phase 6f of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md
-- (ADR-036). Additive only, idempotent (ON CONFLICT DO NOTHING, matching 0003/0005/0018/0019/0020's
-- seed convention) — no destructive statements.
--
-- Seeds exactly one Rime voice: the installed livekit-plugins-rime==1.6.5 package's own
-- constructor default for its default model (`model="arcana"` -> `speaker="astra"`, confirmed by
-- reading the installed package's source, not invented). This is the actual default speaker that
-- plugin version falls back to for the arcana model, not a guessed ID.
--
-- The voice ROW itself is seeded as enabled — actual tenant-facing availability is still gated by
-- worker/providers/capabilities.py's PROVIDER-level rollout_state (planned -> testing -> enabled),
-- the same two-layer gate every other TTS vendor uses. Seeding the row as enabled now avoids a
-- second "promote the voice row too" step once the provider itself gets promoted after its live
-- test.

insert into voices (id, display_name, provider, provider_voice_id, language, rollout_state, enabled)
values (
  'rime-arcana-astra',
  'Rime Arcana (Astra)',
  'rime',
  'astra',
  'en',
  'enabled',
  true
)
on conflict (id) do nothing;
