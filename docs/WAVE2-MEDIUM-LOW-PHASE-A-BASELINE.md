# Wave 2 Medium + Low — Phase A baseline + contracts

**Date:** 2026-09-19  
**Owner (this artifact):** Habiba  
**Plan:** `docs/WAVE2-MEDIUM-LOW-IMPLEMENTATION-PLAN.md`  
**Ehsan handoff (shared Wave 2, including Medium/Low exits):** `docs/WAVE2-EHSAN-HANDOFF.md` §7–§9  

**Phase A goal:** Freeze “what is true today” with line-backed inventories and human-gate questions. **No runtime behaviour change.**

| Item | Status |
|---|---|
| A.1 F-M1 worker `except` inventory | **Done** (this doc §A.1) |
| A.2 F-M15 remap matrix | **Done** (this doc §A.2) |
| A.3 F-M24 / F-M25 / F-L6 / F-L10 / F-L15 one-pagers | **Done** (this doc §A.3) |
| A.4 Human gates | **Signed 2026-09-19** — Gate1 **A**, Gate2 **A**, Gate3 **A**; deploy probe owned by **Habiba** (later) |
| Worker health port already in repo/deploy? | **No evidence in git** — no `UVA_WORKER_HEALTH*`; `docker/worker.Dockerfile` has **no** `HEALTHCHECK`; Render wiring = Habiba later (not Ehsan) |

---

## A.1 — F-M1 Habiba worker silent / opaque handlers

**Method:** AST walk of every `except` in `worker/**/*.py` on 2026-09-19 (**104** handlers total). This section does **not** reprint all 104 rows; it freezes (1) audit delta, (2) Phase B priority queue, (3) leave/OK categories. Re-run the AST inventory in Phase B before editing if lines drift. Portal / control_plane / telephony handlers are **Ehsan** (Appendix A.3 + priority-list split) — listed only as out-of-scope reminder.

**Audit Appendix A.3 (historical worker rows) vs today:**

| Audit site | Today |
|---|---|
| `session_recording.py` storage delete `pass` | **Fixed** — WARNING with path (`~116–122`) |
| `latency.py` bare `return None` | **Still present** (identity / metadata parse) |
| `latency.py` RuntimeError / Exception `pass` | **Still present** (barge-in interrupt; LLM prewarm) |
| `main.py` timeout returns / VAD `pass` | **Still present** (line numbers shifted) |
| `tools.py` http close `pass` | **Still present** (`~178–179`) |
| `gemini.py` thinking_config `pass` | **Still present** (`~74–75`) |

### A.1.1 Phase B priority (Habiba) — silent or opaque production paths

These are the handlers Phase B should change first (log WARNING+ with context, or narrow the catch). Disposition is a **plan**, not yet implemented.

| File:line | Catch | Body today | Proposed disposition |
|---|---|---|---|
| `worker/latency.py:125–126` | `Exception` | telephony metadata JSON → `return False` (no log) | Log debug/warning once; keep False |
| `worker/latency.py:166–167` | `Exception` | `load_session_identity` DB → `return None` (no log) | WARNING with `room=` |
| `worker/latency.py:184–185` | `Exception` | `parse_dispatch_metadata` JSON → `return None` | debug/warning; keep None |
| `worker/latency.py:347–348` | `Exception` | `prewarm_llm` → `pass` | WARNING (prewarm skipped) |
| `worker/latency.py:316–317` | `RuntimeError` | barge-in `interrupt` → `pass` | debug or WARNING once; justify if leave |
| `worker/tools.py:178–179` | `Exception` | httpx `aclose` → `pass` | WARNING |
| `worker/providers/llm/gemini.py:74–75` | `Exception` | `ThinkingConfig(thinking_budget=0)` → `pass` | WARNING (thinking not disabled) |
| `worker/main.py:1486–1487` | `Exception` | VAD `preload_vad` in prewarm → `pass` | WARNING (first call pays cold start) |
| `worker/main.py:1495–1496` | `Exception` | DB prewarm `select 1` → `pass` | WARNING |
| `worker/main.py:879–880` | `Exception` | `db_conn.close` after caller phone → `pass` | WARNING |
| `worker/db_pool.py:44–45` | `Exception` | cached conn `close` → `pass` | WARNING |
| `worker/db_pool.py:80–81` | `Exception` | rollback in `_normalize_idle` → `pass` | WARNING |
| `worker/greeting_cache.py:294–295` | `Exception` | sanitize greeting text for cache seed → `pass` (falls through with unsanitized text) | WARNING; skip seed or continue unsanitized with log |
| `worker/session_close.py:119–120` | `Exception` | conn close best-effort → `pass` | Leave+justify **or** WARNING (close path already ERROR-stages) |
| `worker/main.py:1093–1094` | `(CancelledError, Exception)` | nested → `pass` | Inspect; likely cancel swallow — justify or log |

### A.1.2 Already logged (no Phase B change required unless review finds gaps)

Examples (not exhaustive): most of `session_recording.py`, `session_close.py` ERROR stages, `session_retention.py`, `stale_jobs.py` warning paths, `caller_identity.py`, `recording_disclosure.py`, `provider_retries.py`, `latency.py` publish/prewarm TTS/STT warnings (`~468+`, `~715`).

### A.1.3 Intentional narrow / non-swallow (leave)

| Pattern | Examples | Why leave |
|---|---|---|
| `ImportError` fallback import | `main.py`, `session_close.py`, `stale_jobs.py`, `session_recording.py` | Alternate import path |
| `ValueError` env/parse defaults | `write_tool_gate.py`, `provider_retries.py`, `humanization/*` | Invalid env → safe default |
| Timeout / cancel abort | `main.py` `TimeoutError`/`RuntimeError` → `return` on wait paths | Expected control flow |
| Re-raise after log | `session_close` connect failures return status; `stale_jobs` timeouts re-raise | Caller acts |

### A.1.4 Out of Habiba scope (Ehsan)

From audit Appendix A.3 (still Ehsan unless reassigned):

- `control_plane/app.py` Sentry init `pass`; `/v1/voices` → fake catalogue `pass`
- `tenant_portal_api/telephony_credentials.py` re-encryption `pass`
- `tenant_portal_api/telephony_webhooks.py` event insert `pass`
- `tenant_portal_api/telnyx_client.py` `pass`
- `admin/audit.py` → `return None`

See `WAVE2-EHSAN-HANDOFF.md` §7.

---

## A.2 — F-M15 provider / model substitution matrix

| Trigger | Requested | Effective | Logged today? | Capabilities still advertise requested? |
|---|---|---|---|---|
| Groq dead model ID in agent row / env | e.g. `llama-3.3-70b-versatile`, `qwen/qwen3.6-27b`, … (`_DEAD_GROQ_MODELS` in `groq.py:43–52`) | `GROQ_LLM_MODEL` or fallback live model (`openai/gpt-oss-20b` default path) | **No** log inside `groq.build()`. After pipeline build, `main.py:371–376` logs `llm model remapped` **only if** `cfg.llm_model != getattr(components.llm,"model")` | **Yes** — dead IDs still in `capabilities.py` groq `models` list (`~144–154`) with comment that remaps happen at session start |
| Empty / missing Groq model | `""` / unset | live default | Same as above | N/A |
| Deprecated Gemini model | e.g. `gemini-2.5-flash` → map in `_DEPRECATED_GEMINI_MODELS` (`gemini.py:27–35`) | `GEMINI_LLM_MODEL` / `gemini-3.6-flash` | Same post-build remap log in `main.py` if attribute differs; **no** log inside `gemini.build()` | **Yes** — both `gemini-3.6-flash` and `gemini-2.5-flash` listed (`~112–114`, `~136–138`) |
| Telephony TTS Rime/Fish | `rime` / `fish_audio` on `audio_channel=telephony` | Cartesia + fixed telephony voice IDs (`telephony_tts.force_cartesia_for_telephony`) | **Yes** — `main.py:249–256` WARNING when `cartesia_forced` | Capabilities still list rime/fish as en TTS; remap is channel-forced, not capabilities lie about existence |
| Telephony LLM Gemini→Groq (EN) | `gemini` on telephony, non-Urdu, `GROQ_API_KEY` set | `groq` + `TELEPHONY_GROQ_MODEL` | **Yes** — `main.py:257–264` WARNING when `groq_forced` | Capabilities still show gemini selectable |
| EN WebRTC Gemini→Groq | `UVA_FORCE_GROQ_ENGLISH` default **on** (`telephony_tts.py:108–110`) | Groq | Same `groq_forced` WARNING | Same |
| Urdu | any of the above Groq/Cartesia force paths | **Exempt** — telephony helpers return unchanged for `ur` / Uplift | N/A (no remap) | ur still single Gladia/Gemini/Uplift |
| Unknown provider | n/a | `UnsupportedProviderError` (`registry.py`) | Raises | Not substituted |

**Resolver:** `worker/humanization/resolve.py` `resolve_effective_providers` — single wrap: Cartesia force → Groq telephony → Groq English WebRTC.

**No durable `effective_*` on session row / mint response today** (grep: only logs + in-memory `EffectiveProviders`).

---

## A.3 — Other Habiba findings (one-pagers)

### A.3.1 F-M24 — prompts / transcripts in logs + disk

| Path | Evidence |
|---|---|
| Dump default **on** | `prompt_dump.py:33` — `(os.getenv("UVA_DUMP_PROMPTS") or "1")`; off only for `0/false/no/off` |
| Dump contents | Full system + effective persona + **raw DB persona** to `docs/last_session_prompt.txt` (or `UVA_DUMP_PROMPTS_PATH`) |
| Call site | `main.py` `dump_session_prompt(...)` during agent build (`~134`) |
| Env example | `.env.example:69` documents `UVA_DUMP_PROMPTS=1` |
| Turn logs | `main.py` conversation turns truncated to **200** chars (`~934–938`); **live user speech** logs full `transcript` at INFO (`~940–944`) |
| Retention | Dump file + app logs **not** covered by F-C4 media purge |

### A.3.2 F-M25 — worker health / readiness

| Path | Evidence |
|---|---|
| Control plane | `/healthz`, `/healthz/deep`, `/healthz/warm` — `control_plane/app.py:130+` |
| Portal / admin | `/healthz` present |
| Worker | `python -m worker.main` → LiveKit `WorkerOptions` + `cli.run_app` — **no** HTTP server in worker package |
| Docker | `docker/worker.Dockerfile` CMD starts worker; **no** `HEALTHCHECK` directive |
| Env | No `UVA_WORKER_HEALTH_PORT` (or similar) in `.env.example` |
| Render | **Not confirmed from this repo** — Habiba must ask ops before assuming prod probes |

### A.3.3 F-L6 — latency broadcast into room

| Path | Evidence |
|---|---|
| Publish | `TurnLatencyTracker._publish` → `publish_data` topics `turn_latency` + `metrics_updated` (`latency.py:702–767`) — **unconditional** (no env gate) |
| Payload | Includes `turn_latency_breakdown` stage ms (`build_turn_latency_payload`) |
| Server log | INFO line with e2e/stt/llm/tts/tool (`~747–758`) — keep for ops even if publish gated later |
| SDK | `sdk/src/index.ts` emits `turn_latency` when data received |
| Wire | `main.py:1207` `wire_turn_latency(session_obj, ctx.room, …)` |

### A.3.4 F-L10 — Cartesia alias

| Path | Evidence |
|---|---|
| Alias | `main.py:691–695` `_cartesia_agent_session_extra` → `_tts_agent_session_extra` |
| Production callers | Pipeline uses `_tts_agent_session_extra` (`~452`) |
| Tests | `tests/test_cartesia_tts.py` still imports alias name |

### A.3.5 F-L15 — bucket ensure

| Path | Evidence |
|---|---|
| Cache | `_bucket_ensured: bool \| None` + `reset_bucket_ensure_cache()` (`session_recording.py:18–25`) |
| Behaviour | If `_bucket_ensured is True`, skip list/create; on success set True; on failure set False and return False (retry next session) |
| When list runs | First upload attempt per process (not startup/prewarm) |
| Tests | `reset_bucket_ensure_cache` imported in `tests/test_recording_policy.py`; **no** assertion found that `list_buckets` is called ≤1 across two uploads |

---

## A.4 — Human gates (answer before Phases D / E / F)

Proposed defaults are in the plan §2 (D3 / D5 / D6). **Reply with A / B / C (or your own words).** Phase A docs are done either way; **code for D/E/F must not start until these are signed.**

### Gate 1 — F-M15 honesty (blocks Phase D)

**What this is about (plain language):**  
Today we sometimes change the AI model or voice provider for English phone/browser calls so the call stays fast (e.g. Gemini → Groq, Rime → Cartesia). Some of that is already logged. But the “menu” of models we show tenants still lists old Groq model names that do not actually run. That can look like we promised one vendor/model and ran another.

**Choose one:**

- **A (recommended):** Keep the forced speed remaps. Add clear logs for every model remap. Stop advertising dead Groq IDs as live picker choices (still accept old agent rows by remapping). Optional later: show “what actually ran” on the session.  
- **B:** Make remaps **opt-in only** (env/agent flag); if unset, run exactly what the tenant configured (may be slower / fail on dead IDs).  
- **C:** Same as A, **plus** portal/API must expose `effective_providers` this wave (needs Ehsan portal work).

**Your answer:** **A** (2026-09-19)

### Gate 2 — F-M25 worker health (blocks Phase E)

**What this is about:**  
The control-plane API has a `/healthz` URL so deploy platforms know it is alive. The voice **worker** process does not. If the worker wedges, you only find out when a call fails.

**Choose one:**

- **A (recommended):** Habiba adds a small HTTP probe on `UVA_WORKER_HEALTH_PORT` (default off; prod sets e.g. `8081`) with `/healthz` + `/healthz/ready`. Ehsan wires Docker/Render `HEALTHCHECK` / health path when Habiba lands the code.  
- **B:** Different approach (describe): e.g. only LiveKit Cloud metrics, no HTTP.  
- **C:** Defer F-M25 this wave (document residual).

**Also answer:** Who sets the Render/Docker probe — you, Ehsan, or jointly? **Habiba (later)** — Ehsan does not own Render probe wiring.

**Your answer:** **A** (2026-09-19)

### Gate 3 — F-L6 latency in the browser (blocks Phase F)

**What this is about:**  
Every turn, the worker sends internal timing breakdown (STT/LLM/TTS ms) into the LiveKit room. The browser SDK can read it. That leaks how our pipeline is built to end users (or any client in the room). Server logs already have the same timings for us.

**Choose one:**

- **A (recommended):** Default **off** (`UVA_PUBLISH_TURN_LATENCY=0`). Keep server logs. Hosts/devs turn the flag on when debugging.  
- **B:** Remove room publish entirely (no opt-in).  
- **C:** Keep publishing as today (accept the leak; close F-L6 as won’t-fix — not recommended).

**Your answer:** **A** (2026-09-19)

### Manual (non-blocking for Phase B/C, needed before claiming prod F-M24/F-M25)

1. Confirm staging/prod worker env for `UVA_DUMP_PROMPTS` (today code default is on if unset).  
2. Confirm whether any worker health probe already exists **outside** git (Render dashboard).

---

## A.5 — Phase A exit checklist

- [x] **[Code]** Inventories line-backed against current tree (2026-09-19).  
- [x] **[Code]** Ehsan Medium/Low exits written into `WAVE2-EHSAN-HANDOFF.md`.  
- [x] **[HUMAN GATE]** Gates 1–3 answered **A / A / A** (2026-09-19).  
- [ ] **[Manual]** Render worker health / dump env confirmed (Habiba at deploy time).  

**No production behaviour change in Phase A.**

**Next:** Phase B F-M1 worker logging per §A.1.1 (in progress / landed separately).
