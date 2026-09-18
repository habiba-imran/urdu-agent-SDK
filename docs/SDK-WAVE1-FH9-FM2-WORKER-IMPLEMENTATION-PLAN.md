# Habiba Wave 1 — F-H9 + F-M2 (worker) Implementation Plan

**Owner:** Habiba  
**Wave:** 1  
**Source of truth:** `docs/UVA-PRIORITY-LIST.md` · audit `docs/AwaazLabs UVA Audit.md` (§3.2, §9)  
**Explicitly excluded from this plan:** Humanization + TTFT (CTO brief), Worker cold start / time-to-first-greeting.

Use this doc to start a fresh implementation chat/agent. Do **not** expand into humanization, cold start, history-window truncation, Groq 429 retry behaviour, portal write-time caps, or Wave 2 Habiba items.

---

## Scope (hard stop)

**In scope (this plan only):**

| ID | Plain English | Habiba files |
|---|---|---|
| **F-H9** | Hang-up / escalate tools block the event loop → live audio stalls | `worker/tools.py` **only** |
| **F-M2** (worker side) | Unbounded `agents.prompt` burns Groq ITPM / mid-call silence | `worker/prompt_compact.py` + prompt assembly in `worker/main.py` |

**Out of scope (do not implement here):**

| Item | Why out |
|---|---|
| Humanization + TTFT | User-excluded; separate Wave 1 delivery item |
| Worker cold start / first greeting | User-excluded; separate Wave 1 delivery item |
| Conversation-history truncation | Priority: part of Humanization + TTFT, **not** F-M2 |
| Groq 429 retry / dead-air behaviour | Priority: part of Humanization + TTFT, **not** F-M2 |
| Portal / schema write-time prompt cap | Ehsan Wave 2 (`tenant_portal_api/app.py:107`, migrations) |
| F-C7 / SSRF on tools webhook | Priority freeze: Habiba Wave 1 `worker/tools.py` is **F-H9 only** |
| F-H10, F-L6, F-M15, F-M24, F-M25, … | Habiba Wave 2+ / parked |
| `control_plane/`, `tenant_portal_api/`, `sdk/package.json`, `.github/` | Ehsan exclusive Wave 1 |

**Primary source docs:**

- Priority roster: `docs/UVA-PRIORITY-LIST.md` Habiba Wave 1 table + catalog **F-H9**, **F-M2**
- Audit: `docs/AwaazLabs UVA Audit.md` §9 F-H9; §9 / §3.2 F-M2
- Existing patterns: `asyncio.to_thread` in `worker/main.py` (~214, ~460); `compact_prompt_for_groq` in `worker/prompt_compact.py`

---

## Freeze / ownership

| Path | Rule for this work |
|---|---|
| `worker/tools.py` | Habiba — **F-H9 only**. No SSRF / tool-gateway changes. |
| `worker/prompt_compact.py` | Habiba — F-M2 worker mitigation |
| `worker/main.py` | Habiba may touch **only** the prompt-assembly / compact call site for F-M2. No cold-start, no TTS humanization, no history-window, no 429-retry changes. |
| `tenant_portal_api/**`, `supabase/migrations/**` | **Do not touch** (Wave 1 neither / Ehsan Wave 2 for F-M2 write cap) |
| `pytest.ini` | Habiba may **ask** Ehsan to whitelist `tests/test_prompt_compact.py` (and any new Habiba test file name) — do not restore full discovery (F-H1) |

Prefer **one end PR** on `habiba` after F-H9 + F-M2 phases complete (no mid-work PR). Still implement in order: F-H9 first, then F-M2.

---

## Current code reality (do not re-invent)

### F-H9 — still broken as audited

`worker/tools.py`:

- `end_conversation_summary` (~`:61`) — `async def` + sync `psycopg.connect(...)` on the event loop  
- `escalate_to_human` (~`:87`) — same pattern  

Every other worker DB path uses `asyncio.to_thread` (e.g. `worker/main.py` config load / session identity). Audit fix: wrap both DB blocks in `asyncio.to_thread` (or pooled async — prefer `to_thread` to match existing style).

### F-M2 — partial worker mitigation already exists

- `worker/prompt_compact.py::compact_prompt_for_groq` — soft cap via `GROQ_PROMPT_SOFT_CHARS` (default **3000**), section keep/drop, unstructured truncate  
- `worker/main.py` (~`:94–104`) — compaction runs **only when** `cfg.llm_provider == "groq"` at **session build**  
- `tests/test_prompt_compact.py` — 2 unit tests exist; typically **excluded** by F-H1 whitelist (Ehsan must add that one filename if CI should run them)

Audit §9 F-M2 “correct control” (server-side 422 at write time) is **Ehsan Wave 2**, not this plan. Habiba Wave 1 closes the **worker-side** gap called out in the priority split.

---

## Implementation order (strict)

```text
Phase 0  — Freeze ACK + branch hygiene
  → Phase 1  — F-H9: to_thread for end + escalate
  → Phase 2  — F-H9 tests + lint/pytest for touched tests
  → Phase 3  — F-M2: audit worker compact gaps vs priority (no invention)
  → Phase 4  — F-M2: code changes in prompt_compact + main assembly only
  → Phase 5  — F-M2 tests + Ehsan whitelist handoff
  → Phase 6  — Verification matrix + PR notes (no humanization/cold start)
```

Stop and ask on any human gate. Do not invent caps, providers, or portal behaviour beyond audit + priority.

---

## Phase 0 — Freeze ACK + branch

### 0.1 Confirm

- [x] Working on branch `habiba` (tip `3ecdd1f`, tracks `origin/habiba`)  
- [x] Will not edit portal / migrations / control_plane / sdk package.json  
- [x] Will not start humanization, cold start, history window, or Groq 429 retry work  
- [x] F-H9 PR will touch `worker/tools.py` only (plus tests)

### 0.2 Current behaviour analysis (Phase 0 — no code changes)

**F-H9 today**

- `end_conversation_summary` and `escalate_to_human` are `@function_tool` `async def`s.
- Both call sync `psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True)` **directly on the event loop** (`tools.py` ~61 and ~87).
- `end_conversation_summary` order: DB update summary → `ended_by_agent = True` → `session.shutdown(drain=True)` → `{"status": "saved"}`.
- `escalate_to_human` order: DB select session id → insert `escalations` → `{"status": "escalated"}` (no shutdown).
- Contrast: other worker DB I/O already uses `await asyncio.to_thread(...)` (e.g. `main.py` `load_agent_session_bundle`, `load_session_identity`).
- `asyncio` is already imported in `tools.py` (used by HTTP tools) — F-H9 can use the same import.
- Audit/priority fix remains: wrap those two DB blocks in `asyncio.to_thread`; do not touch other tools / SSRF.

**F-M2 worker today**

- `compact_prompt_for_groq` exists; soft cap from `GROQ_PROMPT_SOFT_CHARS` (code default **3000**; `.env.local` also sets `3000`).
- Compaction runs in `build_agent` / assembly only when `(cfg.llm_provider or "").lower() == "groq"` at session build; non-Groq keeps full DB persona.
- `tests/test_prompt_compact.py` exists (2 tests) but is **not** on the `pytest.ini` `python_files` whitelist (F-H1) — CI will not collect it until Ehsan adds that one name.
- Portal write-time max length is **not** Habiba Wave 1 (Ehsan Wave 2). History window / Groq 429 retries stay out (humanization plan).

### 0.3 Human intervention (blocking — do not start Phase 1 until answered)

- [x] PR strategy: **one end PR** on `habiba` (still implement F-H9 then F-M2 in order; no mid-work PR).  
- [x] `GROQ_PROMPT_SOFT_CHARS` default **3000** stays.

---

## Phase 1 — F-H9: unblock the event loop

### 1.1 Change (`worker/tools.py`)

For both `end_conversation_summary` and `escalate_to_human`:

1. Extract the sync DB body into a small private sync helper **or** inline `def _write_...():` closed over locals.  
2. `await asyncio.to_thread(<sync_fn>)` (or `asyncio.to_thread` with a lambda/partial — match repo style in `main.py`).  
3. Keep tool return shapes unchanged: `{"status": "saved"}` / `{"status": "escalated"}`.  
4. Keep `session.shutdown(drain=True)` **after** the awaited DB write in `end_conversation_summary` (same order as today: DB → flag → shutdown).  
5. Do **not** change HTTP client tools, SSRF, docstrings beyond a one-line note if needed.

### 1.2 Verification

- [x] Grep: `psycopg.connect` only in sync helpers `_save_conversation_summary` / `_insert_escalation`; async tools use `await asyncio.to_thread(...)`.
- [ ] Manual (optional): live call → escalate / end — no multi-second audio freeze during DB (Phase 6 / human).

**Refs:** Audit F-H9; priority F-H9 WHERE `:61`, `:87`; pattern `worker/main.py` `asyncio.to_thread`.

---

## Phase 2 — F-H9 tests

### 2.1 Tests

- [x] Added `tests/test_tools_lifecycle_db.py` (mocked helpers + `to_thread` spy; no real DB)
- [x] Local: `python -m pytest tests/test_tools_lifecycle_db.py -q` → **3 passed**

Do **not** rely on legacy `tests/test_tools.py` (old TechZone tool surface — unrelated).

### 2.2 Human + Ehsan gate

- [ ] **Ask Ehsan:** add `test_tools_lifecycle_db.py` to `pytest.ini` `python_files` whitelist (**that one name only** — F-H1 exception).  
  Until then Habiba runs the explicit path above. File is **not** currently collected by default `pytest` (whitelist omits it).

---

## Phase 3 — F-M2 discovery (no coding until gaps are listed)

**Goal:** State what Habiba still owes vs what already exists. Do not invent a portal cap.

### 3.1 Checklist (filled 2026-09-15)

- [x] Confirm Groq session-build path calls `compact_prompt_for_groq` — **yes**, `worker/main.py` `build_agent` ~94–104 when `(cfg.llm_provider or "").lower() == "groq"`
- [x] Confirm soft cap env `GROQ_PROMPT_SOFT_CHARS` (default **3000**) — **yes** in `prompt_compact._soft_chars()`; `.env.local` / `.env.example` align; Phase 0 ACK to keep 3000
- [x] Gap list vs priority “worker compact + assembly” — see **§3.1a** below
- [x] Explicitly **exclude** history truncation and Groq 429 retry from this list (Humanization + TTFT)

### 3.1a Gap list (Habiba F-M2 worker only)

| # | Finding | Severity for Habiba Wave 1 | Notes |
|---|---|---|---|
| G1 | `tests/test_prompt_compact.py` not on `pytest.ini` whitelist | **Process / CI** | Mitigation code exists; CI never runs the 2 tests (F-H1). Ehsan whitelist. |
| G2 | No unit test that `build_agent` **calls** compact for Groq / **skips** for non-Groq | **Small test gap** | Compact function tested; assembly wiring only implied by reading `main.py`. |
| G3 | After section compact, length can still sit **slightly above** soft cap (soft ≠ hard) | **Optional hardening** | Observed in probe: soft=500 → out≈603 when kept sections are large. Unstructured path already hard-truncates to soft+marker. Not required by audit text (audit’s permanent fix is portal write-time cap). |
| G4 | Compaction is **Groq-only** at session build | **By design** | Matches audit (“mitigates only for Groq”) + priority Habiba split. Do **not** expand to all providers without a new ACK. |
| G5 | Portal / schema max length on `agents.prompt` | **Not Habiba Wave 1** | Ehsan Wave 2 (`tenant_portal_api/app.py:107`). |

**Already in place (not gaps):** `compact_prompt_for_groq` section keep/drop + digest trim + unstructured truncate; `build_agent` Groq gate; info log on compact; prompt dump records `compacted=`.

**Recommended Phase 4 (pending your ACK — pick one):**

- **A (minimal / preferred):** No production code change. Add G2 wiring test only. Rely on existing compact. Ehsan does G1 (+ F-H9 test file).  
- **B:** A + G3 hard-truncate to soft after section pass if still `len > soft` (document as soft→hard residual).  
- **C:** Declare Habiba F-M2 **code-complete**; Phase 4 skip; only Ehsan whitelist (G1).

### 3.2 Human intervention (blocking before Phase 4)

- [x] Habiba ACKs gap list — chose **A** (wiring test only; no compact production rewrite; Ehsan does G1 whitelist).

---

## Phase 4 — F-M2 worker code (only after Phase 3 ACK)

**ACK:** Option **A** — no production `prompt_compact` / `main` rewrite; add G2 assembly wiring tests only.

### 4.1 Allowed changes

- Strengthen / fix `worker/prompt_compact.py` per **agreed gaps only** — **skipped under A**  
- Minimal edits to `worker/main.py` assembly — **skipped under A** (wiring already correct; proven by new tests)  
- Keep non-Groq providers behaviour unless an agreed gap explicitly requires a shared hard truncate (default: **do not** expand compaction to all providers without ACK — audit’s permanent fix is write-time cap)

### 4.2 Forbidden in this phase

- Portal `max_length` / 422  
- Schema migration on `agents.prompt`  
- Chat-history sliding window  
- Changing Groq client retry / LiveKit retry policy  
- Cartesia / telephony TTS humanization edits  

### 4.3 Verification

- [x] Unit tests in `tests/test_prompt_compact.py` (existing soft-char cases still pass)  
- [x] G2 assembly wiring in `tests/test_worker.py`:
  - `test_build_agent_compacts_prompt_when_llm_provider_is_groq`
  - `test_build_agent_skips_compact_when_llm_provider_is_not_groq`
- Log line already present on compact (`groq prompt compacted agent=...`) — keep or extend, don’t remove  

---

## Phase 5 — F-M2 tests + CI handoff

### 5.1 Habiba

- [x] `tests/test_prompt_compact.py` covers soft-char behaviours  
- [x] G2 wiring tests live in **`tests/test_worker.py`** (already on `pytest.ini` whitelist — no new file for G2)  
- [x] Local: F-H9 + F-M2 related tests **7 passed**

### 5.2 Ehsan handoff (required for CI)

Ask Ehsan (separate change): add **`tests/test_prompt_compact.py`** and **`tests/test_tools_lifecycle_db.py`** to `pytest.ini` whitelist — **those names only**.  
(G2 wiring tests do **not** need a new whitelist row; they are in `test_worker.py`.)

Handoff file: `docs/EHSAN-HANDOFF-HABIBA-WAVE1.md`

---

## Phase 6 — Verification matrix + PR notes

| ID | Automated | Manual |
|---|---|---|
| F-H9 | lifecycle tool test with mocked DB / `to_thread` — **3 passed** | Live call: escalate or end — no multi-second audio freeze during DB |
| F-M2 | `test_prompt_compact` + G2 `build_agent` wiring — **4 passed** | Groq agent with oversized persona — log shows compact; call does not immediately ITPM-starve |

### PR description must include

- Findings closed: **F-H9** and **F-M2 (worker only / assembly wiring covered)**  
- Files touched (list)  
- Explicit **not done:** humanization/TTFT, cold start, history window, Groq 429 dead-air, portal write-time cap (Ehsan Wave 2)  
- Explicit **Ehsan follow-ups:** whitelist `tests/test_prompt_compact.py` + `tests/test_tools_lifecycle_db.py` in `pytest.ini`  

### Final human sign-off

- Habiba: F-H9 live escalate/end smoke (optional but preferred)  
- Habiba: F-M2 Groq oversized-prompt smoke if a long persona agent is available  
- Ehsan: pytest whitelist ACK  

**Phase 6 status:** automated verification done locally. One end PR — **do not open until Habiba asks**.

---

## Checklist for implementer agent

- [x] Phase 0 freeze ACK on branch `habiba` @ `3ecdd1f` + current-behaviour notes
- [x] Phase 0 human answers: one end PR; soft-chars 3000
- [x] Phase 1 F-H9 `asyncio.to_thread` on both tools  
- [x] Phase 2 F-H9 unit tests (`tests/test_tools_lifecycle_db.py`, 3 passed locally; Ehsan whitelist pending)
- [x] Phase 3 F-M2 gap list written; Habiba ACK **A**
- [x] Ehsan handoff file drafted: `docs/EHSAN-HANDOFF-HABIBA-WAVE1.md`
- [x] Phase 4 F-M2 — option A: G2 wiring tests only (no compact production rewrite)
- [x] Phase 5 tests local green; Ehsan whitelist still needed for `test_prompt_compact.py` + `test_tools_lifecycle_db.py`
- [x] Phase 6 automated verification done; end PR deferred until Habiba asks  
- [x] Wave1 code paths OK: `worker/tools.py`, `tests/test_tools_lifecycle_db.py`, `tests/test_worker.py` (+ plan/handoff docs)  

---

## Easy English (for Habiba)

| Ticket | Problem | Fix in this plan |
|---|---|---|
| **F-H9** | When the agent hangs up or escalates, the worker freezes audio while waiting on the database | Run those DB writes off the event loop (`to_thread`) |
| **F-M2** | Huge agent personas blow Groq’s token budget | Keep/improve **worker** prompt compaction for Groq; portal “reject too-long prompts” waits for Ehsan |

Not in this plan: making voices sound more human, speeding first greeting, trimming chat history, or fixing Groq rate-limit retries.
