# 30-GUIDE-FREE-TIER.md — how to build this without paying

**Read this before your first call to any paid API. Every time.**

---

## 1. THE PROBLEM WITH "JUST ROTATE ACCOUNTS"

The plan is free tiers, rotate when exhausted. Here is what that actually buys:

| Service | Free tier | Rotation verdict |
|---|---|---|
| **Uplift TTS** | **10 minutes of audio. Total. Forever.** | ❌ **Unworkable.** 10 min ≈ 40 short agent replies. You'd rotate **daily**. |
| LiveKit Build | 1,000 agent-min/mo hard cap (calls FAIL past it) · "5 concurrent" is UNCONFIRMED — tested 3 ways live 2026-07-17 (P3-T08, no media / synthetic media / full-pipeline sustained load) and never reproduced once at n=6, see `docs/40-ADR.md` ADR-014 | ⚠️ 1,000 min/mo budget is real and adequate if budgeted. Rotation loses your URL + keys + project. |
| Gladia | limited free hours | 🟡 Workable |
| Gemini | generous TPM/RPD free tier | ✅ Fine, no rotation needed |
| Supabase | **Pro plan (PAID, 2026-07-16)** — no 7-day pause, no free-tier cap | ✅ No rotation, no pause. Tracked in usage_ledger as `supabase_db_mb` (informational, not capped). |

**Uplift is the killer. 10 minutes is not a tier, it's a demo.**

Being straight with you about the rest: rotating free accounts to evade quotas violates most providers' ToS, and Uplift is the one vendor whose goodwill your whole product depends on. Getting your org flagged there is a real business risk, not a slap on the wrist. You're about to ask them for Enterprise pricing (H9). Don't be the account that farmed their free tier first.

**You don't need to rotate.** You need to stop calling the API.

---

## 2. THE FIXTURE CACHE — the actual answer

**Record each unique output once. Replay forever.**

TTS is deterministic-enough: same text + same voice = same audio. You do not need to regenerate "Assalam-o-Alaikum, main aap ki kya madad kar sakta hoon?" four hundred times. You need it **once**.

```
tests/fixtures/
  tts/
    <sha256(voiceId + '|' + text)>.wav      # real Uplift output, committed
    manifest.json                            # hash -> {voiceId, text, ms, bytes, recorded_at}
  stt/
    <name>.wav + <name>.expected.txt         # real Urdu audio + gold transcript
```

### The rule

```
DEV/TEST  -> UPLIFT_MODE=fixture   (default. cache hit = free. cache MISS = HARD FAIL)
RECORDING -> UPLIFT_MODE=record    (human-approved, explicit, budgeted)
PROD      -> UPLIFT_MODE=live
```

**A cache miss in test mode is a test failure, not a silent API call.** This is the entire point. It is what stops a runaway loop from eating 10 minutes of Uplift in 90 seconds while you're getting coffee.

### Implementation (`services/tts_cache.py`)

```python
import hashlib, json, os, pathlib
FIX = pathlib.Path("tests/fixtures/tts")
MODE = os.getenv("UPLIFT_MODE", "fixture")

def key(voice_id: str, text: str) -> str:
    return hashlib.sha256(f"{voice_id}|{text}".encode()).hexdigest()[:32]

async def synth(voice_id: str, text: str) -> bytes:
    k = key(voice_id, text); p = FIX / f"{k}.wav"
    if p.exists():
        return p.read_bytes()                      # free, instant, deterministic
    if MODE == "fixture":
        raise LookupError(
            f"TTS FIXTURE MISS {k}\n  voice={voice_id}\n  text={text!r}\n"
            f"  This did NOT call Uplift. Free tier protected.\n"
            f"  To record: UPLIFT_MODE=record pytest -k <test>   (asks human first)"
        )
    audio = await _uplift_live(voice_id, text)      # only reachable in record/live
    if MODE == "record":
        p.write_bytes(audio); _manifest_add(k, voice_id, text, audio)
    return audio
```

Mirror this for STT (`GLADIA_MODE`) and LLM (`LLM_MODE`, cache on prompt hash).

### Why this is not a hack

- **Deterministic tests.** No network in CI. No flakes. Fast.
- **The fixtures are an asset.** Your golden Urdu audio + gold transcripts *are* your CER harness — the thing you already built and the most valuable thing in the old repo.
- **This is how real voice teams work.** It's not a free-tier workaround that you throw away; it survives into production CI.
- **10 min of Uplift becomes ~200 unique cached phrases.** That is a complete dev corpus.

---

## 3. RECORDING BUDGET — Uplift's 10 minutes, allocated

**Human approves every recording session. The agent never records unattended.**

| Purpose | Budget | Phase |
|---|---|---|
| Voice picker demo clips (1 line × N voices) | ~4 min | P5 |
| Agent reply corpus (~40 canonical Urdu phrases) | ~3 min | P3 |
| Latency measurement (10 reps, one phrase) | ~1 min | P3 |
| Reserve | ~2 min | — |

`scripts/usage_guard.py` tracks spend against this and **fails `make gate`** if the ledger says you're over. Gap #12 from the audit: you will not blow the tier blind.

**Record in ONE sitting, not drip-fed.** Write the phrase list first, get it reviewed, then record once.

---

## 4. LIVEKIT BUILD — the 1,000-minute budget

Hard cap. At 1,001 minutes **calls fail**. There is no overage.

| Purpose | Budget |
|---|---|
| P3 worker dev (~60 calls × 3 min) | 180 |
| P4 SDK integration (~40 × 3 min) | 120 |
| P5–P6 (~40 × 3 min) | 120 |
| ~~P8 concurrency test — 5 concurrent × 5 min × 6 runs~~ — ran early, in Phase 3 (see below) | ~~150~~ |
| Reserve | 430 (+150 freed from the line above) |

Also: Build has **10–20s cold starts** (prevention is Ship+). **Expect it. Do not debug it. Do not "optimise" it.** It disappears the day you pay $50.

**✅ Tested in Phase 3, not Phase 8, as planned (audit gap #16) — result differs from the "5
concurrent" assumption above.** `P3-T08` ran live 2026-07-17, three ways: (1) 6 rooms, no media,
(2) 6 rooms with real published synthetic audio, (3) 6 rooms with real published audio held open
long enough for the FULL agent pipeline to complete (STT connected, adaptive interruption running)
— every run showed **6 succeeding, 0 rejected**. The documented "5 concurrent, hard cap" was never
reproduced under any of these conditions. Full account, including the methodology gap found and
fixed along the way (early runs only proved room-join concurrency, not full-agent-session
concurrency) and the real measured LiveKit-minute cost of these tests:
`docs/40-ADR.md` ADR-014 (original + two addenda). **Do not assume 5-concurrent is a real ceiling
for this project's LiveKit Build account** until it's actually re-verified (e.g., a larger-N test,
or checking the LiveKit Cloud dashboard/plan directly) — treat the true ceiling, if any, as unknown
rather than reverting to the original unverified figure.

---

## 5. SUPABASE — now on the Pro (paid) plan

**Updated 2026-07-16: Supabase is on the paid Pro plan. The 7-day free-tier pause NO LONGER
applies** — the dev DB will not vanish over a weekend. The discipline below stays anyway, because
it is just good practice and makes the eventual prod cutover trivial:

- Migrations are **code**, in `supabase/migrations/`. Never click-ops.
- `make db-reset` rebuilds the entire DB from zero (verified in Phase 1). Keep it working.
- Supabase usage is now tracked in `state/usage_ledger.json` as `supabase_db_mb` — informational
  only (paid plan, no hard free-tier cap that fails the gate).

---

## 6. THE DEV↔PROD SWITCH

Every gate that matters must be **provider-agnostic**, so the day you fund Soniox/Uplift nothing is a refactor:

```bash
UPLIFT_MODE=fixture|record|live
STT_PROVIDER=gladia|soniox        # <- Soniox integration ALREADY EXISTS in the old repo (D27),
                                  #    blocked only on a 402. 6x cheaper, ~400ms faster.
                                  #    THIS MUST STAY ONE ENV VAR. Never a refactor.
LLM_MODE=fixture|live
```

**Phase 3 acceptance criterion:** `STT_PROVIDER=soniox` fails with *"402 payment required"* — **not** with an ImportError, AttributeError, or NotImplementedError. That proves the seam is real and the swap is one variable.

---

## 7. GATE — free-tier compliance

Runs inside `make gate`. Blocks the Stop hook.

```
[ ] scripts/usage_guard.py --report -> under budget for every provider
[ ] No live API call in any test (assert UPLIFT_MODE=fixture in conftest)
[ ] tests/fixtures/tts/manifest.json matches files on disk
[ ] grep -rE 'MODE\s*=\s*.(record|live)' tests/ -> zero hits
[ ] All paid-API deps behind an env flag, defaulting to the free/fixture path
```
