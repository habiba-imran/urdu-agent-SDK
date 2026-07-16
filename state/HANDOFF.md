# HANDOFF

## Session 5 | 2026-07-16 | Phase 2 (Control plane) — GATE 2 GREEN, awaiting human token-widen review

### What changed
- **P2-prep** (on phase/1-supabase): ADR-005 authorizes `service_role` for the control plane only
  (dev); 33/31-GUIDE updated; Supabase moved to paid Pro in 30-GUIDE + usage_ledger `supabase_db_mb`;
  `.env.local` DB password `@`→`%40` (dbconn also unquotes, robust either way).
- **Phase 2** on branch `phase/2-control-plane`:
  - Schema: `0004_nonces.sql` (used_nonces replay store, RLS on, owner-only) + `allowed_origins text[]`
    added to `tenants` in 0001. `make db-reset` rebuilds from zero (4 migrations). Mirror regenerated.
  - `control_plane/mint.py` — `mint_session`: tenant lookup, HMAC verify (constant-time), ≤60s replay
    window, single-use nonce (unique-PK check), tenant-active, agent-owned IDOR guard, per-tenant
    origin allowlist, quota (concurrent + monthly minutes), then a scoped LiveKit JWT (room=uuid4,
    identity=uuid4, TTL=120s, roomJoin on that one room; NO roomAdmin/Create/List) + session row +
    quota increment, all in one transaction so a replay cannot double-mint.
  - `control_plane/secrets.py` — SecretProvider (raw HMAC secrets stay in the trusted tier; DB keeps
    only the hash). `control_plane/app.py` — FastAPI `POST /v1/session` + per-tenant rate limit.
  - `tests/test_mint.py` — GATE 2, 11 tests.

### What was tested and HOW — GATE 2, green
- `pytest tests/test_mint.py -v` → **11 passed** (~50s, live dev DB): wrong sig / stale ts / replayed
  nonce → 401; IDOR agent / suspended tenant / wrong origin → 403; concurrent + monthly caps → 429;
  token scoped to exactly the minted room (no admin grants); TTL exp-nbf == 120s; endpoint wiring.
- `make gate` (full) → GATE: PASS (test_mint 11, test_isolation 1, CER 7 skipped). rls_check: RLS on
  all 7 tables incl. used_nonces. Mirror matches live.

### Open decisions / flags for the human
- **HMAC secret storage is deferred (real decision needed).** `tenants.hmac_secret_hash` = hash only;
  the raw secret is supplied by `control_plane/secrets.py` SecretProvider (dev: `CP_TENANT_SECRETS`
  JSON in .env.local; tests inject). PROD store — Supabase Vault / secret manager / encrypted column —
  is your call. Nothing is provisioned in dev yet, so the live endpoint has no tenants until secrets
  are added; the gate injects them.
- **service_role key is still ABSENT** from .env.local; the mint uses the postgres OWNER connection
  (SUPABASE_DB_URL) for RLS bypass, which is equivalent (ADR-005). If you want the supabase-py REST
  path (Phase 3 worker), the key becomes an H-task.
- **The Phase-2 human gate** is: try to widen a minted token yourself — must fail (roomJoin is bound
  to one uuid room, TTL 120s, no admin grants).

### Traps discovered
- `livekit.api.AccessToken` sets `nbf`+`exp` (no `iat`); TTL = exp-nbf.
- psycopg3 `conn.transaction()` works on an autocommit connection (wraps the block); the mint relies
  on this for atomic nonce+session+quota.
- fastapi TestClient emits a StarletteDeprecationWarning about httpx — harmless.

### Exact next action
STOP. Human gate for Phase 2: **attempt to widen a minted token yourself; it must fail**
(docs/41-HUMAN-TASKS.md). Do NOT start Phase 3 until the human says "begin Phase 3".
When cleared: Phase 3 = docs/23-PHASE-3-WORKER.md, gate `pytest tests/test_worker.py`.
