# HANDOFF

## Session 7 | 2026-07-17 | Phase 3 (Worker) — non-live work DONE, live items queued
Branch: `phase/3-worker`. Working tree clean at handoff. Resume from `state/PROGRESS.md` + this file.

### Where Phase 3 stands
- **Phase-3 gate = `pytest tests/test_worker.py` → 5/5 green.** (NOT full `make gate`: that shows 3
  pre-existing CER-harness schema-mismatch failures from the ported db.py — tracked, Phase-3 rework.)
- **Everything buildable without live/paid calls is DONE.** What remains is entirely live-gated and is
  queued for the human in `state/MORNING_QUEUE.md`.

### What changed this session (all committed)
- Verified the prior agent's claims (Session-6 audit): worker/mint/isolation/tts tests green, manifest
  hashes correct, ledger 0→8→17, name spelling canonical. Marked `c6228ded` fixture superseded in the
  manifest; fixed persona.py:29 to Latin "TechZone Laptops". (32fbefa, 320e18e)
- **worker session.start() wired** (6cdebf1): `build_agent(cfg)` puts OUR `SYSTEM_INSTRUCTIONS` in
  `Agent(instructions=...)` and the UNTRUSTED tenant prompt in `chat_ctx` as a framed system DATA
  message — never concatenated into instructions (31-GUIDE §4). New test proves an injected "IGNORE
  ALL PREVIOUS INSTRUCTIONS" prompt lands in chat_ctx, not instructions.
- **worker launchable** (bac00ee): `python -m worker.main dev` via cli.run_app(WorkerOptions(...)).
  Installed the worker's media plugins: gladia (STT), silero (VAD); upliftai (TTS) + google (LLM)
  already present.
- **metadata-source bug fixed** (2f65587): the mint sets {tenant_id, agent_id} in the PARTICIPANT JWT
  metadata, but entrypoint read `ctx.room.metadata` (never set). Now: `ctx.connect()` →
  `ctx.wait_for_participant()` → `json.loads(participant.metadata)`. Worker-only, no Phase-2 change.
- **P3-T06 prep** (8918c39): `scripts/measure_gemini_tpm.py` (Gemini TPM/throttle measurement, refuses
  live without `--confirm-live`); installed livekit-plugins-google + google-genai. 41-HUMAN-TASKS H3
  corrected: the key is `UPLIFTAI_API_KEY` (config.py + first-party plugin read that; `UPLIFT_API_KEY`
  in the doc was dead — you said you'd delete it from .env.local yourself).
- **morning helpers** (2f65587): `scripts/provision_demo_tenant.py --commit` (seed a demo tenant/agent,
  free DB write), `scripts/mint_demo_token.py --tenant --agent --secret` (mint a real scoped join
  token, local JWT + free DB write). `state/MORNING_QUEUE.md` has every live command + cost + checks.

### Env / deps installed this session (not in git — record for cold resume)
livekit-plugins-google, google-genai, livekit-plugins-silero, (livekit-plugins-gladia already there),
livekit-plugins-upliftai. `.env.local`: `STT_PROVIDER=gladia`, `UPLIFT_MODE=fixture`, both
`UPLIFTAI_API_KEY` (live) and dead `UPLIFT_API_KEY` present (human to delete the dead one).

### LIVE items — HELD, queued in MORNING_QUEUE.md (do NOT run without explicit human approval)
1. `python scripts/measure_gemini_tpm.py --turns 8 --confirm-live` (P3-T06 TPM — approved earlier but
   the human's do-not list said HOLD, so HELD). Cost: 8 free-tier Gemini calls, no Uplift/LiveKit.
2. Gate-3 human-listen: one live Urdu call. HUMAN runs (worker + client + live media). Uplift budget
   risk if UPLIFT_MODE=live.
3. P3-T08 5-concurrent live LiveKit test. NOTE: a headless livekit.rtc client HANGS in this env
   (proven Session 5) — the concurrency driver likely needs the Agents Playground / browser tabs, not
   a headless script. Flagged.

### Open follow-ups (non-blocking)
- P3-T07 usage_events on session END is not yet wired to session metrics (record_usage exists; needs a
  live session's duration/STT/TTS seconds). Small follow-up after the live call.
- FixtureTTS strips a fixed 44-byte WAV header — fine for our fixtures, fragile if a WAV has extra chunks.

### Exact next action
Human: work MORNING_QUEUE.md top-to-bottom (approve each live command). Q1 (Gemini TPM) is lowest-risk.
Do NOT start Phase 4 or the Gate-3 call without the human. Agent (if resuming before human): Phase-3
non-live is exhausted — see PROGRESS "Now"; only Priority-2 later-phase PREP (docs task breakdowns,
sdk/ scaffold with ZERO Phase-3 dependency) is allowed, logged separately as prep, not "done".
