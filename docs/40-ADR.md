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

### P0-T07 MEASUREMENT — 2026-07-16 (REDONE; supersedes the estimated entry) | model: claude-opus-4-8[1m] (Opus 4.8, 1M context)
**Prior entry retracted.** The first pass reported wall-time and token deltas that were
self-estimated, and labelled the run with a model ("CommandCode (Claude hybrid)") that is not the
one in use. That violates rule 8.3 (measured or cited, never estimated). It is replaced below.

**Task:** Fixture manifest validator (check .wav ↔ manifest.json for both TTS and STT).
**Method:** the same spec implemented twice — once verbose (ponytail-off discipline), once terse
(ponytail-default discipline). Both arms are committed, both run to the same result on this repo,
and the delta is recomputed from the files by a script, so it is reproducible, not asserted:
- `bench/ponytail/off/validate_fixtures.py` — baseline arm
- `bench/ponytail/on/validate_fixtures.py`  — ponytail arm
- `scripts/ponytail_measure.py`             — the counter; re-run to reproduce the table

| Metric (deliverable size) | off | default | Delta |
|---|---|---|---|
| Total lines | 119 | 38 | **-68%** |
| Code lines (no blanks/comments/docstrings) | 73 | 23 | **-68%** |
| Characters | 4407 | 1227 | **-72%** |
| Bytes | 4416 | 1229 | **-72%** |

**What this measures — and what it does NOT.** The figures above are the size of the CODE PRODUCED:
exact and reproducible from the committed files. They are NOT end-to-end agent *session* tokens or
wall-clock time. Those are not observable from inside the agent harness — the agent cannot read its
own usage metering, and a scripted Anthropic call to obtain a real `usage` field would be a paid
call needing a key (out of free-tier scope). Per rule 8.3 they are left unreported rather than
estimated. Session tokens are also the ONLY metric that could justify *disabling* ponytail
(AGENT_SYSTEM.md §1: "token balance goes NEGATIVE on verbose reasoning models"), so the omission is
called out, not buried.

**Reproducible protocol to measure session tokens (deferred — needs metered access):**
1. In two separate sessions, give the identical coding task; run one with `/ponytail-off`, one with
   `/ponytail-default`.
2. After each, read the token total from `/cost` (Claude Code) or the response `usage` field if
   driven via the SDK. Record input+output per session.
3. Negative delta (ponytail costs more) → disable ponytail. Tracked as a measurement candidate in
   state/BLOCKERS.md; it needs a metered environment the agent does not have.

**Decision:** keep ponytail at `default`. Basis is now the *measured* deliverable-size reduction
above plus `default` being the documented-safe setting (never `extremist`). **On the record:** the
session-token-balance risk is UNVERIFIED on this model; the vendor's ~22% token figure (line 42) is
vendor evidence, not our measurement. Re-evaluate via the protocol above before relying on ponytail
for token *cost* rather than code brevity.

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

