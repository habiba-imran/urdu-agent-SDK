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
