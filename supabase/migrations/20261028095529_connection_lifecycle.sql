-- Apply before deploying the worker/API changes. No client write grants are added.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
alter table public.agents
  add column if not exists max_call_duration_seconds integer not null default 1800;
alter table public.agents add constraint agents_max_call_duration_seconds_check
  check (max_call_duration_seconds between 60 and 7200) not valid;
alter table public.agents validate constraint agents_max_call_duration_seconds_check;
alter table public.sessions add column if not exists worker_heartbeat_at timestamptz;
alter table public.sessions add column if not exists lifecycle_metrics jsonb not null default '{}'::jsonb;
alter table public.sessions add column if not exists finalized_at timestamptz;
create index if not exists sessions_open_worker_heartbeat_idx
  on public.sessions(worker_heartbeat_at) where ended_at is null;
comment on column public.agents.max_call_duration_seconds is
  'Shared browser/inbound/outbound call limit. Default 30 minutes, hard ceiling 2 hours.';
comment on column public.sessions.worker_heartbeat_at is
  'Worker lease, renewed every 20 seconds; orphan cleanup is separate from duration policy.';
commit;
