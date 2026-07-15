# HANDOFF

## Session 3 | 2026-07-16 | Phase 0 (harness hardening — Caveats A & B)

### What changed
- **Caveat A** (commit ddf947d): retracted the invalid P0-T07 ADR-004 entry (self-estimated
  tokens, wrong model label "CommandCode") and replaced it with a reproducible deliverable-size
  measurement. Added `bench/ponytail/{off,on}/validate_fixtures.py` (two arms of the same spec)
  and `scripts/ponytail_measure.py` (the counter). Measured on `claude-opus-4-8[1m]`: total lines
  119→38 (**-68%**), chars -72%. Session tokens / wall-time left unreported (not self-measurable
  from inside the agent harness) with an external measurement protocol documented in the ADR.
  Decision unchanged: ponytail at `default`; session-token risk flagged UNVERIFIED.
- **Caveat B** (this commit): `tests/conftest.py` now installs a free-tier offline guard — patches
  `socket.getaddrinfo` + `socket.socket.connect/connect_ex` + `socket.create_connection` to block
  any non-loopback egress, plus a `pytest_runtest_call` wrapper that converts a guard-tripped OR
  no-credentials failure into a SKIP with a clear message. Genuine logic failures (guard not
  tripped, credentials present) still fail. Defaults `UPLIFT_MODE/GLADIA_MODE/LLM_MODE=fixture`.
- **Import-path decision** documented in PROGRESS.md live-decisions: the ported modules are
  harness/pytest-loaded only (`pipecat_stubs/` on `sys.path` via conftest + pytest.ini); a bare
  `python -c "import tools"` failing is acceptable because these transitional modules are exercised
  only by the CER harness until the Phase-3 LiveKit rewrite.

### What was tested and HOW
- `python scripts/ponytail_measure.py` → reproduces the ADR-004 table (119/38, -68%).
- Both validator arms run to OK / exit 0.
- `pytest tests/ -q -rs` → **7 skipped, 0 failed** in ~4.7s (was 5 failed). 2 tests report
  "offline guard blocked 1 connection attempt"; 3 report "no credentials configured". Zero outbound.
- `pytest tests/ --collect-only` → still 7 (gate0 P0-T08 check intact).
- `make gate0` → 16/16 PASS.

### Open decisions / known state
- **FULL `make gate` is RED for PRE-EXISTING reasons** unrelated to the Phase-0 gate (`make gate0`):
  (1) `make secrets` flags `.env.example` because the Makefile regex `^\.env` is too broad — a
  harness bug; (2) `make lint` has 47 ruff errors in the ported CER test files (P0-T08 code). Both
  predate this session and are OUT OF SCOPE of Caveats A/B. Flagged for human decision. gate0 is
  green; `make gate` is the Phase-1+ gate.
- **Phase 1 is BLOCKED** on human tasks **H1** (Supabase dev+prod projects + access token/ref) and
  **H6** (.env.local populated + gitignored). User confirmed H1–H6 = "None done yet".

### Traps discovered
- The ported CER tests reach live providers directly; only the conftest offline guard now stops
  egress. Do NOT remove it. When Phase 3 wires `services/tts_cache.py`, tests can move skip → pass.
- Windows asyncio uses the Proactor loop; patching `socket.getaddrinfo` (not just `connect`) is what
  makes the guard catch aiohttp/socketio egress there.

### Exact next action
Wait for the human. Do NOT start Phase 1 until they say "begin Phase 1" (they are setting up H1/H6).
When cleared: Phase 1 = `docs/21-PHASE-1-SUPABASE.md`; gate = `make gate` + `scripts/rls_check.py`;
human gate = they read every RLS policy by hand (41-HUMAN-TASKS.md).
