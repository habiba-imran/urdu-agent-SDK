# HANDOFF

## Session 8 | 2026-07-17 | Phase 5 (Voice Picker) — GATE 5 CLOSED. Stopped hard, awaiting "begin Phase 6".
Branch: `phase/3-worker`. HEAD: `aaa7bf7`. Working tree clean at handoff (verified: `git status --short` → empty).
Resume from `CLAUDE.md` -> `state/PROGRESS.md` -> `docs/00-INDEX.md` (routes to the right guide) -> this file.

## STANDING RULES ESTABLISHED THIS SESSION — NOT YET WRITTEN INTO CLAUDE.md/AGENT_SYSTEM.md
These were given verbally across Session 8 and are NOT in any committed doc. A resuming agent
that only reads CLAUDE.md/AGENT_SYSTEM.md will NOT know these. Follow them exactly:

1. **Live/paid API call sign-off.** NEVER run a live/paid call (Uplift, Gladia, Soniox, Gemini,
   LiveKit, `UPLIFT_MODE=record`, starting the worker, or any live LiveKit session) without
   explicit prior sign-off on the EXACT command. Early in the session this meant "the human runs
   it themselves"; later in the session the human explicitly directed the agent to run specific
   live commands itself after giving explicit approval + exact design (e.g. the washroom-singer
   re-run, the Supabase Storage upload). **Read the human's most recent instruction literally** —
   if they say "run X and paste the output," that IS the sign-off; don't wait for a second
   confirmation, but don't extrapolate approval beyond the exact scope given either.
2. **Any new live-pipeline test design needs approval before it runs, no exceptions** — even a
   redesign that seems obviously safer than the original (this was a direct correction after the
   agent redesigned + ran a concurrency test mid-task without pausing for approval first).
3. **Standing operating pattern:** work a full phase's tasks in one long, uninterrupted haul — no
   stopping for permission between individual tasks. Stop HARD only at: the phase's actual machine
   gate, a human-gate item (`docs/41-HUMAN-TASKS.md`), any live/paid API call, or the 3-strike
   rule. Post full gate output + every human-gate line batched at the end, not piecemeal. Then wait
   for explicit "begin Phase N+1." Applies to every remaining phase (6, 7, 8).
4. **Never invent a number.** If a true value is genuinely unrecoverable (e.g. lost mid-crash
   data), say so plainly and give a conservative, reasoned estimate with explicit rationale, then
   correct the record openly — modeled on how ADR-016 and ADR-019 both did this. Never silently
   guess or silently omit.
5. **Full literal output required for gate/verification evidence** — never summarized/paraphrased
   when reporting command output back to the human.
6. **Never merge, tag a phase gate, or start a new phase without explicit human "begin Phase N".**
7. Standard project rules still apply on top of these: verify API signatures against installed
   source (never guess), 3-strike rule -> `state/BLOCKERS.md`, cite sources.

## Where the build stands
- **Phases 1-4: closed.** Phase 3 GATE 3 closed (docs/23, ADR-014/016). Phase 4 GATE 4 closed,
  human line signed off (dist/index.js + index.d.ts personally reviewed by the human).
- **Phase 5 (Voice Picker): GATE 5 CLOSED this session, every line with real evidence** (not
  assumed) — see `docs/40-ADR.md` ADR-018 (non-live prep) and **ADR-019 (the full live-recording
  incident + resolution — read this one in full, it's the main event of this session)**.
- **P3-T09 (tool-calling wiring) and remaining voice/persona/prosody polish are DEFERRED** to a
  dedicated end-of-build pass (ADR-013) — do not touch until that pass explicitly begins.
- Ledger, verified by reading `state/usage_ledger.json` directly right now:
  `uplift_tts_sec=327/600`, `livekit_agent_min=7/1000`, `gladia_stt_sec=0`,
  `supabase_db_mb=0`, `livekit_adaptive_interruption_req=0`.

## What happened this session (all committed, newest first)
- **`aaa7bf7`** — GATE 5 closed. `washroom-singer` disabled (`voices.enabled=false`, human
  decision, NOT deleted — see below). `scripts/upload_voice_previews.py` (new): uploads previews
  to a **private Supabase Storage bucket** `voice-previews` (chosen over a new CDN vendor — reuses
  existing free-tier Supabase credentials), signs URLs (7-day TTL), populates
  `voices.preview_url`. Run live: **81/81 uploaded+signed+DB-updated**. Full GATE 5 checklist
  verified with real evidence (see "Exact commands/evidence" below).
- **`25232a4`** — Human-approved re-run of the 2 remaining P5-T02 voices with a **per-voice cap
  override** (`MAX_SECONDS_OVERRIDES = {"washroom-singer": 10.0}` in
  `scripts/record_voice_previews.py`, default stays 6.0 for everyone else). Result:
  `wholesale-trader` recorded cleanly (3.80s, normal range — confirms it was only ever collateral
  damage from the crash bug, never itself slow). `washroom-singer` **still exceeded even the
  raised 10.0s cap**, reaching a real measured **10.07s** — logged to ledger (not lost this time),
  correctly skipped rather than auto-raising the cap again. Ledger 313 -> 327.
- **`4104415`** — The core incident fix. Human's live `UPLIFT_MODE=record` run of
  `scripts/record_voice_previews.py` crashed on `washroom-singer` (80/82 recorded), losing
  unlogged spend and killing the rest of the run. Root cause verified (not guessed): re-fetched
  `docs.upliftai.org/orator_voices` — washroom-singer's file codename `ai_naat_p4_m_za` indicates
  a "naat" (Islamic devotional, melismatic/sung) voice model, genuinely much slower than ordinary
  speech, not a bug/text/config issue. Ledger corrected 305 -> 313 (+8s reasoned estimate: 6.0s
  confirmed floor + 2s pad for streaming-chunk overshoot, grounded in reading the installed
  `upliftai` plugin's actual incremental delivery — full reasoning in ADR-019). Script fixed:
  `synth_one()` now raises a local `CapExceeded` (carries partial pcm) instead of `SystemExit`
  inside the try block, so partial spend is never silently lost again; the per-voice loop logs it
  and `continue`s to the next voice instead of killing the whole run.
- **`01bbcfa`, `3d4ce26`** — earlier Phase-5 prep (voice catalogue seed, picker UI scaffold,
  enable-check trigger, the original P5-T02 script) — see ADR-018 for full account.
- Before Phase 5: Phase 4 client SDK implemented + GATE 4 closed (`45a4ef4`), Phase 3 GATE 3
  closed with real usage instrumentation + corrected concurrency test + a real race condition
  found and fixed (`5904368`, `61a6c20` — ADR-014/016/017).

## A reporting-precision correction (last thing that happened, worth knowing)
The human caught an apparent mismatch in the agent's own GATE 5 report: "82/82 cards render" vs
"81/81 previews uploaded." Investigated and confirmed **not a bug** — the picker UI query
(`voice-picker/index.html` lines 74-78) has **no client-side `enabled` filter at all**; it relies
entirely on the RLS policy `voices_read_all USING (enabled)` to filter server-side. Fresh
re-verified live: 82 enabled rows = **81 catalogue voices** (all with real previews, all playable)
**+ 1 unrelated pre-existing row** (`v_meklc281` / "Uplift Orator (default)", the separate legacy
demo voice from `0003_seed_voices.sql`, explicitly out of P5-T02/T03 scope since ADR-018, never
had a preview). `washroom-singer` correctly absent from all 82 rendered cards, confirmed twice.
Both original numbers (82 and 81) were real and correct — the agent's phrasing just juxtaposed two
different denominators in a way that looked like an inconsistency. No code/data change needed;
this is purely a "be more precise when reporting counts with different scopes" lesson. If this
comes up again, the exact breakdown is: `select id from voices where enabled=true and
preview_url is null` -> only `v_meklc281`.

## Exact commands/evidence for GATE 5 (if the human wants to re-verify or extend)
- DB check: `select count(*) from voices where enabled=true` -> 82; `... and preview_url is not
  null` -> 81; the one gap is `v_meklc281` (expected, out of scope).
- Real signed-URL fetch test: `httpx.get(signed_url)` -> 200, `content-type: audio/wav`, bytes
  match local file exactly, RIFF/WAVE header present.
- Real expiry test: created a `create_signed_url(path, 2)` (2-second TTL), fetched immediately
  (200), waited 4s, fetched again -> **400 InvalidJWT "exp claim timestamp check failed"**.
- Real Playwright/Chromium run against `voice-picker/index.local.html` (gitignored, generated by
  `python voice-picker/render_config.py` from `.env.local` — regenerate if missing): 82 cards, 81
  enabled play buttons, 1 disabled (`v_meklc281`), `washroom-singer` absent, 6 total network
  requests during load + 3 play-button clicks, **zero** to any `upliftai`/`uplift.ai` host.
- `pytest tests/test_worker.py` -> 5/5 green throughout (Phase-5 changes don't touch the worker).

## Open items / not decided (flagged, not silently assumed)
- `washroom-singer`: disabled, not deleted. If ever revisited, needs a purpose-built short line
  (not the shared greeting text) rather than another cap increase — explicitly not attempted here.
- Uplift dashboard true-up against the ledger's 327s: human said they'll check it themselves when
  convenient, not blocking. If they report a different number, that wins over the reasoned
  estimate in ADR-019 — update the ledger/ADR if/when they do.
- `voice-picker/` hosting location (standalone vs Phase-6 admin portal) — still undecided (ADR-018).
- Artwork-to-voice mapping (3-4 owned artworks vs 81 voices) — still undecided (ADR-017/018).
- The `cache-control` upload option on Supabase Storage isn't echoed as a literal `Cache-Control`
  response header — Supabase sets `Expires` instead (same effective 7-day window), Cloudflare
  confirmed actually caching it. Noted as a minor discrepancy in ADR-019, not fixed/investigated
  further (not blocking, "long cache" goal is functionally met).

## Exact next action for a RESUMING agent
1. Read `CLAUDE.md`, `state/PROGRESS.md`, `docs/00-INDEX.md` (route to the Phase-6 guide when the
   human says "begin Phase 6"), this file, and `docs/40-ADR.md` ADR-019 in full (not just this
   summary — it has the complete reasoning chain for the washroom-singer incident).
2. Confirm continuity to the human before doing anything: state back HEAD commit (`aaa7bf7`),
   branch (`phase/3-worker`), the real ledger value (327/600 uplift_tts_sec), and that GATE 5 is
   closed. Re-read the "STANDING RULES" section above out loud in your own words if asked.
3. **Do not start Phase 6 work** until the human explicitly says "begin Phase 6" — currently
   stopped hard awaiting that instruction. If the human instead has follow-up questions about
   Phase 5 (e.g. the 82/81 count, washroom-singer's disposition, the ledger correction reasoning),
   answer from ADR-019 + this file's evidence section — don't re-derive from scratch or guess.
4. If asked to continue Phase 5 in some way not covered here, treat it as new work under the same
   standing rules (sign-off before any live/paid call, batch-report at the gate, etc.) — Phase 5's
   GATE is closed but that doesn't forbid legitimate follow-up if the human raises one.
