# Wave 2 P0 — F-C4 + F-C7 Implementation Plan

> **New chat / status:** read **`docs/WAVE2-FC4-FC7-STATUS-HANDOFF.md` first** (phase A–F done vs open shared exits).  
> **Next Habiba High work:** **`docs/WAVE2-HIGH-FH10-FH18-IMPLEMENTATION-PLAN.md`** (F-H18 then F-H10).

**Owner:** Habiba (worker / tools / recording path)  
**Depends on:** Wave 1 `worker/main.py` + `worker/tools.py` merged  
**Shared with Ehsan:** schema migrations (`supabase/migrations/`), portal erasure/re-sign APIs, mint metadata for browser caller identity, **scheduled purge cron**  
**Goal:** Close audit Criticals **F-C4** and **F-C7** (Gate 3 / Gate 4 Habiba + shared exit criteria below).

Sources:
- `docs/AwaazLabs UVA Audit.md` → F-C4, F-C7 (+ Gate 3 / Gate 4)
- `docs/UVA-PRIORITY-LIST.md`
- Plan audit (codebase cross-check, 2026-09-18) — amendments folded into this doc
- Industry: [Vapi recording consent](https://docs.vapi.ai/security-and-privacy/recording-consent-plan), [Vapi artifacts](https://docs.vapi.ai/assistants/call-recording), [Retell privacy / disclaimer](https://docs.retellai.com/accounts/privacy-disable), Retell/Vapi booking confirmation patterns

**Status:** Implementation-ready. Design decisions below are locked unless product re-opens them.

**Phase A artifact:** `docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md` (baseline snapshots + Ehsan contracts). Phase A has **no runtime behaviour change**. Exit A still needs Render env confirmation + Ehsan sign-off on A.3/A.4 — see that doc §5.

---

## 0. Current behaviour (code reality today)

### F-C4 — Recording / transcript / retention

| Area | Current behaviour | Gap vs audit |
|---|---|---|
| **Audio record start** | `worker/main.py` gates LiveKit `record=` on env `UVA_SESSION_RECORD_AUDIO` (default **off** / `"0"`). | Audit at `94e7000` saw unconditional `record={"audio": True}`. Local/demo is safer now, but this is **process env**, not **per-agent opt-in**, and there is still no consent / disclosure / retention / erasure. |
| **Upload path** | Shutdown → `finalize_and_persist_session_recording` → upload `audio.ogg` to Supabase `session-recordings/{tenant}/{room}.ogg` → write `sessions.recording_url` + `recording_storage_path` (+ telephony mirror). | No consent check before upload. Signed URL (7d) stored in DB. `_ensure_bucket` runs every session (F-L15). Silent `except` on remove (F-M1). |
| **Transcript** | On session close, full user/assistant turns written to `sessions.transcript` JSONB. Always, independent of recording flag. | No redaction, retention, or delete path. |
| **Disclosure** | `session_opening.py` speaks tenant greeting or generated greeting only. `first_speaker=user` → mode `wait` (no opening speech). | No “this call may be recorded” line when recording is on; wait-mode also has nowhere to put it today. |
| **Consent capture** | None. | No `granted` / `declined` / timestamp. |
| **LiveKit `enable_recording`** | Not consulted anywhere in worker; env flag is the only switch. | Audit: honour LiveKit signal; do not override off→on. |
| **Retention columns** | `0014_*` added retention/deletion columns to telephony **infra** tables **and** to `telephony_calls` / `telephony_call_events`. | Columns on `telephony_calls` exist but are **inert** (no purge). **Missing** on `sessions` and `escalations`. No scheduled purge job. |
| **Erasure** | No delete Storage object + null transcript + clear URLs procedure. | GDPR/CCPA erasure impossible. |
| **Agent config** | `AgentConfig` has no `recording_enabled` / consent fields. | Cannot opt-in per agent. |

### F-C7 — Destructive write tools

| Area | Current behaviour | Gap vs audit |
|---|---|---|
| **Write tools** | `book_appointment`, `reschedule_appointment`, `cancel_appointment` → immediate `_post_client_tool` HTTP POST. | Prompt says “only after caller confirmed”; **not enforced in code**. |
| **Identity** | `tenant_id` / `agent_id` come from `AgentUserdata` (good). Mutation key is LLM-transcribed `customer_phone`. | No ownership check vs PSTN ANI or host-verified browser identity. |
| **Schema** | Python type hints only; any string flows to gateway. | No strict pre-dispatch validation. |
| **Idempotency** | None on tool POSTs. | Retries can double-book / double-cancel. |
| **Budget** | No `MAX_TOOL_CALLS` / write-tool budget. | Injection / loop can spam writes. |
| **Read tools** | `lookup_business_info`, `check_availability` — same POST path, non-destructive. | Keep fast; do **not** put confirmation gate on reads. |
| **Telephony identity available** | Job metadata `e164_number` / `from_number` is the **platform trunk / from-number**, not the remote caller. `extract_sip_participant_attributes` only pulls trunk/call-id fields — **no caller ANI**. `telephony_calls` has `from_number` / `to_number` but worker does not load them into userdata. | Ownership binding needs a real `verified_caller_phone` — **never** bind to trunk `e164_number`. |
| **Browser mint** | CP mint metadata is only `tenant_id` + `agent_id` (+ optional greeting). | No host-passed verified caller phone yet (Ehsan/CP touch). |

### What competitors do (design anchors)

| Platform | Recording | Destructive tools |
|---|---|---|
| **Vapi** | Per-assistant `artifactPlan.recordingEnabled` (they default on; we default **off**). Enterprise `recordingConsentPlan`: **verbal** or **stay-on-line**; recording starts **after** consent; `grantedAt` in end-of-call compliance object. | Appointment workflows use an explicit **Booking Confirmation** conversation step (read-back → wait for yes → then Schedule Event). |
| **Retell** | Per-agent storage tiers + retention days + optional PII scrub. Disclaimer usually = first message / blocked-interruption node (no separate consent product). | Docs: check availability → confirm slot → book. Host must validate tool args. |
| **Shared lesson** | Opt-in + spoken disclosure + audit trail + retention/delete. Prompt-only consent is weak. | Confirmation must be **enforced before the write HTTP call**, not only in the system prompt — and must wait for a **caller turn**, not a same-turn double tool call. |

**UVA stance for Wave 2 P0:** Match Vapi’s *structure* (opt-in, disclosure/consent state, no persist without grant) and Retell’s *pragmatic disclosure* for v1; enforce tool confirmation in the **tool layer** with a **user-turn barrier**.

---

## 1. End-state definition of done

### F-C4 done when (all must be true)

1. Recording is **opt-in per agent** (default **off**), not only a worker env knob.  
2. Env `UVA_SESSION_RECORD_AUDIO` may force-enable for local demos, but **cannot** force-enable in prod without agent opt-in (prod = agent flag only; document in `.env.example`).  
3. LiveKit / job `enable_recording=false` is honoured (never start recorder or persist when signal says off).  
4. When recording **will** run (`may_start_recorder`): caller hears a **non-interruptible spoken disclosure** before substantive conversation — including `first_speaker=user` sessions.  
5. Consent outcome is stored on the session (`not_applicable` / `pending` / `granted` / `declined` + timestamp). Stay-on-line → `granted` only **after** disclosure utterance completes.  
6. Upload + URL persist only if `may_persist_recording` (start policy **and** consent satisfied). Local `audio.ogg` deleted when not storing.  
7. `sessions` and `escalations` have retention/deletion columns; `telephony_calls` columns already exist and are **enforced** by purge. Purge deletes Storage object + clears transcript/URLs/`escalations.contact_info`.  
8. Worker does **not** persist long-lived signed URLs as source of truth (store `recording_storage_path`; omit `recording_url` or use ≤1h TTL). Portal re-sign = Ehsan follow-up (documented).  
9. Documented erasure procedure exists and a unit/integration test proves “delete recording + transcript for room X”.  
10. **Shared Gate 3 exit:** Ehsan has scheduled the purge script (cron/workflow). Habiba does **not** mark F-C4 ✅ until this is true (or an accepted interim: documented manual runbook + one staging run + ticket for cron with owner+date).

### F-C7 done when (all must be true)

1. `book` / `reschedule` / `cancel` cannot hit the client gateway until a **code-enforced** confirmation succeeds **and** at least one **user turn** has occurred since the propose/pending was created (no same-turn double-call POST).  
2. Write args validated against a strict schema before POST.  
3. Every write POST sends an **idempotency key** (integration-test host accepts it).  
4. `verified_caller_phone` is wired from **real** sources (PSTN ANI / `telephony_calls` remote party / mint metadata) — **never** from trunk `e164_number`. Cancel/reschedule **fail closed** without it. Book: when verified phone present, must match (or overwrite with verified); when absent (browser without mint field), book may proceed — **documented residual risk**.  
5. Per-session write-tool budget (`MAX_WRITE_TOOL_CALLS`, e.g. 5) enforced.  
6. Unit tests cover gate + **same-turn confirm rejected** + schema + ownership + budget + ANI wiring. Live injection adapted for CLIENT write tools (Phase F).  
7. **Shared browser exit:** cancel/reschedule on browser calls work only after A.4 mint field lands. Do not mark browser F-C7 ✅ until mint metadata is consumed end-to-end. Telephony can close earlier once ANI wiring works.

### Residual risks (explicit — do not claim closed)

- Stay-on-line ≠ affirmative consent in all-party US states — legal opinion still parked.  
- Book without verified phone (browser) can still spam bookings under a wrong number.  
- Idempotency is only as strong as host acceptance; worker always sends the key.  
- Portal re-sign UI and agent recording toggle UI are Ehsan follow-ups (Critical close does not require UI if columns + worker + purge work).

---

## 2. Design decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| D1 Recording default | **Off** per agent | Safer than Vapi’s default-on; matches current local env default. |
| D2 Consent v1 | **Disclosure + stay-on-line** (spoken line completes → `granted`). Verbal yes/no = stretch. | Gate 3 asks for spoken disclosure; Vapi verbal is stretch without blocking P0. |
| D3 Recorder vs persist | **Two policies** (see B.1). Prefer late start after disclosure if LiveKit allows; if start-at-`session.start` is required, allow ephemeral buffer but **`may_persist_recording` gates upload**. | Audit cares about stored personal data more than ephemeral buffers. Consent must **not** be in the start-time AND. |
| D4 Confirmation gate | **Option 1** (same tool + `confirmation_id`) **plus user-turn barrier**. | Tool-layer; blocks same-turn LLM double-call that would fake “spoken” confirm. |
| D5 Ownership | Normalize E.164; bind cancel/reschedule to `verified_caller_phone`. Book matches when verified present. | Audit fix text. |
| D6 Browser identity | Host passes `verified_caller_phone` at mint/dispatch (Ehsan). Until then: cancel/reschedule **blocked**. | Fail closed on destructive ops. |
| D7 Schema owner | Habiba worker validation; gateway may still validate. | Close F-C7 in worker. |
| D8 Migrations | Ehsan owns migration files; Habiba specifies column contract in Phase A. | Priority-list freeze. |
| D9 Disclosure interruptibility | Disclosure utterance is **always non-interruptible**. Greeting interruptibility unchanged after disclosure. | Stay-on-line is meaningless if barge chops the line. |
| D10 Caller identity source | PSTN: LiveKit SIP caller attrs (e.g. `sip.phoneNumber`) and/or `telephony_calls.from_number`/`to_number` by room/call id. Browser: mint metadata. **Never** trunk `e164_number`. | Current `e164_number` is platform number — binding to it would be a security bug. |

---

## 3. Phased plan

Legend for verification:
- **[Code]** — agent runs tests / greps / reads diffs  
- **[Manual]** — you run a live call or check portal/DB  

---

### Phase A — Baseline & contracts (no behaviour change)

**Goal:** Freeze “what is true today” and agree schema/API contracts before coding.

**Deliverable (written):** `docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md`

#### A.1 Snapshot current recording path
- Document call graph: `session.start(record=…)` → RecorderIO → shutdown `_persist_session_recording` → upload → SQL.
- Confirm production Render env value of `UVA_SESSION_RECORD_AUDIO` (**human**).
- Note LiveKit `enable_recording`: field on `ctx.job` (`livekit.protocol.agent.Job`); UVA does not read it yet; staging logs show it arriving.

**Verify A.1**
- [Code] Done in Phase A artifact (grep + line-backed snapshot).
- [Manual] Confirm Render/worker env: recording on or off in staging/prod — **open** (artifact §5).

#### A.2 Snapshot tool write path
- Document `CLIENT_TOOLS` → `_post_client_tool` → host `/api/tools/*`.
- List payloads for book/reschedule/cancel.
- Note: `client-integration-test` has **no** tool routes; real in-repo host gateway is `self-serve-demo-UI/backend/src/routes/tools.ts` (no write-tool idempotency today). Telephony idempotency exists only on purchase/outbound.

**Verify A.2**
- [Code] Done in Phase A artifact.
- [Manual] Optional: one booking call with tools gateway and note whether double-say double-books.

#### A.3 Schema contract (hand to Ehsan)
Full SQL proposal + sign-off box in Phase A artifact §A.3. Summary:

```text
agents: recording_enabled (default false), recording_consent_mode (default disclosure)
sessions: recording_consent_* + retention/deletion columns
telephony_calls: DO NOT re-add retention cols (already 0014)
escalations: retention/deletion columns
session_recording_events: optional v1
```

**Verify A.3**
- [Manual] You + Ehsan sign off — **open** (artifact §5).
- [Code] After migration lands: `\d sessions` / `\d escalations` / confirm `telephony_calls` unchanged for retention cols.

#### A.4 Mint metadata contract (hand to Ehsan)
Full contract + sign-off in Phase A artifact §A.4. Add optional `verified_caller_phone` to dispatch (and agreed token/participant) metadata.

**Verify A.4**
- [Manual] Ehsan agrees CP mint/dispatch forwards the field — **open** (artifact §5).

**Exit A:** Contracts agreed; no production behaviour change yet. **Do not start Phase B until A.3 is signed** (A.1 Render answers + A.4 should be in flight).

---

### Phase B — F-C4 opt-in recording (stop ungoverned capture)

**Goal:** Recording cannot start or persist unless agent opts in **and** signals allow it. Consent is **not** required at start time.

#### B.1 Resolve recording policy in worker
Add `worker/recording_policy.py` (or equivalent) with **two** functions:

```text
may_start_recorder =
    agent.recording_enabled
    AND env_allows   # local: UVA_SESSION_RECORD_AUDIO can force for demos
                     # prod: env alone CANNOT force-on; agent flag required
    AND livekit_enable_recording != false

may_persist_recording =
    may_start_recorder
    AND consent_status in ('granted',)   # stay-on-line marks granted after disclosure completes
    # verbal mode: only after explicit yes; declined → false
```

Wire:
- `session.start(record=…)` ← **`may_start_recorder` only** (no consent in this AND).
- `finalize_and_persist_session_recording` ← **`may_persist_recording`**.

Document how `enable_recording` is read (job metadata / room options / LiveKit API — pick the real field during A.1).

#### B.2 Load `recording_enabled` on `AgentConfig`
Extend `worker/config.py` select + dataclass (default `False` if column missing during rollout).

#### B.3 Upload gate
`finalize_and_persist_session_recording` refuses upload unless `may_persist_recording`. Delete local `audio.ogg` when not storing. Log (WARNING+) on failed Storage remove (fold F-M1 for this path).

#### B.4 Bucket ensure once (fold F-L15)
Move `_ensure_bucket` to process startup / first-use cache.

**Verify B**
- [Code] Unit tests: policy matrix for **both** functions (agent × env × enable_recording × consent). Assert consent does **not** affect `may_start_recorder`.
- [Code] With agent `recording_enabled=false`, assert `record=False` and no upload (mock storage).
- [Manual] Live call with agent opt-out → no `recording_url` / path on session row; no new Storage object.

**Exit B:** Default-off + honour disable signals + no upload without persist policy. Disclosure still Phase C (until then, opt-in agents that start recorder must not upload — persist gate fails closed if consent still `pending`/`not_applicable`).

**Phase B implementation status (Habiba):** Done in code — `worker/recording_policy.py`, `AgentConfig.recording_enabled` (column probe), `session.start` + finalize gates, F-L15 bucket cache, F-M1 remove warning, tests `test_recording_policy.py` (+ whitelist). Persist remains fail-closed until Phase C sets `granted`. Manual live call verify still optional when staging is up.

---

### Phase C — F-C4 disclosure, consent state, opening path

**Goal:** When `may_start_recorder` is true for the session, caller is told; consent state is persisted before substantive talk.

#### C.1 Disclosure text
Platform-owned default (EN/UR as needed), overridable later via agent field:

> “This call may be recorded for quality and training. Continuing means you agree.”

#### C.2 Opening integration (`session_opening.py`)
When recording will run (`may_start_recorder` / agent recording on for this session):

1. Speak disclosure with **`allow_interruptions=False`** (D9) — dedicated `session.say` **before** tenant greeting / generate_reply. Do **not** rely on `UVA_GREETING_INTERRUPTIBLE` alone.
2. **`first_speaker=user`:** still speak disclosure first, then wait for caller (do not skip disclosure because opening mode is `wait`).
3. After disclosure completes → set `recording_consent_status=granted` + timestamp (stay-on-line / D2). Before complete → `pending`.
4. Verbal mode (stretch): stay `pending` until yes/no; decline → `declined`, disable persist, **continue call without recording**.

#### C.3 Persist consent on session
Write status + timestamp as soon as known (and on verbal decision). Shutdown path must not upload if status ≠ `granted`.

#### C.4 Stretch (same phase if time): verbal consent tool
`record_consent(granted: bool)` fixed tool — only when mode=`verbal`.

**Verify C**
- [Code] Unit: opening plan includes non-interruptible disclosure iff recording will run; includes disclosure for `first_speaker=user`.
- [Manual] Call with recording on → hear disclosure before greeting / before caller substantive turn.
- [Manual] DB: `recording_consent_status` + `recording_consent_at` set after disclosure.
- [Manual] Opt-in + disclosure → Storage object exists; decline (if verbal) → no upload.

**Exit C:** Disclosure + consent audit fields live for recording-on agents.

**Phase C implementation status (Habiba):** Done in code — `worker/recording_disclosure.py` (EN/UR stay-on-line text, non-interruptible `session.say`, await playout → `granted`, DB write when columns exist), wired in `_await_opening_and_speak` before greeting/wait. Verbal consent tool (C.4 stretch) deferred. Tests: `test_recording_disclosure.py`. Manual live verify when staging is up.

---

### Phase D — F-C4 retention, purge, erasure, URL hygiene

**Goal:** Personal data is deletable and time-bounded; Gate 3 purge is real.

#### D.1 Set `retention_until` on session end
e.g. `now() + interval '30 days'` (env `UVA_RECORDING_RETENTION_DAYS`). Mirror onto `telephony_calls` for the same room when present. Set on `escalations` rows created in-session if practical; else purge uses session linkage / time heuristics documented in runbook.

#### D.2 Purge script
`scripts/purge_expired_session_media.py`:
- Find `sessions` (and `telephony_calls`) with `retention_until < now()` or `deletion_requested_at` set and `deleted_at` null.
- Delete Storage object at `recording_storage_path`.
- Null `recording_url`, `recording_storage_path`, `transcript`; redact `escalations.contact_info` for related rows.
- Set `deleted_at` / `redacted_at`.

**Ehsan schedules cron/workflow** (same pattern as F-H18 reconcile). Habiba owns script correctness + unit test.

#### D.3 Stop relying on long-lived signed URLs
Worker stores `recording_storage_path`; **stop writing** `recording_url` **or** use short TTL (≤1h) and document re-sign. Portal re-sign = Ehsan follow-up (acceptable if path is source of truth + runbook says so).

#### D.4 Erasure procedure doc
`docs/` short runbook: tenant/end-user request → mark `deletion_requested_at` → run purge (or wait for cron) → verify Storage gone + columns cleared.

**Verify D**
- [Code] Unit test purge against mocked storage + DB fixtures.
- [Manual] Insert expired row + fake path → run script → columns cleared.
- [Manual] Follow runbook once on staging.
- [Manual/Ehsan] Cron/workflow exists **or** interim ticket filed with owner+date (see DoD §1 item 10).

**Exit D:** F-C4 retention/erasure satisfied at worker+script level; shared schedule criterion met or explicitly interim-tracked. Portal UX can lag.

**Phase D implementation status (Habiba):** Done in code — `worker/session_retention.py` (set `retention_until` on close), `scripts/purge_expired_session_media.py`, URL hygiene (path only / null `recording_url`), runbook `docs/WAVE2-SESSION-MEDIA-ERASURE.md`, tests `test_session_retention_purge.py`. **Ehsan still owns purge cron** (documented interim: manual run).

---

### Phase E — F-C7 confirmation gate + schema + idempotency + ownership + budget

**Goal:** Destructive writes cannot fire from a single hallucinated tool call or a same-turn double call.

#### E.1 Session confirmation store on `AgentUserdata`
```text
pending_write: { tool, args_hash, args, confirmation_id, created_at, propose_user_turn_id }
write_tool_calls: int
verified_caller_phone: str | None
user_turn_count: int          # or last_user_turn_id; incremented on final user transcript
```

#### E.2 Two-step protocol (Option 1 + user-turn barrier)

1. First call with write args → **does not POST**; stores `pending_write`; returns `{ needs_confirmation: true, confirmation_id, summary }`.
2. Agent must speak summary and wait for caller “yes”.
3. Second call includes `confirmation_id` (and matching args) → POST **only if**:
   - `confirmation_id` matches pending store,
   - args hash matches,
   - **`user_turn_count` (or turn id) has advanced since propose** (D4),
   - budget not exceeded,
   - ownership + schema OK.
4. Same-turn confirm (no intervening user turn) → error, no HTTP.
5. TTL on pending (e.g. 5 minutes); clear pending on successful POST or expiry.

Update tool docstrings: first call proposes; only confirm after caller affirms.

#### E.3 Schema validation
Pydantic/dataclasses before any POST:
- phone: digits / E.164 normalize
- `slot_start_time`: ISO-8601
- required fields present; reject extras / unknown keys

#### E.4 Idempotency
`idempotency_key = sha256(tenant|agent|room|tool|normalized_args|confirmation_id)`  
Send as body field and/or header. Add acceptance in `client-integration-test` tool routes (telephony already has patterns).

#### E.5 Ownership binding + identity wiring
```text
if tool in (cancel, reschedule):
  require verified_caller_phone
  require normalize(customer_phone) == normalize(verified_caller_phone)
if tool == book and verified_caller_phone:
  require match (or overwrite customer_phone with verified)
```

**Wire `verified_caller_phone` at session build (D10):**
1. Browser: mint/job metadata `verified_caller_phone` (A.4).
2. PSTN: extract caller ANI from LiveKit SIP participant attributes (e.g. `sip.phoneNumber` / equivalent) — extend `extract_sip_participant_attributes`.
3. Fallback: load `telephony_calls.from_number` / `to_number` for this room / `telephony_call_id` and pick the **remote** party (inbound → `from_number`; outbound → `to_number`).
4. **Never** use trunk / job `e164_number` as verified caller.

#### E.6 Budget
`MAX_WRITE_TOOL_CALLS` (e.g. 5/session) incremented on successful POST. Exceed → error, no POST.

#### E.7 Read tools unchanged
`lookup_business_info` / `check_availability` stay one-shot.

**Verify E**
- [Code] Unit tests:
  - first book call → no HTTP
  - confirm with bad id → no HTTP
  - confirm **same turn** (no user turn since propose) → no HTTP
  - confirm after simulated user turn + good id → one HTTP
  - cancel without verified phone → error
  - cancel with mismatched phone → error
  - cancel with match → HTTP
  - trunk e164 must **not** satisfy ownership when ANI differs
  - invalid schema → error
  - budget exceeded → error
  - idempotent second confirm → same key / no duplicate side effect (mock)
- [Manual] Live browser call (after A.4): propose → say yes → one calendar row.
- [Manual] Injection-style “cancel all for 0300…” without verified phone → refuse.
- [Manual] PSTN (if available): ANI matches → cancel allowed; wrong phone → refuse.

**Exit E:** F-C7 worker fix complete. Browser cancel/reschedule path complete only with A.4. Telephony complete with ANI wiring.

**Phase E implementation status (Habiba):** Done in code — `worker/write_tool_gate.py` (propose/confirm + user-turn barrier + schema + ownership + budget + idempotency), `worker/caller_identity.py` (mint / `sip.phoneNumber` / `telephony_calls` remote party; never trunk e164), gated write tools in `worker/tools.py`, identity + turn wiring in `worker/main.py` / `latency.py` / `telephony_runtime.py`, tests `test_write_tool_gate.py`. **Residual:** A.4 mint field still open → browser cancel/reschedule fail-closed without `verified_caller_phone`. Host tool routes in this repo do not yet accept/dedupe `idempotency_key` (worker sends body + `Idempotency-Key` header).

---

### Phase F — Close Criticals (proof + tickets)

#### F.1 Live injection test
Adapt `tests/test_injection_live.py` to attach **CLIENT write tools** (or a harness that exercises the gate) and assert hostile persona cannot cause an unconfirmed POST. Coordinate F-H1 whitelist / `live` marker with Ehsan.

#### F.2 Mark catalog done (only if DoD §1 / §1 F-C7 all true)
Update priority checklist:
- F-C4 ✅ only if Phase B–D + shared purge schedule (or accepted interim) done.
- F-C7 ✅ Habiba worker + telephony ANI; note browser blocked until A.4 if mint not landed.
- List Ehsan follow-ups: portal re-sign, agent toggle UI, mint field (if open), purge cron (if interim).

#### F.3 Regression pass
- Recording off path still fast (Wave 1 latency not regressed).
- Disclosure non-interruptible; greeting behaviour after it unchanged.
- Tools gateway happy path still works (propose → user yes → confirm).

**Verify F**
- [Manual] Run injection script; paste results.
- [Code] `pytest` for new unit modules — **whitelist only those files** in `pytest.ini` while F-H1 is active.
- [Manual] One EN browser call + one tools booking call on staging.

**Exit F:** Wave 2 Criticals closed with evidence per DoD — not “Habiba portions” alone.

**Phase F implementation status (Habiba):** Done for Habiba-owned proof — `tests/test_injection_write_gate.py` (whitelisted), `tests/test_injection_live.py` adapted for CLIENT write tools + unconfirmed-POST check, `pytest.ini` `live` marker + deselect-by-default, priority-list Wave 2 status notes (not full Critical ✅), evidence `docs/WAVE2-PHASE-F-CLOSEOUT.md`. **Still open (human/shared):** live Gemini run paste, staging browser + booking calls, Ehsan A.3/A.4/purge cron, client idempotency accept.

---

## 4. Suggested PR sequence (minimize freeze risk)

| PR | Contents | Blocks |
|---|---|---|
| PR1 | Phase B policy (`may_start` / `may_persist`) + AgentConfig field + upload gate (+ F-L15 bucket, F-M1 log on remove) | Needs migration or feature-flag default false without column |
| PR2 | Phase C disclosure (non-interruptible, incl. `first_speaker=user`) + consent column writes | Needs A.3 migration |
| PR3 | Phase D purge script + retention_until set + URL hygiene + runbook | Needs A.3; cron with Ehsan |
| PR4 | Phase E tool gate + user-turn barrier + schema + idempotency + ANI/mint ownership + tests | Needs A.4 for browser cancel/reschedule; telephony ANI can ship first |
| PR5 | Phase F injection + checklist + whitelist new test files | After PR4 |

Do **not** mix F-C4 and F-C7 in one mega-PR.

---

## 5. Out of scope (explicit)

- Full Retell-style PII beep-scrub on audio (later).
- Portal UI toggle / erasure button (Ehsan; Habiba provides worker/script).
- F-M24 prompt dump default-off (related PII, not F-C4 Critical close).
- F-H10 Urdu failover, F-H18 reconcile cron (separate Highs — purge cron is in scope for F-C4 shared exit).
- Legal opinion on BIPA / two-party consent (parked / later).
- Verbal consent UX polish beyond stretch in Phase C.
- Closing book-without-identity residual on browser (documented only).

---

## 6. Effort sketch

| Phase | Size | Notes |
|---|---|---|
| A | 0.5–1 day | Contracts + env check + enable_recording field discovery |
| B | 1–2 days | Core safety; split policies |
| C | 1–2 days | Opening + disclosure edge cases |
| D | 1–2 days | Purge + runbook; cron with Ehsan |
| E | 2–3 days | Hardest: user-turn gate + ANI wiring |
| F | 0.5–1 day | Proof |

**Total:** ~1–1.5 weeks focused Habiba time, assuming Ehsan migrations/mint/cron land in parallel.

---

## 7. Immediate next action

1. **Finish Phase A human gates** in `docs/WAVE2-PHASE-A-BASELINE-AND-CONTRACTS.md` §5 (Render env + Ehsan A.3/A.4 sign-off).  
2. Only after A.3 signed: start coding Phase B (`recording_policy.py` with split `may_start_recorder` / `may_persist_recording`).  
3. Do not mark Criticals done until §1 DoD checkboxes (including shared exits) are green.

**Locked without further confirmation:** D2 stay-on-line v1, D6 fail-closed cancel/reschedule, D4 user-turn barrier, D9 non-interruptible disclosure, D10 never bind trunk e164.
