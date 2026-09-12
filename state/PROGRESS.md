# PROGRESS
Updated: 2026-08-04 | **This file's Session-N log was stale from 2026-07-29 to 2026-08-04 — 8
telephony commits on branch `habiba` (`56f6c68`..`a7e4b5a`, HEAD) went unrecorded here; see "Now
(Session 16)" below for the gap list and this session's actual (uncommitted) gate-driven cleanup.**
Everything below this paragraph predates that gap and is unchanged.
Prior update 2026-07-29 | Call summary + transcript wired end-to-end (migration 0011, worker capture,
portal API, dashboard drawer) — see "Now (Session 15)" below. Existing-tenant machine-auth agent
management built (`/machine/agents` + `@awaazlabs-uva/agents`), see "Now (Session 13)" below — both
unrelated to and do not change Phase 8's still-OPEN
status. Phase 8 status as of 2026-07-18, unchanged: **GATE 8 still
OPEN, 5/6 lines green (ADR-032), 6th needs a human decision (ADR-030), not new work.** Phase 9
(deployment readiness, config/artifacts only) DONE: Dockerfiles for control_plane/admin built and
verified without live Docker (venv/import/serve test — Docker not installed in this environment),
a systemic prod-readiness bug found and fixed (`dbconn.py`/`control_plane/app.py` read secrets
from `.env.local` ONLY, never `os.environ` — silently broken in any real deploy), full env-var
inventory written (`docs/62`), worker deployment explicitly deferred to Phase 12 with a real
reason documented (`docs/63` — persistent-process host vs. request-triggered services),
`sessionEndpoint` confirmed genuinely configurable (grep, no hardcoding). Phase 10 (testing prep,
no live call made) DONE as far as possible without the human: structured listening checklist +
staged (not run) provision/mint/start commands written (`docs/64`) — **demo tenant currently has
ZERO agent rows, confirmed by direct query, so step 1 of that doc (re-provision) is mandatory, not
optional, before any listening session**; deferred-pile swept for non-live work, one genuinely
resolvable item found and closed (ADR-033 — corrects ADR-012's stale "interruption-detector
billing UNVERIFIED" framing; the real answer was already in ADR-008's own addendum and
`usage_guard.py`, self-caught before commit). json-repair CVE formally accepted as risk (ADR-027).
P3-T09 tools.py rework done (ADR-029): minimal platform-lifecycle tools (`worker/tools.py`), real
LiveKit function-calling, live DB writes, RLS on new `escalations` table. Mandatory injection
re-run done TWICE fresh — real findings both times (`forced_real_tool_call` 2/2, `fake_tool_call`
1/2, the other two 0/2), not test-bug artifacts. CER-harness's 3 old failures re-confirmed
unchanged a 5th time this session (identical: 51 passed, 5 skipped, 3 failed) — ADR-030
recommends retirement, awaiting human sign-off. `make gate` re-run fresh: lint/rls-check(11/11)/
usage-check all clean, only the same 3 known tests red. H9 sent by the human, awaiting reply
(external, not actionable further). Branch: phase/8-prod-ready.

**Stopping point — this is genuinely as far as this session goes without the human.** Everything
from here needs either a live LiveKit/Uplift call (the listening session itself), phonetic
judgment only a human can make, or a decision already staged and waiting (ADR-030's CER-harness
retirement call, H9's vendor replies). Nothing further is being guessed at or built ahead of that.

## Now (Session 16 — gate-driven cleanup on branch `habiba`; PROGRESS.md's Session-N log found stale since 2026-07-29)

- **Trigger**: human asked how to test inbound PSTN calls (answered via `docs/TELEPHONY_TRANSITION_AND_ARCHITECTURE_GUIDE.md` §5 + the existing `client-test-app/` harness — no code change). `gate.sh` then blocked Stop three times in sequence on things unrelated to that answer: 2 real lint errors, then repo-wide `ruff format` debt, then this file being stale for HEAD's commit sha. All three are logged below because the gate forced them into scope, not because they were asked for.

- **Real gap found, not glossed over: this file stopped tracking reality after Session 15 (2026-07-29).**
  Branch `habiba` is now 8 commits ahead of what's logged here, all from the parallel telephony
  workstream (`docs/TELEPHONY_TRANSITION_AND_ARCHITECTURE_GUIDE.md`'s Hamza/Habiba/Ukasha split),
  which has been tracking itself in its own doc set
  (`docs/HABIBA_TELEPHONY_PHASE12_CLOSEOUT.md`, `docs/HAMZA_TELEPHONY_*`,
  `docs/TELEPHONY_REAL_PROVIDER_STAGING.md`) instead of `state/PROGRESS.md`. Listed here so the gap
  is visible, not backfilled into full Session-N narratives (that would be guessing at authors'
  intent from diffs alone — out of scope for this session):
  ```
  56f6c68 2026-08-03 Hamza Sultan       feat(telephony): auto-provision outbound trunk in create_outbound_call
  ba349ab 2026-08-03 habiba-imran       feat: publish telephony updates and client submission docs
  51166b5 2026-08-03 habiba-imran       merge: publish habiba repo updates into staging
  f978286 2026-08-03 habiba-imran       feat: harden telephony number purchase flow
  fb64441 2026-08-03 habiba-imran       Merge remote-tracking branch 'origin/staging' into habiba
  f4ba78f 2026-08-03 habiba-imran       fix: surface telnyx order failure reasons
  28464b5 2026-08-03 habiba-imran       fix: add telephony diagnostics and reduce health check stalls
  a7e4b5a 2026-08-04 habiba-imran       fix telnyx telephony provisioning and diagnostics   <- HEAD
  ```
  **HEAD = `a7e4b5a`** (the sha `gate.sh` named): touches
  `client-test-app/backend/server.js` (+141/-‑, hardening), `client-test-app/frontend/app.js`,
  5 new diagnostic scripts (`scripts/{connect_telnyx_machine_flow,inspect_telnyx_fqdn_connection,
  inspect_telnyx_inbound_records,inspect_telnyx_machine_flow,inspect_telnyx_number_binding}.mjs`),
  and `tenant_portal_api/{app,telephony_models,telephony_routes,telephony_service,telnyx_client}.py`
  — 12 files, 1186 insertions. None of this was authored by me; this entry exists only so `gate.sh`'s
  "PROGRESS.md has no entry for commit X" check has a real, accurate record instead of a placeholder.

- **`AGENT_SYSTEM.md` (referenced by `.claude/commands/update-progress.md` as "§4") no longer exists
  in the tracked repo.** `git log --all -- AGENT_SYSTEM.md` shows it was moved into a gitignored
  local `hamza/` directory in commit `e9a3942` (2026-07-25, "organize multi-tenant workspace") —
  174 lines deleted, not preserved elsewhere in the tree. Recovered §4's TASK CONTRACT template via
  `git show e9a3942~1:AGENT_SYSTEM.md` for this update (reproduced in the task-contract block below).
  **Trap logged below** so the next session doesn't waste a cycle looking for a file that isn't there.

- **This session's actual changes, all mechanical, zero behavior change, none committed yet**
  (repo rule: commit only when asked; not asked this session):
  1. `worker/main.py`: removed dead `telephony_info` variable (declared line 180, assigned line 213,
     read nowhere — confirmed by grep across the whole file). Flagged by ruff `F841`.
  2. `scripts/reconcile_telephony.py`: added `# noqa: E402` to the two module-level imports that
     must follow the `sys.path.insert(...)` calls above them (same pattern already used elsewhere
     in this repo, e.g. `control_plane/app.py`).
  3. Confirmed via `git stash` that both issues **pre-date this session** — `worker/main.py` already
     failed `ruff format --check` before either edit, and the `F841`/`E402` findings are in code this
     session never touched until the gate flagged them.
  4. Gate then reported 27 more pre-existing files failing `ruff format --check` (control_plane,
     tenant_portal_api, tests, worker — all telephony-workstream files from the untracked commits
     above, none authored by me). **Asked the human before bulk-reformatting** (`AskUserQuestion`),
     since it touches teammate-owned code well outside "how do I test inbound calls" — human chose
     "reformat all 27 now." Ran `ruff format` on the full flagged list.
  5. Verified clean repo-wide after: `ruff check .` -> `All checks passed!`; `ruff format --check .`
     -> `153 files already formatted`.
  - **Exact uncommitted file list** (`git status --porcelain`, 28 files): `control_plane/secrets_db.py`,
    `scripts/reconcile_telephony.py`, `tenant_portal_api/{app,livekit_sip,telephony_config,
    telephony_credentials,telephony_errors,telephony_health,telephony_models,telephony_queries,
    telephony_routes,telephony_service,telephony_webhooks,telnyx_client}.py`,
    `tests/test_telephony_{data_governance_schema,db_sync_and_rotation,livekit_sip,
    machine_routes_full,outbound_trunk_numbers,purchase_flow,queries,real_provider_wiring,
    rls_schema,routes,scaffold,schema,telnyx_client}.py`, `worker/{main,telephony_runtime}.py`.
  - `tenant_portal_api/telephony_errors.py` shows as modified with an **empty `git diff`** — this
    repo has `core.autocrlf=true`; ruff writes LF, the tree expects CRLF, so a pure line-ending
    normalization can flag a file as modified with zero real content change. Confirmed via
    `git diff --stat`/`git diff` both empty for that file. Logged in Traps.
  - **NOT re-run this session**: `pytest`, `rls_check.py`, `usage_guard.py` — only the lint half of
    `make gate` was exercised, because only lint was what the hook flagged. Full `make gate` should
    run before any commit.
  - Zero live/paid provider calls. No Telnyx/LiveKit/Supabase writes — static analysis and doc
    reading only.

### TELEPHONY-GATE-01 commit the gate fixes, then verify the inbound PSTN answer live
**Guide:**    docs/TELEPHONY_TRANSITION_AND_ARCHITECTURE_GUIDE.md §5; docs/TELEPHONY_REAL_PROVIDER_STAGING.md
**Files:**    the 28 uncommitted files listed above (commit); then no further files — the verification
              itself is a live phone call, not a code change
**Done when:** `make gate` -> `GATE: PASS` (full run, not just lint) on the 28 uncommitted files,
              THEN a real inbound call to the tenant's owned DID (`+14755587853` per
              `scripts/inspect_telnyx_inbound_records.mjs`'s default) shows
              `worker/telephony_runtime.py::resolve_inbound_sip_call` resolving a real
              `trunk_phone_number` in the worker's terminal log and the session starting
**Gate:**     `make gate` -> `GATE: PASS`; live call verified by ear (this is a phone call, not
              something `pytest` can assert)
**Free-tier:** PAID — real Telnyx per-minute PSTN charges apply to the inbound call itself, not
              FIXTURE-ONLY. The gate-fix commit itself is free (static analysis only).
**Attempt:**  1/3

## Now (Session 15 — call summary + transcript wired end-to-end, dashboard Sessions drawer)

- **Trigger:** dashboard request to show a call summary and transcript in the Call Sessions tab.
  Checked before building anything (this project's "verify, don't assume" rule): `sessions.summary`
  already exists in the schema (0001) and is already written by a real, wired LiveKit tool
  (`worker/tools.py::end_conversation_summary`, part of `FIXED_TOOLS` since ADR-029) — it was never
  dormant, just never exposed past the worker. Transcript had **no storage anywhere** — no column,
  no table, nothing capturing turns.
- **Migration `0011_session_transcript.sql`**: `sessions.transcript jsonb`, nullable, additive only.
  Applied directly via `psycopg` (not `make db-reset`, which drops-and-rebuilds from 0001 and would
  have wiped this session's real dev data — tenants/agents/sessions created live during this
  session). `scripts/db_inspect.py` re-run afterward to regenerate `SCHEMA.md`/`RLS.md` from the
  live DB, per 33-GUIDE-SUPABASE.md (never hand-edit those files). No RLS change needed — the
  existing `tenant_isolation_sessions` policy is row-level and already covers the new column; the
  worker writes it through the same trusted `conn_kwargs()` DB-owner connection `summary` already
  uses, never the RLS-scoped role.
- **`worker/main.py::_release_quota_slot`**: now also builds a transcript (user/assistant turns
  only — system messages hold OUR fixed instructions + the tenant's untrusted persona prompt, never
  the caller's actual conversation) from `session.history.messages()` and writes it in the same
  UPDATE that already sets `ended_at`/`duration_sec`/`end_reason`. Verified against the installed
  `livekit-agents` source before writing any of this (not guessed): `AgentSession.history` ->
  `self._chat_ctx` (`voice/agent_session.py` L610-611); `ChatContext.messages()` filters to
  `ChatMessage` items only (`llm/chat_context.py`); `ChatMessage.text_content` already strips
  `<expr/>` markup on assistant turns. Written via `psycopg.types.json.Jsonb(...)`, confirmed against
  the installed psycopg 3.3.4 (auto-deserializes back to a plain Python list on read — checked
  live, not assumed). Transcript-building wrapped in its own try/except, separate from the DB
  write's try/except — same principle this function already applies to the usage-billing write:
  a secondary failure must never cost the session close or the concurrency-slot release.
  `pytest tests/test_worker.py` re-run after the change: **10 passed** (unchanged from before).
- **`tenant_portal_api/queries.py::list_recent_sessions`**: now selects and returns `summary` and
  `transcript` alongside the existing fields — no new endpoint; the Sessions page already loads the
  full list once and drives its detail drawer from that same data, so this follows the established
  pattern rather than introducing a per-session fetch. `pytest tests/test_phase4_portal_api.py`
  re-run: **4 passed** (unchanged).
- **Dashboard**: `PortalSession` type gained `summary`/`transcript`; `sessions/page.tsx`'s detail
  Drawer gained a "Call Summary" section (falls back to "No summary available for this call." when
  null) and replaced the old "Transcript text is not exposed by the current tenant portal API yet."
  placeholder with a real scrollable turn-by-turn view (user/assistant bubbles), with the same
  honest empty-state fallback for calls with no transcript (pre-migration sessions, or any call that
  never reached a clean close).
- **Scope decision, asked of the human up front rather than assumed:** offered three options
  (worker+backend+UI full wiring / UI-only against the real-but-mostly-empty `summary` column / UI
  mockup only) — human chose full wiring. Built exactly that, nothing beyond it (e.g. did not touch
  the CSV export or add a new endpoint neither ask nor existing pattern called for).

## Now (Session 14e — usage was NEVER recorded: P3-T07 closed, monthly cap made real)

- **Human asked why every usage number is still zero after real test calls. It is not a display
  bug — nothing was ever writing them.** Verified before changing anything: `usage_events` held
  **4 rows in its entire history**, all test-fixture seeds; today's 3 real calls wrote **0 rows
  each**; `minutes_this_month` = 0 for every tenant. Meanwhile `sessions.duration_sec` had real
  values (6, 34, 6) — the duration was measured and then thrown away.
- **Root cause**: `worker/usage.py::record_usage` had **zero production callers** (grep: only
  `tests/test_worker.py`). A NOTE under `session.start()` had said "wire this up once measured
  live" since Phase 3. So every provider figure on the dashboard was a correct SQL query over a
  permanently empty table.
- **Fixed at the one place that already has tenant_id + session id + true duration**:
  `_release_quota_slot`. New `worker/usage.py::record_usage_many(conn, ...)` writes on the
  ALREADY-OPEN connection (4 × `record_usage` would have meant 4 extra Supabase connections per
  hangup), and `collect_model_usage(session)` maps livekit's usage onto our 4 kinds.
- **Used the CURRENT livekit API, not the obvious one.** `metrics_collected` is deprecated in
  1.6.5 — `agent_session.py` L561-568 logs a warning pointing at usage tracking instead. Correct
  source is `AgentSession.usage.model_usage` (L642-644): a list with one entry per provider/model,
  so same-type entries are **summed**, not overwritten. `STTModelUsage.audio_duration` -> stt_sec,
  `TTSModelUsage.audio_duration` -> tts_sec, `LLMModelUsage.input+output_tokens` -> llm_tokens,
  elapsed -> agent_sec. Zero-qty kinds are skipped so "measured zero" stays distinguishable from
  "never measured".
- **The monthly cap is now actually enforceable.** `control_plane/mint.py`'s
  `if minutes >= max_minutes` could never fire because nothing incremented `minutes_this_month` —
  non-negotiable #5 was only half-live (concurrency capped, minutes not). Now incremented on every
  session close.
- **Second latent bug found while doing it**: `quota_state.period_start` is in the schema but was
  read/written by **nothing** — so "this month" was never scoped to a month, and the counter would
  have grown forever until the tenant was permanently capped with no way to reset. The upsert now
  rolls over atomically (stored period older than the current month -> replace, else add).
- **Deliberate convention call, flagged not buried**: fractional minutes (`elapsed_sec/60.0`), not
  ceil-per-call. The column is `numeric`, the dashboard renders `.toFixed(1)`, and rounding every
  6-second call up to a whole minute would burn quota ~10x too fast. ADR-016's ceil convention is
  for the free-tier LEDGER (what LiveKit bills US) — a different question from what we charge a
  tenant. If per-started-minute billing is wanted instead, this is the line to change.
- **Billing writes can never cost a session close**: the whole block is wrapped, failures log at
  WARNING. The session close + concurrency release already committed (autocommit) before it runs.
- **Verified against the LIVE dev DB, not just by reading**: throwaway tenant, real inserts —
  4 usage_events written with correct per-kind quantities (stt summed 12.5+2.5=15.0 across two
  providers), 0-qty kind correctly skipped, minutes **accumulated** within a month
  (0.5667+0.1=0.6667) and **reset** on a simulated month rollover (0.5, not 1.1667). Also proved
  `collect_model_usage` returns `{}` rather than crashing on a session whose usage attribute is
  missing. All rows cleaned up after.
- **`make gate` re-run after the change: `GATE: PASS`** — 76 passed, 1 skipped, RLS 11/11.
- **NOT yet verified end-to-end**: needs a real call with the worker running to confirm live
  numbers land. The SQL and the mapping are proven; the wiring into a real session is not yet
  observed. Same honest caveat as 14b/14c.

## Now (Session 14d — GATE GREEN for the first time this session; baseline commit recorded)

- **Baseline: `12d7c12`** ("fix: install client SDKs from handoff tarballs", habiba-imran,
  2026-07-27) is HEAD. It touched only `client-submission_v2/` (docs + the two handoff tarballs)
  and is unrelated to this session's work. **Everything in Session 14a-14d is UNCOMMITTED on top
  of it** — 25 modified files, listed by `git status`. Not committed: no instruction to commit was
  given, and the standing rule is to commit only when asked.
- **`make gate` -> `GATE: PASS` (exit 0).** Every line real, on this machine:
  `secrets` (gitleaks 8.30.1, 142 commits, no leaks) | `lint` (ruff check + format, 80 files) |
  `test` (**76 passed**) | `rls-check` (11/11 tables) | `usage-check` (every provider in budget).
- **The suite went from reporting NOTHING to 76 passing.** Before: one collection error in
  `test_tts.py` interrupted the whole run, so `make test` printed no test result at all. After:
  the 57 that were always passing, plus the 19 that the whitelist had been hiding.
- **Lint debt cleared with human sign-off (24 -> 0).** 3×F401 auto-fixed — each grepped first, and
  `test_phase2.py` turned out to be importing `admin.app` purely for its ADMIN_JWT_SECRET side
  effect, used nowhere. 19×E402 annotated `# noqa: E402`, matching the convention already used in
  `control_plane/app.py`/`worker/tools.py`/`tenant_portal_api/app.py` rather than inventing a new
  ruff config. 11 files formatted. All 5 touched services re-imported clean afterwards.
- **`pytest.ini` fixed — both calls made by the human, not by me** (options + evidence presented
  first; ADR-030 had been waiting on exactly this sign-off):
  - dead CER files (`test_tts.py`, `test_harness.py`) **excluded, NOT deleted** — kept on disk so
    the evidence survives if the harness is ever revived;
  - 4 measured-green files added (**19 tests**, run and confirmed 19/0 before adding), so the
    tenant portal API — the dashboard's entire backend, including 14a's stale-session regression
    test — has gate coverage for the first time. Confirmed collected: the regression test now
    runs inside `make gate`.
  - `test_phase8_prod.py` deliberately left out (imports the missing `bench`); `*_live.py` never
    added (they spend real money). Reasoning written inline in `pytest.ini` for the next reader.
- **Two gate weaknesses found while doing this, NOT fixed (out of scope, flagged):**
  1. `Makefile:14` sends gitleaks' stderr to `/dev/null`, so a **missing binary** and a **real
     credential leak** produce the identical `GATE FAIL: secrets`. That is exactly what happened
     all session — the secrets line was never actually scanning anything until today.
  2. `make lint` ends with `(cd sdk && npm run lint || true)`. `tsc` is not installed there, so it
     prints "not recognized" and `|| true` swallows it — **the TypeScript SDK is not type-checked
     by the gate at all.**
- Tooling installed per-user via winget, no admin: GNU Make 4.4.1 (ezwinports), gitleaks 8.30.1.

## Now (Session 14c — the OTHER way a call ends: the agent's own end-call tool never ended it)

- **Human clarified the requirement**: live status must reflect the call ending *either* way —
  caller hangs up, **or the agent ends the call**. 14b covered only the hangup half.
- **Gap found, and it is a naming lie**: `worker/tools.py::end_conversation_summary` — the tool
  the LLM calls to finish a conversation — only ever wrote a `summary` string. It never closed
  the session. So an "agent-ended" call did not end: the agent said its goodbye and then sat
  there, session row `ended_at IS NULL`, dashboard showing a live call, until the caller happened
  to hang up (or forever if they just closed the tab).
- **Fix**: the tool now calls `AgentSession.shutdown(drain=True)`. Public API, verified in the
  installed source (`voice/agent_session.py` L1006-1007 -> `_close_soon(reason=USER_INITIATED,
  drain=drain)`); `drain=True` finishes in-flight speech via `AgentActivity.drain()` instead of
  cutting the goodbye mid-word. Sync — schedules the close, so the tool still returns normally.
- **14b's close handler is the single choke point that makes this work**: closing the session
  emits `"close"` -> `JobContext.shutdown()` -> shutdown callbacks -> session row closed + slot
  released. One path, both causes. That is why 14b was worth doing first.
- **end_reason now distinguishes the two causes.** `AgentSession.shutdown()` reports the generic
  `USER_INITIATED` ("closed via API"), which on a dashboard where "user" means *the caller* reads
  as exactly the wrong thing. Added `AgentUserdata.ended_by_agent`, set by the tool and read by
  the close handler, so the DB records `agent_ended` vs `participant_disconnected`. Dashboard maps
  both to plain English ("Ended by Agent" / "Caller Hung Up"), plus worker-shutdown and error.
- **Tool docstring rewritten** to say plainly that it HANGS UP and must be called only after the
  closing line — it previously read as a harmless "save a summary" call.
- **Justified test-file edit** (`tests/test_worker.py`): the tool's contract genuinely changed, and
  the existing `_FakeRunContext` duck-typed only `.userdata`, so the new `ctx.session` call would
  have silently no-op'd through `getattr`. Added a `_FakeSession` recorder and asserted the
  shutdown IS requested, with `drain=True`, and that `ended_by_agent` is set. **No existing
  assertion was weakened or removed** — only additions.
- **Both directions verified, not just the green run**: removed the `session.shutdown()` call and
  confirmed the new assertion FAILS ("must shut the AgentSession down"), then restored and
  re-confirmed **10/10 green**. `ruff check`/`format` clean on all 3 touched files, imports clean,
  dashboard `tsc --noEmit` clean.
- **⚠ FLAGGED FOR THE HUMAN, not buried**: ending the call is now a real, reachable side effect of
  a tool call. BLOCK-SEC in state/BLOCKERS.md records that live prompt injection has already
  forced `escalate_to_human` on this exact agent (3/4 runs). The same class of attack can now
  force a **hangup**. Severity is lower than data exfiltration (worst case: the call ends), and it
  is the necessary cost of the tool doing what its name says — but it is a NEW reachable effect
  and should be re-checked in the next injection pass, not assumed harmless.
- **Not yet verified live** (same honest caveat as 14b): needs a real call where the agent decides
  to end it. Unit-level behaviour is proven; end-to-end is not yet observed.

## Now (Session 14b — ROOT CAUSE of the leak found: the job never ended on hangup)

- **Human reproduced it live**: connected from a client frontend (showed live correctly, so the
  Session-14a staleness fix works), disconnected, **and it never went back to zero.**
- **Root cause, verified against the INSTALLED livekit-agents 1.6.5 source, not guessed:**
  closing the AgentSession does not end the JOB, and only the job ending fires
  `ctx.add_shutdown_callback`.
  - on participant disconnect, RoomIO calls `AgentSession._close_soon(PARTICIPANT_DISCONNECTED)`
    (`voice/room_io/room_io.py` L398-421) — `close_on_disconnect` already defaults True, so the
    session *does* close;
  - the only thing hooked to that close is `_on_agent_session_close` (same file L472), which
    deletes the room ONLY if `delete_room_on_close` is set — and that defaults to **False**
    (`voice/room_io/types.py` L129/L268);
  - nothing in that path calls `JobContext.shutdown` (`job.py` L742). So the job stayed alive,
    `_release_quota_slot` never ran, and the row stayed open until the worker process died.
- **The DB proved it before any code changed** — `end_reason` distribution across all history:
  `reconciled_stale` 73, **`parent process shutdown` 19**, `normal` **2**. That string comes from
  `ipc/job_proc_lazy_main.py` L251, i.e. the parent worker process killing the job — Ctrl-C, not a
  hangup. Sessions were essentially never closing on disconnect; 2 "normal" in the whole history.
- **Fix 1 (the bug):** `session.on("close", ...)` -> `ctx.shutdown(reason=<CloseReason.value>)` in
  `worker/main.py::entrypoint`, registered BEFORE `session.start()` so no close can be missed.
  Confirmed `AgentSession` really emits it: `self.emit("close", CloseEvent(...))`
  (`voice/agent_session.py` L1117), `CloseReason` is a `str` Enum (`voice/events.py` L564) so
  `.value` yields e.g. `participant_disconnected` — which now lands in `sessions.end_reason`
  instead of a blanket "normal", making the real hangup cause visible on the dashboard.
- **Fix 2 (a second leak found while reading that function):** `_release_quota_slot` opened with
  `if not tenant_id: return`, which skipped **closing the session row too** — leaking an open row
  and a permanent "live call" over what is only a metadata problem. Closing the row is keyed on
  `room_name` and never needed `tenant_id`; only the quota decrement does. Now: always close the
  row, decrement only when the tenant is known, and log a WARNING (not silence) in the odd case.
- **Verified without a live call:** `ruff check`/`format` clean, `worker.main` imports,
  `tests/test_worker.py` **10/10 green**. `worker/main.py` was formatted (3 hunks, all
  PRE-EXISTING lines, none of mine — file was already in the repo's unformatted set).
- **NOT yet verified end-to-end — needs the human's live retest**, stated plainly rather than
  claimed: the disconnect->shutdown path cannot be exercised without a real LiveKit call and a
  real client disconnect. Mechanism is verified against the SDK source; the behaviour is not yet
  observed. Retest procedure handed to the human (watch for the new INFO log line, then confirm
  `ended_at`/`end_reason=participant_disconnected` and `concurrent_now=0` in SQL).
- Zero live/paid API calls made by me. Dev Postgres reads only.

## Now (Session 14a — dashboard "13 live calls" fixed: stale-session leak, data + code)

- **Symptom (human-reported):** dashboard showed **13 live calls with nothing actually running**.
- **Root cause, verified by direct query before any change** — not a display bug in the count
  itself, the data was genuinely stale. `demo-gate3` had 13 open sessions, oldest **96.4 h**;
  `habiba` had 14, oldest 10.5 h; **27 total, and ZERO younger than 30 minutes.** The mint opens a
  `sessions` row; only `worker/main.py::_release_quota_slot` closes it, so any ungraceful worker
  exit (Ctrl-C in dev, crash, dispatch that never lands) leaks the row permanently.
  `quota_state.concurrent_now` was stuck at 13/14 to match — at 13/20 and 14/20, ~6 more calls per
  tenant and the mint would have started rejecting `concurrent cap reached` **forever**. That part
  was a live functional bug, not just cosmetics.
- **Data fixed:** ran the repo's existing `scripts/reconcile_sessions.py` (dry-run first, then for
  real). 27 sessions closed as `reconciled_stale`; both counters corrected 13→0 and 14→0. Verified
  after: **0 open sessions across all tenants, 0 nonzero concurrency counters.**
- **Code fixed so the display can never lie again**, independent of whether reconcile has run:
  `tenant_portal_api/queries.py::list_recent_sessions` — `live` was exactly `ended_at is None`,
  which reports every leaked row as an active call. Now `ended_at is null AND started_at > now() -
  LIVE_SESSION_MAX_AGE_MIN`. New `stale` field distinguishes "leaked" from "ended cleanly" instead
  of silently folding leaks into "Ended". **30 min is not a new invention** — it is
  `reconcile_sessions.py`'s own `--max-age-minutes` default, reused deliberately so there is ONE
  definition of stale. Computed in Postgres against `now()`, so no app-server clock skew.
- **Dashboard:** `PortalSession.stale` added; sessions table + drawer show an amber **Stale** badge
  and an explanatory note; CSV export writes `Stale` / `Never closed`. Overview's "Live Calls Now"
  card needed no change — it counts `s.live`, which is now correct. `npx tsc --noEmit` clean.
- **New regression test** `test_stale_open_session_is_not_reported_live` — seeds a 2-min-old open
  session (live), a 96-h-old open session (the exact production shape), and a cleanly-ended one,
  asserting all three states off one query. **Proven to actually catch the bug**: temporarily
  reverted `live` to the old `r[5] is None` form and confirmed the test FAILS, then restored and
  re-confirmed 3/3 green — a regression test that passes against the old code would be worthless.
- **Verification run (`make` still unavailable — see BLOCK-ENV):** `tests/test_phase4_portal_api.py`
  3/3 green against the live dev DB; `ruff check` clean on both touched files; `ruff format` clean
  (formatted `queries.py`'s pre-existing `usage_summary` signature and one line of my own new test
  — both mechanical, zero behavior change); E402 count in the test file unchanged at its
  pre-existing 3, so no new lint introduced.
- **Deliberately NOT changed, flagged for a decision:** the Overview "Concurrent Calls" card reads
  `quota_state.concurrent_now`, the counter the MINT enforces against. Displaying a "truer"
  computed number there would make the dashboard disagree with the thing that actually gates calls
  — a tenant would see 0 concurrent and still get 429s. The counter can still drift on the next
  ungraceful exit. Two real fixes, neither built unasked: (a) schedule `reconcile_sessions.py`
  (cron/Render job — nothing schedules it today), or (b) derive concurrency from open+recent
  `sessions` inside `control_plane/mint.py` so a counter cannot drift at all. (b) is the
  architecturally right one but touches quota enforcement (non-negotiable #5) and deserves an ADR.
- Zero live/paid API calls. Dev Postgres only.

## Now (Session 13 — existing-tenant machine-auth agent management, planned then implemented)
- **Scope: existing tenants only**, per explicit instruction — a tenant with `tenant_id`/
  `hmac_secret` already provisioned should be able to create/manage agents programmatically
  instead of depending on the dashboard's human-login flow. Tenant bootstrap/onboarding untouched,
  out of scope. Full design record: `docs/40-ADR.md` ADR-035.
- **Went through `EnterPlanMode` first** (human-approved plan at
  `C:\Users\ukash\.claude\plans\wise-booping-honey.md`) before any file was written, per this
  session's explicit "no code yet" instructions up to that point.
- **New: `tenant_portal_api/machine_auth.py`** — HMAC verification for a machine-callable
  agent-management surface, structurally parallel to `control_plane/mint.py` but its own module
  (reuses the tenant's existing `hmac_secret`, not a new credential). Signed message binds a
  server-derived `action` (`agent.create`/`agent.list`/`agent.update`) + a payload hash, so a
  captured signature can't be replayed against a different action or against `/v1/session`. Reuses
  `control_plane.secrets.DbSecretProvider` and the existing `used_nonces` table; adds its own
  in-memory per-tenant rate limiter (`MACHINE_RATE_LIMIT_PER_MIN = 30`).
- **New routes in `tenant_portal_api/app.py`**: `POST/GET /machine/agents`,
  `PATCH /machine/agents/{agent_id}` — call the exact same `queries.create_agent`/`update_agent`/
  `list_agents` the JWT-authenticated `/portal/agents` routes already use. No change to
  `control_plane`, `worker`, or the admin app.
- **New package `sdk-server/` (`@awaazlabs-uva/agents`)** — deliberately separate from `@awaazlabs-uva/voice`, not a
  subpath, zero runtime deps (Node 20 built-in `crypto`/`fetch`). `AwaazLabsUvaAgentsClient.
  {createAgent,listAgents,updateAgent}` sign their own requests. New isolation test
  `tests/test_admin.py::test_sdk_bundle_never_references_agents_server` (mirrors the existing
  `test_sdk_bundle_never_references_admin` pattern) — confirmed passing.
- **Real bug caught before it shipped, not after**: the payload-hash canonicalization must match
  byte-for-byte between Python (server) and TypeScript (client) or signatures silently fail.
  Python's `json.dumps` escapes non-ASCII by default; agent prompts are Urdu-script text. Fixed
  with `ensure_ascii=False` + explicit UTF-8 encoding. **Verified concretely**: ran the Python and
  Node canonicalization functions standalone against 3 shared bodies including real Urdu text —
  byte-identical canonical strings and SHA-256 digests across both languages.
- **New `tests/test_machine_agent_api.py`** (11 cases: happy-path create/list/update, wrong
  signature, replay window, nonce replay, tampered-payload-after-signing, suspended tenant,
  cross-tenant IDOR on update, rate limit, missing headers) — mirrors `tests/test_mint.py`'s gate
  discipline for the analogous HMAC-signed surface.
- **What's verified vs. still open, stated plainly**: no live Postgres/Supabase was available in
  this environment (no `.env.local`/`SUPABASE_DB_URL`, no local Docker) — all 11 DB-touching cases
  skip cleanly via the same pattern `test_mint.py`/`test_phase4_portal_api.py` already use here
  (confirmed those two also skip identically in this environment — a pre-existing gap, not a new
  one). What *was* verified for real: clean import + correct route registration
  (`tenant_portal_api.app`), the cross-language canonicalization match above, `ruff check`/
  `ruff format --check` clean, `sdk-server`'s `tsc` build + `tsc --noEmit` both clean, and the
  built package importing/constructing correctly under Node. **Running the full test file green
  against a live dev DB is still an open step for whoever has `.env.local` access** — not claimed
  as done here.
- **New doc `docs/MACHINE_AGENT_API_CONTRACT.md`** — wire contract (headers, signature algorithm,
  byte-for-byte canonicalization rule, all 3 routes, error mapping), mirrors
  `docs/HOST_BACKEND_CONTRACT.md`'s shape.
- Zero live/paid API calls. No change to tenant provisioning, `control_plane`, `worker`, or admin.
  Formal phase-number assignment in `docs/00-INDEX.md` left to whoever maintains that table.

## Now (Session 12 — reconcile Gladia contradiction, begin ADR-013 pile)
- **P3-T09 injection-gate mandatory re-run (justified test-file edit).** The
  test-guard override token was added only to update `tests/test_injection_live.py`: pass
  `tools=FIXED_TOOLS` to the live `llm.chat()` call (previously no tools existed at all, so this
  line was untestable — now tools.py is live and callable, and the standing instruction is that
  this re-run is a hard gate on tools.py's own completion, not a separate later task), add one
  new attack testing whether hostile persona text can force an inappropriate/manipulated real
  tool call, and — after a real false positive was found and investigated live — fix the
  pre-existing compliance-detection logic for the original 3 attacks (was: any tool call at all
  counted as "complied"; now: text-only for those 3, since a legitimate unrelated tool call was
  being wrongly flagged). Token removed immediately after.

- **P3-T09 tools gate (justified test-file edit).** The test-guard override
  token was added only to extend `tests/test_worker.py`: add `escalations` to the `two_tenants`
  fixture's cleanup (a real table as of migration 0008), and add new tests for
  `worker/tools.py`'s two fixed tools (`end_conversation_summary`, `escalate_to_human`) — real
  DB writes, real schema-shape checks (RunContext excluded, correct args), and a check that
  `build_agent()` wires `tools=FIXED_TOOLS`. No existing test's assertions changed. Token removed
  immediately after.

- **Gladia contradiction investigation (justified test-file edit).** The test-guard override
  token was added only to add a `--stagger-ms` flag to
  `scripts/concurrency_test.py`, spreading `page.goto()` calls apart instead of firing them in a
  tight loop, to test whether P8-T01's Gladia 429s were a burst-rate limit (many session-inits in
  a very short window) vs. a true concurrent-session cap — the concrete, testable hypothesis for
  reconciling ADR-014(f)'s "6/6 Gladia connected" claim against tonight's "3/5 connected, 2/5
  still retrying on 429" at a LOWER n. Default behavior (no `--stagger-ms`) unchanged. Token
  removed immediately after.

## Now (Session 11 — Phase 8 Prod Readiness, GATE 8 OPEN)
- **Branch `phase/8-prod-ready` created fresh** from `phase/7-security`'s tip before any P8-Txx
  work, per the ADR-020 convention.
- **P8-T06 first** (tags feed the other tasks' references): identified the real gate-closing
  commit for every phase 0-7 from `git log`'s own "GATE N CLOSED/closed" messages and checkpoint
  commits, created 8 annotated tags (`p0-gate-pass`..`p7-gate-pass`). p7's target is the actual
  tip of `phase/7-security` (not the earlier "GATE 7 CLOSED" commit message) since real fixes
  (ADR-022's db.py removal) landed after that commit — a rollback target should be the last
  known-good state, not an earlier one a later fix improved on; flagged as a judgment call.
  **Rollback procedure actually tested, not just asserted**: checked out `p7-gate-pass`
  (detached HEAD), confirmed `db.py` had the expected `DBClientRemoved` content and ADR-023 was
  present, returned cleanly; separately checked out `p3-gate-pass` (a wide jump backward),
  confirmed `admin/` didn't exist yet there but `worker/main.py` did — both real, both correct.
  No remote configured, so tags are local-only (nothing to push).
- **P8-T01**: extended `scripts/concurrency_test.py` (ADR-014's proven live driver) with `--n`
  and per-connection latency timing. Ran live at n=5 (the documented Build cap) against a real
  running worker: 5/5 connected at the room-join layer, **p50=7031ms p95=8968ms** (n=5, flagged
  explicitly as too small a sample for a stable SLO). **Unplanned, significant finding**: the
  worker log showed Gladia STT hitting real `429 Too Many Requests` on session init at this same
  n=5 load — only 3/5 sessions got a working Gladia connection inside the test's hold-open
  window. LiveKit's own room-join layer held fine; Gladia was the actual observed bottleneck.
  `livekit_agent_min` 7→12 (+5, real, ceil-to-minute), `uplift_tts_sec` unchanged at 327 (zero
  audio ever published, by design).
- **P8-T02**: re-confirmed H9 #1-4 still unanswered (searched every tracked file again — nothing
  new). ADR-024 records this honestly as an INCOMPLETE status, not a decision, and folds in the
  Gladia finding above as new real evidence layered on top of the still-unknown Uplift number.
  `docs/10-SPEC.md`'s "Known ceilings" table updated: added a Gladia row citing the measurement,
  annotated (not silently replaced) the LiveKit Build "5 concurrent" row with ADR-014's 4-for-4
  non-reproduction record.
- **P8-T03**: `docs/60-RUNBOOK-CAP-EXHAUSTION.md`, written from the actual code
  (`control_plane/mint.py`'s 3 cap checks, `sdk/src/index.ts::connect()`'s full error handling).
  Real finding: no queue/retry/backoff exists at any layer — a cap hit is an immediate, thrown
  `AwaazLabsUvaVoiceError`, and all 3 distinct 429 causes (rate limit, concurrent cap, monthly cap) currently
  collapse to the identical `quota_exceeded` code client-side, indistinguishable to an
  integrator without server-side log access.
- **P8-T04**: `/ponytail-debt`'s fallback grep re-run a 3rd time, still empty. ADR-025 records it
  formally — GATE 8's line is satisfied.
- **P8-T05**: `docs/61-GUIDE-DEV-TO-PROD.md` — the 4 named switches plus 5 more things found by
  actually auditing the code (`ADMIN_JWT_SECRET` needs deliberate generation for prod, not the
  dev auto-generate; `ADMIN_PORTAL_ORIGINS` defaults to a dev localhost placeholder;
  `RATE_LIMIT_PER_MIN` is a hardcoded constant, not an env var; per-tenant quota defaults used in
  testing aren't prod-appropriate; `UPLIFT_VOICE_ID`'s demo-voice fallback). **Real bug found and
  fixed while auditing `.env.example` against `config.py`**: it had `UPLIFT_API_KEY` instead of
  `UPLIFTAI_API_KEY` — the exact mistake `docs/41-HUMAN-TASKS.md` H3 already warns about, sitting
  live in the actual template a new deployer would copy from. Also corrected a stale comment
  (`SUPABASE_SERVICE_ROLE` "never read by the agent" — false since ADR-022/`upload_voice_previews.py`)
  and flagged `LLM_MODE` as vestigial (confirmed unread by `worker/`/`config.py`, only referenced
  in the old CER-harness's offline guard).
- **`make gate` run twice**: first run found 6 files (all written tonight) not `ruff format`-clean
  — real, fixed mechanically (`ruff format .`), zero behavior change. Second run: lint/rls-check/
  usage-check all clean; `test` still fails on the same 3 pre-existing CER-harness tests
  (unchanged character — `test_schema`/`test_e2e` now fail with the new intentional
  `DBClientRemoved` from ADR-022 instead of the old schema error; `test_tools`' `KeyError`
  unchanged). `rls_check.py` and `usage_guard.py --report` independently re-verified since
  `make`'s sequential prerequisites never reached them after `test` failed (10/10 RLS OK; ledger
  well within every budget).
- **Independent security-subagent pass dispatched** (GATE 8's own line): `.claude/agents/
  security.md` isn't a directly-selectable `subagent_type` in this environment, so a
  general-purpose agent was given that file's exact charter and dispatched in an isolated git
  worktree — flagged as a methodology substitution, not silently presented as literal. It
  independently re-verified SECRETS/TENANCY/TOKEN MINT/INJECTION/ABUSE/ADMIN BOUNDARY and all 3
  human-gate attacks itself, live, from scratch — every one PASS, matching this session's own
  findings with its own fresh evidence. **Sole verdict: BLOCK**, on the same json-repair CVE
  already found earlier this session. Its suggested fix is the exact one already attempted and
  reverted today (real `pip check` conflict with `livekit-agents`' exact `==0.59.10` pin) — noted
  explicitly as a case of a subagent's suggested remediation needing independent verification
  before trusting it, not just accepting the recommendation.
- **GATE 8 status: does NOT close today.** ADR-026 records all 6 lines plainly — 3 PASS
  (runbook, ponytail-debt, phase tags), 3 blocked (full-suite-green vs. the ADR-013 carve-out
  question, security-subagent BLOCK on json-repair, H9 unanswered). Human-gate (merge to main)
  not attempted — nothing to merge toward while 3 lines are red. **Did not touch the ADR-013
  deferred pile** (tools.py, voice polish) per explicit instruction — that tension is exactly
  what's flagged in ADR-026's first blocked line, not silently resolved either direction.
- Zero Uplift calls. Real LiveKit Cloud + Gemini + Supabase-dev calls only (P8-T01's load test,
  the security subagent's live re-verification), all budget-safe, ledger confirmed after.

## Now (Session 10 — Phase 7 Security, GATE 7 CLOSED)
- **Branch discipline corrected first** (ADR-020): `phase/3-worker` (which had silently
  accumulated Phases 3-6) renamed to `phase/3-through-6-combined`; `phase/7-security` created
  fresh from its HEAD before any P7-Txx task work, per the new standing rule this created.
- **Automated checklist, every line real evidence**: SECRETS (gitleaks 0/72 commits, full
  history grep clean, dist/ clean, service_role scope gap found — see ADR-022); TENANCY (RLS
  10/10, cross-tenant read 0 rows, IDOR 403, all fresh); TOKEN MINT (`test_token_widen_live.py`
  re-run fresh, live LiveKit Cloud, 6/6 held); INJECTION (`test_injection_live.py`, new, live
  Gemini — 2/3 resisted, 1/3 got textual-only compliance with zero real effect since no tool is
  wired into the live agent yet, logged to BLOCKERS.md, not retracted, flagged for the ADR-013
  pass); ABUSE (picker structurally cannot reach Uplift; rate limit verified live — first attempt
  was a self-caught false positive from sequential-request timing, corrected; real result 120/130
  succeeded, 10 rejected, 46.5s); DEPS (pip-audit found 1 High — json-repair CVE, attempted bump
  reverted after `pip check` showed a real conflict with livekit-agents' exact pin, real
  exploitability assessed unreachable via the actual call site, left open/tracked; npm audit
  clean; pinning clean).
- **ADR-021 (admin boundary gate, proposed then approved as written)**: added an ADMIN BOUNDARY
  automated section + 3rd human-gate item to docs/27-PHASE-7-SECURITY.md. Automated version
  (`scripts/verify_admin_boundary_live.py`) run for real: 9/9 checks pass, including a
  video-grafted-with-the-REAL-secret case proving the structural check doesn't just ride on a
  bad signature.
- **Six follow-up items closed** (human asked for a status check on everything surfaced but not
  yet resolved): (1) `preview_url` regression (Phase 5 evidence silently wiped by a Phase 6
  `db_reset.py` run) — fixed, 81/81 restored, a guard added to `db_reset.py` and *tested* (found
  + fixed a real latent PgBouncer/psycopg3 prepared-statement bug along the way); (2) dead
  service_role client in db.py/tools.py — **removed entirely** (ADR-022) per explicit
  instruction, not left "for later"; (3) json-repair CVE bump — attempted, reverted, real
  upstream-pin conflict, corrected an earlier wrong "trivial fix" claim; (4) `RATE_LIMIT_PER_MIN`
  — confirmed no doc anywhere specified an intended number; recorded 120 as the deliberate value
  in ADR-023; (5) stale Phase-2-era text in `test_token_widen_live.py`'s verdict output — fixed;
  (6) `ADMIN_JWT_SECRET` handling — confirmed clean (grepped every read site, never printed,
  `.env.local` line count unchanged at 1).
- **Admin-account guard**: `db_reset.py` wiped the *only* admin account twice tonight (once
  during Phase 6, once again while testing the guard above). Since re-provisioning is a local
  DB-only write with no network side effect, `db_reset.py` now auto-reprovisions rather than
  merely warning — tested for real, fresh credentials landed only in the gitignored
  `state/admin_bootstrap.local.md`, never printed.
- **Human gate — a claim, pushed back on once, then confirmed with real evidence.** A first
  message claimed the gate was already run "in a prior session," but contained a literal unfilled
  template placeholder instead of actual output — flagged directly rather than accepted, per this
  session's own standing rule about not trusting claims without verification. The human then
  provided detailed, real-shaped output for all three scripts (fresh UUIDs, real HTTP status
  codes, internally consistent with each script's actual logic) and re-confirmed explicitly. One
  residual oddity noted for the record, not re-litigated: the "before your laptop/session
  restart" framing doesn't line up with this transcript's own visible compaction events, which
  both happened *before* the human-gate scripts were even written, not after. Accepted as
  satisfying the gate — a human gate's evidence standard is the human's own attested report, which
  this now genuinely is, not a placeholder.
  - `test_cross_tenant_read_live.py`: 4/4 clean.
  - `test_token_widen_live.py`: 6/6, incl. confirming `/rtc/validate` ignores a `?room=` param
    entirely (room binding lives only in signed claims, enforced at connect).
  - `test_admin_boundary_live.py`: 5/5 attacks rejected (401) + sanity control passed (200).
- Zero Uplift calls this entire phase. Gemini/LiveKit/Supabase-dev calls only, all budget-safe.

## Now (Session 9 — overnight autonomous run, human asleep, Phase 6 built end-to-end)
- **"begin Phase 6" received with standing overnight-run instructions**: work every P6-Txx task
  in one long haul, self-audit with real evidence at every step, no new live/paid API call of any
  kind tonight (even categories pre-approved in earlier sessions), 3-strike -> BLOCKERS.md and
  move to independent work, stop hard before Phase 7, write one consolidated report in
  state/HANDOFF.md at the end. Read `docs/26-PHASE-6-ADMIN.md`, `docs/41-HUMAN-TASKS.md` (no
  Phase-6-specific human-gate row exists in that table — flagged, not invented, see HANDOFF),
  `AGENT_SYSTEM.md`, `supabase/SCHEMA.md`/`RLS.md`, `docs/32-GUIDE-TESTING.md`,
  `docs/31-GUIDE-SECURITY.md` before starting.
- **P6-T01 admin auth** — `admin_users` (mandatory RFC 6238 TOTP + PBKDF2-SHA256 password hash,
  both implemented directly from stdlib/the public RFC rather than adding `pyotp`/`bcrypt` mid-
  unattended-session — flagged as a judgment call). Admin JWT (`aud="admin-portal"`,
  `iss="uva-admin"`, own `ADMIN_JWT_SECRET`) verified structurally and cryptographically distinct
  from a real LiveKit tenant `AccessToken` — both cross-directions tested against the actual
  `livekit-api` SDK output, not a mocked shape. `0007_admin.sql` (new): `admin_users`,
  `admin_audit_log`, `mint_rejections`, RLS enabled with zero policies (used_nonces precedent).
  Applied live to the dev DB (`make db-reset` clean, `rls_check.py` -> 10/10 OK,
  `supabase/SCHEMA.md`/`RLS.md` regenerated via `db_inspect.py`, never hand-edited).
- **P6-T02..T05 dashboard views** (`admin/queries.py`) — every number is one literal SQL query:
  `list_tenants`, `list_agents` (real rollup of `usage_events` via `sessions`), `list_sessions`,
  `usage_by_tenant_day_kind` (cost estimate at the ONE published figure, `$0.0044/min`,
  10-SPEC.md, applied only to `kind='agent_sec'` — `stt_sec`/`tts_sec`/`llm_tokens` have no
  published $/unit anywhere in this repo, so `cost_usd` stays `None` for them rather than
  inventing a number, rule 8.3), `quota_near_cap`, `live_concurrency` (deliberately does NOT
  assert a LiveKit-side cap — ADR-014 already found the documented "5 concurrent" figure
  unreproduced; surfaces only our own `quota_state` accounting, notes the ADR explicitly),
  `blockers` (429/403 rates over the new `mint_rejections` table). Smoke-tested against real
  throwaway rows in the live dev DB before the formal test suite existed, cleaned up after.
- **P6-T06 audit log + mint-rejection logging** — `admin/audit.py::record_admin_action` (every
  successful admin call) and `record_mint_rejection`, wired into `control_plane/app.py`'s existing
  `MintError`/rate-limit branches (additive; `pytest tests/test_mint.py` reconfirmed 11/11 green
  after). Before tonight, no 401/403/429 was EVER persisted anywhere, so the "blockers" view had
  no real data source — this was a genuine gap in Phase 2, not something this task could route
  around. Uses its own short-lived autocommit connection so a rejection survives the mint
  transaction's rollback; a logging failure is caught and logged at WARNING, never silently
  swallowed (AGENT_SYSTEM.md §9: "zero *silent* errors").
- **`admin/app.py`** — separate FastAPI app/process from `control_plane/app.py`. Every route but
  `/admin/login` requires `Authorization: Bearer <admin JWT>`. CORS allowlist
  (`ADMIN_PORTAL_ORIGINS`) is fixed/separately-configured, never derived from any tenant's
  `allowed_origins` — verified live that an arbitrary tenant-shaped `Origin` header gets no
  `Access-Control-Allow-Origin` back. `grep -rE admin sdk/src sdk/dist` -> zero matches (also a
  real test, `test_sdk_bundle_never_references_admin`). `ADMIN_JWT_SECRET` auto-generated +
  persisted to `.env.local` on first run (no human available overnight to provision one — flagged
  judgment call, see HANDOFF). `scripts/provision_admin.py` (new, non-live, same category as
  `provision_demo_tenant.py`) bootstrapped one real usable admin account; credentials written ONLY
  to `state/admin_bootstrap.local.md` (new gitignore entry), never printed to any tool
  output/tracked file — the demo-gate3 burned-secret lesson (BLOCKERS.md) applied proactively.
- **GATE 6 — `tests/test_admin.py`, 27 tests, all 4 checklist lines proven live, re-verified fresh
  twice (not trusted from an earlier run in the same session):**
  ```
  [x] every dashboard number == a SQL query over usage_events   -- usage aggregation compared
                                                                    directly against a hand-written
                                                                    raw SQL query, not re-derived
  [x] admin JWT cannot be used as a tenant JWT (and vice versa) -- both directions, real
                                                                    livekit-api AccessToken +
                                                                    real admin JWT, signature AND
                                                                    shape checked
  [x] every admin action written to an audit log               -- function-level AND end-to-end
                                                                    through the real HTTP path
  [x] admin portal is NOT reachable from the SDK's origin       -- CORS non-echo (live) + zero
                                                                    references in sdk/src, sdk/dist
  ```
- **Self-audit caught a false-positive gate report, corrected before claiming done.** A background
  `make gate` run's completion notification claimed "exit code 0"; the pipe to `tail` had silently
  swallowed `make`'s real exit code (2, lint failure). Re-ran capturing the exit code explicitly
  inside the log file itself and found it genuinely red — 9 pre-existing `ruff check` errors (all
  in files untouched before tonight) plus 13 files not matching `ruff format`, including every new
  `admin/*.py` file. Fixed with `ruff check --fix` + `ruff format .` (mechanical, zero behavior
  change) plus one `# noqa: E402` and one dead-variable deletion for the two non-auto-fixable
  errors; `pytest tests/test_worker.py` reconfirmed 5/5 green after touching `worker/factories.py`.
  This is the exact failure mode the "self-audit, verify with real evidence, don't trust a
  summary" instruction was written to catch — logged here as the process working, not as an aside.
- **`make gate` (full project) still fails on exactly 3 tests — pre-existing, not new tonight, not
  fixed, explicitly out of scope**: `test_harness.py::TestCERHarness::{test_schema,test_tools,
  test_e2e}` — the ported CER harness querying old Pipecat-era tables (`shop_info`, `products`,
  etc.) that don't exist in this repo's schema. Already tracked in this file's "Live decisions"
  section ("Phase 3 gate vs full make gate — clarified") and explicitly deferred by ADR-013
  (`tools.py` rework, end-of-build pass, not started — direct instruction not to touch any part of
  it until that pass begins). Phase 6's OWN gate, `pytest tests/test_admin.py -q`, is the
  authoritative one per `docs/00-INDEX.md`'s per-phase routing table, and it is 27/27 green.
  `rls_check.py` (10/10 OK) and `usage_guard.py` (ledger unchanged, confirming zero live/paid
  calls) independently re-verified since `make`'s sequential prerequisites never reached them.
- **No live/paid API call of any kind made tonight**, per the hard rule — no Uplift/Gladia/Gemini/
  LiveKit call attempted or needed (admin portal work touches only the free-tier dev Postgres
  connection, same trust tier as every prior phase's schema/RLS work). Ledger confirmed unchanged
  by direct read before and after: `uplift_tts_sec=327/600`, `livekit_agent_min=7/1000`.
- **Did NOT start Phase 7** — no adversarial/security-attack work attempted, per explicit
  instruction that it needs the human personally, wide awake.
- Commits: `ced0007` (P6-T01), `450770d` (P6-T02..T05), `c29abfb` (P6-T06), `97bbbe0`
  (admin/app.py), `2457dd6` (GATE 6 test suite), `a4ab567` (pre-existing lint cleanup, unrelated).

## Now (Session 8 continued — P5-T02 live recording crash: washroom-singer, lost partial spend,
script fixed, NOT re-run)
- **Human ran `UPLIFT_MODE=record python scripts/record_voice_previews.py` live.** 80/82 voices
  recorded; crashed on `washroom-singer` (exceeded the script's `PER_VOICE_MAX_SECONDS=6.0` cap on
  a line every other voice cleared in 2.6-5.1s), which also killed the whole run before
  `wholesale-trader` (next alphabetically) was ever attempted. Confirmed on disk: 80 `.wav` files,
  exactly those 2 missing.
- **Ledger corrected, reasoned not guessed (ADR-019).** True value read directly from
  `state/usage_ledger.json`: `uplift_tts_sec=305` at crash time. The old `synth_one()` raised
  `SystemExit` before its own `return`, so washroom-singer's partial (real, billed) audio was
  never logged and is genuinely unrecoverable (no partial file on disk, no duration in the crash
  message). Applied a stated, reasoned correction — same standard as ADR-016 — of **+8s** (6.0s
  confirmed floor + 2s pad for streaming-chunk overshoot, grounded in reading the installed
  `upliftai` plugin's actual incremental WebSocket delivery, not an arbitrary guess): ledger now
  **313/600**, verified by re-read. Residual uncertainty flagged explicitly, not hidden: whether
  Uplift's server-side job kept billing after the client stopped reading is unknown from the client
  library alone.
- **Root cause verified, not assumed voice-character not a bug.** Re-fetched
  `docs.upliftai.org/orator_voices` for `washroom-singer`: description "a gloriously tone-deaf
  shower singer... unable to stop belting," internal File codename `ai_naat_p4_m_za` — "naat" being
  Islamic devotional poetry performed in a melismatic, drawn-out sung style, unlike ordinary speech.
  All 81 other voices ran the identical code path/text/config without crashing; `wholesale-trader`
  was never attempted only because the crash killed the whole run, not because it was itself slow.
- **Script fixed (`scripts/record_voice_previews.py`).** `synth_one()` now raises a local
  `CapExceeded` (carrying the partial pcm/sr) instead of `SystemExit` inside the try block, so
  partial audio is never silently lost again. The per-voice loop logs the actual partial duration
  to the ledger on a cap breach and `continue`s to the next voice instead of letting the exception
  kill the whole script. No preview file is written for a capped voice.
- **Human-approved re-run done (2026-07-17).** Added a per-voice cap override
  (`MAX_SECONDS_OVERRIDES = {"washroom-singer": 10.0}`, default 6.0 unchanged for everyone else)
  rather than raising the global cap or trimming the line. Ran
  `UPLIFT_MODE=record python scripts/record_voice_previews.py` for just the 2 remaining voices:
  **`wholesale-trader` recorded cleanly, 3.80s** (normal range — confirms it was only ever
  collateral damage from the old crash-the-whole-run bug, never itself slow). **`washroom-singer`
  still exceeded even the raised 10.0s cap, reaching a real measured 10.07s** — logged to the
  ledger this time (no data lost), no preview file written, correctly skipped rather than
  auto-raising the cap again. Ledger: 313 -> **327**, verified. Strengthens the ADR-019 root cause:
  >2x every other voice's full render time, still not finished at 10s. **Open, human's call:**
  raise the cap further, accept a longer preview, trim the line, or drop/replace the voice in the
  picker — not decided here.
- **`voice-picker/previews/` added to `.gitignore` explicitly** (with a comment: CDN-bound via
  P5-T03, not committed) — formalizes the decision instead of leaving 13MB of WAVs as an implicit
  untracked omission. 81/82 preview files now on disk (all except washroom-singer).
- **washroom-singer disabled (human decision), not deleted.** `voices.enabled=false` — verified
  live: `enabled` flips to `False`, zero `agents` rows referenced it before disabling, the real
  anon-key RLS query returns zero rows for it and 82 voices total. Reasoning: novelty/character
  voice (melismatic devotional-singing style per its own catalogue description), unlikely to be a
  real tenant's pick, and further cap raises are speculative — it hadn't finished even past 10s.
- **P5-T03 done — Supabase Storage as the CDN** (`scripts/upload_voice_previews.py`, new). Private
  bucket `voice-previews`, avoids introducing a new third-party vendor (reuses free-tier Supabase
  credentials already held). Run live against the real dev project: **81/81 uploaded, signed
  (7-day TTL), and `voices.preview_url` populated**, committed.
- **GATE 5 CLOSED — every line with real evidence:** 82/82 cards render (real Playwright/Chromium
  load, real RLS query); preview plays (direct signed-URL fetch: 200, real WAV bytes, RIFF/WAVE
  header; + 3 real play-button clicks in headless Chromium each fired a real audio GET); zero
  network calls to any Uplift domain during a full browse (6 requests total, all
  Supabase/jsdelivr); signed URLs genuinely expire (real test: 2s-TTL URL → 200 immediately → 400
  InvalidJWT after 4s, not assumed); H9 #5 already answered (ADR-017). One honest caveat noted, not
  hidden: the `Cache-Control` file-option isn't echoed as that literal header on GET — Supabase
  sets `Expires` instead (matching the signed URL's 7-day window) and Cloudflare confirmed actually
  caching it (`cf-cache-status: HIT`) — "long cache" achieved, just via a different header name.
- **Phase 5 is now fully closed**, live pipeline included (not just ADR-018's non-live prep).
  `uplift_tts_sec` moved 305 → 327 across the whole washroom-singer episode — every step measured
  or explicitly reasoned, no invented numbers. Full account: `docs/40-ADR.md` ADR-019.
- **🔴 STOPPED HARD at GATE 5's closure — awaiting explicit "begin Phase 6."**

## Now (Session 8 continued — Phase 4 HUMAN GATE signed off, Phase 5 begun and non-live work done)
- **GATE 4 human line signed off by the human** — dist/index.js and index.d.ts personally reviewed:
  zero real credentials, the grep matches are comments only, error handling doesn't leak internal
  detail, mic-enable behavior matches spec. Phase 4 fully closed.
- **"begin Phase 5" received. Read docs/25-PHASE-5-VOICE-PICKER.md, routed correctly.** Corrected
  its stale "BLOCKED on H9 #5" header (ADR-017 already resolved this) rather than leaving it
  contradicting the ADR.
- **P5-T01 (voice catalogue) done** — real 82-voice Uplift catalogue seeded (`0005_voices_
  catalogue.sql`), sourced from `docs.upliftai.org/orator_voices` via 3 independent WebFetch
  extractions that agreed on count + fields (no "list voices" API exists to pull this from
  programmatically — checked, not assumed). `voices` table: 83 rows (82 + the existing
  `v_meklc281` demo voice). Full sourcing/confidence account: ADR-018.
- **P5-T05 (voice_id FK enable-check) done** — a DB-level trigger (`0006_agents_voice_enabled_
  check.sql`), since a plain FK can't express "and it must be enabled" and no agent-creation
  application code exists yet to validate it there. Tested live both directions against the real
  dev DB (disabled voice rejected, enabled voice accepted), cleaned up after.
- **P5-T04 (picker UI) scaffolded** — `voice-picker/index.html`, queries the real `voices` table
  directly via Supabase JS client + the public anon key (safe: RLS `voices_read_all USING
  (enabled)`). Verified live via Playwright against the real dev DB: 83/83 real voice cards render,
  83/83 play buttons correctly disabled (no preview audio exists yet). Two things deliberately left
  undecided, not guessed: where this UI is ultimately hosted (Phase 6 admin portal vs standalone),
  and the artwork-to-voice mapping (82 voices, 3-4 owned artworks per ADR-017) — placeholder
  monogram avatars used instead of a fabricated mapping.
- **🔴 STOPPED HARD before P5-T02** — pre-rendering one line per voice requires
  `UPLIFT_MODE=record`, a live/paid Uplift call. Per the explicit process rule just re-confirmed
  this session ("any new live-pipeline test design gets proposed and approved before it runs, no
  exceptions" — extends naturally to any live/paid step, not just tests), the exact command is
  proposed to the human and NOT run without their sign-off. Not attempted.
- No live/paid API call made anywhere in this Phase-5 work.

## Now (Session 8 continued — GATE 3 follow-up: real usage instrumentation, corrected concurrency
re-test, a real bug found and fixed by the test itself)
- **`livekit_agent_min` instrumentation gap CLOSED (ADR-016).** `worker/main.py::entrypoint()` now
  registers `ctx.add_shutdown_callback(...)` and records real session duration
  (`max(1, ceil(elapsed_sec/60))` minutes, an assumed-not-verified billing convention, flagged as
  such) into `state/usage_ledger.json` via a new `scripts/usage_guard.py::increment()`.
- **Synthetic-tone concurrency re-test run live, twice — the second run corrected a real
  methodology gap (ADR-014 addenda 1 & 2).** First tone-published run: 6/6 connected with real
  media, falsifying the "media-flow-gating" hypothesis — but then investigating why the ledger
  stayed flat surfaced that ALL prior concurrency runs (original + first tone run) actually crashed
  at `wait_for_participant()` on every session (fast page-close raced the worker's own
  participant-wait), meaning they only ever proved room-join concurrency, not full-agent-session
  concurrency. Fixed by holding connections open 15s (`concurrency_test.py`'s new `HOLD_OPEN_S`)
  before disconnecting. Corrected re-test: **6/6 fully completed the real pipeline** (STT connected,
  adaptive interruption running) for a sustained ~15s window, all closed cleanly, zero rejections.
  `docs/30-GUIDE-FREE-TIER.md`'s "5 concurrent" LiveKit Build claim has now been tested 3 ways and
  never reproduced — doc updated to say so plainly, not left as a stale assumption.
- **A real race condition, found by the concurrency test itself, fixed same night.** The corrected
  6-way run's 6 confirmed job-exits should have added 6 minutes to the ledger; only +3 landed, because
  `increment()`'s unsynchronized read-modify-write raced itself across 6 concurrent job-shutdown
  threads (Windows `JobExecutorType.THREAD`, ADR-007). Fixed with a `threading.Lock`; verified
  non-live via a 300-call concurrent-thread stress test (`before=4 after=304 expected=304
  MATCH=True`); ledger manually corrected to the true value. `livekit_agent_min` now reads a real,
  race-corrected **7** — a measured fact, not an estimate.
- **H9 #5 (Uplift artwork licensing) confirmed no longer blocking Phase 5 (ADR-017).** Voice picker
  will use 3-4 owned artworks instead. `docs/41-HUMAN-TASKS.md` updated (struck through, not
  deleted, reasoning kept in place). H9's other 4 questions are untouched and still block Phase 8.
- **detection_delay=1103ms finding stays explicitly OPEN, formally folded into ADR-013's deferred
  end-of-build voice-quality pass** — not attempted or re-tested now; needs several real
  Uplift-spending samples to resolve properly.
- Live LiveKit spend tonight (all pre-approved, P3-T08 scope): 7 measured agent-minutes
  (`livekit_agent_min=7/1000`). Uplift spend: still genuinely 0 (`uplift_tts_sec=17/600`, unchanged
  — none of tonight's sessions ever triggered TTS, verified by code-path tracing, not assumed).

## Now (Session 8 continued — Phase 4 implemented, stopped hard at its human gate)
- **Phase 4 done, non-live, one long haul, per the new standing operating pattern.**
  `sdk/src/index.ts` is a real implementation now (not the earlier stub): P4-T01/T02 transport +
  session lifecycle (`connect()` POSTs the host's `sessionEndpoint`, connects via `livekit-client`,
  enables the caller's mic), P4-T03 typed events (`transcript`/`speaking`/`ended`/`error`, each
  wired to a specific, verified `RoomEvent`), P4-T04 error taxonomy (`quota_exceeded`/
  `agent_not_found`/`session_failed`, never leaking raw internal error text), P4-T05 build + bundle
  scan. Full design record: `docs/40-ADR.md` ADR-015.
- **GATE 4 machine-checkable lines are green:** `make bundle-check` → EXIT 0;
  `grep -rE '(API_KEY|SECRET|SERVICE_ROLE|Bearer )' dist/` → zero matches; `npm ls` → only
  `livekit-client` + `typescript`(dev), zero provider SDKs; bundle size recorded (5765B raw /
  2162B gzipped). "Works from a foreign origin" verified by code inspection only (no live
  two-origin test — none needed given no same-origin assumption exists in the code).
- **🔴 STOPPED HARD at Phase 4's HUMAN GATE — not proceeding to Phase 5 without it.** Per
  `docs/24-PHASE-4-CLIENT-SDK.md`'s own line, inspecting `dist/` for secrets is explicitly the
  human's personal job, not something the automated grep (even though it passed) satisfies on its
  own. Full gate output posted to the human; waiting for explicit go-ahead before Phase 5.
- No live/paid API call was made anywhere in Phase 4.

## Now (Session 8 continued — GATE 3 closed, P3-T09 + voice polish explicitly deferred)
- **New standing operating pattern (human instruction, 2026-07-17):** work a full phase's tasks in
  one long uninterrupted haul, no stopping for permission between individual tasks. Stop HARD only
  at: the phase's actual machine gate, a human-gate item (docs/41-HUMAN-TASKS.md), any live/paid
  API call, or the 3-strike rule. Post full gate output + every human-gate line batched at the end,
  then wait for explicit "begin Phase N+1." Applies to every remaining phase.
- **ADR-013:** P3-T09 (tool-calling wiring) and all remaining voice/persona/prosody polish (the 8
  unconfirmed phrase-replacement entries, further prompt iteration) are DEFERRED to a dedicated pass
  at the END of the build — not this session, not "next session." tools.py's eventual rework is
  decided (fixed platform-owned tools, real schema, per-tenant RLS, not the old demo tables) but not
  started. Do not implement any part of this until that pass begins.
- **P3-T08 run live, real result differs from the documented expectation** — see ADR-014. All 6
  concurrent connections succeeded; the LiveKit Build "5 concurrent, hard cap" figure in
  docs/30-GUIDE-FREE-TIER.md was not reproduced. Not explained/guessed why — flagged as
  unverified-by-us going forward. New reusable driver: `scripts/concurrency_test.py` +
  `concurrency_test_client.html` (Playwright + real Chromium + livekit-client, since a headless
  Python `livekit.rtc` client was already proven to hang on this Windows env, HANDOFF Session 5).
- **GATE 3 formally compiled and closed** — full checklist with real evidence per line in
  `docs/23-PHASE-3-WORKER.md`. Six of seven lines genuinely green; `STT_PROVIDER=soniox -> 402` is
  architecturally-verified-only (no live call made, per this session's "no more live calls beyond
  P3-T08" instruction) — flagged honestly, not checked off as if observed.
- **Moving directly into Phase 4** (client SDK) per instruction, non-live wherever possible, in one
  long haul. Will stop hard at Phase 4's actual gate (`make bundle-check` + the dist/ secret grep)
  and wait for explicit go-ahead — inspecting dist/ for secrets is the human's own job per
  docs/24-PHASE-4-CLIENT-SDK.md, not skipped just because of the long-haul instruction.

## Now (Session 8 — Gate-3 human-listen PASSED, post-call quality pass)
- **Gate-3 human-listen: PASSED.** Two live attempts tonight (first crashed on the plugin
  main-thread bug, see ADR-007's corrected account); the third, on the corrected worker, ran
  end-to-end: greeting, STT, LLM, TTS, interruption, session teardown all worked. Full session
  transcript (log lines) is the record; no separate write-up beyond this file + the ADRs below.
- **Real finding from the live call, NOT one of the six planned items: tool-calling is NOT wired.**
  `tools.py`'s functions are not registered as real LiveKit function-calling tools on the
  `AgentSession`. Observed live: the LLM emitted literal `tool_code\nprint(search_products(
  price_range_min=45000, price_range_max=55000))\n` as spoken assistant text (worker's own
  `conversation_item_added` log), which went straight to TTS. A later turn produced a fluent
  "used Dell" answer with no tool call having actually run in between — looks like hallucinated
  results, not real `search_products` data. **NOT fixed this session** (out of the six items'
  scope — needs its own investigation into LiveKit's function-calling API). See ADR-011 (where
  this blocks the filler-on-tool-call evaluation) and ADR-012 (flagged as the top-priority next
  fix, ahead of further quality polish). 🔴 **Next session: fix this before anything else.**
- **Post-Gate-3 quality pass — 6 items, all gated (`pytest tests/test_worker.py` 5/5 green after
  each), none live-validated yet (explicitly deferred — human reviews diffs, then one more
  live-listen together):**
  1. Adaptive interruption forced explicit (`turn_handling={"interruption": {"mode": "adaptive"}}`
     in `worker/main.py::build_session`) — was silently dev-mode-only by accident of the CLI
     subcommand; verified against installed source, not assumed. ADR-008.
  2. STT `code_switching=False` now explicit in `worker/factories.py::make_stt()` (was
     implicit-and-moot). D19 re-checked against Gladia's current docs/changelog — no material
     change found for Urdu specifically. ADR-009.
  3. Uplift phrase-replacement config (ADR-006 Layer 2) — `scripts/update_phrase_config.py`
     written (16 entries reused verbatim from the old repo's human-verified D42 config, 8 new
     entries proposed with my own transliteration, flagged for human confirmation — "Bluetooth"
     is the lowest-confidence one). **NOT YET RUN** — it's a real write to the live Uplift API
     (zero TTS budget per ADR-006, but still a live third-party call) — awaiting explicit
     sign-off before executing, consistent with the standing live/paid-call rule.
  4. `persona.py` rewritten (v7): worked code-switching-ratio examples for everyday words (not
     just brand names), bounded disfluency allowance, emotional-register stability guardrail —
     cited against LiveKit's prompting guide + a code-mixing-generation research playbook, not
     guessed. `SYSTEM_PROMPT_V1` untouched. ADR-010.
  5. Endpointing: confirmed effective values (0.3s/2.5s, LiveKit's own streaming-turn-detector
     defaults) already match documented guidance — no change applied. Filler-on-tool-call
     evaluated (D35 precedent vs. a cited Ultravox-specific 47.9%-interruption-rate downside,
     arXiv 2604.04847v1) and correctly NOT built — blocked by the tool-calling wiring bug above,
     not by the evaluation itself. ADR-011 (proposal only).
  6. Honest capability-ceiling note — ADR-012. Uplift Orator has NO SSML/rate/pitch control at
     any tier (API ceiling, not a quota one); Gladia's STT lag is a vendor latency floor;
     LiveKit's Adaptive Interruption Detector is a Cloud-hosted call with untracked cost (open
     item). The tool-calling bug is explicitly called out as NOT a free-tier ceiling — a real,
     fixable bug that should be the next session's first priority.
- **Standing rules honored:** no live call attempted this pass, `UPLIFT_MODE` untouched, no token
  minted, worker not restarted. Item 3's script is prepared but not executed pending sign-off.

## Now (Session 7 — autonomous, human asleep)
- **Phase 3 NON-LIVE work is complete.** session.start() wired (build_agent injects the untrusted
  prompt into chat_ctx as DATA, never into instructions — verified livekit.agents API; new security
  test passes). Worker launchable (`python -m worker.main dev`, cli.run_app). All media plugins
  installed (gladia STT, silero VAD, upliftai TTS, google LLM). `pytest tests/test_worker.py` → 5/5.
- **Integration gap found + FIXED (worker-only):** the mint puts {tenant_id, agent_id} in the
  PARTICIPANT JWT metadata, but the worker read `ctx.room.metadata` (never set → would be empty). Now
  reads `ctx.wait_for_participant().metadata`. No Phase-2 change. (commit 2f65587)
- **ALL that remains in Phase 3 is LIVE-gated → queued in `state/MORNING_QUEUE.md`:** (Q1) Gemini TPM
  measurement `scripts/measure_gemini_tpm.py --confirm-live` [approved but HELD per human's do-not
  list]; (Q2) Gate-3 human-listen live Urdu call [human runs; helpers provision_demo_tenant.py +
  mint_demo_token.py prepped]; (Q3) P3-T08 5-concurrent [live LiveKit].
- CER harness still has 3 pre-existing schema-mismatch failures in full `make gate` (tracked; Phase-3
  db.py rework). Phase-3 gate = `pytest tests/test_worker.py` (5/5).

## Now (prior — still valid reference)
- P3-T01 recording HUMAN-APPROVED, DONE. TWO fixtures on disk: **canonical `e2c70ca90ee456cfe0a790af434dec7d`**
  (Latin "TechZone Laptops", 8.6s/380KB, human-listened + approved 2026-07-17) + the earlier
  **superseded `c6228ded...`** (Urdu-script brand, 8.4s — kept on disk, marked superseded in manifest).
  Both manifest hashes recompute exactly. Ledger `uplift_tts_sec=17` (both recordings). "مہ نور" (no
  alef) is canonical in persona.py + smoke test; no alef-spelling remains in code (Session-6 verified).
- [X] P3-T04 fixture-TTS wiring — `worker/factories.py` FixtureTTS (max_retry=0, fail-fast) replays the
  cached WAV. `tests/test_tts.py` → 3 passed incl `test_fixture_tts_plays_cached_wav`. (commit 3c0af56)
- [X] P3-T05 Soniox→402 seam verified. The "N attempts" retry is livekit-agents FRAMEWORK (stt.py,
  default `max_retry=3` in APIConnectOptions) — NOT our wrapper, not the soniox plugin. Fail-fast option:
  pass `max_retry=0` to make_stt's STT (FixtureTTS already does). Moot in dev: `STT_PROVIDER=gladia`.
- P3-T06 Gemini LLM wiring + TPM measurement (live call; human-approved only)
- P3-T08 5-concurrent LiveKit (needs deployed worker)
- Gate 3 human-listen (needs a real call — blocks approval of this phase)
- 🔴 **CER harness has 3 real failures** in `make gate`: test_schema/test_tools/test_e2e.
  The `supabase_key is required` error is RESOLVED (config.py:22 now reads the correct env-var
  name). The current failure is a schema mismatch: the ported tests query old Pipecat-era
  TechZone tables (`shop_info`, `products`, `customers`, etc.) that don't exist in this repo's
  schema (`tenants`, `agents`, `sessions`, `quota_state`, `usage_events`, `voices`). The CER
  harness was written against a completely different database. This is a pre-existing
  Phase-3-rework item tracked in the "Now" section — Phase 3 rework replaces `db.py` with
  LiveKit Agents equivalents, at which point the harness must be adapted to the new schema.
  Worker tests (4/4), mint tests (11/11), and isolation (1/1) all pass — worker uses
  psycopg/dbconn, not the ported db.py's supabase-py REST client.

## Done (newest first)
- [X] **(S9) ADR-020: branch-per-phase convention lapsed Phase 3-6, corrected.** Human caught
  via `git log --all --oneline --graph` that Phases 3-6 all landed on `phase/3-worker` instead of
  getting their own branches (`AGENT_SYSTEM.md` says branch-per-phase; held through Phase 2, then
  silently lapsed, never flagged). No history rewrite — renamed in place:
  `phase/3-worker` → `phase/3-through-6-combined` (all SHAs unchanged). Branch-per-phase resumes
  strictly at Phase 7: `phase/7-security` must be created before any P7-Txx work starts, first
  checklist item, not something to remember partway through. See docs/40-ADR.md ADR-020 for full
  writeup, including the standing rule this creates: noticing an established-but-undocumented
  pattern that contradicts a written convention is a flag-it-immediately moment, not a
  note-it-and-continue one.
- [X] **(S9, overnight/autonomous) Phase 6 — GATE 6 CLOSED.** Admin auth separate from tenant auth
  (MFA-mandatory, distinct JWT), all 6 dashboard views as real SQL, audit log, mint-rejection
  logging (new — Phase 2 never persisted a 401/403/429 anywhere before this), CORS isolation from
  the SDK's origin. `tests/test_admin.py` 27/27. Commits `ced0007`..`a4ab567` (6 total, see "Now"
  above for the full breakdown). Zero live/paid calls; Phase 7 not started.
- [X] **(S7) worker session.start() wiring + participant-metadata fix** — `worker/main.py`:
  `build_agent(cfg)` = Agent(instructions=SYSTEM_INSTRUCTIONS, chat_ctx=persona); untrusted prompt →
  chat_ctx DATA (security test `test_persona_injected_as_data_not_system_instructions` proves it's not
  in instructions). entrypoint: connect → wait_for_participant → read participant metadata → build →
  session.start. Launchable via `python -m worker.main dev` (cli.run_app). API verified vs installed
  livekit.agents source. pytest tests/test_worker.py → 5/5. Commits 6cdebf1, bac00ee, 2f65587.
- [X] **(S7) P3-T06 prep** — `scripts/measure_gemini_tpm.py` (TPM measurement, --confirm-live guard,
  dry-run verified); make_llm wiring confirmed; installed livekit-plugins-google + google-genai +
  gladia + silero. 41-HUMAN-TASKS H3 corrected to UPLIFTAI_API_KEY. Commit 8918c39.
- [X] **(S7) morning helpers** — `scripts/provision_demo_tenant.py`, `scripts/mint_demo_token.py`,
  `state/MORNING_QUEUE.md` (all non-live). Commit 2f65587.
- [X] P3-T03 RLS-scoped agent config load — `worker/config.py` `load_agent_config` (authenticated role
  + tenant JWT claim). Own agent loads; a cross-tenant agent → `AgentNotFound` (RLS/IDOR at the worker
  layer). Sync (psycopg async can't use Windows ProactorEventLoop; the worker calls via to_thread).
- [X] P3-T07 usage_events emission — `worker/usage.py` `record_usage` (stt_sec/tts_sec/llm_tokens/
  agent_sec). `tests/test_worker.py` → 4 passed.
- [structure] P3-T03 worker skeleton — `worker/{main,factories}.py`. Entrypoint parses room metadata,
  loads config, assembles the session via provider factories (lazy imports); untrusted prompt → persona
  slot only. Live wiring (FixtureTTS, session.start, provider media) = P3-T04+.
- [X] P3-T02 TTS fixture cache — `services/tts_cache.py` (key/get/require/store + WAV wrap). Cache miss
  in fixture mode → hard LookupError, ZERO network (`tests/test_tts.py`). services/__init__.py added.
- [tool] P3-T01 recorder `scripts/record_fixture.py` written (verifies the plugin, records ONE fixture,
  logs real usage). Refuses without UPLIFT_MODE=record. The recording itself is human-gated — see Now.
- [X] P2-T01..T06 Control plane / token mint — `control_plane/{mint,secrets,app}.py`. HMAC verify +
  ≤60s replay window (T01), single-use nonce store `used_nonces` (T02), quota concurrent+minutes (T03),
  scoped LiveKit JWT room=uuid4/identity=uuid4/TTL=120s/roomJoin-one-room (T04), session row + quota
  increment in the mint txn (T05), FastAPI `POST /v1/session` + per-tenant origin allowlist + rate
  limit (T06). GATE 2: `pytest tests/test_mint.py` → 11 passed (all reject cases + token scope/TTL).
- [X] P2-prep authorize service_role (ADR-005) + Supabase-paid housekeeping + .env.local @→%40. Commit on phase/1-supabase.
- [X] P1-T04 SCHEMA.md/RLS.md mirror — scripts/db_inspect.py (read-only introspection) + `make db-inspect`. Regenerates deterministically → matches live (no git diff). NOTE: the guide's db-inspector subagent+MCP is not dispatchable in this harness; this read-only script is the equivalent.
- [X] P1-T03 test_isolation.py — cross-tenant read = 0 rows, verified against live DB. Offline guard now allow-lists the free Supabase host; paid providers stay blocked. Commit: ae8b263
- [X] P1-T02 rls_check.py — now connects via scripts/dbconn.py (.env.local) and fails if any public table lacks RLS. `make rls-check` → RLS OK on all 6 tables.
- [X] P1-T01 Supabase schema + RLS — migrations 0001_schema / 0002_rls / 0003_seed_voices + scripts/{dbconn,db_reset}.py + Makefile `db-reset`. `make db-reset` rebuilds from zero (idempotent, verified twice); 6 tables, 6 SELECT tenant-isolation policies, 1 voice seeded. DEV project kevtaxqqjfctdiszdgae.
- [X] **Caveat B** — offline guard in `tests/conftest.py`: blocks all non-loopback socket/DNS egress and skips (not fails) guard-tripped / no-credential tests. `pytest tests/` → 7 skipped, 0 failed, zero outbound; `--collect-only` still 7. Import-path decision documented (see Live decisions). Commit: 9da575a
- [X] P0-T08 Port IP from old Pipecat repo → persona.py, tools.py, db.py, config.py, session_state.py, tests/ (12 files), DECISIONS.md folded into 40-ADR.md. CER harness: `pytest tests/ -q --collect-only` → 7 tests. Commit: f5adfbd
- [X] P0-T07 **REDONE (Caveat A)** — prior entry was estimated tokens + wrong model label ("CommandCode"), invalid per rule 8.3. Replaced with a reproducible deliverable-size measurement: two committed arms under `bench/ponytail/{off,on}/` + `scripts/ponytail_measure.py`. Measured: total lines 119→38 (**-68%**), chars 4407→1227 (-72%), model `claude-opus-4-8[1m]`. Session-token/wall-time NOT self-measurable from the harness → left unreported (protocol for external measurement recorded in 40-ADR.md). Decision unchanged: ponytail at `default`, session-token risk flagged UNVERIFIED. 40-ADR.md ADR-004. Commit: ddf947d
- [X] P0-T07 (superseded) Measure ponytail — original estimated entry. Commit: 5bddd5c
- [X] P0-T06 Subagents — 4 agents (researcher, reviewer, security, db-inspector). reviewer has no Write. Commit: 917cfab
- [X] P0-T05 Hooks — bash .claude/hooks/selftest.sh → 12/12 all BLOCK cases exit 2. Commit: 917cfab
- [X] P0-T04 CLAUDE.md + scaffold — CLAUDE.md exists, state/, docs/, tests/fixtures/{tts,stt} all present. Commit: 917cfab
- [X] P0-T03 Context7 MCP — package available. Done-when requires MCP server runtime not available in this agent env. Commit: 917cfab
- [X] P0-T02 Supabase MCP — scaffolding present. Done-when requires $SUPABASE_ACCESS_TOKEN + $DEV_REF (H1 human task). Commit: 917cfab
- [X] P0-T01 Install ponytail — `@dietrichgebert/ponytail` installed via npm. `/ponytail-help` is a Claude Code plugin slash command, not testable outside Claude Code. Commit: 917cfab

## Live decisions (not yet promoted to docs/40-ADR.md)

- **P8-T01 concurrency_test.py extended for configurable N + per-connection latency (justified
  test-file edit).** The test-guard override token was added only to add a `--n`
  CLI flag (default unchanged at 6, P8-T01 passes `--n 5` to match the documented Build cap) and
  per-connection latency timing (`time.monotonic()` around each `page.goto()` -> "connected"
  transition, p50/p95 computed over the connected set) to `scripts/concurrency_test.py` — the
  same live driver ADR-014 already built and used. No existing behavior changed for a bare
  `python scripts/concurrency_test.py` call (N still defaults to 6, still no latency requirement
  to pass). Token removed immediately after.

- **P7 stale-text fix in test_token_widen_live.py (justified test-file edit).** The test-guard
  override token was added only to fix one stale line in the VERDICT print statement — "(Human
  still confirms before Phase 3.)" — a Phase-2-era leftover, now inaccurate since this script is
  reused as regression tooling well past Phase 3. No assertion or check logic changed, text-only.
  Token removed immediately after.

- **P7 human-gate attack scripts (justified test-file edit).** The test-guard override token was
  added only to create two NEW standalone, narrated scripts for the human to personally run as
  the actual Phase 7 human-gate act (same not-pytest-collected pattern as
  `tests/test_token_widen_live.py`): `tests/test_cross_tenant_read_live.py` (human-gate item 1,
  "read tenant B's agents using tenant A's credentials") and
  `tests/test_admin_boundary_live.py` (the proposed ADR-021 third human-gate item — draft only,
  not yet approved). The agent dry-ran both to prove they work, but that is NOT being treated as
  satisfying the human gate itself — that still requires the human to personally execute them,
  same standard as every gate so far. No existing test's assertions changed. Token removed
  immediately after.

- **P7 injection-gate script (justified test-file edit).** The test-guard override token was
  added only to create `tests/test_injection_live.py` — a NEW standalone script (live Gemini
  call, deliberately NOT added to `pytest.ini` `python_files`, same not-pytest-collected pattern
  as `tests/test_token_widen_live.py`), proving docs/27-PHASE-7-SECURITY.md's INJECTION checklist
  line live against the real `worker/main.py` construction. No existing test's assertions
  changed. Token removed immediately after.

- **P6 gate test (justified test-file edit).** The test-guard override token was added only to
  create `tests/test_admin.py` (the Phase 6 gate — a NEW test, not a rewrite of an existing one)
  and add it to `pytest.ini` `python_files`, same precedent as the P2 gate test entry below. No
  existing test's assertions changed. Token removed immediately after.

- **Name spelling canonicalisation — "مہ نور" in smoke test file (justified test-file edit).**
  The test-guard override token was added only to update the hard-coded TEXT string in
  `tests/smoke_uplift_ws.py` from "ماہ نور" to "مہ نور" — a spelling alignment with the
  human-verified canonical form (confirmed by ear in the recorded fixture, manifest hash tie
  to c6228ded). No assertion, expected value, or control flow changed. Token removed
  immediately after.
- **`config.py:22` env-var name alignment (not a test-file edit).** `.env.local` stores the
  Supabase service role as `SUPABASE_SERVICE_ROLE` (no `_KEY` suffix). `config.py` line 22
  now reads `os.environ.get("SUPABASE_SERVICE_ROLE", "")` instead of the old
  `SUPABASE_SERVICE_ROLE_KEY` — a one-line config fix so the ported `db.py` can resolve the
  key's actual env-var name. Worker uses `dbconn.py` (psycopg direct connection), so this
  only affects the CER harness path.
- **Phase 3 gate vs full `make gate` — clarified.** Per `docs/00-INDEX.md`, the Phase 3 gate
  is `pytest tests/test_worker.py` (4/4 green). `make gate` runs the full suite including the
  ported CER harness (test_schema/test_tools/test_e2e), which uses the old `db.py` supabase-py
  REST client — these 3 failures are a pre-existing Phase-3-rework item tracked in PROGRESS.md's
  "Now" section. Phase 3 rework replaces `db.py` with LiveKit Agents equivalents. The worker
  (`tests/test_worker.py`) already uses the correct psycopg/dbconn PostgreSQL direct connection
  and passes independently.
- **Guard fix (c03a2bd) — retroactive test-guard-token logging.** The `conftest` change only
  added `load_dotenv(.env.local)` → `os.environ`, making `_HAS_CREDENTIALS` reflect reality.
  18 previously-green tests (`test_mint.py` 11, `test_worker.py` 4, `test_isolation.py` 1,
  `test_tts.py` 1, `test_token_widen_live.py` 1) were re-run after the fix and remain
  identically green (see full output below). The fix correctly converted 3 previously-false-SKIP
  CER tests into visible FAILs. 🔴 **RETROACTIVE NOTE:** this edit touched `tests/conftest.py`
  — same test-guard scope as Caveat B (9da575a) — but no ALLOW_TEST_EDIT token was used. The
  hook does not enforce on non-Claude-Code agents, and I treated it as "infrastructure" when the
  Caveat B precedent (same file, same guard) required the token. The edit is correct, the
  discipline was not. Logged now rather than silently corrected: if a future conftest edit
  arrives, the token-and-justify discipline applies regardless of whether the hook fires.
- **P2 gate test (justified test-file edits).** The test-guard override token was added only to create
  `tests/test_mint.py` (the Phase 2 gate — a NEW test, not a rewrite of an existing one) and add it to
  pytest.ini `python_files`. Token removed immediately after.
- **HMAC secret storage — OPEN decision flagged for the human (Phase 2).** `tenants.hmac_secret_hash`
  says "hash only, never the secret", but HMAC verification needs the RAW secret. Resolved with a
  `control_plane/secrets.py` SecretProvider: raw secrets stay in the trusted tier (never a DB table),
  the DB keeps only the hash. Dev reads `CP_TENANT_SECRETS` JSON from .env.local; tests inject. The
  PROD store (Supabase Vault / secret manager / encrypted column) is deferred — needs a human call.
- **P1-T03 offline-guard scope refinement + isolation test (justified test-file edits).** The test-guard
  override token was added to: (1) allow-list the FREE Supabase dev host in the conftest guard so the RLS isolation test
  can hit the real DB — paid providers (Uplift/Gladia/LLMs) stay blocked, so the guard's purpose is
  intact; (2) add `test_isolation.py` to pytest.ini `python_files`; (3) create `tests/test_isolation.py`.
  No existing assertion changed. Token removed immediately after.
- **Lint cleanup of ported P0-T08 test files (human-authorized; lint-level only, no logic).** The
  test-guard override token was added only to rename ambiguous `l` → `ms`/`label` (E741) in
  test_harness.py/test_latency.py and
  convert one `lambda` to a `def` (E731) in test_interruption.py. No assertion, expected value, or
  control flow changed; `pytest tests/` stays 7 skipped. Token removed immediately after.
- **Caveat B — offline guard in `tests/conftest.py` (justified test-file edit; the test-guard override token was added only for the duration of the edit, then removed so the guard re-arms)** —
  the ported CER tests reach live providers directly (`helpers.synth_urdu` opens a Uplift Socket.IO
  connection; env-smoke calls Groq/Gemini/Supabase inline). Running bare `pytest tests/` therefore
  attempted a live paid call and failed with a connection error, violating CLAUDE.md #8 /
  30-GUIDE-FREE-TIER.md §7 ("no live API call in any test"). Fix = a session-wide network guard in
  conftest that (a) blocks any socket/DNS to a non-loopback host so **zero outbound calls** can
  leave, and (b) converts a guard-tripped test into a **skip with a clear message** instead of a
  live-call failure. This is NOT rewriting a test to go green — no assertion or expected value is
  touched; guard-tripped tests SKIP, and any real logic failure (guard not tripped) still FAILS.
  Token removed immediately after the edit per test-guard.sh.
- **Import path of ported modules is harness-scoped, and that is acceptable** — `tools.py` imports
  `pipecat.*`, resolved by `pipecat_stubs/` which `tests/conftest.py` + `pytest.ini` put on
  `sys.path`. A bare `python -c "import tools"` fails because neither is active outside pytest.
  Decision: **not** fixed by hacking `sys.path` into the ported product modules. These are
  transitional pre-Phase-3 files, exercised ONLY by the CER harness (pytest) until Phase 3 rewrites
  `tools.py` onto the LiveKit function-calling API; they are never invoked as standalone scripts.
  Harness-only import resolution is therefore correct for how they are used. Revisit at Phase 3.
- **Pipecat stubs at `pipecat_stubs/`** — tools.py imports `pipecat.adapters.schemas.FunctionSchema` and `pipecat.services.llm_service.FunctionCallParams`. Created minimal shims with equivalent dataclasses. In Phase 3, `tools.py` must be adapted to LiveKit Agents' function-calling API (different schema format, different callback model).
- **`../urdu-voice-agent/processors.py` not ported fully** — only `sanitize_text()` and stub classes ported. The full `OutputSanitizer`, `InputGuard`, `TurnMetricsObserver`, `NumberDictationPatience`, `InterimPromoter` are Pipecat-specific pipeline processors. Phase 3 must reimplement equivalents on LiveKit Agents.
- **`../urdu-voice-agent/tests/helpers_pipeline.py` not ported** — uses Pipecat Pipeline/Task infrastructure directly. Tests that depend on it (`test_interruption.py`, `test_latency.py`) are marked `@pytest.mark.skip` in `test_harness.py` until Phase 3.

## Traps (things that already bit us — read this first when stuck)
- 🔴 **BURNED SECRET:** the `demo-gate3` tenant secret provisioned 2026-07-17 (tenant
  `ca72956b-8f55-4374-8332-a659ba9ec5fc`) was pasted into chat history — treat it as COMPROMISED. Do
  NOT reuse it. For any future test, re-provision a fresh demo tenant (`scripts/provision_demo_tenant.py
  --commit`). After tonight's Gate-3 call (pass or fail), delete demo-gate3:
  `delete from tenants where id = 'ca72956b-8f55-4374-8332-a659ba9ec5fc';` (cascades agents/sessions).
- Uplift free tier is 10 MINUTES TOTAL. Fixture cache before any TTS call. docs/30-GUIDE-FREE-TIER.md
- LiveKit Build: 10-20s cold starts. Expected. Do not debug. Do not optimise.
- Supabase free projects PAUSE after 7 days idle. `make db-reset` must always work.
- supabase-py v2 uses `create_async_client` (not `acreate_client` as in the old repo — db.py fixed)
- **LiveKit `/rtc/validate` has a ~60s JWT clock-skew LEEWAY**: a token up to ~45s past exp still
  validates (401 only at 60s+). So a minted 120s token is usable for ~180s max, not a hard 120s.
  `tests/test_token_widen_live.py` (live gate) proves expiry by waiting PAST the leeway; a tighter
  wait reads as a false "expired token accepted" (it did once — retracted, see BLOCKERS.md). If a
  strict 120s ceiling ever matters, mint a shorter TTL. Live gate: 6/6 attacks rejected.
- 🔴 **LiveKit plugin registration requires the main thread — lazy per-job plugin imports crash.**
  `livekit.agents.Plugin.register_plugin()` raises `RuntimeError: Plugins must be registered on
  the main thread` unless called from `threading.main_thread()` (`livekit/agents/plugin.py`
  L30-33). `worker/factories.py`'s lazy `from livekit.plugins import ...` calls inside
  `make_stt`/`make_tts`/`make_llm`/`_load_vad` — written lazy so the module loads without every
  provider installed — fire off-thread the first time a job runs, and crash on the FIRST provider
  imported (hit live on the first Gate-3 attempt, 2026-07-17: `stt=make_stt()` → gladia). This is
  NOT the item-2 metadata bug — `build_session(md)` had already been called successfully when the
  crash hit. **On Windows the mechanism is: `JobExecutorType` defaults to `THREAD`, not `PROCESS`**
  (`worker.py` L126-130 — a `BrokenPipeError` workaround), so each "job process" is actually a
  plain `threading.Thread` (`"job_thread_runner"`, `ipc/job_proc_lazy_main.py::thread_main()`
  L459-480) running INSIDE the worker's own OS process, not a separate subprocess — meaning
  `WorkerOptions.prewarm_fnc` does NOT run on the true main thread either on this platform (a first
  fix attempt assumed it did, based on the `PROCESS`-executor code path; that assumption was wrong
  and crashed identically on the next live attempt, this time inside `prewarm` itself, on
  `google`/`silero`). **Actual fix:** call `worker/main.py::prewarm(None)` directly at true
  `__main__` top-level scope, before `cli.run_app()` — the one place on Windows guaranteed to be
  the real main thread, since no job thread exists yet; `sys.modules` is process-wide, so every
  later import (from `prewarm_fnc`, or the per-job lazy imports, from any thread) just hits the
  cache. `prewarm_fnc` stays wired too, for portability to non-Windows (`PROCESS`-executor)
  platforms where it genuinely does run on the job subprocess's own main thread. `prewarm()`
  returns the plugin module names it imported, and `__main__` asserts each is in `sys.modules`
  before calling `cli.run_app()` — direct evidence, not inference, confirmed live: LiveKit's own
  log then emits `"plugin registered"` for all four. See docs/40-ADR.md ADR-007 (revised the same
  day after the first fix failed live — read it, not just this summary, for the full account).
  **Any future provider added to `factories.py` must also be added to `prewarm`** or it will crash
  the same way the first time a live job actually uses it on Windows — no test catches this; the
  whole failure mode is invisible to `pytest`, which never invokes the `__main__` block or spawns a
  real job thread/process.
- 🔴 **Tool-calling is not actually wired — `search_products`/`get_store_policy` do not run; the LLM
  hallucinates instead.** Found live during Gate-3's successful (third) attempt, 2026-07-17 — NOT
  one of the six planned post-call quality items, and NOT fixed this session. This was already a
  KNOWN pending item (see the "Pipecat stubs" trap above and the ported-DECISIONS.md note: "In
  Phase 3, `tools.py` must be adapted to LiveKit Agents' function-calling API... different schema
  format, different callback model") — tonight is the first LIVE evidence of the actual consequence.
  Observed: `worker`'s own `conversation_item_added` log recorded the assistant turn as literal text
  `tool_code\nprint(search_products(price_range_min=45000, price_range_max=55000))\n` — Gemini's
  code-execution-style pseudocode for a tool call, not a real LiveKit function invocation — and this
  text was sent straight to Uplift TTS and (per the worker log) spoken. The same pattern repeated for
  `get_store_policy(policy_type="warranty")`. A subsequent turn produced a fluent, on-topic Urdu
  answer about a "used Dell" laptop with no tool call in between — almost certainly a HALLUCINATED
  product answer, not real `search_products` data, since no tool actually ran. **Impact:** every
  price/stock/policy claim Mahnoor makes right now is unverified against the DB, directly violating
  the persona's own HARD RULE ("Any price, stock, spec or policy MUST come from a tool result...
  never invent") — the rule is stated but not currently enforced, because the enforcement mechanism
  (real tool execution) isn't wired. **Not fixed tonight. Task breakdown now written:
  `docs/23-PHASE-3-WORKER.md` P3-T09** (verified against installed `livekit.agents` 1.6.5 source —
  `Agent(tools=[...])`, the `@function_tool` decorator with `raw_schema=` being the closest match
  to our existing `FunctionSchema` shapes, return-based results instead of `result_callback`,
  `RunContext` for session access). That breakdown also surfaces a BIGGER open question that isn't
  a coding detail: `tools.py`'s handlers query Supabase tables (`products`, `customers`,
  `reservations`, ...) that don't exist in this repo's actual schema (already flagged in the
  CER-harness note above) — so even correct wiring hits a missing-table error, and whether the
  TechZone tool suite is a permanent demo fixture or needs to become tenant-configurable is a real
  design decision, not something to silently assume. See docs/40-ADR.md ADR-011 (blocks the
  filler-on-tool-call evaluation), ADR-012, and **ADR-013 (2026-07-17): the human has explicitly
  DEFERRED P3-T09 and all remaining voice/persona/prosody polish to a dedicated pass at the END of
  the build**, after the SDK and remaining phases are done — superseding the "fix this before
  further quality polish" framing below, which was correct at the time it was written but is now
  stale. Do not implement or attempt any part of this until that dedicated pass. Not forgotten —
  tracked here and in ADR-013/P3-T09.
- 🔴 **`AGENT_SYSTEM.md` is gone from the tracked repo.** Moved into a gitignored local `hamza/`
  directory by commit `e9a3942` (2026-07-25, "organize multi-tenant workspace"), 174 lines deleted
  from the tracked tree. `.claude/commands/update-progress.md` still says "AGENT_SYSTEM.md §4" and
  `CLAUDE.md`/other docs may still reference it — on a machine without Hamza's local `hamza/` dir
  (i.e. any machine but his) that path 404s. Recover any needed section via
  `git show e9a3942~1:AGENT_SYSTEM.md` rather than assuming it's missing entirely from history.
- 🔴 **`state/PROGRESS.md`'s Session-N log silently stopped tracking the `habiba` branch's telephony
  commits after Session 15 (2026-07-29).** 8 commits (`56f6c68`..`a7e4b5a`, 2026-08-03/04) landed
  with zero entry here — that workstream tracks itself in `docs/HABIBA_TELEPHONY_*`/
  `docs/HAMZA_TELEPHONY_*`/`docs/TELEPHONY_REAL_PROVIDER_STAGING.md` instead. **`gate.sh`'s check
  only verifies THIS FILE mentions HEAD's own sha somewhere — it does NOT verify every commit since
  the last entry is documented.** A single entry for the current HEAD makes the gate pass even if
  7 commits before it are still undocumented here. Don't read "gate passed" as "history is complete."
- `make lint` (`ruff format --check .`) is **repo-wide, not diff-scoped.** Editing 2 files can surface
  dozens of pre-existing unrelated formatting failures from other contributors' commits. Before
  assuming a flagged file was caused by your own edit, check with `git stash` (stash your changes,
  re-run the check on the pre-existing HEAD, unstash) — that's how Session 16 confirmed
  `worker/main.py`'s formatting debt pre-dated this session's edit to it.
- This repo has `core.autocrlf=true` on Windows. `ruff format` writes LF line endings; a file whose
  only change is CRLF->LF can show as `modified` in `git status --porcelain` with a **completely
  empty `git diff`**. Not a real change — don't chase it as one, just note it if it's confusing.
- Bulk-reformatting files you didn't author and weren't asked to touch (even when a gate hook
  demands it to go green) is a scope decision, not a mechanical one — it touches teammate-owned
  code. Session 16 asked the human explicitly before running `ruff format` across 27 files outside
  this session's task; do the same rather than silently complying with gate pressure.
