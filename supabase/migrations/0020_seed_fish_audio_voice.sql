-- 0020_seed_fish_audio_voice.sql — Phase 6e of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md
-- (ADR-036). Additive only, idempotent (ON CONFLICT DO NOTHING, matching 0003/0005/0018/0019's
-- seed convention) — no destructive statements.
--
-- Seeds exactly one Fish Audio voice: the installed livekit-plugins-fishaudio==1.6.5 package's own
-- constructor default (`voice_id='933563129e564b19a115bedd57b7406a'`, `DEFAULT_VOICE_ID` in the
-- package's own tts.py, confirmed via inspect.signature on the real installed package, not
-- invented). This is the actual default voice that plugin version ships with, not a guessed ID.
--
-- The voice ROW itself is seeded as enabled — actual tenant-facing availability is still gated by
-- worker/providers/capabilities.py's PROVIDER-level rollout_state (planned -> testing -> enabled),
-- the same two-layer gate every other TTS vendor uses. Seeding the row as enabled now avoids a
-- second "promote the voice row too" step once the provider itself gets promoted after its live
-- test.

insert into voices (id, display_name, provider, provider_voice_id, language, rollout_state, enabled)
values (
  'fish-audio-default',
  'Fish Audio (default)',
  'fish_audio',
  '933563129e564b19a115bedd57b7406a',
  'en',
  'enabled',
  true
)
on conflict (id) do nothing;
