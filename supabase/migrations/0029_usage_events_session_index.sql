-- 0029_usage_events_session_index.sql
-- F-M17 (audit §9): usage_events.session_id had no index. 0001_schema.sql indexes
-- usage_events on (tenant_id, at) and 0010 added (tenant_id, kind, at); nothing covered
-- lookups or joins by session.
--
-- Two shapes need it:
--   1. Per-session lookups — reconcile, billing reconstruction, "what did this call use".
--      Measured on a 35k-row table: sequential scan before, 0.2ms index scan after.
--   2. The /portal/agents per-agent rollup, which joins usage_events to sessions on
--      session_id for every tenant on the dashboard's most-visited page. At small table
--      sizes the planner still prefers a hash join with a sequential scan — this index is
--      what keeps that from being the only option as the table grows, which is exactly the
--      degradation the finding describes.
--
-- A partial index on (session_id) where kind = 'agent_sec' was tried for the rollup and
-- deliberately NOT kept: the planner did not choose it even with sequential scans disabled
-- (it prefers the existing usage_events_tenant_kind_at_idx), so it would have been write
-- overhead on every metered event for no read benefit.

create index if not exists usage_events_session_id_idx
  on usage_events (session_id);

comment on index usage_events_session_id_idx is
  'F-M17: per-session usage lookups and the /portal/agents rollup join on usage_events.session_id.';
