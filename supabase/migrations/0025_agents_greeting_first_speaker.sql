-- 0025_agents_greeting_first_speaker.sql
-- Tenant-owned session opening: optional greeting text + who speaks first.
-- Additive only, idempotent. Existing rows keep current runtime behavior
-- (agent greets immediately via generate_reply from persona).

alter table agents
  add column if not exists greeting text,
  add column if not exists first_speaker text not null default 'agent';

alter table agents drop constraint if exists agents_first_speaker_check;
alter table agents
  add constraint agents_first_speaker_check
  check (first_speaker in ('agent', 'user'));

comment on column agents.greeting is
  'Optional tenant-owned opening line spoken when first_speaker=agent. NULL means the worker generates a greeting from persona. Untrusted tenant text — TTS input only, never system instructions.';

comment on column agents.first_speaker is
  'Who speaks first after session start: agent (default, greets immediately) or user (wait for caller).';
