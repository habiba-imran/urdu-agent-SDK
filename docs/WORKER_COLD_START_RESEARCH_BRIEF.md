# Worker Cold Start — Self-Contained Research Brief for Claude

**Purpose:** Research what Habiba can still improve on the **worker** so time-to-first-greeting feels snappy — **without** touching Ehsan’s control-plane work and **without** humanization/TTFT work.

**This document is self-contained.** Do not ask the user for other repo files. Everything you need about ownership, current code behavior, already-shipped fixes, remaining levers, and constraints is below. Propose designs and an ordered plan; do not implement unless asked.

**Out of scope for this research:**
- Humanization (Cartesia emotion tags, spoken-output prompts, history window, Groq 429 mid-call) — separate Habiba ticket
- Control-plane mint/dispatch TLS handshake — **Ehsan only**
- Portal, CI, npm package metadata — Ehsan
- Per-turn voice-to-voice after the greeting (LLM TTFT) — humanization/TTFT ticket

**In scope:** Everything after the LiveKit **job is assigned to the worker** until the caller **hears the first greeting audio** — and anything Habiba can do in `worker/**` (and optionally local `demo-app/` smoke) to shrink that.

---

## 1. Ownership freeze (do not violate)

| Owner | Wave 1 cold-start related work | Paths |
|-------|--------------------------------|-------|
| **Habiba** | Worker greeting path / time-to-first-greeting after room exists | `worker/main.py`, `worker/greeting_cache.py`, `worker/session_opening.py`, `worker/latency.py` (prewarm/turn), `worker/config.py`, `worker/db_pool.py`, `worker/provider_client_cache.py`, `worker/stale_jobs.py`, `worker/providers/**` if needed for warm clients |
| **Ehsan** | Mint → agent job assignment latency | `control_plane/app.py` **only** `_run_dispatch_background` (~lines 419–445) and the `_dispatch_agent` helper it calls |

### Ehsan’s ticket (DO NOT DESIGN CHANGES HERE — describe as fixed floor only)

Every browser/PSTN session mint eventually calls background dispatch:

```text
_run_dispatch_background(room, tenant, agent, greeting?)
  → asyncio.run(_dispatch_agent(...))     # NEW event loop per dispatch
      → async with LiveKitAPI(...) as lkapi:   # NEW TLS client per dispatch
            await lkapi.agent_dispatch.create_dispatch(...)
```

**Why it matters:** Fresh `asyncio.run` + new `LiveKitAPI` TLS handshake sits on the critical path from “session mint returned” to “worker job starts.” Audit called this a concrete contributor to “>20s to first audio.”

**Ehsan’s intended fix (for your awareness only):** Replace per-call `asyncio.run` + new `LiveKitAPI` with an **app-lifespan singleton LiveKitAPI** + async background task (no drive-by CORS/dev-mint edits).

**Your research must:**
- Treat CP dispatch latency as an **external floor** Habiba cannot remove
- Optimize **worker-side** stages so that once the job arrives, first audio is as fast as possible
- Never propose edits under `control_plane/`

---

## 2. What “cold start / time-to-first-greeting” means

Two different latencies (do not conflate):

| Metric | Meaning | Owner |
|--------|---------|-------|
| **Mint → job assigned** | Host/CP creates room + dispatches agent | Mostly Ehsan (dispatch) + host mint |
| **Job assigned → first audible greeting** | Worker connects, builds pipeline, `session.start`, speaks | **Habiba** |

Product feel for demos is often **button → first audio** = mint + dispatch + worker. Habiba owns only the worker half.

**Aspirational worker-side target (from historical latency checklist):**  
Static greeting path: first audible greeting **≤ ~3 s after track publish** when worker is warm and greeting is static (no LLM). Historical baseline before Habiba Wave 1 cold-start work was far worse (join→track ~10.7 s; button→greeting ~28 s in one staging capture — includes mint + self-serve + worker).

---

## 3. End-to-end timeline (browser demo)

```text
[Host] POST session mint
   → CP creates LiveKit room + session row + JWT
   → CP schedules _run_dispatch_background  ……… EHSAN FLOOR (TLS + asyncio.run)
   → returns { token, wsUrl, roomName, … } to browser

[Browser] LiveKit Room.connect + mic

[LiveKit Cloud] assigns job to idle worker process/thread

[Worker] entrypoint(ctx)                         ……… HABIBA FROM HERE
   1. ctx.connect()                              # must be within ~10s of job_entry
   2. parse dispatch metadata (tenant/agent/greeting) OR DB identity
   3. overlap: stale check (skipped if fresh dispatch metadata)
   4. build_session: load config, build STT/LLM/TTS/VAD, schedule provider prewarm
   5. build_agent (prompt assembly — ignore humanization for this research)
   6. session.start(...)                         # publishes agent audio track
   7. await short prewarm gate (0 / 1s / 2s depending on greeting cache)
   8. apply_session_opening: session.say(static) OR generate_reply OR wait
   9. first PCM hits the room → caller hears greeting
```

**Critical Habiba insight already encoded in code comments:**  
Do **not** `await wait_for_participant()` before the opening greeting. LiveKit may wait until the participant is fully ACTIVE (seconds after the browser already shows “connected”). That was a Habiba-side ~10 s gap. Current code starts greeting after `session.start` while participant wait runs in parallel when early identity exists.

---

## 4. What Habiba already shipped (treat as current baseline)

Do not re-propose these as new ideas unless you are improving them further.

### 4.1 Greeting PCM cache
- **Module:** in-process LRU `GreetingAudioCache` (max 32 entries)
- **Key:** `(agent_id, tts_provider, provider_voice_id, hash(greeting_text), audio_channel)`
- **Hit:** skip TTS websocket prewarm; `session.say(text, audio=cached_frames)` — no live TTS RTT
- **Miss:** schedule async cache fill; await up to **1.0 s** TTS/STT prewarm; then live `session.say(text)`
- **Limits:** process-local (multi-worker / redeploy = cold); only helps `mode=say` (static greeting text); first call after boot is always miss

### 4.2 Prewarm gate shortened
- Cache hit: **0 s** wait (was historically up to 5 s default)
- Static greeting miss: **1.0 s** budget
- `generate_reply` opening (no static greeting): **2.0 s** budget
- LLM prewarm never blocks greeting (background only; Groq LLM prewarm skipped entirely for TPM)

### 4.3 Provider client cache (thread-local)
- Keyed by language/provider/model/voice/options/channel
- Reuses STT/LLM/TTS plugin instances across sequential jobs on the same Windows THREAD job runner
- Cuts `build_ms` when the same agent/provider combo repeats on a warm process

### 4.4 DB connection reuse
- Process-local locked `psycopg` connection for config/stale/identity hot path
- Avoids 1–3 s cross-region TLS on every lookup when pooler is remote

### 4.5 Agent config TTL cache
- Key `(tenant_id, agent_id)`, TTL **30 s**
- Tradeoff: longer TTL risks stale empty greeting after prepare sync → accidental `generate_reply` (LLM on turn zero)

### 4.6 Entrypoint ordering
- `ctx.connect()` first (LiveKit requires ~10 s)
- Fresh dispatch metadata → skip Supabase stale check
- Early identity from dispatch metadata → `build_session` + `session.start` + opening **before** awaiting participant
- Mint-time `greeting` in dispatch metadata preferred over racing DB `agents.greeting`

### 4.7 Interruption / session.start cost
- Default `UVA_INTERRUPTION_MODE=vad` (local Silero) — skips LiveKit Cloud adaptive-detector init on `session.start` (often multi-second)
- Recording default **off** unless `UVA_SESSION_RECORD_AUDIO=1` — saves seconds on `session.start` in local demos (prod must set env if recordings required)

### 4.8 Plugin import prewarm
- At process `__main__`, imports google/silero/groq/gladia/deepgram/cartesia/elevenlabs/fishaudio/rime/… so `Plugin.register_plugin` runs on real main thread (Windows THREAD executor quirk)

### 4.9 Static greeting path
- If `agents.greeting` / mint greeting present → `session.say` (TTS-only, no LLM) — UVA-10 intent
- If missing → `generate_reply` (LLM+TTS) — **still slow for first audio**

---

## 5. Worker code map (behavior, not “open these files”)

### 5.1 Entrypoint sequence (`worker/main.py::entrypoint`)
1. Time `ctx.connect()` → log `connect_ms`
2. `parse_dispatch_metadata(job.metadata)` → may include `tenant_id`, `agent_id`, `greeting`, `direction`
3. `abandon_stale_job_if_needed(skip_db=from_dispatch is not None)` as background task
4. Resolve `audio_channel` webrtc vs telephony
5. `early_md = from_dispatch or _early_session_identity(...)`
6. If `early_md`: parallel `wait_for_session_participant`; `build_session` → `build_agent` → `_setup_and_start` → `_await_opening_and_speak`
7. Else (e.g. some SIP inbound): wait for participant first, then build

### 5.2 `build_session`
- `asyncio.to_thread(load_agent_session_bundle)` — config + provider voice id (cached 30 s)
- Optional mint greeting override → force `first_speaker=agent`
- Telephony remaps: force Cartesia TTS; EN Gemini→Groq if key present (latency policy; not humanization research)
- `build_components_cached(runtime_cfg)` — thread-local plugin cache
- If static greeting: check greeting PCM cache → maybe `skip_tts` on provider prewarm; else `schedule_greeting_cache_fill`
- `schedule_provider_prewarm(tts, llm, stt, skip_tts=...)` — returns Task; LLM warm always background
- Construct `AgentSession` with VAD singleton, turn_handling, conn timeouts 30 s, TTS sanitizer transforms when Cartesia/Rime
- Log split timers: `config_ms`, `components_ms`, `components_cache_hit`, `session_ctor_ms`, `total_ms`

### 5.3 `_await_opening_and_speak`
- `plan_greeting_prewarm` → decide wait + cached frames
- Optionally `await_greeting_prewarm(task, timeout=plan.prewarm_timeout)`
- `apply_session_opening(..., greeting_audio=...)`
- Log `opening_mode`, `greeting_cache_hit`, `prewarm_wait_ms`, `ms_since_connect`

### 5.4 Opening modes (`session_opening.py`)
| Mode | When | First audio cost |
|------|------|------------------|
| `wait` | `first_speaker != agent` | No greeting |
| `say` | Non-empty greeting text | TTS-only; cache hit = PCM replay |
| `generate_reply` | No greeting | **LLM TTFT + TTS** — worst cold greeting |

### 5.5 Provider prewarm (`latency.py`)
- `prewarm_tts` / `prewarm_stt`: call plugin `.prewarm()` on event loop (not `to_thread` — websocket pools need running loop)
- `prewarm_llm`: one-token chat; **skipped for Groq** (TPM)
- Greeting path awaits TTS+STT only; LLM always fire-and-forget after

### 5.6 Stale jobs (`stale_jobs.py`)
- `request_fnc` accepts immediately (must not DB-block accept — AssignmentTimeout)
- After connect: DB stale check unless `skip_db` for fresh dispatch
- Participant wait timeout default 90 s (env override)

### 5.7 VAD
- Process singleton Silero with `min_silence_duration=0.35`, etc.
- Loaded in `prewarm` / first use — not per-job reload when singleton hot

---

## 6. Measured / known pain points (context for prioritization)

Historical staging capture (pre many Habiba fixes; still useful for stage names):

| Stage | Order of magnitude | Notes |
|-------|--------------------|-------|
| Host/CP mint | ~5–6 s class when Render cold | Includes CP; Ehsan/host |
| Worker join → audio track | was ~10.7 s | Habiba UVA-2 target |
| Button → first greeting | was ~28 s | Sum of mint + worker + track |
| `build_ms` on warm/2nd call | reported ~4 s class in research notes | Config fetch + plugin construct; caches should shrink this |
| Stale DB check | ~2–3 s class if not skipped | Now skipped on fresh dispatch |
| `session.start` | multi-second if adaptive interruption / recording on | vad mode + record off help |
| Greeting prewarm | was up to 5 s | Now 0/1/2 s by plan |
| Static vs generate_reply | generate_reply adds LLM TTFT | Demo agents should have static greeting |

**Logged worker fields to use in any plan:**  
`connect_ms`, `build_ms` / `config_ms` / `components_ms` / `session_ctor_ms`, `start_ms`, `prewarm_wait_ms`, `ms_since_connect`, `greeting_cache_hit`, `opening_mode`, `components_cache_hit`.

---

## 7. Remaining Habiba levers (research these — ranked by likely impact)

These are **hypotheses to evaluate**, not prescriptions. Prefer changes that improve **first call after worker boot** and **cache-miss** paths, not only 2nd-call cache hits.

### A. First-call / cache-miss greeting (high)
- Pre-synthesize greeting PCM **before** first Connect (e.g. on worker idle after config known, or during mint-adjacent prepare — **without** touching CP dispatch)
- Warm common demo agent greeting into cache at process prewarm if agent id known via env
- Parallelize cache fill with `session.start` more aggressively so miss path doesn’t serialize TTS twice
- Ensure demos **always** set static `greeting` (avoid `generate_reply` on turn zero) — product/config guidance + worker guardrails?

### B. `session.start` cost (high)
- Confirm adaptive interruption never accidentally on in demo
- Recording default: document prod env; avoid RecorderIO on critical path
- Anything else LiveKit AgentSession initializes lazily that can move to process prewarm?

### C. `build_session` / plugin construction (high–medium)
- Process-level (not only thread-local) safe client shells for default EN stack Gladia/Deepgram + Groq + Cartesia?
- Proactive construct of **default demo combo** inside `prewarm()` into `proc.userdata` / process cache
- Split and attack whichever of `config_ms` vs `components_ms` still dominates after current caches
- Voice ID resolution: avoid DB when slug prefixes already map locally (partially done)

### D. DB / region (medium)
- Confirm transaction pooler usage; connection already reused — any remaining sync connects on greeting path? (shutdown paths still open fresh connections — OK if off greeting path)
- Config TTL vs stale greeting race — smarter invalidation on greeting sync instead of short TTL?

### E. Opening path structure (medium)
- Can greeting PCM publish **before** full AgentSession start in some LiveKit patterns? (may be impossible — research LiveKit agents APIs)
- Can STT prewarm be deferred until after greeting for static-say mode? (today STT still warms on miss path; on cache hit skip TTS but STT may still run in schedule_provider_prewarm — verify if STT warm blocks greeting unnecessarily)

### F. Windows / idle process (medium–dev)
- Ensure idle job processes stay warm (`num_idle_processes`); Windows THREAD vs PROCESS behavior
- Avoid measuring “new tid every connect” as prod truth if it’s local spawn artifact

### G. Explicitly NOT Habiba
- `_run_dispatch_background` singleton LiveKitAPI
- Render CP cold start / keeping CP warm
- Host mint path duration (except demo-app local smoke Habiba already owns)
- Humanization prompt size / Groq ITPM / history window

---

## 8. Constraints and safety

1. **File freeze:** Habiba Wave 1 worker files OK; **do not** edit `control_plane/`, `tenant_portal_api/`, `.github/`, `sdk/package.json` / README ownership for Ehsan.
2. **LiveKit accept deadline:** never put slow DB before `req.accept()` or before `ctx.connect()`.
3. **Greeting text is untrusted DATA** — sanitize for TTS provider; never inject into system instructions.
4. **Provider clients:** cache transport shells only; do not share mutable per-call stream state across concurrent jobs/threads unsafely. Windows uses THREAD job runners — thread-local cache exists for that reason; process-global sharing needs concurrency analysis.
5. **Telephony:** Rime→Cartesia and Gemini→Groq remaps change effective providers; greeting cache keys include provider+voice+channel.
6. **Recording:** flipping default off is a product behavior change; call it out if recommending prod defaults.
7. **Do not invent F-* IDs.** This is the Wave 1 delivery item “Worker cold start / time-to-first-greeting.”

---

## 9. Success criteria for your research output

Return:

1. **Stage diagram** of Habiba-owned ms from job start → first audio, with which stages are already mitigated vs still open.
2. **Ranked improvement list** (impact × effort × risk), Habiba-only.
3. For top 3: concrete design (where in worker architecture), failure modes, how to measure with existing log fields.
4. **What will still feel slow** after Habiba-only work (Ehsan floor + mint + network) — be honest so demos aren’t oversold.
5. **Do-not-do list** (including anything that touches CP dispatch or humanization).
6. Optional: minimal demo-app / agent-config checklist so Connect always uses static greeting + warm worker.

Search LiveKit agents docs/issues for: prewarm_fnc, proc.userdata, publishing audio before participant active, AgentSession.start cost, TTS prewarm, idle processes — and map findings onto **this** architecture (dynamic per-agent providers, Windows THREAD, greeting PCM cache already present).

---

## 10. Paste-ready prompt for Claude

> You are researching **worker cold start / time-to-first-greeting** for AwaazLabs UVA. Read the full brief in this message (self-contained). Habiba owns the worker path after LiveKit assigns the job; Ehsan owns `control_plane` `_run_dispatch_background` (`asyncio.run` + per-dispatch `LiveKitAPI`) — do not propose CP changes. Humanization/TTFT is out of scope. Habiba already shipped greeting PCM cache, shortened prewarm gates, thread-local provider client cache, DB pool, 30s config cache, connect-first entrypoint, skip stale DB on fresh dispatch, greeting before wait_for_participant, vad interruption default, optional recording off. Research what else Habiba can do in `worker/**` so first greeting audio is fast on **first** call and cache miss—not only warm second calls—and deliver a ranked plan with measurement via existing worker latency logs. Be brutally honest about the remaining Ehsan/mint floor.
