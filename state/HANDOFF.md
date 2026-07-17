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

### Priority-2 forward prep done this session (PREP ONLY — review fresh, NOT "done")
- `docs/50-FORWARD-PREP-P4-P8.md` — per-phase (4–8) task breakdown + 6 open questions (0844bee).
- `requirements.txt` — 25 direct deps pinned from the installed env (c841e4b). Phase-7 prep + makes a
  cold clone reproducible (many pkgs were pip-installed ad-hoc across sessions).
- `sdk/` — Phase-4 PUBLIC TYPE SURFACE stub only (f0df147): typed events/errors exactly per docs/24,
  every method throws "not implemented — Phase 4". No npm install, no wiring, zero Phase-3 dependency.

### Incident (non-blocking, resolved)
A transient git **fsync error** ("Bad file descriptor" / "Function not implemented") crashed one commit
and left a stale `.git/index.lock`. Repo verified INTACT (`git log` + `git fsck --connectivity-only`
clean); removed the lock, commit succeeded (f0df147). `E:\Finova-Internal` may be cloud-synced / AV-
scanned — if fsync errors recur, just retry the git op (not corruption).

### Current status (updated after Q1 fired + Q2 staged — 2026-07-17)
- **Q1 DONE:** Gemini TPM measured + recorded in `docs/40-ADR.md` (commit bbfad23): 6 rapid calls OK
  (1.9–3.5s each), turn 7 → `429 RESOURCE_EXHAUSTED` (free-tier RPM cap). Ledger untouched (17/600).
- **Q2 STAGED (NOT run):** demo tenant `demo-gate3` seeded in dev DB — tenant_id
  `ca72956b-8f55-4374-8332-a659ba9ec5fc`, agent_id `71f87c75-1150-489e-8b1d-bbf4e0488bf0`, voice
  v_meklc281, gemini-2.5-flash, persona 3606 chars. **Secret BURNED** (pasted in chat) — re-provision
  fresh for future tests (see PROGRESS Traps). Worker NOT run; `UPLIFT_MODE` untouched (=fixture).

### Gate-3 human-listen — STAGED, the HUMAN runs it (agent: do NOT run the worker/mint/live session)
Recommendation: `UPLIFT_MODE=live` (fixture can't synth the LLM's dynamic replies — every TTS call
cache-misses; even the greeting text ≠ the one recorded fixture). Budget ~20–40s of 600.
**Item-2 risk (metadata fix is UNVERIFIED by any test):** if `participant.metadata` comes through
empty, `build_session(md)` throws `KeyError: 'agent_id'` / `AgentNotFound` in the WORKER LOG and the
agent never greets — this fails BEFORE any TTS, so ZERO Uplift is spent. Success = agent greets in
Urdu ("…TechZone Laptops…مہ نور…").
Human steps (own terminals): (1) .env.local `UPLIFT_MODE=live` (revert after); (2)
`python -m worker.main dev`; (3) `python scripts/mint_demo_token.py --tenant <tid> --agent <aid>
--secret <secret>`; (4) join room at https://agents-playground.livekit.io (manual connect: paste
wsUrl + token). First-live unknowns: Playground manual connect + worker auto-dispatch to the room.

### Exact next action for a RESUMING agent
1. Read CLAUDE.md, docs/00-INDEX.md, this file, state/PROGRESS.md, state/MORNING_QUEUE.md,
   docs/23-PHASE-3-WORKER.md, docs/40-ADR.md (P3-T06 + P3-T01). Brief the human.
2. Ask the human the **Gate-3 outcome** (did the agent greet in Urdu? was it good?).
   - PASS → record in PROGRESS + ADR; Phase-3 human gate met. Remaining Phase-3: P3-T08 5-concurrent
     (live, MORNING_QUEUE Q3), P3-T07 usage-on-session-end wiring, full Gate-3 checklist. Do NOT start
     Phase 4 without explicit "begin Phase 4".
   - FAIL (config didn't load / KeyError) → item-2 metadata fix needs iteration: inspect the worker
     log, re-verify the participant-metadata read (or dispatch/room-metadata) against livekit.agents
     source — DO NOT guess. Re-provision a fresh demo tenant (secret is burned).
3. Standing rules (unchanged): NO live/paid call (Uplift/Gladia/Gemini/LiveKit/UPLIFT_MODE=record)
   without explicit human approval on the exact command; no Gate-3 call or P3-T08 live run started by
   the agent; no phase-gate merge/tag; no Phase 4 real tasks. Full LITERAL output, no summaries.
   3-strike rule. Verify APIs against installed source/Context7, never guess.
