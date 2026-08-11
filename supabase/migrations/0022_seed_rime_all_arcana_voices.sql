-- 0022_seed_rime_all_arcana_voices.sql — voice-catalogue expansion, follow-up to Phase 6f
-- (docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036). Additive only, idempotent
-- (ON CONFLICT DO NOTHING) — no destructive statements.
--
-- 0021 seeded exactly one Rime voice (astra, the package's own default). This migration seeds
-- the remaining 7 Arcana voices — the full, real list confirmed directly off the installed
-- livekit-plugins-rime==1.6.5 package's own `ArcanaVoices` Literal type
-- (livekit.plugins.rime.models.ArcanaVoices = Literal["luna", "celeste", "orion", "ursa",
-- "astra", "esther", "estelle", "andromeda"]), not guessed or invented. `provider_voice_id` is
-- the speaker name itself — Rime's `speaker` kwarg takes these names directly, no separate
-- vendor-side ID to resolve (unlike Cartesia/ElevenLabs' opaque UUIDs).
--
-- Seeded as enabled at the voice-row level, same as every other voice — actual tenant-facing
-- availability is still gated by worker/providers/capabilities.py's PROVIDER-level rollout_state
-- (`en.tts.rime` is already `enabled`, Phase 6f), so these become immediately selectable.

insert into voices (id, display_name, provider, provider_voice_id, language, rollout_state, enabled)
values
  ('rime-arcana-luna', 'Rime Arcana (Luna)', 'rime', 'luna', 'en', 'enabled', true),
  ('rime-arcana-celeste', 'Rime Arcana (Celeste)', 'rime', 'celeste', 'en', 'enabled', true),
  ('rime-arcana-orion', 'Rime Arcana (Orion)', 'rime', 'orion', 'en', 'enabled', true),
  ('rime-arcana-ursa', 'Rime Arcana (Ursa)', 'rime', 'ursa', 'en', 'enabled', true),
  ('rime-arcana-esther', 'Rime Arcana (Esther)', 'rime', 'esther', 'en', 'enabled', true),
  ('rime-arcana-estelle', 'Rime Arcana (Estelle)', 'rime', 'estelle', 'en', 'enabled', true),
  ('rime-arcana-andromeda', 'Rime Arcana (Andromeda)', 'rime', 'andromeda', 'en', 'enabled', true)
on conflict (id) do nothing;
