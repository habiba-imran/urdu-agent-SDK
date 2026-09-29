# Wave 2 High — F-H18 + F-H10 Implementation Plan

**Owner (Habiba):** worker close path (F-H18), Urdu redundancy / failover (F-H10)  
**Shared (Ehsan):** schedule `scripts/reconcile_sessions.py` **and** `scripts/reconcile_telephony.py` (F-H18 shared exit)  
**Out of scope here:** Medium/Low (F-M24, F-M25, F-M15, F-L6, …); F-C4/F-C7 Habiba code (already landed — full ✅ still needs Ehsan A.3/A.4/purge cron; see `docs/WAVE2-FC4-FC7-STATUS-HANDOFF.md` if present, else `WAVE2-P0-FC4-FC7-IMPLEMENTATION-PLAN.md`)

**Sources:** `docs/UVA-PRIORITY-LIST.md` (F-H10, F-H18), `docs/AwaazLabs UVA Audit.md` §9 / Gate 5–6, codebase read 2026-09-18  
**Industry anchors (researched):** LiveKit Agents job/shutdown + Cloud drain; Vapi call-ended reasons / voice+transcriber `fallbackPlan`; Retell reliability + TTS/LLM/STT failover

**Status:** Implementation-ready. Design decisions below are locked unless product re-opens them.

**Phase A artifact:** `docs/WAVE2-HIGH-PHASE-A-BASELINE-AND-CONTRACTS.md` · **Ehsan handoff:** `docs/WAVE2-EHSAN-HANDOFF.md`  
**Phase A status (Habiba):** Done in docs — A.1/A.2 snapshots line-backed; A.3 cron contract drafted for Ehsan. **No runtime behaviour change.** Exit A still needs Ehsan schedule ack.  
**Phase B status (Habiba):** Done in code — `worker/session_close.py` + `tests/test_session_close.py`; `main.py` `_release_quota_slot` delegates. Crash safety still needs Phase C + Ehsan cron.  
**Phase C status (Habiba):** Done — runbook `docs/WAVE2-SESSION-RECONCILE.md` + `tests/test_reconcile_sessions.py`. **C.3 schedule remains Ehsan** (F-H18 full ✅ blocked on that).  
**Phase D status (Habiba):** Done — inventory + `worker/provider_retries.py`. Product signed **“A — No #2 yet”** (2026-09-18).  
**Phase E status (Habiba):** **Skipped** (no approved #2). Residual documented; no fallback code / no Ehsan schema.  
**Phase F status (Habiba):** Done — `docs/WAVE2-HIGH-PHASE-F-CLOSEOUT.md`; priority list honest (no false full ✅); regression **74 passed**; new tests whitelisted in `pytest.ini`.

---

## 0. Current behaviour (code reality today)

### F-H18 — Billing / quota only on clean shutdown

| Area | Current behaviour | Gap |
|---|---|---|
| **Close path** | `worker/main.py` registers LiveKit `ctx.add_shutdown_callback(_release_quota_slot)` (+ usage minutes + recording persist). Session `close` → `ctx.shutdown(reason=…)` so callbacks run on **clean** job end. | Process crash / OOM / hard kill / FFI abort → callbacks never run. |
| **What `_release_quota_slot` does** | `UPDATE sessions` (`ended_at`, `duration_sec`, `end_reason`, `transcript`) → decrement `quota_state.concurrent_now` → `record_usage_many` + minutes bump → retention helper. | Entire body wrapped in `except Exception: logger.warning` — failures are easy to miss; no retry; no durable “close attempted” signal outside this process. |
| **Idempotency** | SQL uses `where ended_at is null` (good). Quota decrement is not paired with a “already released” flag beyond “session was open”. | Double-close on callback + reconcile is mostly safe for session row; quota can still drift if decrement skipped or double-run races exist. |
| **Safety net** | `scripts/reconcile_sessions.py` closes open sessions older than N minutes (`end_reason='reconciled_stale'`) and resets `concurrent_now` to true open count. `scripts/reconcile_telephony.py` repairs stale telephony calls / quota leaks. | **Neither is scheduled** (audit + priority list). README even mislabels dry-run as migrations (F-L1, Ehsan). |
| **Related** | `worker/stale_jobs.py` rejects orphan **jobs** before connect — does **not** close DB sessions after a mid-call worker death. | Different problem (dispatch orphans vs in-call crash). |

**Industry (workers / agents):**

- **LiveKit:** Each job is an isolated process; shutdown hooks must finish quickly (default ~10s); Cloud uses graceful **drain** on deploy (`drain_timeout`). If the process dies hard, hooks do not run — LiveKit may re-dispatch a **new** session with no memory; post-call DB work for the dead job is **not guaranteed**.
- **Vapi:** Explicit end reasons for `worker-died` / `worker-shutdown`; infrastructure faults are treated as transient; calls still need durable billing/state repair outside the dead worker.
- **Lesson for UVA:** Worker must make the clean path hard to fail silently; **scheduled reconcile is mandatory** for crash/OOM. Do not pretend LiveKit re-dispatch replaces reconcile.

### F-H10 — Urdu zero redundancy / no failover

| Area | Current behaviour | Gap |
|---|---|---|
| **Capabilities** | `worker/providers/capabilities.py`: `ur` = **one** STT (Gladia), **one** LLM (Gemini), **one** TTS (Uplift). | Any vendor outage = 100% Urdu offline. |
| **Registry** | `worker/providers/registry.py`: unknown provider → `UnsupportedProviderError`. Comment: **no silent provider fallback** (ADR-036). | Correct for “don’t swap English Cartesia in for Urdu Uplift by accident”; wrong if it also forbids an **explicit** ordered fallback plan. |
| **Retries** | Uplift adapter sets `APIConnectOptions(max_retry=0)`. Groq (en) also uses `max_retries=0`. | Transient 429/503 become hard call failures. |
| **Remaps** | Gemini remaps retired model IDs; telephony may force Groq for **en**. Groq is **structurally excluded** from `ur` LLM. | Model remap ≠ provider failover. |
| **English** | Multiple STT/LLM/TTS already listed for `en`. | Redundancy exists for EN product path; Urdu does not. |

**Industry (failover):**

- **Retell:** Platform reliability docs — automatic LLM retries/fallback; TTS fallback voices from **different** providers; STT auto-failover (e.g. Deepgram ↔ Azure) even mid-call.
- **Vapi:** Explicit `voice.fallbackPlan.voices` and `transcriber.fallbackPlan` (manual ordered list + optional auto). Without a plan, primary voice failure can end the call.
- **Lesson for UVA:** Prefer **explicit ordered fallback plans** (config/platform defaults), **different providers**, language-safe only. Mid-call hot-swap is a stretch; session-start failover + retries are the P0 for F-H10. **Do not** invent a second Urdu TTS/STT that we have not proven in this repo.

---

## 1. End-state definition of done

### F-H18 done when (all true)

1. Clean shutdown still closes session, releases quota, writes usage (existing happy path preserved).  
2. Worker close path is **idempotent** and fails **loudly** (ERROR + metric/log field) when DB close/quota/usage fails — not only `warning` swallowed.  
3. Partial failure isolation: transcript build failure must not skip session close + quota release.  
4. Unit/integration tests cover: second close no-ops; quota not double-decremented incorrectly; reconcile closes stale open sessions and repairs `concurrent_now`.  
5. **Shared exit:** Ehsan has scheduled **both** `reconcile_sessions.py` and `reconcile_telephony.py` (or accepted interim: documented manual cadence + ticket with owner+date). Habiba does **not** mark F-H18 ✅ until this is true.  
6. Runbook: how to dry-run / apply both scripts; what `reconciled_stale` means for billing.

### F-H10 done when (all true)

1. Written inventory of **language-safe** secondary options for `ur` (STT/LLM/TTS) based on capabilities + provider docs + what adapters already exist — no hallucinated vendors.  
2. Transient retries enabled for Urdu critical adapters where LiveKit/plugin options allow (at least TTS/LLM connect path) — documented env caps.  
3. **Explicit** fallback policy for Urdu (platform default and/or agent fields) for layers that have a proven second provider; layers with **no** proven second stay documented residual + monitoring, not fake ✅.  
4. Failover is **observable** (log: primary → fallback reason) — never silent (addresses F-M15 direction without full honesty API).  
5. Unit tests: capabilities/fallback resolver; registry still rejects unknown providers; fallback only when chain configured.  
6. Manual: one Urdu call with primary forced-fail (env/mock) → fallback or controlled degrade; one normal Urdu call unchanged.

### Explicit residuals

- Mid-call STT hot-swap like Retell (stretch; not required to mark F-H10 Habiba P0).  
- Uplift concurrency ceiling still UNVERIFIED (RQ-001) — capacity sheet stays parked.  
- F-C4/F-C7 full Critical ✅ remains on the **other** plan’s shared exits.

---

## 2. Design decisions (locked)

| ID | Choice | Why |
|---|---|---|
| D1 F-H18 split | Habiba = resilient close + tests + runbook; Ehsan = cron/workflow on **both** existing scripts | Matches priority-list ownership; audit fix text names schedule. |
| D2 No second billing system | Reuse `reconcile_sessions` / `reconcile_telephony`; do not invent a new table unless close-path needs a tiny `close_attempts` log | Scripts already encode the repair semantics. |
| D3 Close isolation | Close session + quota first; transcript/usage/recording best-effort after | Crash recovery cares most about slot leak + open rows. |
| D4 F-H10 no silent swap | Fallback only via explicit chain / platform Urdu defaults; registry still raises on unknown | Preserves ADR-036; matches Vapi/Retell “configured plan” model. |
| D5 Language-safe only | Do not fall Urdu TTS → English-only Cartesia without product sign-off; LLM: do not enable Groq for `ur` without product sign-off (today structurally forbidden) | Product is Urdu; wrong-language “failover” is worse than a failed call. |
| D6 Retries before cross-provider | Raise carefully bounded retries for transient errors first | Cheap; Retell/Vapi both retry. |
| D7 Phase order | **F-H18 before F-H10** | Gate 5 operable/billing before Gate 6 commercial redundancy. |
| D8 Criticals | This plan does **not** re-open F-C4/F-C7 implementation | Already Habiba-done; mark ✅ when shared exits land. |

---

## 3. Phased plan

Legend: **[Code]** agent/tests · **[Manual]** Habiba/ops · **[Ehsan]** shared

---

### Phase A — Baseline & contracts (no behaviour change)

**Goal:** Freeze today’s close path + Urdu provider map; agree Ehsan cron contract.

#### A.1 Snapshot F-H18 call graph
Document (in this doc §0 + short appendix under `docs/` if needed):  
`session.close` → `ctx.shutdown` → `_release_quota_slot` / usage / recording; what survives kill -9.

#### A.2 Snapshot F-H10 matrix
Table: language × layer × providers × `max_retry` × known Urdu support (cite capabilities + adapter files).

#### A.3 Ehsan cron contract (hand-off)
Exact commands for staging/prod:

```text
python scripts/reconcile_sessions.py --max-age-minutes 30
python scripts/reconcile_telephony.py --apply   # after dry-run
```

Suggested cadence: every 5–15 minutes. Habiba does not own Render cron UI.

**Verify A**
- [Code] §0 matches `main.py` / reconcile scripts / `capabilities.py` (line-backed).  
- [Manual] Confirm whether any cron already exists (ask Ehsan/ops) — **do not assume**.  
- [Ehsan] Written ack of cron ownership for both scripts.

**Exit A:** Snapshots + cron contract agreed. No production behaviour change.

---

### Phase B — F-H18 worker close hardening

**Goal:** Clean path hard to skip; partial failures don’t leave slots forever when process still alive.

**Status (2026-09-18 Habiba):** **Done.** Module `worker/session_close.py`; shutdown callback in `worker/main.py` calls `release_session_quota_slot`. Tests: `tests/test_session_close.py` (9).

#### B.1 Extract close helper
Move session-close / quota / usage into a testable module (e.g. `worker/session_close.py`) called from `_release_quota_slot`. Keep LiveKit wiring in `main.py`.

#### B.2 Failure isolation order
1. Mark session ended (if still open)  
2. Decrement quota if session was open  
3. Then transcript / usage / retention / recording (already separate callback)

#### B.3 Logging
DB/quota failures → **ERROR** with `room_name`, `tenant_id`, stage. Success stays INFO.

#### B.4 Idempotency tests
Second close: no second usage double-count; quota stays consistent with open-session count.

**Verify B**
- [x] [Code] Unit tests for close helper (mock conn).  
- [x] [Code] Happy-path still updates `ended_at` + `concurrent_now`.  
- [ ] [Manual] Optional: one local call hang-up → session closed, quota decremented.

**Exit B:** Worker clean-close is resilient and tested. Crash still needs Phase C/D reconcile.

---

### Phase C — F-H18 reconcile as the crash safety net (Habiba docs + tests; Ehsan schedule)

**Goal:** Unscheduled scripts become a real Gate 5 control.

**Status (2026-09-18 Habiba):** **C.1 + C.2 done.** C.3 open for Ehsan (`WAVE2-EHSAN-HANDOFF.md` §1).

#### C.1 Habiba: runbook
Short runbook (new `docs/WAVE2-SESSION-RECONCILE.md` or section here): dry-run vs apply; max-age meaning; telephony `--apply`; what operators should see after a kill.

#### C.2 Habiba: tests
Extend/add tests that `reconcile_sessions` closes stale opens and fixes `concurrent_now` (pattern already used elsewhere in telephony tests if present).

#### C.3 Ehsan: schedule both
Wire cron/GitHub Action/Render job for **both** scripts. Interim acceptable only with owner+date+manual cadence written.

**Verify C**
- [x] [Code] Reconcile unit/integration green (`tests/test_reconcile_sessions.py`).  
- [ ] [Manual] Dry-run both scripts against staging DB; paste counts. (**Deferred** — no Render deploy yet.)  
- [ ] [Ehsan] Cron live **or** interim ticket filed.  
- [ ] [Manual] Simulate: leave a fake open session older than max-age → reconcile closes it. (**Deferred** / `simulate_worker_crash.py` when DB available.)

**Exit C:** F-H18 shared safety net real. Mark F-H18 Habiba+shared ✅ only when C.3 done.

---

### Phase D — F-H10 inventory + transient retries (no fake providers)

**Goal:** Truthful redundancy map + stop dying on first 429.

**Status (2026-09-18 Habiba):** **D.1 inventory + D.2/D.3 retries landed.** Product signed **“No #2 yet”** → Phase E skipped.

#### D.1 Inventory (code + docs, human sign-off where unknown)
For each layer, answer with evidence:

| Layer | Primary (`ur`) | Candidate #2 in **this** repo? | Urdu-safe? |
|---|---|---|---|
| STT | Gladia | Deepgram / Soniox adapters exist — **Urdu quality UNVERIFIED** | Stop for human listening if enabling |
| LLM | Gemini | Groq exists but **forbidden for `ur` today** | Needs product decision to allow |
| TTS | Uplift | Other TTS adapters are EN-oriented in capabilities | Needs product + voice mapping |

Artifact: `docs/WAVE2-FH10-PHASE-D-INVENTORY.md`

#### D.2 Bounded retries
Where plugins allow: enable small `max_retry` / timeout for Urdu Uplift + Gemini (env-tunable). Document defaults in `.env.example`.

Implemented via session connect options (`worker/provider_retries.py`): `UVA_PROVIDER_MAX_RETRY` default **2**.

#### D.3 Observability
Log retry attempts; do not swallow.

Logs configured `provider_retries max_retry=…` at option build; LiveKit performs connect retries.

**Verify D**
- [x] [Code] Inventory table in plan/runbook matches `capabilities.py`.  
- [x] [Manual] Product sign-off on any cross-provider Urdu candidate (or explicit “no #2 yet”).  
  → **2026-09-18: “A — No #2 yet”** (see inventory sign-off).  
- [x] [Code] Unit: retry options applied for named adapters (`tests/test_provider_retries.py`).  
- [ ] [Manual] Optional: force 503 once → retry then succeed/fail visibly in logs.

**Exit D:** Retries live; fallback chain only proceeds where D.1 approved.

---

### Phase E — F-H10 explicit fallback (only where approved)

**Goal:** Vapi/Retell-style **configured** failover for approved layers.

**Status (2026-09-18 Habiba):** **Skipped by product decision A (“No #2 yet”).**  
Artifact: `docs/WAVE2-FH10-PHASE-E-RESIDUAL.md`.  
No fallback chain code, no `capabilities.py` `ur` expansion, no Ehsan migration. Residual: vendor outage on Gladia/Gemini/Uplift still takes that layer offline after bounded retries exhaust. Re-open only with a named #2 approval.

#### E.1 Platform default chain for `ur`
e.g. config structure (names illustrative — implement against real AgentConfig/DB fields Habiba owns, or env/platform JSON if schema frozen for Ehsan):

```text
fallback: { stt: [...], llm: [...], tts: [...] }  # ordered, different providers
```

If schema needs Ehsan migration → Habiba drafts contract (like A.3 for FC4); do not invent columns in prod without sign-off.

#### E.2 Resolver
At session build: try primary `build_components`; on **provider construct / first-connect** failure, try next in chain; log `primary=… fallback=… reason=…`.

#### E.3 Mid-call failover
**Stretch / defer:** LiveKit pipeline swap mid-call is hard; document as Phase E.3 optional after E.1–E.2.

**Verify E**
- [x] [Docs] Product chose no #2 → E.1–E.2 **not implemented** (correct; ADR-036 / D4–D5).  
- [ ] [Code] Resolver unit tests — **N/A** until a #2 is approved.  
- [ ] [Manual] Urdu call with primary disabled → secondary — **N/A**.  
- [x] [Residual] Documented in `docs/WAVE2-FH10-PHASE-D-INVENTORY.md` + this status block.

**Exit E (this Wave 2 pass):** Satisfied as **residual close** — layers without approved #2 have no fake failover. Full cross-provider F-H10 remains open until a future #2 approval + real Phase E.

---

### Phase F — Close High tickets (proof)

#### F.1 Mark priority list
- F-H18 ✅ only if Phase B + C.3 true.  
- F-H10 ✅ only if Phase D + E (for approved layers) true; list residuals.  

**Status (2026-09-18 Habiba):** Catalog updated honestly in `docs/UVA-PRIORITY-LIST.md` — **neither** F-H18 nor F-H10 marked full ✅. Evidence: `docs/WAVE2-HIGH-PHASE-F-CLOSEOUT.md`.

#### F.2 Regression
EN path unchanged; FC4/FC7 gates still pass (`test_write_tool_gate`, recording policy suite).

**Status:** Regression suite **74 passed** (includes High + FC4/FC7 gates + EN capabilities). See closeout.

#### F.3 Do **not** mark F-C4/F-C7 ✅ here
Point to FC4/FC7 handoff checklist.

**Verify F**
- [x] [Code] Whitelisted pytest for new modules (`test_session_close`, `test_reconcile_sessions`, `test_provider_retries`).  
- [x] [Manual/docs] Reconcile cron proof **open for Ehsan**; Urdu failover = **signed residual** (no #2).  

**Exit F:** Habiba Wave 2 **High** gaps closed with evidence (shared exits still open).

---

## 4. Suggested PR sequence

| PR | Contents | Blocks |
|---|---|---|
| PR1 | Phase B session close helper + tests | None |
| PR2 | Phase C runbook + reconcile tests | Ehsan cron can parallel |
| PR3 | Phase D retries + inventory doc | Product sign-off for D.1 |
| PR4 | Phase E explicit fallback resolver | D.1 approvals; maybe Ehsan schema |
| PR5 | Phase F checklist + whitelist | After PR1–4 |

Do **not** mix F-H18 and F-H10 in one mega-PR.

---

## 5. Out of scope

- F-M24 / F-M25 / F-M15 full honesty API / F-L6 / F-L10  
- Capacity sheet / Uplift ceiling measurement (parked RQ-001)  
- Legal DPA / SSO  
- Replacing LiveKit with custom supervisor  
- Silent English provider substitution for Urdu calls  

---

## 6. Effort sketch

| Phase | Size | Notes |
|---|---|---|
| A | 0.5 d | Docs + Ehsan ask |
| B | 1–2 d | Close helper |
| C | 0.5–1 d Habiba + Ehsan cron | Shared exit |
| D | 1 d | Inventory + retries |
| E | 2–3 d | Fallback; schema may block |
| F | 0.5 d | Proof |

**Total Habiba:** ~1–1.5 weeks focused, assuming Ehsan cron + product Urdu #2 decisions land in parallel.

---

## 7. Immediate next action

1. **Start Phase A** — freeze §0 with any extra line cites if needed; ask Ehsan: “Are reconcile_sessions + reconcile_telephony on any schedule today?”  
2. Do **not** start coding Phase B until A.3 cron ownership is acknowledged (can be “you own cron; Habiba ships runbook”).  
3. For F-H10, **do not** enable Groq for `ur` or Cartesia for Urdu TTS without an explicit product yes in Phase D.

**Locked without further confirmation:** D1–D4, D6–D8, phase order F-H18 → F-H10.  
**Needs human before E:** D5 product sign-off on any concrete Urdu secondary provider.
