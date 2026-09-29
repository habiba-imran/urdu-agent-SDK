-- 0028_session_recording_consent_retention.sql
-- F-C4 (audit §9): call recording had no consent capture, no disclosure state, no retention
-- and no erasure path. The worker code for all three landed in Wave 2 and probes for these
-- columns at runtime, skipping consent/retention writes while they are absent. This migration
-- turns those paths on.
--
-- Contract: docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md §A.3.
-- Consumers: worker/recording_policy.py, worker/recording_disclosure.py,
-- worker/session_retention.py, worker/config.py, scripts/purge_expired_session_media.py.
--
-- Deliberately NOT re-adding retention columns to telephony_calls: they already exist from
-- 0014_telephony_data_governance_audit.sql, and the purge script uses those.
--
-- Filename note: the repo already has two different 0014_ migrations. 0028 is the next free
-- number and is unique (see supabase/migrations/).

-- ---------------------------------------------------------------------------
-- agents: per-agent recording opt-in (default OFF — recording stays off until a
-- tenant explicitly enables it, which is the F-C4 position).
-- ---------------------------------------------------------------------------
alter table agents
  add column if not exists recording_enabled boolean not null default false,
  add column if not exists recording_consent_mode text not null default 'disclosure';

-- Allowed modes per A.3. Added separately (not inline) so re-running is safe.
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'agents_recording_consent_mode_check'
  ) then
    alter table agents
      add constraint agents_recording_consent_mode_check
      check (recording_consent_mode in ('off', 'disclosure', 'verbal'));
  end if;
end $$;

comment on column agents.recording_enabled is
  'F-C4: per-agent opt-in for call audio recording. Default false; env alone cannot force recording on in hosted environments (worker/recording_policy.py).';

comment on column agents.recording_consent_mode is
  'F-C4: how consent is obtained before persisting audio — off | disclosure (spoken notice) | verbal (explicit spoken agreement).';

-- ---------------------------------------------------------------------------
-- sessions: consent state + retention / erasure bookkeeping.
-- Values written by worker/recording_policy.py:
--   not_applicable | pending | granted | declined
-- ---------------------------------------------------------------------------
alter table sessions
  add column if not exists recording_consent_status text,
  add column if not exists recording_consent_at timestamptz,
  add column if not exists retention_until timestamptz,
  add column if not exists deletion_requested_at timestamptz,
  add column if not exists deleted_at timestamptz,
  add column if not exists redacted_at timestamptz;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'sessions_recording_consent_status_check'
  ) then
    alter table sessions
      add constraint sessions_recording_consent_status_check
      check (
        recording_consent_status is null
        or recording_consent_status in ('not_applicable', 'pending', 'granted', 'declined')
      );
  end if;
end $$;

comment on column sessions.recording_consent_status is
  'F-C4: not_applicable | pending | granted | declined. Audio is only persisted when granted (worker/session_recording.py).';

comment on column sessions.recording_consent_at is
  'F-C4: when consent reached its current status.';

comment on column sessions.retention_until is
  'F-C4: when session media/transcript become eligible for purge (set on close by worker/session_retention.py).';

comment on column sessions.deletion_requested_at is
  'F-C4: erasure requested (GDPR/CCPA). Purged on the next run regardless of retention_until.';

comment on column sessions.deleted_at is
  'F-C4: media deleted and row cleared by scripts/purge_expired_session_media.py.';

comment on column sessions.redacted_at is
  'F-C4: transcript / personal fields cleared.';

-- ---------------------------------------------------------------------------
-- escalations: holds caller phone numbers in contact_info with no retention (F-C4/F-M12).
-- ---------------------------------------------------------------------------
alter table escalations
  add column if not exists retention_until timestamptz,
  add column if not exists deletion_requested_at timestamptz,
  add column if not exists deleted_at timestamptz,
  add column if not exists redacted_at timestamptz;

comment on column escalations.retention_until is
  'F-C4: when contact_info becomes eligible for redaction.';

comment on column escalations.deleted_at is
  'F-C4: set when contact_info was cleared by the purge job.';

-- ---------------------------------------------------------------------------
-- Purge selects on (deleted_at is null) + retention_until / deletion_requested_at.
-- Partial indexes keep that scan cheap as these tables grow.
-- ---------------------------------------------------------------------------
create index if not exists sessions_purge_idx
  on sessions (retention_until, deletion_requested_at)
  where deleted_at is null;

create index if not exists escalations_purge_idx
  on escalations (retention_until, deletion_requested_at)
  where deleted_at is null;
