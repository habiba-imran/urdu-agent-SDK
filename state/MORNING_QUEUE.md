# MORNING_QUEUE — live/human-gated items, ready to fire on your approval

Everything here is BLOCKED on you (live/paid quota or the human-listen). Nothing below has been run.
Fire them top-to-bottom. Ledger before any of this: **`uplift_tts_sec=17/600`**, `livekit_agent_min=0/1000`.
Run `python scripts/usage_guard.py --report` first to reconfirm.

---
## Q1 — P3-T06 Gemini TPM measurement  (you already approved the exact command; I held it per your do-not list)
**Command:**
```
python scripts/measure_gemini_tpm.py --turns 8 --confirm-live
```
**Cost:** 8 short sequential `generate_content` calls to `gemini-2.5-flash`. Free-tier RPD; **no Uplift, no LiveKit** budget.
**What to check:** the per-turn latency table + the "throttle onset" line. The D14 trap = latency ballooning / a `429 RESOURCE_EXHAUSTED` around a few turns.
**After it runs:** paste me the full output; I'll record the measured numbers in `docs/40-ADR.md` (P3-T06 — measured, not assumed). This is the lowest-risk item — safe to fire first.

---
## Q2 — GATE 3 human-listen: one live Urdu call (YOURS to run + listen)
This is the Phase-3 human gate ("Listen to a real Urdu call. Is it good? Only a human can answer."). It needs a running worker + a client joining a minted room + live media. Steps:

**Setup (non-live, one-time):**
1. Provision a demo tenant/agent (writes to dev DB, free; omit `--commit` first to preview):
   ```
   python scripts/provision_demo_tenant.py --commit
   ```
   It prints `tenant_id`, `agent_id`, and a generated HMAC `secret`. Add the secret to `.env.local` as:
   `CP_TENANT_SECRETS={"<tenant_id>":"<secret>"}`  (the control plane reads this).
2. For a REAL conversation you need live TTS — set `UPLIFT_MODE=live` in `.env.local`. ⚠️ **This spends the 10-minute-forever Uplift budget.** Keep the call SHORT (2–3 turns ≈ 20–40s of TTS). Or leave `UPLIFT_MODE=fixture` to only hear the one recorded greeting (proves audio path, not a full conversation).

**Run (LIVE — your call):**
3. Start the worker (connects live to LiveKit):
   ```
   python -m worker.main dev
   ```
4. Mint a token + join the room with a LiveKit client (Agents Playground https://agents-playground.livekit.io using our `LIVEKIT_URL`+a minted token, or a browser client). A token-mint helper:
   ```
   python scripts/mint_demo_token.py --tenant <tenant_id> --agent <agent_id> --secret <secret>
   ```
   (prints token + wsUrl + roomName; join that room in the client).
   > METADATA FLOW (fixed this session): the worker reads `{tenant_id, agent_id}` from your
   > **participant token metadata** (what the mint sets), via `ctx.wait_for_participant()` — NOT room
   > metadata. So minting a token + joining is all that's needed; no room-metadata setup.
**Cost:** LiveKit Build agent-minutes (~1–3 min) + live Gladia STT + live Gemini LLM + live Uplift TTS (if `UPLIFT_MODE=live`). Uplift is the constrained one — watch the ledger.
**What to listen for:** greeting is correct Urdu ("TechZone Laptops"…"مہ نور"), STT understands you, the reply is on-topic and natural, latency tolerable (Gladia won't hit 800ms — expected, noted).
> `scripts/provision_demo_tenant.py` and `scripts/mint_demo_token.py` are prepped for you (non-live) — see PROGRESS. Do NOT let me run step 3/4; they're live and yours.

---
## Q3 — P3-T08 5-concurrent test (LIVE LiveKit)
Only after Q2 confirms the worker works end-to-end. Spin up 6 concurrent sessions against the running worker; LiveKit Build free tier caps at 5 concurrent → the 6th must fail cleanly with a typed error (observe it — I won't guess the error type).
**Driver (prepped, non-live to write; running it is live):** `scripts/concurrency_test.py` (see PROGRESS — status: scaffold; needs the mint helper + a headless client, which depends on how Q2's client works).
**Cost:** 5 concurrent × ~1 min × a couple runs ≈ 10–15 LiveKit agent-min + live STT/LLM/TTS ×5. Budget-aware: keep runs short.
**What to check:** 5 sessions succeed, the 6th returns a clean typed error (not a crash/hang). Record the exact error in `docs/40-ADR.md`.

---
## Hard don'ts (unchanged) until you're back and approve each above
- No `UPLIFT_MODE=record`. No Gate-3 call started by me. No P3-T08 live run by me. No phase-gate merge/tag. No Phase 4 real tasks.
