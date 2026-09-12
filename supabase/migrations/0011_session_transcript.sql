-- 0011_session_transcript.sql — store the conversation transcript alongside the existing
-- sessions.summary column (0001_schema.sql), so the dashboard's Call Sessions detail view
-- can show both.
--
-- jsonb, not text: the worker already has each turn as discrete {role, text} pairs from
-- AgentSession.history (see worker/main.py's _release_quota_slot) — jsonb keeps that
-- structure so the dashboard can render turn-by-turn without re-parsing a flattened blob.
-- Nullable: older sessions (recorded before this migration, and any session that never
-- reaches a clean shutdown) simply have no transcript, same as summary already can be null.
--
-- No RLS change needed: row-level policies (0002_rls.sql's tenant_isolation_sessions) apply
-- to every column on the row, including this new one, and the worker writes it through the
-- same trusted DB-owner connection (conn_kwargs()) that already writes summary/duration_sec/
-- end_reason — never through the RLS-scoped `authenticated` role.

alter table sessions add column if not exists transcript jsonb;
