# PHASE 3 — AGENT WORKER
**Goal:** ONE worker serving all tenants. Config per session from room metadata.
**Read first:** 30-GUIDE-FREE-TIER.md (🔴 **before your first API call**)
**Gate:** `pytest tests/test_worker.py -q`

## Shape
```python
async def entrypoint(ctx: JobContext):
    md = json.loads(ctx.room.metadata)             # {tenant_id, agent_id}
    cfg = await load_agent_config(md["agent_id"], md["tenant_id"])  # RLS-scoped
    session = AgentSession(
        stt=make_stt(),                            # STT_PROVIDER env -> gladia|soniox
        llm=google.LLM(model=cfg.llm_model),       # BYO key, NOT LiveKit Inference
        tts=make_tts(cfg.voice_id),                # UPLIFT_MODE env -> fixture|record|live
        vad=silero.VAD.load(),
    )
```
🔴 **`cfg.prompt` is UNTRUSTED.** It is the tenant's text. It goes in the assistant persona slot,
never concatenated into our system instructions, never near a tool definition. See 31-GUIDE-SECURITY.md §4.
🔴 **Do not use LiveKit Inference** — its concurrency cap (50 on Scale) sits *below* the agent-session
cap (600) and would become your real ceiling. BYO Google key.

## Tasks
### P3-T01 🔴 VERIFY the Uplift plugin FIRST — before building anything on it
Our old repo (D3/D5) says Uplift is Socket.IO @22.05kHz PCM, and that Pipecat's websocket mixin
couldn't speak it. **That's about OUR code. The LiveKit plugin is UNVERIFIED BY US.**
```
pip install livekit-plugins-upliftai
# minimal script: one voice, one Urdu phrase, UPLIFT_MODE=record (HUMAN-APPROVED, ~5s of budget)
```
**Done when:** a wav exists, is audible Urdu, and its sample rate is **recorded in 40-ADR.md**.
**If it fails →** BLOCK + RQ-003. **Fallback:** port `services/uplift_tts.py` from the old repo as a
LiveKit `TTS` subclass. That fallback is why we kept the file. But **try the plugin first** — the
whole reason we chose LiveKit is to not own that code (ADR-001).

### P3-T02 Fixture cache (30-GUIDE-FREE-TIER.md §2)
Done: `UPLIFT_MODE=fixture` + cache miss → **LookupError**, and **zero** network calls (assert with a socket guard in conftest).

### P3-T03 Worker skeleton + metadata config load. Done: 2 tenants, 2 prompts, 2 voices, one worker.
### P3-T04 Uplift TTS wired. Done: `pytest tests/test_tts.py`
### P3-T05 STT behind `STT_PROVIDER`. 🔴 Done: `STT_PROVIDER=soniox` → **402 payment required**, NOT ImportError.
### P3-T06 Gemini LLM. Record TPM limits in ADR — old repo D14 documented Groq free-tier throttling → TTFB 13–30s at ~4 turns. **Same trap. Measure it.**
### P3-T07 usage_events emission. Done: a call writes stt_sec+tts_sec+agent_sec.
### P3-T08 🔴 CONCURRENCY TEST NOW — not Phase 8 (audit gap #16)
5 simultaneous calls (LiveKit Build cap). Done: 5 succeed, 6th fails **cleanly** with a typed error.
*Finding a concurrency flaw in week 8 is a rewrite. In week 3 it's an afternoon.*

## GATE 3
```
[ ] tests/test_worker.py green
[ ] one live Urdu call, e2e, human-listened          <- HUMAN GATE
[ ] latency recorded (will NOT hit 800ms on Gladia — expected, note it, move on)
[ ] CER harness runs against fixtures
[ ] 5 concurrent OK, 6th fails cleanly
[ ] STT_PROVIDER=soniox -> 402
[ ] make usage -> under budget
```
