-- 0006_agents_voice_enabled_check.sql — P5-T05: agents.voice_id validated against voices.enabled.
--
-- The existing FK (agents.voice_id -> voices(id)) only guarantees the voice_id refers to SOME
-- row in voices — it says nothing about whether that voice is currently enabled. A plain CHECK
-- constraint can't do a cross-table lookup in Postgres, so this is a trigger: it fires on every
-- INSERT and on UPDATE of voice_id, and rejects the write if the referenced voice is disabled.
-- This is enforced at the DB level (not application code, which doesn't exist yet for agent
-- creation/update — that's Phase 6 admin-portal territory) so no future write path can bypass it.

create or replace function check_agent_voice_enabled() returns trigger as $$
begin
  if not exists (
    select 1 from voices where id = new.voice_id and enabled = true
  ) then
    raise exception 'voice_id % is not an enabled voice', new.voice_id
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$ language plpgsql;

drop trigger if exists agents_voice_enabled_check on agents;
create trigger agents_voice_enabled_check
  before insert or update of voice_id on agents
  for each row execute function check_agent_voice_enabled();
