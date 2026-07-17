-- 0005_voices_catalogue.sql — full voice picker catalogue (Phase 5, P5-T01).
--
-- H9 #5 (Uplift character-artwork licensing) no longer blocks this — the picker uses 3-4 owned
-- artworks instead of Uplift's licensed art (ADR-017). artwork_url/preview_url are left NULL
-- here: preview_url is populated by P5-T02 (one live-rendered line per voice, human-approved
-- UPLIFT_MODE=record session, not run yet) and P5-T03 (CDN upload); artwork_url depends on the
-- still-open voice-to-owned-artwork mapping question (docs/25-PHASE-5-VOICE-PICKER.md).
--
-- Source of this data: Uplift's own docs page (docs.upliftai.org/orator_voices), extracted via
-- three independent fetches that agreed on the row count (82) and every field checked across
-- overlapping rows — not a guess, not fabricated, but also not a raw API pull (Uplift does not
-- document a programmatic "list voices" endpoint as of 2026-07-17; this is the only source that
-- exists). Flagged at this confidence level deliberately, per this project's anti-hallucination
-- discipline: cite the source, don't overclaim certainty beyond what's actually verified.
--
-- gender is derived mechanically from the "File" internal codename pattern (`_m_` = male,
-- `_f_` = female — a naming convention visible across all 82 entries), NOT re-guessed per voice.
-- One deliberate exception: 'khwajasara' ("Khwajasara" — an androgynous/third-gender character
-- voice per its own description) is left NULL rather than mechanically labeled male from its
-- file code (ai_trg_m_nk) — the source page itself listed this one as gender-unspecified across
-- every extraction, not a one-off artifact, and mechanically overriding that would misrepresent
-- the character.
--
-- These 82 are Uplift's "Primary Voices" catalogue (the current, actively-offered set — matches
-- every example name docs/25-PHASE-5-VOICE-PICKER.md's own spec text already named: Street
-- Vendor, Nosey Aunty, Helpdesk Agent, Prime Time Anchor, all present below). Uplift's site
-- separately lists a smaller "Legacy Voices" set (older v_xxxxx-id voices kept for backward
-- compatibility with existing integrations) — v_meklc281 (this project's own demo agent voice,
-- seeded in 0003) is one of those. The legacy set is NOT seeded here; it is a different, smaller
-- catalogue serving existing agents, not new tenant voice selection, and mixing the two ID
-- schemes into one undifferentiated picker list was not decided here — flagged, not assumed.

insert into voices (id, display_name, gender, enabled) values
  ('jinn', 'Jinn', 'male', true),
  ('sindhi-patriarch', 'Sindhi Patriarch', 'male', true),
  ('punjabi-masi', 'Punjabi Masi', 'female', true),
  ('cricket-commentator', 'Cricket Commentator', 'female', true),
  ('pashtun-pensioner', 'Pashtun Pensioner', 'male', true),
  ('crime-don', 'Crime Don', 'male', true),
  ('schoolgirl', 'Schoolgirl', 'female', true),
  ('bengali-grandfather', 'Bengali Grandfather', 'male', true),
  ('churail', 'Churail', 'female', true),
  ('balochi-seamstress', 'Balochi Seamstress', 'female', true),
  ('iqbalian-shayar', 'Iqbalian Shayar', 'male', true),
  ('late-night-rj', 'Late Night RJ', 'female', true),
  ('dha-matriarch', 'DHA Matriarch', 'female', true),
  ('bihari-organizer', 'Bihari Organizer', 'female', true),
  ('memon-organizer', 'Memon Organizer', 'female', true),
  ('crisp-storyteller', 'Crisp Storyteller', 'male', true),
  ('qissa-khawan', 'Qissa Khawan', 'male', true),
  ('female-narrator', 'Female Narrator', 'female', true),
  ('male-narrator', 'Male Narrator', 'male', true),
  ('podcast-host', 'Podcast Host', 'male', true),
  ('horror-narrator', 'Horror Narrator', 'male', true),
  ('prime-time-anchor', 'Prime Time Anchor', 'male', true),
  ('senior-anchor', 'Senior Anchor', 'male', true),
  ('news-anchor', 'News Anchor', 'female', true),
  ('news-reader', 'News Reader', 'female', true),
  ('field-correspondent', 'Field Correspondent', 'male', true),
  ('paediatrician', 'Paediatrician', 'female', true),
  ('diabetologist', 'Diabetologist', 'male', true),
  ('family-lawyer', 'Family Lawyer', 'female', true),
  ('defense-advocate', 'Defense Advocate', 'male', true),
  ('navy-officer', 'Navy Officer', 'male', true),
  ('stock-analyst', 'Stock Analyst', 'male', true),
  ('helpdesk-agent', 'Helpdesk Agent', 'female', true),
  ('broadband-support', 'Broadband Support', 'male', true),
  ('montessori-teacher', 'Montessori Teacher', 'female', true),
  ('urdu-professor', 'Urdu Professor', 'male', true),
  ('washroom-singer', 'Washroom Singer', 'male', true),
  ('khateeb', 'Khateeb', 'male', true),
  ('seerah-scholar', 'Seerah Scholar', 'male', true),
  ('hadith-narrator', 'Hadith Narrator', 'female', true),
  ('seerah-educator', 'Seerah Educator', 'male', true),
  ('dawah-youtuber', 'Dawah YouTuber', 'male', true),
  ('nosey-aunty', 'Nosey Aunty', 'female', true),
  ('orangi-khala', 'Orangi Khala', 'female', true),
  ('rohtaki-aunty', 'Rohtaki Aunty', 'female', true),
  ('dua-uncle', 'Dua Uncle', 'male', true),
  ('bus-conductor', 'Bus Conductor', 'male', true),
  ('lahori-barber', 'Lahori Barber', 'male', true),
  ('shopkeeper', 'Shopkeeper', 'male', true),
  ('street-vendor', 'Street Vendor', 'male', true),
  ('traffic-cop', 'Traffic Cop', 'male', true),
  ('khwajasara', 'Khwajasara', null, true),
  ('dha-teen-girl', 'DHA Teen Girl', 'female', true),
  ('dha-fitness-devotee', 'DHA Fitness Devotee', 'female', true),
  ('dha-hostess', 'DHA Hostess', 'female', true),
  ('nazimabad-boy', 'Nazimabad Boy', 'male', true),
  ('karachi-romeo', 'Karachi Romeo', 'male', true),
  ('wholesale-trader', 'Wholesale Trader', 'male', true),
  ('college-girl', 'College Girl', 'female', true),
  ('gaming-kid', 'Gaming Kid', 'male', true),
  ('udaas-aashiq', 'Udaas Aashiq', 'male', true),
  ('heartbroken', 'Heartbroken', 'male', true),
  ('udaas-philosopher', 'Udaas Philosopher', 'male', true),
  ('mohalla-storyteller', 'Mohalla Storyteller', 'male', true),
  ('mohalla-patriarch', 'Mohalla Patriarch', 'male', true),
  ('balochi-elder', 'Balochi Elder', 'male', true),
  ('bengali-businesswoman', 'Bengali Businesswoman', 'female', true),
  ('punjabi-manager', 'Punjabi Manager', 'male', true),
  ('lahori-story-uncle', 'Lahori Story Uncle', 'male', true),
  ('pashtun-teen', 'Pashtun Teen', 'male', true),
  ('pashtun-woman', 'Pashtun Woman', 'female', true),
  ('pashtun-navigator', 'Pashtun Navigator', 'male', true),
  ('sindhi-professional', 'Sindhi Professional', 'female', true),
  ('sindhi-networker', 'Sindhi Networker', 'male', true),
  ('sindhi-navigator', 'Sindhi Navigator', 'male', true),
  ('memon-trader', 'Memon Trader', 'male', true),
  ('headmaster', 'Headmaster', 'male', true),
  ('jalsa-mimic', 'Jalsa Mimic', 'male', true),
  ('street-vlogger', 'Street Vlogger', 'female', true),
  ('biryani-reviewer', 'Biryani Reviewer', 'male', true),
  ('female-debater', 'Female Debater', 'female', true),
  ('male-debater', 'Male Debater', 'male', true)
on conflict (id) do nothing;
