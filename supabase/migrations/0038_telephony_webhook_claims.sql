-- M4-F02: durable Telnyx webhook claim before side effects, even when no call row matches yet.
-- Service role (portal) writes; authenticated gets no access.

create table if not exists telephony_webhook_claims (
  provider_event_id text primary key,
  event_type text not null,
  payload jsonb,
  created_at timestamptz not null default now()
);

comment on table telephony_webhook_claims is
  'Idempotent Telnyx webhook inbox — claim row before mutating call/quota state.';

alter table telephony_webhook_claims enable row level security;

revoke all on table telephony_webhook_claims from public, anon, authenticated;
