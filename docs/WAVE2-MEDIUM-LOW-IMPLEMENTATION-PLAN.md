# Wave 2 Medium + Low — Habiba Implementation Plan

**Owner (Habiba):** F-M1 (worker handlers only), F-M15, F-M24, F-M25, F-L6, F-L10, F-L15  
**Out of scope:** Ehsan Medium/Low (portal silent handlers half of F-M1, F-M9 HEALTHCHECK, F-M10, …); Critical/High already tracked in `WAVE2-P0-FC4-FC7-*` and `WAVE2-HIGH-FH10-FH18-*`

**Sources:** `docs/UVA-PRIORITY-LIST.md`, `docs/AwaazLabs UVA Audit.md` §9 / Appendix A.3, codebase read **2026-09-18** (this plan)  
**Industry anchors:** Vapi Monitoring + call-ended / provider-fault reasons; Retell reliability (explicit TTS/LLM/ASR fallback + ops alerts); Hamming / production voice guidance (PII out of logs before central storage)

**Status:** Phase A–H **done** (Habiba Medium/Low worker track). Closeout: `docs/WAVE2-MEDIUM-LOW-PHASE-H-CLOSEOUT.md`. Habiba still owns Render health deploy + optional manual spot-checks.

---

## 0. Current behaviour (code reality today — not assumptions)

### F-M1 — Worker silent / opaque exception handlers

**Audit Appendix A.3 (historical):** listed worker sites including `latency.py` bare returns, `main.py` timeout returns / VAD `pass`, `session_recording.py:82` delete `pass`, `tools.py` http close `pass`, `gemini.py` thinking_config `pass`.

**Today (re-read 2026-09-18):**

| Site | Current behaviour | Still a gap? |
|---|---|---|
| `worker/session_recording.py` prior-object `remove` | Now logs **WARNING** with path + exc (F-M1 comment in code). | **Mostly closed** for that site; keep in regression inventory. |
| `worker/latency.py` `load_session_identity` / `parse_dispatch_metadata` | `except Exception: return None` — **no log**. | **Yes** — identity/parse failure looks like “no row”. |
| `worker/latency.py` telephony job JSON parse | Same pattern. | **Yes** (low severity). |
| `worker/main.py` | Many `except Exception` → warning/continue on setup paths; some still thin. | **Yes** — need full inventory in Phase A (line-backed). |
| `worker/tools.py` `_shared_http_client` aclose | `except Exception: pass`. | **Yes** — close failure invisible. |
| `worker/providers/llm/gemini.py` | `thinking_config` construction `except Exception: pass`. | **Yes** — thinking disable may silently fail. |
| Portal / control_plane / telephony | Ehsan ownership per priority list split. | **Out of Habiba scope.** |

**Done-when (Habiba slice):** Every Habiba-owned production `except` either logs at WARNING+ with context, or is an intentional narrow catch with a one-line justification comment; no bare `pass` on I/O that can hide outages.

---

### F-M15 — Silent provider / model substitution

| Mechanism | Current behaviour | Honesty gap |
|---|---|---|
| **Groq dead models** | `worker/providers/llm/groq.py`: `_DEAD_GROQ_MODELS` → remap to live default (`GROQ_LLM_MODEL` / fallback). **No log inside `build()`.** | Tenant thinks Llama/Qwen; runtime is `openai/gpt-oss-*`. |
| **Capabilities still advertise dead IDs** | `worker/providers/capabilities.py` groq `models` list keeps retired IDs “so existing agent rows validate”; comment admits remaps at session start. | Sub-processor / picker honesty broken. |
| **Gemini deprecated IDs** | `gemini.py` maps 2.x → `GEMINI_LLM_MODEL` (default `gemini-3.6-flash`). | Capabilities still list both; remap mostly silent at adapter. |
| **Telephony TTS remap** | `force_cartesia_for_telephony`: Rime/Fish → Cartesia Katie on PSTN; Urdu/Uplift exempt. | `main.py` logs `telephony TTS remapped…` when `cartesia_forced`. |
| **Telephony / EN WebRTC LLM remap** | `force_groq_for_telephony` + `force_groq_for_english_webrtc` (env `UVA_FORCE_GROQ_ENGLISH` default **on**). | `main.py` logs `telephony LLM remapped…`. |
| **Registry** | Unknown provider → `UnsupportedProviderError` (no silent provider invent). | Correct; remaps happen *before* build via `resolve_effective_providers`. |
| **Session / API surface** | No durable `effective_llm` / `effective_tts` on session row or capabilities response. | Host/dashboard cannot show “what actually ran”. |

**Industry:** Retell/Vapi treat fallback as an **explicit configured plan** and surface provider faults in call end reasons / monitoring — not as a quiet rewrite of the tenant’s choice. UVA already logs *some* telephony remaps; model-ID collapse and capabilities advertising remain the compliance problem (§8 Part B).

**Related:** F-H10 Phase E skipped (“No #2”); this ticket is **honesty + observability of existing remaps**, not inventing new Urdu secondaries.

---

### F-M24 — Prompts / transcripts in logs + disk by default

| Path | Current behaviour |
|---|---|
| **Prompt dump** | `worker/prompt_dump.py`: default **on** unless `UVA_DUMP_PROMPTS` in `{0,false,no,off}`. Writes full system + persona (+ raw DB persona) to `docs/last_session_prompt.txt` (or `UVA_DUMP_PROMPTS_PATH`). |
| **Env docs** | `.env.example`: `UVA_DUMP_PROMPTS=1` documented as write-each-call. |
| **Turn logs** | `worker/main.py`: `conversation turn [USER/AGENT] … text=%r` (truncated **200** chars) and `live user speech … text=%r` (**full** transcript string at INFO). |
| **Retention** | Dump file + app logs are **outside** F-C4 session media purge / recording policy. |

**Industry:** Production voice stacks redact or omit PII from application logs; debug dumps are opt-in. Vapi HIPAA-style modes and Hamming guidance: scrub before central log/storage.

---

### F-M25 — No worker health / readiness HTTP surface

| Component | Current behaviour |
|---|---|
| **Control plane** | FastAPI `/healthz`, `/healthz/deep`, `/healthz/warm` (`control_plane/app.py`). |
| **Worker** | LiveKit `WorkerOptions` + `cli.run_app` in `worker/main.py` — **no** HTTP listener, no `/healthz`. |
| **Detect wedged worker** | Only via failed call / LiveKit dashboard job state. |

**Industry:** Vapi Monitoring + Retell alerting assume infrastructure signals beyond “call failed”. LiveKit Cloud drain helps deploys; it does **not** replace a liveness probe on the agent process for self-hosted / Render workers.

---

### F-L6 — Per-turn latency broadcast into the room

| Path | Current behaviour |
|---|---|
| **Worker** | `TurnLatencyTracker._publish` → `room.local_participant.publish_data(..., topic="turn_latency"|"metrics_updated")` with stage breakdown (`stt`, `llm`, `tts_ttfb`, `tool`, `e2e`). Also logs INFO server-side. |
| **SDK** | `sdk/src/index.ts` parses those topics and emits `turn_latency` / metrics events to the **browser host app**. |
| **Dashboard** | Audit notes dashboard does not render them — leak is still to any participant/SDK consumer in the room. |

**Industry:** Retell exposes latency aggregates to **operators**; broadcasting full stage timings to the **end-user browser** is unusual and helps fingerprint infrastructure.

---

### F-L10 — `_cartesia_agent_session_extra` dead alias

| Path | Current behaviour |
|---|---|
| `worker/main.py` | `_cartesia_agent_session_extra` → thin alias of `_tts_agent_session_extra` “kept for tests”. |
| `tests/test_cartesia_tts.py` | Still imports the alias name. |

Harmless clutter; fix is rename tests → canonical helper and delete alias.

---

### F-L15 — `_ensure_bucket` on every session end

| Audit claim | Code today |
|---|---|
| `list_buckets` / `create_bucket` every upload | **Partially fixed:** process-level `_bucket_ensured` cache (`None` / `True` / `False`) + `reset_bucket_ensure_cache()` for tests. Docstring explicitly cites F-L15. |
| Remaining gap | Still runs list/create on **first upload in process**, not at **startup/prewarm**; failed ensure caches `False` and retries next session (good) but no dedicated unit test asserting “second upload does not call list_buckets”. |

---

## 1. End-state definition of done

### F-M1 (Habiba worker) done when
1. Phase A inventory lists every Habiba production handler with disposition (log / narrow / leave+justify).  
2. No production `except Exception: pass` on Habiba worker I/O without WARNING+ context (or explicit `# noqa-f-m1: reason`).  
3. Tests cover at least: recording remove failure logs; identity load failure logs (or structured metric); tools client close failure logs.

### F-M15 done when
1. **[HUMAN GATE]** Product choice recorded (see §2 D3).  
2. Every remap (model ID or provider) emits a structured log: `requested=` / `effective=` / `reason=`.  
3. Capabilities / validation honesty matches choice (dead IDs deprecated or clearly marked non-runtime).  
4. Optional but preferred: session or mint response includes `effective_providers` for the live call.  
5. Unit tests for remap resolver + capabilities contract; one **[Manual]** call proving log lines.

### F-M24 done when
1. `UVA_DUMP_PROMPTS` defaults **off** in code + `.env.example`.  
2. INFO turn / live-speech logs are truncated and/or gated (`UVA_LOG_TRANSCRIPTS=0` default off in prod docs).  
3. Tests: dump skipped when unset/0; no full persona written.  
4. **[Manual]** Confirm staging worker env has dump off.

### F-M25 done when
1. **[HUMAN GATE]** Probe shape approved (see §2 D5).  
2. Worker exposes liveness (and ideally readiness: VAD loaded, LK creds present, optional DB ping).  
3. Documented curl + Docker/Render probe notes for Ehsan (Habiba does not own F-M9 Dockerfile alone).  
4. Unit/integration test for handler logic without needing a full LiveKit room.

### F-L6 done when
1. **[HUMAN GATE]** Product choice (see §2 D6).  
2. Default: end-user room does **not** receive stage breakdown (or only coarse e2e under opt-in).  
3. Server-side INFO latency logs remain for ops.  
4. SDK still safe if topics absent; tests updated.

### F-L10 done when
Alias removed; tests import `_tts_agent_session_extra` (or public name); cartesia tests pass.

### F-L15 done when
1. Process cache behaviour covered by unit test (list_buckets called ≤1 per process success path).  
2. Optionally ensure-at-prewarm (if cheap and keyed); document residual if first-upload-only is accepted.

---

## 2. Design decisions

| ID | Choice | Why | Gate? |
|---|---|---|---|
| D1 Scope | Habiba = worker Medium/Low only; portal F-M1 stays Ehsan | Matches priority-list split / Appendix A.3 ownership | — |
| D2 F-M1 bar | Prefer WARNING+ log over re-raise on best-effort paths; re-raise only where caller can abort safely | Matches audit fix text without turning soft paths into hard call kills | — |
| D3 F-M15 honesty | **Proposed default A:** Keep forced telephony/EN remaps (latency product), but (1) log every model remap in adapters, (2) stop advertising dead Groq IDs as selectable *runtime* models — mark `legacy_alias` or drop from picker list while validation still accepts old agent rows, (3) add `effective_*` fields on session start log + optional API later | Matches Retell/Vapi “explicit + observable”; avoids re-opening F-H10 #2 | **[HUMAN GATE]** before Phase D code ships |
| D4 F-M15 non-goal | Do not invent Urdu secondaries here | F-H10 residual | — |
| D5 F-M25 shape | **Proposed default:** small `aiohttp`/`http.server` thread or asyncio task on `UVA_WORKER_HEALTH_PORT` (default `0`=disabled, prod set e.g. `8081`) with `/healthz` + `/healthz/ready` | LiveKit CLI owns main process; sidecar port is standard for agent workers; mirrors control plane naming | **[HUMAN GATE]** port + Render/Docker with Ehsan |
| D6 F-L6 | **Proposed default:** `UVA_PUBLISH_TURN_LATENCY=0` default — keep server logs; hosts opt in for room publish | Stops accidental end-user leak; preserves debug for Habiba/demo | **[HUMAN GATE]** before Phase F |
| D7 F-M24 | Default dump **off**; transcript INFO behind flag default **off**; keep 200-char cap if flag on | Aligns with F-C4 / industry PII | Confirm staging env **[Manual]** |
| D8 F-L15 | Accept process cache as fix if tests prove ≤1 list; optional prewarm ensure | Avoid scope creep | — |
| D9 Phase order | A → B (M1) → C (M24) → D (M15) → E (M25) → F (L6) → G (L10/L15) → H closeout | Observability & PII before honesty API & probes; lows last | — |

---

## 3. Phased plan

Legend: **[Code]** agent/tests · **[Manual]** Habiba · **[HUMAN GATE]** must pause for product/ops sign-off · **[Ehsan]** shared / out of Habiba merge

---

### Phase A — Baseline & contracts (no behaviour change)

**Status (2026-09-19 Habiba):** **Done** — `docs/WAVE2-MEDIUM-LOW-PHASE-A-BASELINE.md` + Ehsan handoff §7–§9. Gates **A/A/A** signed; Render probe = Habiba later. **No runtime behaviour change in Phase A.**

**Goal:** Freeze line-backed inventories; lock human gates in writing.

#### A.1 F-M1 worker inventory
Table of every Habiba `except` in `worker/**` (exclude scripts): file:line, catch type, current body, disposition plan (log / narrow / leave+justify).

#### A.2 F-M15 remap matrix
Rows: trigger → requested → effective → already logged? → capabilities still advertise?

#### A.3 F-M24 / F-L6 / F-M25 / F-L10 / F-L15 one-pagers
Copy §0 tables into a short baseline doc if needed: `docs/WAVE2-MEDIUM-LOW-PHASE-A-BASELINE.md`.

#### A.4 Human gate questionnaire (blockers)
Record answers before D/E/F:

1. **F-M15:** Accept proposed D3-A, or require remaps become opt-in only, or require portal API field this wave?  
2. **F-M25:** Approve health port approach + who sets Render/Docker probe?  
3. **F-L6:** Default publish off vs remove SDK event entirely?

**Verify A**
- [x] **[Code]** Baseline doc matches current files (AST inventory + spot-check groq/gemini/telephony_tts/prompt_dump/latency publish/session_recording cache).  
- [ ] **[Manual]** Confirm no existing worker health port already in Render (Habiba at deploy).  
- [x] **[HUMAN GATE]** Written answers for A.4: **A / A / A** (2026-09-19).  
- [x] **[Code]** Ehsan Medium/Low exits in `WAVE2-EHSAN-HANDOFF.md` §7–§9.

**Exit A:** Baseline + gate answers. No production behaviour change.

---

### Phase B — F-M1 worker handler hardening

**Status (2026-09-19 Habiba):** **Done** — WARNING(+)/debug on A.1.1 inventory sites; justified leave for overlapped build cancel; tests `tests/test_fm1_worker_handlers.py` (6). Ehsan portal half still open (`WAVE2-EHSAN-HANDOFF.md` §7).

**Goal:** No silent swallows on Habiba production I/O.

#### B.1 Apply inventory dispositions
Priority order: `session_recording` (confirm), `latency` identity/parse, `tools` http close, `gemini` thinking_config, remaining `main.py` thin catches.

#### B.2 Logging contract
Include `room=` / `tenant_id=` / `stage=` when available. Prefer `logger.warning(..., exc_info=False)` unless unexpected.

#### B.3 Tests
- Force identity DB failure → expect warning (mock).  
- Force recording remove failure → warning (already partially there).  
- Tools aclose failure → warning.

**Verify B**
- [x] **[Code]** Unit tests green; whitelist `test_fm1_worker_handlers.py` in `pytest.ini`.  
- [x] **[Code]** Priority A.1.1 sites no longer silent `pass` (build-cancel leave justified).  
- [ ] **[Manual]** Optional: one local call, confirm no new ERROR spam on happy path.  

**Exit B:** Habiba F-M1 slice closable in priority list (note Ehsan half still open).

---

### Phase C — F-M24 log / dump PII defaults

**Status (2026-09-19 Habiba):** **Done** — `UVA_DUMP_PROMPTS` / `UVA_LOG_TRANSCRIPTS` default **off**; `.env.example` updated; `worker/transcript_logging.py`; tests `tests/test_fm24_prompt_transcript_logging.py` (8). Staging/prod env confirm = Habiba at deploy (not Ehsan).

**Goal:** Prod-safe defaults; debug opt-in.

#### C.1 Prompt dump default off
Change `prompt_dump.py` so unset / empty → **no write**. Keep explicit `1` for local debug. Update `.env.example`.

#### C.2 Transcript logging gate
Introduce `UVA_LOG_TRANSCRIPTS` (default off): when off, log only lengths / hashes / first N chars (document N). When on, keep ≤200 for conversation turns; live speech also capped.

#### C.3 Docs
One paragraph in worker runbook / `.env.example`: “never enable dump in shared prod disks”.

**Verify C**
- [x] **[Code]** Tests: default env → no file; `=1` → file contains markers.  
- [x] **[Code]** Tests: default → no full transcript in log message helpers.  
- [ ] **[Manual]** Staging env vars confirmed dump/transcripts off (Habiba at deploy — code default is already off if unset).  
- [x] **[HUMAN GATE]** D7 accepted with Phase A Gate answers.  

**Exit C:** F-M24 Habiba worker ✅ (central log-platform retention may remain ops residual — not Ehsan Wave 2 blocker).

---

### Phase D — F-M15 provider / model honesty

**Status (2026-09-19 Habiba):** **Done** (Gate **A**) — adapter remap logs; `models` vs `legacy_aliases`; validation accepts both; `effective_providers` session log; public API exposes `legacyAliases`. Tests `tests/test_fm15_provider_honesty.py`. Portal UI field deferred (Gate A). Manual live EN/Urdu calls = Habiba optional residual.

**Goal:** Remaps observable; capabilities not lying about runtime.

#### D.1 Adapter logging
In `groq.build` / `gemini.build`: if `requested != resolved`, log WARNING or INFO with reason (`dead_model` / `deprecated_id`).

#### D.2 Capabilities contract (per gate)
- **If D3-A:** Split advertised list into `runtime_models` vs `legacy_aliases` (or drop dead IDs from tenant picker validation path while worker still remaps old rows).  
- Document in capabilities module docstring.

#### D.3 Effective providers on session
At minimum structured log after `resolve_effective_providers`. Stretch: persist JSON on `sessions` or return via existing mint metadata — **only if gate asked**.

#### D.4 Tests
Remap matrix unit tests; capabilities snapshot test; no silent groq collapse without log assertion.

**Verify D**
- [x] **[Code]** Unit tests (`test_fm15_provider_honesty.py` + validation suite).  
- [ ] **[Manual]** One EN telephony (or forced remap) call — logs show requested→effective (Habiba when convenient).  
- [ ] **[Manual]** One Urdu call — **no** English Cartesia/Groq remap (regression).  
- [x] **[Ehsan]** Gate A — **no** portal `effective_providers` work; picker auto-uses shorter `models` list.  

**Exit D:** F-M15 Habiba ✅ under signed D3-A; API portal field residual (not this wave).

---

### Phase E — F-M25 worker health / readiness

**Status (2026-09-19 Habiba):** **Done** (Gate **A**) — `worker/health_http.py`; wired after prewarm in `worker/main.py`; `.env.example` docs; tests `tests/test_fm25_worker_health.py` (7). **Render probe = Habiba later.** Optional Dockerfile HEALTHCHECK snippet for Ehsan F-M9 in handoff §9.

**Goal:** Probeable worker process.

#### E.1 Health module
e.g. `worker/health_http.py`: `/healthz` → `{status, service, active_jobs?}`; `/healthz/ready` → VAD singleton loaded? LK env present? optional DB `SELECT 1`.

#### E.2 Wire from `main.py` / prewarm
Start only if `UVA_WORKER_HEALTH_PORT` > 0. Bind `127.0.0.1` by default; document `0.0.0.0` for container probes.

#### E.3 Docs for Ehsan
Snippet for Docker `HEALTHCHECK` / Render health path — Habiba does not merge Ehsan Dockerfile unless asked.

**Verify E**
- [x] **[Code]** Handler unit tests (ready unhealthy when creds missing).  
- [ ] **[Manual]** Local: set port, `curl` liveness while worker idle (Habiba when convenient).  
- [x] **[Ehsan]** Render = Habiba; optional Dockerfile HEALTHCHECK only (handoff §9).  

**Exit E:** Habiba code ✅; prod probe ✅ when Habiba sets Render/env (not Ehsan).

---

### Phase F — F-L6 latency room publish

**Status (2026-09-19 Habiba):** **Done** (Gate **A**) — `UVA_PUBLISH_TURN_LATENCY` default **off**; server INFO kept; tests `tests/test_fl6_turn_latency_publish.py`. SDK unchanged (safe when topics absent). Manual browser confirm = Habiba residual.

**Depends on:** Phase A **[HUMAN GATE]** D6.

**Goal:** No accidental end-user stage leak.

#### F.1 Gate publish
`UVA_PUBLISH_TURN_LATENCY` default `0`. When `0`, skip `_publish` (keep server INFO). When `1`, current behaviour.

#### F.2 SDK
No break if topics missing; optional docs note “opt-in worker flag”. Avoid Wave 1 SDK freeze conflicts — worker-only fix is enough for F-L6 §9 WHERE.

#### F.3 Tests
Tracker does not call `publish_data` when flag off; does when on.

**Verify F**
- [x] **[Code]** Unit tests with mock room.  
- [ ] **[Manual]** Browser call with flag off — SDK receives no `turn_latency` (or host confirms).  
- [ ] **[Manual]** Flag on — debug still works for Habiba.  

**Exit F:** F-L6 ✅ (Habiba code); manual browser residual optional.

---

### Phase G — Low cleanup (F-L10 + F-L15)

**Status (2026-09-19 Habiba):** **Done** — F-L10 alias removed; F-L15 once-per-process ensure covered by `tests/test_fl15_bucket_ensure.py`. Optional prewarm ensure **not** added (D8: first-upload-only accepted).

**Goal:** Dead alias gone; bucket ensure proven once-per-process.

#### G.1 F-L10
Update `tests/test_cartesia_tts.py` imports; delete `_cartesia_agent_session_extra`.

#### G.2 F-L15
Add unit test: two uploads → `list_buckets` once on success path. Optional: call ensure from `prewarm` if Supabase env present (best-effort WARNING on fail).

**Verify G**
- [x] **[Code]** cartesia + recording tests green.  
- [x] **[Code]** No remaining references to alias in `*.py`.  

**Exit G:** F-L10 + F-L15 ✅.

---

### Phase H — Closeout

**Status (2026-09-19 Habiba):** **Done** — priority-list honesty; regression **55 passed**; closeout `docs/WAVE2-MEDIUM-LOW-PHASE-H-CLOSEOUT.md`. No separate Medium/Low Ehsan file (existing `WAVE2-EHSAN-HANDOFF.md` §7–§9).

#### H.1 Priority list status
Update `docs/UVA-PRIORITY-LIST.md` honestly (Habiba ✅ vs Ehsan residual for F-M1 portal / F-M25 deploy).

#### H.2 Regression
Run whitelisted pytest set touched by this track + prior Wave 2 worker tests.

#### H.3 Handoff
Short `docs/WAVE2-MEDIUM-LOW-EHSAN-HANDOFF.md` only if Ehsan must wire health probes or portal picker copy — do not dump unrelated Ehsan tickets.

**Verify H**
- [x] **[Code]** Regression pass count recorded (**55 passed**, 2026-09-19).  
- [x] **[Manual]** Spot-check each finding status row (Habiba — see closeout H.1 table).  
- [x] Review subagent (or peer) on final diff.  

**Exit H:** Track closed for Habiba Medium/Low list above.

---

## 4. Human intervention map (quick reference)

| When | Who | What |
|---|---|---|
| End of Phase A | Habiba + product | Sign D3 (M15), D5 (M25), D6 (L6) |
| Phase C | Habiba ops | Confirm staging `UVA_DUMP_PROMPTS=0` |
| Phase D | Habiba | Manual remap + Urdu non-remap calls |
| Phase E | Habiba + **Ehsan** | Port/bind + deploy HEALTHCHECK |
| Phase F | Habiba | Browser confirm no leak / opt-in works |
| Phase H | Habiba | Priority list honesty; no false full ✅ |

---

## 5. Explicit residuals (do not fake ✅)

- Ehsan half of F-M1 (control_plane / telephony_credentials / webhooks).  
- Central log platform retention / SIEM (beyond worker defaults).  
- F-H10 Urdu second provider (#2) — still product-parked.  
- Mid-call provider hot-swap (Retell-class) — out of scope.  
- Full portal “effective providers” UI — unless D3 gate demands it this wave.  
- F-M9 Docker `HEALTHCHECK` ownership — Ehsan; Habiba only documents worker path.

---

## 6. Suggested calendar (indicative)

| Phase | Effort (Habiba) |
|---|---|
| A | 0.5–1 day |
| B | 1 day |
| C | 0.5–1 day |
| D | 1–2 days after gate |
| E | 1 day after gate (+ Ehsan deploy) |
| F | 0.5 day after gate |
| G | 0.5 day |
| H | 0.5 day |

---

## 7. First action after plan approval

Start **Phase A** only: write `docs/WAVE2-MEDIUM-LOW-PHASE-A-BASELINE.md` from §0 with live line numbers, then ask the three **[HUMAN GATE]** questions — **no behaviour change until gates return**.
