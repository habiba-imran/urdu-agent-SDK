# UVA Worker Latency Fix Checklist

**Audience:** UVA / Finova worker team (`python -m worker.main`, session control plane on Render)  
**Context:** Browser test-call instrumentation (Mar 2026) on tenant `urdu-agent-sdk-1`  
**Self-serve repo scope:** Dashboard backend configures agents and mints sessions; **STT → LLM → TTS runs entirely on UVA.**

This document lists **upstream issues only** — items already fixed or owned in this repo are noted for context but are not action items here.

---

## Target budgets (product spec)

From [`AwaazLabs-SelfServe-Spec.md`](./AwaazLabs-SelfServe-Spec.md) §1.5:

| Metric | P50 target | P95 target |
|--------|------------|------------|
| **Voice-to-voice** (user stops → first agent audio) | **≤ 800 ms** | **≤ 1200 ms** |
| STT (streaming partial) | 150–300 ms | — |
| Turn detection / EOU | minimize | — |
| LLM time-to-first-token | ~600 ms | — |
| TTS time-to-first-byte (once text exists) | ≤ 150 ms | — |

**Measured on staging web call (pre-fix baseline):**

| Metric | Measured | Gap vs target |
|--------|----------|---------------|
| `/session` total (after self-serve greeting-cache fix) | ~6.1s est. | Mint still ~5.6s |
| Worker join → audio track published | **~10.7 s** | Critical |
| Button → first greeting audio | **~28.4 s** | Critical |
| Turn 1 voice-to-voice | **8.6 s** | 10× over P50 |
| Turn 2 voice-to-voice | **4.8 s** | 6× over P50 |
| First TTS VAD burst after user stop | **9–12 s** gap | Critical |
| Inter-chunk gaps during agent speech | **~400 ms** | Choppy playback |

Reference room from baseline capture: `b37e3b5c-b197-4a79-9a3c-c6bd6bb5371e`  
Agent: `0a20a104-b69f-4ffa-8631-12ab2624fcbc` (Lena, Cartesia TTS, Gemini 2.5 Flash, Deepgram Nova-3)

---

## Already fixed in self-serve repo (not UVA work)

| Item | Savings |
|------|---------|
| Skip redundant `greeting_sync` on `/session` when prepare already synced same text | **~2.7 s** per Connect |
| Session latency instrumentation (`latencyTrace`, frontend debug panel) | Diagnostics only |

Remaining Connect time after that fix is dominated by **UVA dev-mint** and **worker behavior below**.

---

## Priority 1 — Critical (blocks “usable” latency)

### UVA-1. Session mint / dev-mint is too slow (~5.6 s)

**Symptom:** Backend log shows `mint_start` → `mint_end` ≈ **5,645 ms** on first attempt; frontend `session_responseMs` ≈ **8.8 s** total (before greeting-cache fix).

**Evidence:**
```
[VOICE-LATENCY] mint_start +3193ms { attempt: 1 }
[VOICE-SESSION ✅] Dev-mint success room=b37e3b5c-...
[VOICE-LATENCY] mint_end +8838ms
```

**Likely causes:**
- Render cold start on control plane (`urdu-agent-sdk-1.onrender.com`)
- Worker pool not warm before mint completes
- Dev-mint path doing full worker provisioning synchronously before returning token

**Fix goals:**
- P50 mint **≤ 1.5 s** when control plane is warm
- P95 mint **≤ 3 s**
- Return LiveKit token as soon as room exists; worker join may complete asynchronously **but** audio track must follow quickly (see UVA-2)

**Verify:**
- Backend `[VOICE-LATENCY] mint_end` − `mint_start`
- Frontend `session_response.sessionResponseMs`

---

### UVA-2. Worker joins room but delays publishing audio track (~10.7 s)

**Symptom:** LiveKit participant appears (`agent_ready`) long before any audio track is subscribed.

**Evidence (frontend t+ ms from Connect click):**
```
t+14249ms  agent_ready (remote_participant_joined)
t+24998ms  agent_track_subscribed   ← +10,749 ms gap
t+28423ms  first_agent_audio
```

**Impact:** Dominates “time to hear greeting” even after session mint returns.

**Likely causes:**
- Worker connects to room before TTS/greeting pipeline is ready
- Greeting synthesis blocking track publish instead of publishing track first
- Worker initialization (model load, TTS websocket connect) on critical path after join
- Cartesia websocket not pre-warmed at worker start

**Fix goals:**
- **Agent audio track published ≤ 2 s** after worker participant join
- **First audible greeting ≤ 3 s** after track publish (static greeting — no LLM)

**Verify:**
- Frontend: gap between `agent_ready` and `agent_track_subscribed`
- LiveKit room inspector: time from participant join to first audio track

---

### UVA-3. Voice-to-voice turn latency 5–9 s (target ≤ 800 ms)

**Symptom:** Long dead air after user finishes speaking.

**Evidence:**
```
t+34222ms  user_stopped_speaking
t+42823ms  voice_to_voice = 8601 ms (turn 1)

t+56433ms  user_stopped_speaking
t+61224ms  voice_to_voice = 4791 ms (turn 2)
```

**Pipeline stages to inspect (worker-internal):**
1. STT finalization / end-of-utterance
2. LLM TTFT (Gemini 2.5 Flash)
3. Tool calls (`lookup_business_info`, scheduling) — extra round-trips
4. TTS time-to-first-byte
5. Audio chunk streaming to LiveKit

**Fix goals:**
- P50 voice-to-voice **≤ 800 ms** for simple turns (no tools)
- P50 **≤ 1200 ms** for tool/RAG turns
- P95 **≤ 1200 ms** / **≤ 1800 ms** respectively

**Verify:**
- Frontend `voice_to_voice` events
- Worker-emitted `turn_latency` with per-stage breakdown (see UVA-7)

---

### UVA-4. TTS not streaming — multi-second silence before first chunk

**Symptom:** Agent eventually speaks, but first audio burst arrives after **9–12 s** of silence; then ~400 ms gaps between bursts.

**Evidence:**
```
audio_vad_chunk_gap  timeSincePreviousChunkMs: 11999  (turn 1)
audio_vad_chunk_gap  timeSincePreviousChunkMs: 9600   (turn 2)
audio_continuity_report  diagnosis: upstream_vad_or_rtp_gaps
  interBurstGapsMs: [11999, 400, 399, 399]
```

**Spec requirement ([§1.3.3](./AwaazLabs-SelfServe-Spec.md)):**
> TTS must stream audio the moment the first tokens are generated.

**Likely causes:**
- LLM waits for full completion before TTS starts (no token streaming)
- TTS waits for full sentence/paragraph buffer
- Cartesia/Rime websocket not used in streaming mode
- Worker batches audio before RTP send

**Fix goals:**
- TTS TTFB **≤ 150 ms** after first speakable LLM token
- No gap **> 200 ms** between audio chunks during a single utterance (except intentional pauses)

**Verify:**
- Worker logs: first LLM token timestamp vs first TTS byte vs first RTP packet
- Frontend `audio_vad_chunk_gap` / `audio_continuity_report`

---

## Priority 2 — High (observability + pipeline tuning)

### UVA-5. Emit per-turn stage metrics on every turn

**Symptom:** Browser never received `turn_latency_breakdown` with `llmMs`, `ttsMs`, `sttMs`, `turnMs` on test call.

**Spec requirement ([§1.5](./AwaazLabs-SelfServe-Spec.md)):**
> The pipeline emits per-stage timing on every turn.

**Fix:**
- Send `DataReceived` / room metadata payload on each turn, e.g.:
  ```json
  {
    "type": "turn_latency",
    "e2eMs": 720,
    "sttMs": 200,
    "turnMs": 80,
    "llmMs": 360,
    "ttsMs": 80,
    "ttsTtfbMs": 75,
    "toolMs": 0,
    "toolName": null
  }
  ```
- Include `toolMs` and `toolName` when RAG/scheduling tools run

**Verify:**
- Frontend debug: `turn_latency_breakdown`
- Self-serve analytics ingest

---

### UVA-6. Turn detection / end-of-utterance tuning

**Symptom:** May contribute to delayed LLM start; hard to isolate without worker metrics.

**Spec notes ([§1.3.2](./AwaazLabs-SelfServe-Spec.md)):**
- Mis-tuned VAD + separate EOU can add **200–600 ms**
- Deepgram Flux / EagerEndOfTurn are documented alternatives

**Fix goals:**
- Turn/EOU stage **≤ 150 ms** median on test recordings
- Do not wait for excessive trailing silence before triggering LLM

**Verify:**
- Worker `turnMs` in telemetry
- A/B on identical audio: Nova-3 + LiveKit EOU vs Deepgram Flux

---

### UVA-7. LLM TTFT optimization (Gemini 2.5 Flash)

**Symptom:** Likely largest share of turn delay when tools are not invoked.

**Current config (from self-serve):**
- `llmProvider: gemini`
- `llmModel: gemini-2.5-flash`
- System prompt ≈ **10,137 chars (~2,535 tokens)** on test agent

**Fix goals:**
- LLM TTFT **≤ 600 ms** P50 for non-tool turns
- **No reasoning/thinking mode** on live voice path
- Prompt caching enabled for stable system prompt prefix

**Worker actions:**
- Confirm model string resolves to flash, not pro/3.x reasoning
- Stream tokens to TTS immediately (ties to UVA-4)
- Log TTFT per turn

**Verify:**
- Worker `llmMs` / TTFT in `turn_latency` events

---

### UVA-8. Tool / RAG path latency

**Symptom:** Knowledge questions may add full tool round-trip before TTS can start.

**Architecture:**
```
User question → LLM decides tool → HTTP POST self-serve /api/tools/lookup_business_info
  → embedding + Supabase vector search → LLM again → TTS
```

**Self-serve RAG timing (when tool fires):** logged as `[RAG-TIMING]` in backend terminal.

**Worker actions:**
- Emit `toolMs` in turn telemetry when tools run
- Do not invoke `lookup_business_info` for greetings, scheduling intake, or answers already in prompt
- Consider parallel tool prefetch for predictable intents (optional)

**Verify:**
- Backend `[RAG-TIMING]` lines during call
- Compare voice-to-voice on “hello” vs “what are your hours?”

---

## Priority 3 — Medium (cold start + reliability)

### UVA-9. Render / control plane cold start

**Symptom:** First request after idle can take **~30 s** (documented in [`staging-live-dial-runbook.md`](./staging-live-dial-runbook.md)).

**Evidence:** Greeting sync to Render agents API ≈ **2.7 s** even when warm; mint adds **~5.6 s**.

**Fix goals:**
- Keep worker + control plane warm on staging during demo hours
- Health ping should warm worker pool, not just HTTP process
- Consider always-on minimum instances for voice tenant

**Verify:**
- Second call within 5 min vs first call after 30 min idle

---

### UVA-10. Static greeting path must bypass LLM entirely

**Symptom:** Turn-zero should be TTS-only; total time to first audio was still **~28 s** in baseline (mint + track delay dominate, but worker must not add LLM on greeting).

**Self-serve already sends:**
- `greeting_mode: static`
- `greeting` / `custom_greeting` at session mint

**Worker actions:**
- Confirm turn-zero uses precomputed greeting text only
- Do not call Gemini before first spoken line
- Pre-synthesize or stream greeting TTS immediately on join

**Verify:**
- Worker logs: no LLM call before first `first_agent_audio`
- Turn 0 voice-to-voice N/A; measure join → first audio only

---

### UVA-11. Cartesia TTS websocket warm-up

**Current TTS on test agent:** Cartesia (`ttsProvider: cartesia`, voice `f014dce5-...`)

**Spec expectation:** Cartesia Sonic 3.5 TTFB **~75–90 ms** over WebSocket.

**Worker actions:**
- Open Cartesia websocket at worker start or agent session start, not first utterance
- Use streaming endpoint; do not wait for full MP3/buffer
- Log `ttsTtfbMs` separately from total `ttsMs`

**Verify:**
- Worker telemetry vs Cartesia dashboard latency

---

### UVA-12. LiveKit audio publish path

**Symptom:** Browser saw `audio_playback_element { type: "waiting" }` — may indicate delayed RTP arrival.

**Worker actions:**
- Publish audio track as soon as pipeline starts (even if first chunk is milliseconds later)
- Ensure Opus frame pacing is steady (avoid batching large buffers)
- Confirm worker uses same LiveKit cloud region as room (`urdu-voice-agent-sdk-22to3tyc.livekit.cloud`)

**Verify:**
- LiveKit server-side participant metrics
- Frontend `agent_track_subscribed` → `first_agent_audio` gap

---

## Priority 4 — Lower (quality + future-proofing)

### UVA-13. Barge-in and audio flush

Self-serve frontend intentionally does **not** flush agent audio on barge-in (avoids distortion). True interrupt handling must happen **upstream**.

**Worker actions:**
- Stop TTS generation and clear outbound audio buffer on user speech
- Cancel in-flight LLM/TTS when user interrupts

---

### UVA-14. Deepgram STT streaming + partial LLM feed

**Spec ([§1.3.3](./AwaazLabs-SelfServe-Spec.md)):** Partial STT must feed LLM as it arrives.

**Worker actions:**
- Confirm partial transcripts reach LLM before EOU when safe
- Evaluate Deepgram Flux for integrated EOU (spec §1.3.2 decision D1)

---

### UVA-15. Concurrent room / 429 handling

Staging enforces low concurrent room cap (429 retries observed in self-serve).

**Worker actions:**
- Fast room teardown when browser disconnects
- Ensure worker exits room promptly on session end

---

## Suggested fix order (UVA team)

| Order | ID | Issue | Est. user impact |
|-------|-----|-------|------------------|
| 1 | UVA-2 | Publish audio track quickly after join | **~10 s** off time-to-greeting |
| 2 | UVA-1 | Faster dev-mint / warm worker pool | **~3–5 s** off Connect |
| 3 | UVA-4 | Stream TTS on first LLM token | Fixes choppy speech + long pre-audio silence |
| 4 | UVA-3 | End-to-end turn budget | **~4–8 s** off each reply |
| 5 | UVA-5 | Emit stage metrics | Unblocks tuning |
| 6 | UVA-7 | LLM TTFT | Turn latency |
| 7 | UVA-8 | Tool path discipline | Knowledge turns only |
| 8 | UVA-6 | EOU tuning | 200–600 ms potential |
| 9 | UVA-9 | Render cold start | First call after idle |
| 10 | UVA-10–12 | Greeting + Cartesia + LiveKit hardening | Polish |

---

## Acceptance test script (repeat after each UVA fix)

1. Restart self-serve backend; hard-refresh frontend.
2. Open Test Agent drawer; wait for `prepare_end`.
3. Click Connect; record:
   - `session_responseMs` (target **≤ 3 s** warm)
   - `agent_ready` → `agent_track_subscribed` (target **≤ 2 s**)
   - `first_agent_audio` (target **≤ 5 s** from Connect click, warm path)
4. Say: **“Hello”** — record `voice_to_voice` (target **≤ 800 ms**).
5. Say: **“What are your hours?”** — record `voice_to_voice` + check backend for `[RAG-TIMING]` (target **≤ 1200 ms** if RAG fires).
6. Confirm `turn_latency_breakdown` appears with `llmMs`, `ttsMs`, `sttMs`.
7. Confirm no `audio_vad_chunk_gap` **> 500 ms** during agent speech.

---

## References in this repo

| Doc / code | Relevance |
|------------|-----------|
| [`docs/AwaazLabs-SelfServe-Spec.md`](./AwaazLabs-SelfServe-Spec.md) §1.3–1.5 | Latency budgets, streaming requirement |
| [`docs/staging-live-dial-runbook.md`](./staging-live-dial-runbook.md) | Worker must be running; Render cold start |
| [`backend/src/routes/voice.ts`](../backend/src/routes/voice.ts) | Session mint, agent config |
| [`backend/src/voice/greeting-sync-cache.ts`](../backend/src/voice/greeting-sync-cache.ts) | Self-serve greeting sync skip |
| [`frontend/src/lib/uva-voice.ts`](../frontend/src/lib/uva-voice.ts) | Browser latency instrumentation |
| [`frontend/src/hooks/use-voice-session.ts`](../frontend/src/hooks/use-voice-session.ts) | Debug panel + `voice_to_voice` |

---

## Summary

**Self-serve dashboard is no longer the Connect bottleneck** after greeting-sync caching. Perfect latency requires UVA to:

1. **Mint sessions faster** and keep workers warm.
2. **Publish audio immediately** after joining a room.
3. **Stream LLM → TTS → LiveKit** with no multi-second buffering.
4. **Hit ≤ 800 ms voice-to-voice** on simple turns.
5. **Emit per-stage telemetry** so regressions are visible.

Until UVA-2 and UVA-4 are fixed, users will perceive multi-second delays regardless of frontend or self-serve backend optimizations.
