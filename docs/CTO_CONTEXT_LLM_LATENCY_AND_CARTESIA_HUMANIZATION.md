# Context Brief: Voice Agent LLM Latency & Cartesia Humanization

**Purpose:** Standalone research context for leadership. Readable without opening either codebase. Repos exist only as optional reference if someone later wants to verify implementation details.

**Products in scope:**
- **Agent platform (UVA)** — LiveKit voice worker that runs STT → LLM → TTS for real calls
- **Self-Serve demo app** — onboarding UI, agent provisioning, browser voice test, business tools API

**Evidence window:** September 2026 (live web + PSTN sessions, provider rate-limit responses, in-session latency telemetry)

**How numbers are labeled:**
- **Measured** — observed in our live logs / telemetry
- **Inferred** — strong engineering conclusion, not a controlled study
- **Open** — explicitly needs further research or a commercial decision

---

## Executive summary

We run a **cascaded** voice agent (separate speech-to-text, language model, and text-to-speech), not a single realtime multimodal model. End-to-end “caller stopped talking → first audible reply” is therefore the sum of several stages. In practice:

1. **Gemini** (current Flash-class models) is too slow on first token for English phone voice. We measured multi-second time-to-first-token; Cartesia TTS first audio is fine (~0.1–0.2s), so Gemini was dominating silence.
2. **Groq + Qwen 3.6 27B** brings first-token latency into a usable range (~1s on a healthy turn) but hits a hard **free-tier input-token-per-minute ceiling (~7,000 ITPM)**. Front-desk prompts + tool schemas + chat history mean each turn requests ~3,000+ input tokens. Turn two in the same minute often 429s and the call feels broken.
3. **Cartesia humanization** (Sonic 3.5, Katie voice, emotion/pause markup from the LLM) works and keeps TTS fast, but the platform instructions that teach the model to emit emotion tags are a **fixed input-token tax on every turn**, competing with the same Groq free-tier budget.

**Bottom line for research:** latency and humanization are coupled through **tokens per turn** and **billing tier**, not only through “pick a faster model.”

---

## 1. System architecture (conceptual)

### 1.1 Critical split of responsibility

| Layer | What it does | Runs STT / LLM / TTS? |
|-------|----------------|------------------------|
| Self-Serve app | Create/update agents, mint LiveKit room credentials, browser test UI, optional business tools (availability, booking, FAQ lookup) | **No** |
| Agent platform worker | Joins the LiveKit room, streams audio, runs the turn loop | **Yes — always** |
| LiveKit | Media + signaling (WebRTC for browser, SIP for phone) | Transport only |
| Telnyx | PSTN carrier into LiveKit SIP | Transport only |

**Implication:** Fixing “the demo sounds slow” or “the phone is silent” almost always means changing the **shared worker pipeline**, not the Self-Serve React app. Self-Serve can only change defaults (which model/voice is stored on the agent), prompt assembly at provision time, and tool backends.

### 1.2 Two entry paths, one brain

```
Browser tester                    Phone caller
     │                                 │
     │  HTTP: mint session             │  PSTN
     ▼                                 ▼
Self-Serve ──► LiveKit Cloud ◄── Telnyx / SIP
                     │
                     ▼
              Agent platform worker
              VAD → STT → LLM → TTS
              (+ optional HTTP tools)
                     │
                     ▼
              Audio back to user
```

| Channel | How audio arrives | Same worker? | Notable differences |
|---------|-------------------|--------------|---------------------|
| Web test | Browser ↔ LiveKit WebRTC | Yes | Can start LLM early while user still speaking (preemptive) — **disabled when using Groq** to save tokens |
| Telephony | Telnyx → LiveKit SIP → worker | Yes | English Gemini agents are **forced to Groq** at session start; TTS forced to Cartesia if the agent was still on a slower telephony TTS; preemptive LLM **off**; barge-in tuned for no browser echo cancellation |

### 1.3 Per-turn pipeline

```
User speaks
  → Capture + network into LiveKit
  → Voice activity detection (when did they stop?)
  → Streaming speech-to-text
  → End-of-turn commit
  → Build LLM request:
        platform system rules
      + tenant persona (business facts)
      + full conversation history so far
      + tool definitions (if tools enabled)
  → LLM streams tokens
  → Optional: model calls a tool → HTTP to Self-Serve → second LLM pass to speak the result
  → Text cleanup (strip markdown; keep emotion/pause tags for Cartesia)
  → Text-to-speech streams audio
  → Playback (browser or back through SIP/PSTN)
```

**Multiple LLM calls per user turn:** yes, whenever a tool is used (decide tool → wait for tool → speak). A normal FAQ answer from the persona is one LLM call.

---

# ISSUE 1 — LLM LATENCY

## 2. Current LLM setup

### 2.1 What we use today

| Language | Allowed LLM providers | Runtime default (English voice) |
|----------|----------------------|----------------------------------|
| English | Google Gemini, Groq | **Groq · Qwen 3.6 27B** |
| Urdu | Gemini only | Gemini Flash-class (Groq not offered for Urdu) |

Self-Serve prefers Groq over Gemini when provisioning English demo agents. The portal’s English create path also defaults toward Groq + Qwen.

### 2.2 Model ID churn (important for vendors)

Providers retire model IDs often. We keep older names in pickers so existing agents still validate, then **remap at session start** to a live model:

| Family | What agents may still store | What actually runs |
|--------|-----------------------------|--------------------|
| Gemini | 2.5 Flash, 2.0 Flash, 3.1 Flash Lite, etc. | Current Flash default (**3.6 Flash** class), unless env override |
| Groq Llama / older Qwen / Kimi / Scout | Including **Llama 3.1 8B Instant** | Current Groq default (**Qwen 3.6 27B**) |
| Groq GPT-OSS 20B / 120B | Still listed | Remapped to Qwen unless explicitly allowed (OSS burns tokens on a reasoning channel) |

**Vendor fact:** Groq decommissioned **Llama 3.1 8B Instant** (and related Llama IDs) on **16 Aug 2026**. We briefly considered it as a cheaper free-tier default; it is **not** usable.

### 2.3 What goes into every LLM request

| Piece | Sent every turn? | Notes |
|-------|------------------|-------|
| Platform system instructions | Yes | Tool discipline, latency rules, **Cartesia speaking rules** (emotion tags, etc.) |
| Tenant persona | Yes | Business identity, safety/911, intake rules, custom directives; **runtime-shrunk on Groq** when oversized |
| Conversation history | Yes | Full session history today — **no sliding window yet** |
| Tool JSON schemas | Yes, if tools configured | Large fixed cost even when unused that turn |
| Completion budget | Capped short | Groq default ~96 completion tokens (spoken replies stay short) |

**Streaming:** yes — tokens stream into TTS as soon as available (with a low-latency sentence splitter so Cartesia does not wait for huge buffers).

**Retries:** provider adapters avoid aggressive retry on Groq (retries burn the same TPM window). The LiveKit session layer may still retry 429s, which the caller experiences as multi-second dead air.

**Warm-up:** on telephony we warm TTS (and often LLM) before the greeting so the first utterance does not pay a cold websocket / cold first-token penalty.

### 2.4 Telephony-specific LLM policy

For **English phone** sessions, if the agent is still configured as Gemini and a Groq API key is present, the worker **rewrites the session to Groq + Qwen** before the call proceeds. Reason: measured Gemini first-token latency dominated voice-to-voice delay; Cartesia was not the bottleneck.

Urdu calls keep Gemini.

---

## 3. Gemini investigation

### 3.1 Why Gemini was in play

- Historical default for many English agents and still the only path for Urdu.
- No Groq free-tier ITPM ceiling.
- Flash branding suggests “voice-suitable” speed (vendor marketing — not our measurement).

### 3.2 What we actually tried / observed

| Model / class | What happened | Label |
|---------------|---------------|-------|
| Gemini 3.1 Flash Lite | Multi-second TTFT on PSTN; one analysis cited ~4.3s | Measured / logged |
| Gemini 2.0 Flash | Returned **404** for current keys (retired ID) | Measured |
| Gemini 2.5 Flash | Still advertised in product capabilities; remapped at runtime | Measured (remap) |
| Gemini 3.6 Flash | Current remap target; still **~1.5–3s+** first token even with thinking set to minimal | Measured (ops + code commentary from live runs) |
| Extreme outliers | Cold / misconfigured path reported ~tens of seconds TTFT in earlier debugging | Measured (spot), not a baseline |

**Configuration knobs we applied:** longer HTTP timeout (vendor/plugin default was too short and timed out in demos), disable/minimize thinking, lower temperature, short max output tokens. These help variance and cost; they did **not** bring English telephony into an acceptable first-token band.

### 3.3 Effect on the voice agent

When Gemini TTFT is 1.5–4+ seconds, the caller hears a long pause after they stop speaking even if STT and TTS are fast. That reads as “the agent is broken,” not “the model is thinking.”

### 3.4 Decision

| Keep Gemini for | Do not use Gemini for (current policy) |
|-----------------|----------------------------------------|
| Urdu | English telephony when Groq is available |
| Fallback if no Groq key | Primary English voice latency path |

### 3.5 Open (Gemini)

- Paid / Vertex / regional routing — can TTFT approach ~sub-second consistently?
- Any remaining lite SKU on current keys that beats 3.6 Flash TTFT?
- Formal p50/p95 table over ≥50 turns (we have spot evidence, not a published latency study).

---

## 4. Groq + Qwen investigation

### 4.1 Why Groq

After Gemini dominated pause time, we needed a provider with much lower time-to-first-token for cascaded English voice, using an integration we already had (OpenAI-compatible Groq endpoint via LiveKit).

### 4.2 Models exercised

| Model | Role | Outcome |
|-------|------|---------|
| GPT-OSS 20B on Groq | Early voice candidate; low reasoning effort | Speakable content could be ~0.5s class when healthy, but **reasoning tokens + TPM** made free tier worse → remapped away by default |
| Qwen 3.6 27B | Current default | **Kept.** Thinking/reasoning channel disabled so completion budget is spoken text (needed for Cartesia tags + short replies) |
| Llama 3.1 8B Instant | Tried as cheaper ITPM default | **Rejected** — decommissioned by Groq 16 Aug 2026 |
| Other listed Groq IDs (32B Qwen, Llama 3.3, Scout, Kimi) | Picker compatibility | Remap to Qwen default |

### 4.3 Latency comparison (spot)

| Condition | LLM first token | End-to-end (stop → first audio) | TTS first audio | Label |
|-----------|-----------------|-----------------------------------|-----------------|-------|
| Groq Qwen, healthy turn, no tool | ~**993 ms** | ~**3.7 s** | ~**142 ms** | Measured (one instrumented turn) |
| Gemini on telephony (typical) | **~1.5–3 s+** | Dominated by LLM | Cartesia still ~0.1–0.2 s when warm | Measured / ops |
| Groq after TPM 429 | Retries / wait **several seconds** | Feels hung | N/A | Measured |

**Quality:** not formally scored. Operationally, Qwen + Cartesia emotion tags produce usable receptionist turns when not rate-limited.

### 4.4 Rate limits (the real Groq failure mode)

On Groq **free / on_demand** for our org:

| Metric | Value | Label |
|--------|-------|-------|
| Input tokens per minute | **7,000 ITPM** | Measured (429 body) |
| Tokens requested per turn (before aggressive prompt shrink) | ~**3,700–3,800** | Measured |
| Tokens requested per turn (after shrink) | ~**3,250** | Measured |
| Pattern | Turn 1 OK; turn 2 within the same minute often `Used + Requested > 7000` → **429** | Measured |

So Groq is not “failing to think.” It is **too expensive per turn on free tier** for a front-desk agent with rich system rules, tools, and history.

### 4.5 What we already changed to reduce tokens / latency

1. **Runtime persona compaction on Groq** — keep business facts and safety; drop long rule sections that duplicate platform instructions; stub appointment intake; strip duplicate emergency triage text.
2. **Self-Serve prompt profiles at assemble time** — “free tier compact” vs “voice optimized” vs “legacy full” (smaller knowledge digest and shorter boilerplate when compact).
3. **Disable preemptive generation** for Groq and for telephony — cancelled partial turns were burning TPM before end-of-utterance.
4. **Short completion cap** + Qwen reasoning off.
5. **Remap GPT-OSS** unless explicitly allowed.
6. **Slim tool results** before the second LLM pass (short voice summary, not huge JSON).
7. **Prompt dump for debugging** — shows what is actually sent vs raw DB persona (raw is debug-only; not billed twice).

**Result:** persona sent dropped from ~9.6k characters raw to ~3.5k effective after compact; per-turn request size fell but **still ~3.2k**, so two turns still break a 7k ITPM window.

### 4.6 Decision

| Status | Model / approach |
|--------|------------------|
| Selected for English voice default | Groq · Qwen 3.6 27B |
| Rejected as default | Gemini on EN telephony; GPT-OSS; Llama 8B Instant |
| Optional overrides | Pin another Groq model; allow GPT-OSS explicitly |

### 4.7 Open (Groq)

- Move to **Dev / paid tier** — commercial ITPM vs free.
- **History truncation** (not built yet).
- **Fewer tools** on free-tier demos (schema cost).
- Whether another live Groq model offers better free ITPM at acceptable quality (vendor matrix).

---

## 5. Full latency breakdown

### 5.1 Two different “latencies”

| Term | Meaning |
|------|---------|
| **LLM latency** | Time from request to first model token (and generation after that) |
| **End-to-end conversational latency** | Time from caller end-of-speech to **first audible** agent audio |

Product feel is end-to-end. Optimizing only “LLM ms” while ignoring 429 waits, end-of-turn detection, or tool round-trips will mislead.

**Aspirational target (engineering commentary, not a formal SLO):** keep the LLM contribution near **≤800 ms** on telephony so Cartesia’s ~150 ms first audio can yield a snappy feel. Gemini routinely missed that; healthy Groq is near ~1 s (close but above); free-tier 429s miss it catastrophically.

### 5.2 What we measure today

We aggregate LiveKit stage metrics per turn and log:

- STT-related delay  
- End-of-utterance / turn delay  
- LLM time-to-first-token  
- TTS time-to-first-byte  
- Tool execution time (if any)  
- Composite end-to-end (prefer wall clock from “user stopped” to TTS first audio when available)

These can also be published into the browser session for the web tester. We do **not** yet have a warehouse of p50/p95 across production.

### 5.3 Stage-by-stage

| Stage | Exists? | Typical / known | Sequential? | Optimization notes |
|-------|---------|-----------------|-------------|--------------------|
| Caller speaks / device capture | Yes | Unknown ms | — | Device-dependent |
| Network into LiveKit | Yes | Unknown | Parallel with VAD | Region / network |
| VAD (stop detection) | Yes | Tuned ~0.35 s silence gate | Continuous | Already tightened; trade false cuts |
| End-of-turn commit | Yes | Min delay ~0.15 s (cap higher) | After stop | Faster = more cutoffs |
| STT streaming + finalize | Yes | Often near-zero extra if already final | Overlaps speech | Provider choice |
| Build prompt / context | Yes | CPU tiny; **token size** dominates provider | Before LLM | Compaction, tools, history |
| LLM queue + TTFT + generation | Yes | Groq ~1 s healthy; Gemini 1.5–3 s+; 429 = multi-second | Blocks speech start when preemptive off | **Largest healthy-path lever**; **largest broken-path lever = TPM** |
| Stream sanitize | Yes | Negligible | With TTS | — |
| Tool HTTP | Optional | Connect ≤1 s, read ≤4 s hard caps | Between two LLM calls | Backend SLA + tool discipline |
| Second LLM (after tool) | Optional | Another ~0.8–1.5 s Groq TTFT class | After tool | Avoid unnecessary tools |
| TTS first audio | Yes | ~135–220 ms warm Cartesia | After first tokens | Warm socket (done); low-latency tokenizer (done) |
| Playback / PSTN jitter | Yes | Unmeasured | After TTS | Carrier |

### 5.4 What usually dominates

1. **Healthy Groq, no tool:** LLM first token is the largest single measured component; TTS is small; e2e still multi-second because of turn detection + generation + pipeline.
2. **Gemini English phone:** LLM first token dominates.
3. **Groq free tier under load:** **429 retry delay** dominates — not model speed.
4. **Tool turns:** add tool HTTP + a full second LLM pass → typically **~+1.5–3 s** if the backend is fast, up to ~**5–6 s** if the tool is slow (**Inferred** from timeouts + double TTFT; few tool turns in the cited logs).

### 5.5 p50 / p95

**Open.** Instrumentation exists; a formal multi-turn study (web vs phone, Groq vs Gemini, with/without tools) has not been published as p50/p95.

---

## 6. Self-Serve web test — latency context

### 6.1 How a browser test starts

1. UI loads publishable config and may **prepare** (warm upstream, ensure agent exists, pre-mint credentials).
2. User clicks connect → HTTP session mint → LiveKit room token + WebSocket URL.
3. Browser connects **WebRTC** to LiveKit.
4. Platform worker joins the same room and runs the same STT/LLM/TTS loop as phone.

Setup latency (mint, provision, cold worker) affects **time-to-first-greeting**, not necessarily every later turn. Prepare/pre-mint caches exist to reduce connect friction.

### 6.2 Where time goes on web

| Category | Notes |
|----------|-------|
| Infrastructure / network | User ↔ LiveKit RTT; browser mic/AEC |
| Model processing | Same worker LLM/TTS as phone |
| Unique to web | Preemptive generation possible when **not** on Groq; richer false-interruption handling |
| Shared pain | Same Groq org ITPM as telephony |

### 6.3 Web vs model processing

Mint/prepare are **control-plane** costs. Once the room is up, conversational lag is almost entirely **VAD/EOU + STT + LLM (+ tools) + TTS**, same as phone, minus PSTN.

---

## 7. Telephony — latency context

### 7.1 Path

Caller → Telnyx (PSTN) → LiveKit SIP → worker → (STT/LLM/TTS) → SIP → Telnyx → caller.

English sessions: force Cartesia + Groq as described above. Audio to Cartesia is linear PCM at 16 kHz; LiveKit SIP resamples for the carrier. (An earlier attempt to emit µ-law directly from Cartesia **garbled** audio because the plugin path treats bytes as linear PCM — fixed.)

### 7.2 Extra delay vs web

| Stage | Web | Telephony | Known difference |
|-------|-----|-----------|------------------|
| Transport | WebRTC | PSTN + SIP + Telnyx | Extra hops — **ms not measured here** |
| VAD / STT | Same family | Same | ~0 |
| LLM | May remain Gemini if not remapped | Forced Groq for EN Gemini agents | Phone often **faster LLM** when Groq healthy |
| Preemptive LLM | On (non-Groq) | Off | Web can hide some latency when enabled |
| TTS | Cartesia | Cartesia + SIP resample | Small when encoding correct |
| Playback | Browser | Handset / carrier | Unmeasured |
| Barge-in policy | More aggressive resume | Tuned to avoid flicker on PSTN | UX, not raw TTFT |
| End-to-end | ~3.7 s sample on healthy Groq | Same order when healthy; worse on Gemini or 429 | Shared TPM |

**Earlier telephony “laggy / flickering” symptom** was often **wrong TTS (Rime under-running realtime on PSTN)** and interrupt policy — not Gemini alone. Forcing Cartesia aligned phone with the web test voice path.

---

## 8. Comparison table (only known cells)

| Stage | Self-Serve web | Telephony | Difference |
|-------|---------------:|----------:|------------|
| Audio transport | WebRTC | PSTN + SIP | Extra; **unmeasured** |
| VAD | Tuned ~0.35 s silence | Same | ~0 |
| STT | Streaming (e.g. Deepgram Nova-3 for EN demos) | Same providers | ~0 |
| LLM (healthy Groq) | ~1 s TTFT class | ~1 s TTFT class | ~0 |
| LLM (Gemini) | Possible if agent left on Gemini | Forced off for EN when Groq key present | Phone avoids Gemini lag by policy |
| LLM (free-tier 429) | Multi-second stalls | Same org limits | Shared |
| TTS first audio | ~0.14–0.22 s Cartesia | Same class | ~0 |
| Tool round-trip | Optional HTTP to Self-Serve | Same | Backend reachability (localhost/tunnel in dev) |
| End-to-end (one healthy Groq turn) | ~3.7 s sample | Same pipeline | Transport delta unknown |

---

# ISSUE 2 — CARTESIA HUMANIZATION

## 9. What we use

| Setting | Choice |
|---------|--------|
| Provider | Cartesia |
| Model | **Sonic 3.5** |
| Default demo / telephony voice | **Katie** (friendly receptionist-style) |
| Baseline delivery | Slightly slow (**0.95** speed), emotions **calm + content** |
| Streaming | Yes, over Cartesia’s streaming API via the voice framework |
| Audio | 16 kHz linear PCM into LiveKit (both web and phone) |

### 9.1 How “human” is produced (layers)

Humanization is multi-layer. Robotic sound usually comes from stacking: old model, generic voice, clean chatbot prose, no prosody cues, and (on phone) wrong audio encoding.

| Layer | What we do |
|-------|------------|
| Model | Sonic 3.5 (clear upgrade over older Sonic) |
| Voice | Katie first for agent demos; other Cartesia voices available |
| Baseline TTS params | calm/content, speed 0.95 |
| LLM speaking style | Platform rules: short spoken prose, no markdown, no corporate filler |
| Prosody markup | Model should start turns with emotion tags; optional pause tags, spell-out for IDs, rare laughter token |
| Safety net | Strip markdown/emoji before TTS; **keep** emotion/pause/spell tags |
| Framework “expressive” mode | Explored; **not active** on our current LiveKit stack with the Cartesia plugin — turning it on without real injection produced **flat** voice (rules said “don’t emit tags,” nothing else added them) |

Punctuation still drives most natural pausing; explicit pause tags are for longer gaps.

### 9.2 How LLM output reaches Cartesia

LLM streams text → sanitizer → low-latency splitter that understands XML-like tags → Cartesia → audio to the user.

Greeting path can also inject a short scripted-style instruction so the first line includes a natural pause.

---

## 10. The Cartesia ↔ LLM token problem

### 10.1 The tension

To sound human on Cartesia **without** a working framework expressive injector, the **LLM must emit markup** (emotion tags, occasional breaks, spell tags). Teaching that behavior requires a **large permanent system-instruction block**.

That block is billed as **input tokens on every turn**, alongside persona, tools, and history.

| Cost type | Size class | When paid |
|-----------|------------|-----------|
| Cartesia / tool / latency system rules | Large fixed **input** | Every turn |
| `<emotion …/>` and fillers | Small **output** | Every turn if obeyed |
| Completion reserved for tags + speech | Tight cap (~96 on Groq) | Must not spend the whole budget on thinking |

**Groq free tier:** input dominates ITPM. Humanization and “fast cheap Groq” are in direct conflict unless we pay for higher ITPM, shrink other context, or get markup from somewhere that is not the LLM.

### 10.2 Latency interaction

| Effect | Direction |
|--------|-----------|
| Larger system prompt | Slightly more LLM work; always more ITPM |
| Markup in the stream | Must not stall TTS; low-latency XML-aware splitting mitigates |
| Future expressive injector | Could shorten system rules (LLM says less markup) — **Open**, blocked on framework support today |
| Skipping tags while keeping rules | Saves little input; voice goes flat |

### 10.3 Tradeoff statement for research

```
More natural Cartesia (manual emotion/pause tags)
  → larger system instructions + tagged outputs
  → more tokens per turn
  → more free-tier 429 risk OR need paid Groq / smaller prompts / fewer tools

vs.

Smaller prompts for TPM
  → risk flatter, more “chatbot” voice unless another humanization path appears
```

### 10.4 Guardrails we already learned

- Do not default “expressive” on without proof the framework injects delivery tags.
- Do not emit telephony audio in a format the media stack misinterprets (caused garbled PSTN earlier).
- Do not put security-critical speaking rules only in the tenant persona — persona is treated as untrusted data; platform rules stay authoritative.

---

## 11. Recommended research / decision agenda

Ordered by evidence strength:

1. **Commercial Groq (or other) ITPM** — until per-turn input is far below half of the minute budget, free tier cannot sustain multi-turn front-desk + tools + humanization rules.  
2. **History policy** — truncate or summarize older turns; today history grows without bound.  
3. **Tool surface on free tier** — every registered tool’s schema is paid even when unused.  
4. **Humanization profile for free tier** — shorter speaking rules that still force one emotion tag, or wait for framework expressive.  
5. **Formal latency study** — web vs phone, p50/p95 for stop→audio, LLM TTFT, TTS TTFB, with/without tools, Groq vs Gemini.  
6. **Gemini only as a paid/low-TTFT research track** — do not undo English telephony Groq forcing without new measurements.  
7. **Voice A/B on Cartesia** — Katie vs more “emotive” catalog voices (quality, not speed).

---

## 12. Glossary

| Term | Meaning |
|------|---------|
| TTFT | Time to first token (LLM) |
| TTFB | Time to first audio byte (TTS) |
| ITPM | Input tokens per minute (Groq rate limit dimension we hit) |
| Cascaded voice agent | Separate STT + LLM + TTS (our architecture) |
| Preemptive generation | Start LLM (and maybe TTS) before end-of-utterance is final |
| Persona | Tenant-supplied business/character prompt (data to the model) |
| Platform instructions | Our fixed operating rules (authoritative) |

---

## 13. What this document is / is not

**Is:** a self-contained context pack so someone can reason about latency and humanization, what we tried, what failed, what is still open, and where product vs infra vs vendor decisions sit.

**Is not:** an implementation guide, a file index, or a substitute for a formal latency benchmark report (that remains **Open**).

---

*Evidence window: September 2026. Update this brief when tier, default model, or humanization strategy changes.*
