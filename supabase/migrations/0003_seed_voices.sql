-- 0003_seed_voices.sql — minimal voice seed.
-- Just enough so agents.voice_id has a valid FK target. The FULL Uplift catalogue
-- (display names, genders, preview + artwork URLs) is populated in Phase 5, gated
-- on H9 #5 (commercial artwork licensing). Only the default voice id is known and
-- verified here (config.py UPLIFT_VOICE_ID); gender is left NULL rather than guessed.
insert into voices (id, display_name, gender, enabled) values
  ('v_meklc281', 'Uplift Orator (default)', null, true)
on conflict (id) do nothing;
