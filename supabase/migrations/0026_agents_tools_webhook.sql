-- 0026_agents_tools_webhook.sql
-- Per-agent HTTP tools webhook (RAG / FAQ / scheduling). Multi-client safe:
-- each tenant/agent points at THEIR backend; worker does not hardcode one client URL.
-- Additive only, idempotent.

alter table agents
  add column if not exists tools_base_url text,
  add column if not exists tools_auth_secret text;

comment on column agents.tools_base_url is
  'HTTPS (or http for local) base URL of the client backend tool gateway, e.g. https://api.client.com — worker POSTs to {base}/api/tools/*. NULL = tools disabled for this agent (unless worker env fallback).';

comment on column agents.tools_auth_secret is
  'Shared secret sent as x-tool-gateway-secret when calling tools_base_url. Never expose to browsers. NULL allowed if the client gateway is open (not recommended).';
