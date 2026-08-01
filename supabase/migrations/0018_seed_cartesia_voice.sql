-- 0018_seed_cartesia_voice.sql — Phase 6c of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md
-- (ADR-036). Additive only, idempotent (ON CONFLICT DO NOTHING, matching 0003/0005's seed
-- convention) — no destructive statements.
--
-- Seeds exactly one Cartesia voice: the installed livekit-plugins-cartesia==1.6.5 package's own
-- constructor default (`voice='f786b574-daa5-4673-aa0c-cbe3e8534c02'`, confirmed via
-- inspect.signature on the real installed package, not invented). This is the actual default
-- Cartesia ships with that plugin version, not a guessed ID.
--
-- The voice ROW itself is seeded as enabled — actual tenant-facing availability is still gated by
-- worker/providers/capabilities.py's PROVIDER-level rollout_state (planned -> testing -> enabled),
-- the same two-layer gate every other TTS vendor uses. Seeding the row as enabled now avoids a
-- second "promote the voice row too" step once the provider itself gets promoted after its live
-- test.

insert into voices (id, display_name, provider, provider_voice_id, language, rollout_state, enabled)
values (
  'cartesia-sonic-default',
  'Cartesia Sonic (default)',
  'cartesia',
  'f786b574-daa5-4673-aa0c-cbe3e8534c02',
  'en',
  'enabled',
  true
)
on conflict (id) do nothing;
