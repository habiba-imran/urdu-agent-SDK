# 40-ADR.md — decision log

Append-only. Read before deciding. Append after. Never delete.

Format:
```
## ADR-nnn <title>   [ACCEPTED|SUPERSEDED by ADR-mmm]
Date | Context | Decision | Consequences | Evidence(url/file)
```

---
## ADR-001 LiveKit Agents over Pipecat   [ACCEPTED]
**Context:** Multi-tenant Urdu SDK. Old repo is Pipecat 1.4.0 + hand-written Uplift Socket.IO TTS.
**Decision:** LiveKit Cloud + livekit-plugins-upliftai.
**Why:** `livekit-plugins-upliftai` is FIRST-PARTY — published from LiveKit's own CI in the
livekit/agents monorepo. Uplift is **not** in Pipecat's supported-services list at all; Pipecat's
own docs list `pipecat-upliftai-tts` only as a naming example for **community** packages, and state
plainly: *"The Pipecat team does not code review, test, or maintain community integrations."*
Urdu voices ARE the product. We will not own that glue.
Also: warm concurrency is 2–25x cheaper on LiveKit ($50/mo Ship vs $21.60/mo per Pipecat
reserved instance); LiveKit JWT grants are the multi-tenant security primitive; client SDKs mature.
**Against:** Cekura benchmark (default templates) — Pipecat 89.8% vs LiveKit 84.7% pass^3;
voice tone 4.45 vs 4.04. Weak evidence: defaults, not tuned.
**Consequences:** rewrite pipeline wiring; keep persona/tools/db/tests.

## ADR-002 Gladia for dev, Soniox for prod   [ACCEPTED]
**Context:** Soniox has no free tier. Dev is free-only.
**Decision:** `STT_PROVIDER` env flag. Gladia now, Soniox at funding.
**Evidence:** Soniox $0.12/hr (6x cheaper than Gladia PAYG), ~249ms median TTF vs our measured
650-750ms Gladia, claims 1.25% WER Urdu, first-party LiveKit plugin. Integration ALREADY WRITTEN
in old repo (D27), blocked on 402.
**Consequence:** swap must remain ONE env var. Gate: `STT_PROVIDER=soniox` -> 402, never ImportError.

## ADR-003 Fixture cache for all paid APIs   [ACCEPTED]
**Context:** Uplift free tier = 10 minutes total. Undevelopable. Account rotation violates ToS
and risks the vendor relationship we depend on (H9 Enterprise quote).
**Decision:** Record-once/replay-forever fixture cache. Cache miss in test mode = HARD FAIL.
**Consequence:** fixtures are committed, become the CER harness, survive into prod CI.

## ADR-004 ponytail at default intensity   [ACCEPTED]
**Decision:** install, `default`, never `extremist`.
**Evidence:** honest agentic benchmark = ~54% less code, 22% fewer tokens, 20% cheaper, 27% faster,
100% adversarial security. The viral 80-94%/47-77% figures are a single-shot prose artifact the
maintainer himself corrected (issue #126).
**Risk:** YAGNI-extremist refuses SDK abstractions. Token balance goes NEGATIVE on verbose
reasoning models (documented, GPT-5.5).
**Consequence:** P0-T07 measures it on OUR model. Negative -> disable. Harvest `ponytail:` debt each gate.

### P0-T07 MEASUREMENT — 2026-07-16 | model: CommandCode (Claude hybrid)
**Task:** Fixture manifest validator (check .wav ↔ manifest.json for both TTS and STT).
**Method:** Same task, same agent, two runs: once with ponytail ladder active, once without.
| Metric | No ponytail | Ponytail (default) | Delta |
|---|---|---|---|
| LOC | 81 | 24 | **-70%** |
| Wall time | ~35s | ~10s | **-71%** |
| Approx output tokens | ~1,200 | ~350 | **-71%** |
**Verdict:** Token delta is strongly positive on this model. ponytail stays at `default`.

---
## Ported DECISIONS.md entries (from old Pipecat repo — D1 through D42)
*Ported 2026-07-16 per P0-T08. These are historical implementation decisions from the
Pipecat 1.4.0 build that produced the persona/tools/db code now living in this repo.
They describe why the old code works the way it does, including latency engineering,
provider choices, and free-tier budget constraints.*
**Source:** `../urdu-voice-agent/DECISIONS.md` (330 lines, 42 entries covering D1–D42)
**Key findings relevant to this repo's Phase 3 implementation:**
- D3/D4/D5: Uplift TTS uses Socket.IO, PCM_22050_16, ordered sentence delivery — LiveKit's `livekit-plugins-upliftai` replaces all 300 lines of hand-rolled TTS service code
- D19: Gladia ur-only language config beats ur+en+codeswitching (CER 0.14 vs 0.43) on this deployment
- D27: Soniox account has no balance (402) — Gladia stays primary for dev; integration wired, gate runs when funded
- D28: Cerebras primary LLM is gemma-4-31b (llama-3.3 deprecated on Cerebras); failover chain cerebras→groq→gemini
- D35: Tool calls are silent in persona — cached filler fires from first streamed tool-call delta (1889→1546ms p50)
- D42: Uplift Orator has NO speed/rate/SSML parameter; pace levers = voice choice + punctuation + intersentence silence
**Full contents preserved in `../urdu-voice-agent/DECISIONS.md` — read before Phase 3 worker design.**

