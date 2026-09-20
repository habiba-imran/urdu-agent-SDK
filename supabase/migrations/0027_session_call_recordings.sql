-- 0027_session_call_recordings.sql
-- Persist LiveKit session audio recordings so telephony get/list APIs and
-- host CRM (Activity) can archive playable call audio.

alter table sessions
  add column if not exists recording_url text,
  add column if not exists recording_storage_path text;

alter table telephony_calls
  add column if not exists recording_url text,
  add column if not exists recording_storage_path text;

comment on column sessions.recording_url is
  'Signed or provider URL for the mixed session audio recording (ogg). Short-lived; prefer re-signing from recording_storage_path when possible.';

comment on column sessions.recording_storage_path is
  'Private storage object path for the session recording, e.g. {tenant_id}/{room_name}.ogg.';

comment on column telephony_calls.recording_url is
  'Signed or provider URL for the call audio recording. Mirrored from the linked session when available.';

comment on column telephony_calls.recording_storage_path is
  'Private storage object path for the call recording.';
