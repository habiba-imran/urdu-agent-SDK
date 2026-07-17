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
## ADR-005 Agent may use service_role for the control plane (dev only)   [ACCEPTED]
Date: 2026-07-16 | Decided by: the human (recorded here per that instruction)

**Deviation, stated plainly.** 33-GUIDE-SUPABASE.md originally said `service_role` is for migrations
only, run by a HUMAN, and NEVER read by the agent. That is now SUPERSEDED: the agent is authorized to
use `SUPABASE_SERVICE_ROLE_KEY` in server-side code going forward.

**What changed.** The agent now has `service_role` access, which BYPASSES RLS by design.

**Why.** The Phase 2 control plane / token mint (`POST /v1/session`) authenticates each tenant by
**HMAC — not by a Supabase JWT** — and must read a tenant's secret/status/quota and write the session
+ quota rows BEFORE any tenant JWT exists. RLS cannot govern a trusted service that, by design,
operates across the tenant boundary; so the mint's DB layer genuinely requires RLS bypass. This was a
human call, recorded here as the permanent record, not a one-line comment.

**Scope — narrowed, not blanket. Where service_role IS and IS NOT used:**
- USE service_role ONLY in server-side control-plane / mint operations that must cross the tenant
  boundary before authentication: tenant + agent lookup for HMAC verify and the IDOR check,
  `quota_state` read/increment, and the `sessions` insert (Phase 2, P2-T03 / P2-T05).
- Do NOT use it for anything RLS can already govern. Tenant-scoped reads during a live call (Phase 3
  worker reading its own tenant's rows) use the `authenticated` role carrying the tenant JWT.
- The ported `db.py` currently builds its default client with service_role and targets OLD-schema
  tables (conversations/messages/turn_metrics, not in this schema). It is Phase-3 rework and will move
  to the scoped role wherever RLS applies. Tracked as a Phase-3 item.

**Mitigation still in force.** The uva-dev / uva-prod project split (H1): the agent's service_role key
only ever touches DEV. Production is never in the agent's reach — that is the durable control. RLS
bypass on dev cannot exfiltrate prod data.

**Phase 7 note.** Phase 7's human gate ("attempt a cross-tenant read + a token-widening attack; both
must fail") must be run KNOWING the agent has broader dev-DB access than the original design assumed.
Those attacks must still fail regardless — what makes them fail is RLS on the app path plus the ≤120s
scoped-JWT mint, not the absence of a service_role key. If either attack succeeds, this deviation is
the first suspect.

---
## P3-T01 — Uplift plugin API (DECLARED; measured values pending the human-approved recording)
Date: 2026-07-16 | plugin: `livekit-plugins-upliftai` 1.6.5 (read from source, NOT yet exercised live)

**Declared (from `livekit/plugins/upliftai/tts.py`):**
- Sample rate is FIXED at **22050 Hz, mono** (`DEFAULT_SAMPLE_RATE=22050`, `num_channels=1`). Every
  output format is 22.05 kHz except `ULAW_8000_8` (8 kHz telephony µ-law, out of scope).
- **No latency/model tier** — the constructor has no `model` param (no ElevenLabs flash-vs-multilingual
  equivalent). Levers are `voice_id` (voice/character; pace is intrinsic per D42) and `output_format`.
- `output_format` ∈ {PCM_22050_16, WAV_22050_16/32, MP3_22050_32 (default)/64/128, OGG_22050_16,
  ULAW_8000_8}. The plugin default `MP3_22050_32` is LOSSY 32 kbps — wrong for a golden reference
  fixture; we record `WAV_22050_16` (lossless).

**Decision:** fixture voice `v_meklc281`, format `WAV_22050_16`. Reference utterance lives in
`tests/fixtures/reference_greeting.txt` (fixture key `c6228ded3cd7af7e5d49954e0cbae817`).

🔴 **PENDING:** the MEASURED sample rate + "is it audible Urdu?" confirmation from the human-approved
recording (`scripts/record_fixture.py`) is what actually COMPLETES P3-T01. This entry is updated with
the measured value once the human runs the recording. Until then, the plugin is UNVERIFIED-BY-US.

---
## ADR-006 Two-layer phrase-replacement for Uplift pronunciation   [ACCEPTED]
Date: 2026-07-17 | Decided by: the human (recorded here per that instruction)

**Context:** Listening to the recorded reference greeting fixture revealed that the old persona
transliterated English-origin brand names into Urdu script — "ٹیک زون" for "TechZone", "لیپ ٹاپس"
for "Laptops" — and the engine read them wrong. The product issue is real and audible in the
committed fixture.

**Evidence — Uplift's own docs confirm mixed-script works natively.** Their Node.js SDK docs show
an explicitly mixed example: "Meezan Bank اعتماد کا ضامن" — English-origin brand name in Latin
script, rest in Urdu script. Their phrase replacement docs state the feature handles exactly
this: brand names, technical terms, LLM misspellings, and regional variations.

**Evidence — Budget safety.** Phrase replacement config CRUD (`POST /v1/synthesis/phrase-replacement-config`)
is a REST config operation documented separately from TTS synthesis. It returns a `configId`, not
audio bytes. Creating a config does NOT synthesize audio — it modifies config state. Confirmed
by the endpoint appearing alongside `list/get/update` config management endpoints rather than
under "Text to Speech" synthesis. **Cost: zero TTS budget consumed.**

**Decision — Two layers:**

**Layer 1: Persona convention (the common case).** The system prompt instructs the LLM to write
English-origin words (brands/tech terms/products/units) in Latin script inline within Urdu
sentences. This covers ~90% of the problem — the LLM just stops transliterating. Example of
correct output: «TechZone میں MacBook Air M2 256GB 315000 روپے کا ہے» — not the old «ٹیک زون میں
میک بک ایئر ایم ٹو ہے».

**Layer 2: Phrase replacement config (the safety net).** A committed config at `.uplift_phrase_config`
(configId `38949e76-6ad9-4ff4-9caa-61419b387fc0`) exists as the wiring target. It is currently
EMPTY (0 entries). Mappings from the old repo's D42 list were removed — they were ported on
assumption, not measured. Layer 1 (Latin-script convention) may be sufficient on its own. When a
real mispronunciation is heard in a recording, the specific problem phrase goes here as a tested
correction, not a guessed one.

**Wiring:** configId read from `.uplift_phrase_config` by both `worker/factories.py` (live
sessions) and `scripts/record_fixture.py` (fixture recording). Both pass it as the
`phrase_replacement_config_id` keyword argument to `upliftai.TTS(...)`.

**The recorded greeting: what a fresh synthesis would sound like.** Without the Layer 1 change,
the old greeting `السلام علیکم! ٹیک زون لیپ ٹاپس میں خوش آمدید...` went through the engine with
transliterated brand names and mispronounced them. With Layer 1 (persona now outputting "TechZone")
+ Layer 2 (`MacBook→میک بک` in the config), a fresh synthesis would produce: the engine reads
the Latin "TechZone" correctly per its native mixed-script handling, and any residual LLM/
engine mismatches are caught by the phrase config. The human should evaluate whether to spend
budget on a re-record now or fold it into P3-T04.

---
## P3-T06 — Gemini free-tier throttling (MEASURED 2026-07-17, not assumed)
model: `gemini-2.5-flash` | `scripts/measure_gemini_tpm.py --turns 8 --confirm-live` | human-approved.
8 rapid sequential calls (16 input tok, ~11 output tok each):

| turn | latency_ms | status |
|---|---|---|
| 1 | 3547 | OK |
| 2 | 3172 | OK |
| 3 | 2937 | OK |
| 4 | 2485 | OK |
| 5 | 2859 | OK |
| 6 | 1922 | OK |
| 7 | 203 | **429 RESOURCE_EXHAUSTED (throttled)** |
| 8 | 609 | **429 RESOURCE_EXHAUSTED (throttled)** |

**Throttle onset: turn 7** — the free-tier RPM cap hits after ~6 rapid calls (~18s). Successful-call
latency 1.9–3.5s. (Exact RPM not captured — the script truncates the 429 body; observed as a hard
reject after 6 rapid calls.)
**D14 parallel (Groq throttled to TTFB 13–30s at ~4 turns):** Gemini's free-tier failure mode is a
HARD 429 (it REJECTS, not slows) — different shape from Groq's latency creep. In a real voice call
turns are spaced by seconds of user speech, so a single caller is less likely to hit the RPM cap than
this burst test; but a burst, or several concurrent tenants, WILL 429. **Implication:** production
needs the paid Gemini tier and/or LLM failover (the ported config.py already defines a
cerebras→groq→gemini failover chain — wire it in the Phase-3 worker LLM path). Ledger unchanged
(17/600 uplift, 0 livekit) before + after — Gemini touches neither.

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

