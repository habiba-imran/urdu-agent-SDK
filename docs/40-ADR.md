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
## ADR-007 Worker imports provider plugins at true `__main__` scope, on the real main thread   [ACCEPTED]
Date: 2026-07-17 | Found live during the Gate-3 human-listen call; fix verified against installed
`livekit.agents` source, human-approved to apply. **Revised same day** — the first accepted fix
below was itself wrong and failed on a second live attempt; this entry documents the corrected
mechanism, not the original guess, so a future reader isn't misled by the first draft.

**Context.** The first live Gate-3 attempt crashed immediately on job dispatch:
`RuntimeError: Plugins must be registered on the main thread`, raised by
`livekit.agents.Plugin.register_plugin()` (`livekit/agents/plugin.py` L30-33) when
`worker/factories.py::make_stt()` lazily imported `livekit.plugins.gladia` from inside the job
entrypoint. `factories.py`'s lazy-import design is deliberate (module docstring: "so this
module... load[s] without every provider plugin installed and nothing touches the network at
import") and is correct for keeping `pytest tests/test_worker.py` fast and dependency-light — but
it collided with a LiveKit Agents constraint we had not previously verified. This is a distinct
failure from the item-2 metadata-read risk flagged in HANDOFF — `build_session(md)` had already
run successfully; the crash was purely in provider-plugin construction.

**First fix attempt (WRONG — kept here only as engineering record).** We initially assumed every
job runs in its own OS subprocess (`multiprocessing`, name `"job_proc"`), and added
`WorkerOptions.prewarm_fnc`, reasoning it would run on that subprocess's own main thread before
the job entrypoint. `pytest` stayed green and the worker restarted cleanly — but the fix crashed
identically on the very next live join, this time on `from livekit.plugins import google, silero`
*inside `prewarm` itself*. `prewarm_fnc` was not exempt from the same guard; our model of where it
executes was incomplete.

**Actual mechanism (verified after the second failure).** `livekit/agents/worker.py` L126-130:
```python
if sys.platform.startswith("win"):
    # Some python versions on Windows gets a BrokenPipeError when creating a new process
    _default_job_executor_type = JobExecutorType.THREAD
else:
    _default_job_executor_type = JobExecutorType.PROCESS
```
On Windows (our dev platform), the default job executor is `THREAD`, not `PROCESS`. Under
`THREAD` execution, each "job process" is actually a plain `threading.Thread` named
`"job_thread_runner"` (`ipc/job_proc_lazy_main.py::thread_main()` L459-480), spawned **inside the
same OS process** as the worker and sharing its `sys.modules` cache — it is NOT a separate
subprocess. `thread_main()` calls `client.initialize()`, which invokes `prewarm_fnc`, from inside
that thread — which is not the process's main thread. So on Windows, `prewarm_fnc` alone never
satisfies the main-thread guard, regardless of what it imports.

**Decision.** Call `worker/main.py::prewarm(None)` directly at true `__main__` top-level scope,
**before** `cli.run_app()` is invoked — the one place on Windows guaranteed to execute on the
process's actual main thread, since no job thread exists yet. `sys.modules` is process-wide, so
every later import of the same module — from `prewarm_fnc`, or the per-job lazy imports in
`factories.py`, from any thread — hits the cache and never re-registers. `prewarm_fnc` is still
also wired into `WorkerOptions` for portability: on non-Windows platforms the default genuinely is
`JobExecutorType.PROCESS`, where each job gets its own OS subprocess and `prewarm_fnc` *does* run
on that subprocess's own real main thread before its job entrypoint (`proc_main()`,
`ipc/job_proc_lazy_main.py` L68-99: `client.initialize()` strictly before `client.run()`) — so it
remains correct there, redundant-but-harmless on Windows. `prewarm()` now returns the dotted names
of every plugin module it imported; `__main__` asserts each one is actually in `sys.modules`
before calling `cli.run_app()` and prints the confirmed list — direct evidence, not an inference
from Python's general import-caching behavior, checked on every worker start. Live output at the
corrected startup: `[prewarm] confirmed in sys.modules before any job thread:
['livekit.plugins.google', 'livekit.plugins.silero', 'livekit.plugins.gladia',
'livekit.plugins.upliftai']`, immediately followed by LiveKit's own `"plugin registered"` log line
for all four — independent confirmation from the framework itself.

**Consequences.** `factories.py`'s lazy-import design is preserved as-is (no behavior change to
provider selection; `pytest tests/test_worker.py` reconfirmed 5/5 green after both the original
and the corrected fix, since `pytest` never invokes the `__main__` block or spawns a real job
thread/process, so it cannot exercise this path either way — this class of bug is invisible to the
unit-test gate by construction). **Any future provider added to `factories.py` must also be added
to `prewarm`**, or it will hit this identical crash the first time it's used in a real live job on
Windows. The `sys.modules` assertion in `__main__` will now fail loudly and immediately on worker
startup if that's ever missed, rather than surfacing mid-live-call.

**Evidence.** `livekit/agents/plugin.py` L30-33 (the main-thread guard); `livekit/agents/worker.py`
L126-130 (`JobExecutorType` platform default — the fact that actually mattered), L186
(`prewarm_fnc` field), L437 (wired into the proc pool); `livekit/agents/ipc/job_proc_lazy_main.py`
L68-99 (`proc_main`, the `PROCESS`-executor path — correct for non-Windows) and L459-480
(`thread_main`, the `THREAD`-executor path actually taken on Windows — where the first fix's
assumption broke). Full crash tracebacks (both attempts) and the corrected worker's clean
re-registration log, including the `sys.modules` evidence line, are in the Gate-3 session
transcript, 2026-07-17. Trap logged in `state/PROGRESS.md` Traps section.

---
## ADR-008 Adaptive interruption forced explicit — was silently dev-mode-only   [ACCEPTED]
Date: 2026-07-17 | Post-Gate-3 quality pass, item 1 | Verified against installed `livekit.agents`
source, not assumed.

**Context.** Gate-3's live call surfaced an interruption-handling complaint. The worker never set
`turn_handling`, so whether "adaptive" (ML-based, LiveKit-hosted) or plain VAD-based interruption
detection was active depended entirely on undocumented auto-detection.

**What was verified (`livekit/agents/voice/agent_activity.py::_resolve_interruption_detection`,
L4183-4228).** Adaptive interruption requires ALL of: STT `capabilities.streaming` and
`capabilities.aligned_transcript` both truthy, a VAD instance present, `turn_detection` not
`"manual"`/`"realtime_llm"`, and the LLM not an `llm.RealtimeModel`. Our gladia/silero/google config
satisfies every one of these (gladia sets `streaming=True, aligned_transcript="word"` —
`livekit/plugins/gladia/stt.py` L279; `google.LLM` subclasses plain `llm.LLM`, not `RealtimeModel`
— `livekit/plugins/google/llm.py` L100). **But** even when all of that holds, if no mode is
explicitly requested, adaptive interruption is auto-enabled ONLY when `LIVEKIT_DEV_MODE=1` or
`utils.is_hosted()` is true (`agent_activity.py` L4218-4225). `LIVEKIT_DEV_MODE=1` is set
automatically by the CLI's `dev`/`console` subcommands only (`cli/_legacy.py` L1611-1616) — **not**
by `start` (production). So tonight's Gate-3 call (`python -m worker.main dev`) had adaptive
interruption active by accident of which CLI subcommand launches the worker, and it would have
silently fallen back to plain VAD-based interruption in production, logging only a single INFO line
("adaptive interruption is disabled by default in production mode") — easy to miss.

**Decision.** `worker/main.py::build_session()` now passes
`turn_handling={"interruption": {"mode": "adaptive"}}` explicitly to `AgentSession(...)`, making dev
and prod behave identically, and logs the configured value (`session.interruption_detection`) at
session start. Also noted: the `AdaptiveInterruptionDetector` (`livekit/agents/inference/
interruption.py`) is a **LiveKit Cloud-hosted inference call** over websocket
(`LIVEKIT_INFERENCE_URL`/`{base_url}/bargein`, authenticated with `LIVEKIT_API_KEY`/
`LIVEKIT_API_SECRET`) — not a local/free component. It was firing live during tonight's call
("adaptive interruption detector initialized", "adaptive interruption session created" in the
worker log) with no cost tracked anywhere in `usage_ledger.json`. **Addendum, same day:** the quota
is now on record — LiveKit's docs (docs.livekit.io/agents/logic/turns/adaptive-interruption-
handling/, fetched live) state plainly: *"For local development and testing, every plan includes
40,000 free inference requests per month"* (unlimited/free instead for agents deployed to LiveKit
Cloud). Added as `livekit_adaptive_interruption_req` in `scripts/usage_guard.py` /
`state/usage_ledger.json`, `limit: None` (informational, never fails the gate) — because `used` is
NOT instrumented (nothing increments a real per-call count yet), not because the quota is uncapped.
**Still open:** what happens past 40,000/mo (hard block vs overage billing) is not stated on that
page — unverified. Real per-call instrumentation is future work, not done here.

**How to confirm which mode is actually active in any future log.** LiveKit's own
`"adaptive interruption detector initialized"` INFO line (`inference/interruption.py` L336-347)
fires only when construction succeeds; a WARNING (`"interruption_detection is provided, but it's
not compatible with the current configuration and will be disabled"`, `agent_activity.py`
L4199-4201) means it silently fell back to VAD. These are the ground truth, not an assumption.

**Consequences.** Explicit config removes the dev/prod discrepancy. Residual risk: if
`STT_PROVIDER` ever changes to a plugin without `aligned_transcript`/`streaming` support, this
falls back to VAD-based interruption with a WARNING log, not a crash — `soniox` was checked and
also sets `aligned_transcript="chunk"` (`livekit/plugins/soniox/stt.py` L178), so the existing
`STT_PROVIDER=soniox` seam stays compatible; `deepgram` was NOT checked (plugin not installed in
this environment) — flagged, not verified.

**Evidence.** `livekit/agents/voice/agent_activity.py` L4183-4228; `livekit/agents/voice/
agent_session.py` L466 (`interruption_detection` derivation), L1841-1843 (property); `livekit/
agents/voice/turn.py` L150-165 (`InterruptionOptions` TypedDict, `mode` key); `livekit/agents/
utils/misc.py` L49-60 (`is_dev_mode`/`is_hosted`); `livekit/agents/cli/_legacy.py` L1611-1616
(`LIVEKIT_DEV_MODE` set only for `dev`/`console`); `livekit/plugins/gladia/stt.py` L279; `livekit/
plugins/google/llm.py` L100; `livekit/agents/inference/interruption.py` (whole file, hosted
inference call). `pytest tests/test_worker.py` reconfirmed 5/5 green.

---
## ADR-009 STT `code_switching` — explicit False, D19 re-checked, no material change found   [ACCEPTED]
Date: 2026-07-17 | Post-Gate-3 quality pass, item 2 | INPUT-side (how STT interprets the customer's
mixed speech) — distinct from ADR-010 (OUTPUT-side, how the LLM generates its own mixed speech).

**Context.** D19 (ported `DECISIONS.md`, old Pipecat repo, raw-Gladia-WebSocket integration)
measured `languages=["ur"], code_switching=False` at CER 0.14 vs `["ur","en"], code_switching=True`
at CER 0.43 — Gladia produced English TRANSLATIONS of pure-Urdu speech for half the test set. Task
instruction: do not enable `code_switching` without addressing D19 head-on; check whether Gladia's
model has materially changed since; if unchanged, leave off and say so explicitly; if there's a case
to revisit, propose a separate flagged test, don't bundle it in.

**What was checked (not guessed).** `livekit-plugins-gladia` 1.6.5 installed source
(`gladia/stt.py` L205-211): the constructor's default `model` is **already `"solaria-1"`**
(`GladiaModels = Literal["solaria-1"]` — `gladia/models.py` L3; this plugin version does not expose
any other model), and the default `code_switching` is **`True`** — our `factories.py` call did not
override either, so it was running Solaria-1 with the Python-level default `code_switching=True`.
This did not regress live tonight only because we pass a single-element `languages=["ur"]`, and
Gladia's own docs state: *"If one language is set, this option will be ignored"*
(docs.gladia.io/api-reference/v2/live/init, confirmed via fetch). Checked Gladia's changelog
(gladia.io/changelog) and code-switching docs (docs.gladia.io/chapters/language/code-switching) for
a material accuracy change since D19: the only recent model-accuracy entries are Solaria-3 (June 10,
2026 — English/European languages) and a Hebrew accuracy upgrade (March 16, 2026) — **neither
mentions Urdu or code-switching accuracy**. The code-switching docs page itself still warns that
broad language sets cause *"frequent misdetections—especially between similar-sounding
languages"* — consistent with, not contradicting, D19's finding. A general Gladia blog post claimed
Solaria-1 has "native code-switching support" reducing WER "by up to 55% at language boundaries",
but this is marketing copy, not a changelog/benchmark entry, and was not treated as evidence.

**Decision.** `worker/factories.py::make_stt()` now passes `code_switching=False` EXPLICITLY
(previously implicit-and-moot via the single-language override) — defensive: if a second language
is ever added to `languages`, the plugin's `True` default won't silently re-enable it unnoticed.
D19's conclusion stands, unchanged, as of 2026-07-17.

**Proposed (not applied) future test, flagged separately per the task instruction.** Gladia is
actively shipping per-language accuracy upgrades (the Hebrew entry is the precedent — before/after
WER improvement, single language). If Gladia ever ships a comparable dedicated Urdu upgrade,
re-measure `code_switching=True` CER against the current D19 baseline before considering it. Not
scheduled; no date; not this pass.

**Evidence.** `livekit/plugins/gladia/stt.py` L205-211 (constructor defaults); `livekit/plugins/
gladia/models.py` L3 (`GladiaModels` literal); docs.gladia.io/api-reference/v2/live/init
(single-language overrides `code_switching`); gladia.io/changelog (Solaria-3, Hebrew entries, dated);
docs.gladia.io/chapters/language/code-switching (current guidance); ported `DECISIONS.md` D19.
`pytest tests/test_worker.py` reconfirmed 5/5 green.

---
## ADR-010 Persona rewritten for calibrated code-switching + disfluency (OUTPUT-side)   [ACCEPTED]
Date: 2026-07-17 | Post-Gate-3 quality pass, item 4 | OUTPUT-side (how the LLM generates its own
mixed Urdu/English speech) — distinct from ADR-009 (INPUT-side STT code-switching).

**Context.** The prior persona (`persona.py` v6) instructed "Natural Pakistani Urdu with everyday
English tech words" — a vague style instruction with worked examples ONLY for brand/tech-term
Latin-script formatting (ADR-006 Layer 1), none for the natural code-switching RATIO of ordinary
words. Task instruction: give the system prompt specific worked examples of the target
code-switching ratio/style (not just brand names), and explicit personality/disfluency instructions
per LiveKit's own prompting guidance, since under-specified prompts are known to mis-produce
code-switching.

**Research checked (not guessed).** LiveKit's prompting guide (docs.livekit.io/agents/start/
prompting/) recommends: state formatting rules for TTS explicitly (plain text, no markdown, brief
replies); be SPECIFIC about disfluencies — pair "um" with a pause and a recovery word, since filler
words don't appear in LLM output without explicit prompting; treat emotion controls as guardrails —
an agent that swings between emotional registers within one turn "will sound very unstable"; and
reinforce rules from multiple angles (state the rule, show examples, restate with more examples).
Separately, "Code-Mixing and Code-Switching for Text in the LLM Era: A Playbook" (arXiv 2602.11181v2,
§3.2 "Prompting Strategies for Controlled Code-Mixed Generation") states plainly: *"Vague
instructions like 'act as a bilingual speaker' are often insufficient for maintaining a mixed
output"* and recommends explicit constraint/rule-based prompting over persona-only instructions —
directly on point for what our prior STYLE paragraph was doing.

**Decision.** `persona.py` `SYSTEM_PROMPT` (v7): STYLE now shows two full worked-example utterances
demonstrating the target code-switching ratio for everyday words («دیکھیں، ہمارے پاس ایک اچھا
option ہے، آپ کے بجٹ میں fit بھی ہو جائے گا۔» / «بالکل، میں ابھی check کر لیتی ہوں، one second
دیجیے۔»), with an explicit rule (grammar/verbs/structure stay Urdu; don't switch every noun; never
produce a mostly-English sentence) stated alongside the examples per the "state + show + restate"
pattern. Added a tightly-bounded disfluency allowance (at most once per reply, never stacked, never
on a firm answer, paired with a pause+recovery word) and an emotional-register stability guardrail
(stay warm and stable across a call; don't swing registers within one reply) — both cited LiveKit
guidance, not invented. PACING was reworded to state explicitly that Uplift has NO SSML/rate/pitch
control **at all** — a hard product constraint, not a tunable — so a future session doesn't spend
time looking for a config fix that cannot exist (reinforced in ADR-012).

**Consequences.** `SYSTEM_PROMPT_V1` (the original, kept for reference/A-B testing) is untouched.
This is a prompt-only change; nothing here is machine-verifiable by `pytest tests/test_worker.py`
(reconfirmed 5/5 green — unaffected, as expected) — quality can only be judged by a human listening
to the next live call. Not applied: no live call was made to validate this rewrite tonight, per the
task's explicit "no live call" instruction.

**Evidence.** docs.livekit.io/agents/start/prompting/ (fetched 2026-07-17); arXiv 2602.11181v2 §3.2
(fetched 2026-07-17); ADR-006 (Layer 1 precedent this extends, not replaces).

---
## ADR-011 Endpointing: no change proposed; filler-on-tool-call blocked by a deeper bug   [PROPOSED — not applied]
Date: 2026-07-17 | Post-Gate-3 quality pass, item 5 | Propose only, per task instruction — nothing
in this entry has been applied to code.

**Endpointing.** Verified (not assumed) that the worker uses LiveKit's own ML turn detector
("turn-detector-v1", confirmed live in tonight's log: `"audio turn detector initialized"`), which is
a `_StreamingTurnDetector` — so the EFFECTIVE current values, since `worker/main.py` never overrides
`turn_handling["endpointing"]`, are LiveKit's OWN streaming defaults: `min_delay=0.3s,
max_delay=2.5s, alpha=0.9, mode="fixed"` (`livekit/agents/voice/turn.py` L142-147), confirmed live
in the eot-prediction log lines (`"endpointing_delay": 0.3"` appeared repeatedly). Per LiveKit's
turn-handling docs (docs.livekit.io/reference/agents/turn-handling-options/): with the audio turn
detector, unset `min_delay`/`max_delay` already default to 0.3/2.5 instead of the older 0.5/3.0,
"since the model provides a confident end-of-turn signal, so the agent can commit sooner"; in STT
mode the delay is applied ON TOP OF the STT provider's own end-of-speech signal, and D21 (ported
DECISIONS.md) measured Gladia's finalization lag at ~550-650ms after VAD stop — so real perceived
latency is closer to (Gladia's own lag) + 0.3s, not 0.3s alone.

**Proposal: no change right now.** Current values already match LiveKit's own documented defaults
for the exact turn-detector configuration in use; there is no live-measured complaint from tonight's
call specifically about response latency (the "interruption complaint" that motivated ADR-008 was
about the agent not reacting to being talked over, not about how long it waits before replying) to
justify deviating from documented guidance. **If** a future live-listen judges response timing too
slow, the first lever to try is lowering `min_delay` toward ~0.15-0.2s (trading some false-turn-
boundary risk on noisy audio, per LiveKit's own stated tradeoff — LiveKit's docs: "lower it from the
default to push response time down at the cost of more false turn boundaries"), not touching
`max_delay`. This must be validated against a real live-listen, not applied blind.

**Filler-on-tool-call: evaluated, correctly NOT built — blocked by a bug found live tonight, not by
this evaluation's downside citation alone.** D35 (ported DECISIONS.md) precedent: the old repo's
cached filler fired from the FIRST STREAMED TOOL-CALL DELTA — i.e., triggered by the model's actual
structured function-call output beginning to form, not by the model verbally announcing an
intention. Cited downside, checked precisely (not the vague "~48%" the task description
approximated): "Full-Duplex-Bench-v3: Benchmarking Tool Use for Full-Duplex Voice Agents Under
Real-World Disfluency" (arXiv 2604.04847v1) measured **Ultravox v0.7** specifically — a DIFFERENT
architecture where the model speaks a filler sentence BEFORE deciding to call the tool — at a
**47.9% interruption rate** ("interrupts users... nearly half of all turns") and inflated
task-completion latency to **8.40s** ("the model speaks before it calls any tool... deferring tool
execution until after the filler inflates task-completion latency to 8.40s"). This is evidence
against Ultravox's specific speak-then-decide pattern, not proof D35's event-triggered pattern has
the same flaw — but it is the real, cited caution the task asked for, and it argues for the
tool-call-EVENT trigger (D35's design), never a model-verbalized one.

**The actual blocker, found live during tonight's Gate-3 call, not by this evaluation.** `tools.py`'s
functions are **not currently wired as real LiveKit function-calling tools** on the `AgentSession` —
observed live: the LLM emitted literal `tool_code\nprint(search_products(price_range_min=45000,
price_range_max=55000))\n` as spoken assistant TEXT (confirmed via the worker's own
`conversation_item_added` log), which Uplift then synthesized and (per the worker log) sent to
speech. There is no real "first streamed tool-call delta" event happening right now for a filler to
trigger on — `search_products`/`get_store_policy` do not actually execute; the LLM appears to
hallucinate plausible-sounding results afterward (a second turn produced a fluent but unverifiable
"used Dell" answer with no tool call in between). **This is a separate, more fundamental bug than
filler timing** — logged as its own trap in `state/PROGRESS.md`, NOT fixed in this pass (out of the
six items' scope; fixing it requires understanding LiveKit's function-calling API wiring, a
distinct investigation). Filler-on-tool-call cannot be meaningfully evaluated or built until this is
fixed first.

**Evidence.** docs.livekit.io/reference/agents/turn-handling-options/ (fetched 2026-07-17);
`livekit/agents/voice/turn.py` L142-147; live worker log, Gate-3 session, 2026-07-17 (eot-prediction
lines, `conversation_item_added` lines); arXiv 2604.04847v1 (fetched 2026-07-17); ported
`DECISIONS.md` D21, D35.

---
## ADR-012 Honest capability ceiling — what's fixed tonight, what's structurally capped   [ACCEPTED]
Date: 2026-07-17 | Post-Gate-3 quality pass, item 6 | Written so nobody chases an unfalsifiable
"Retell-parity" target, or reports something "fixed" that can't be verified without spending
unapproved budget.

**Fixed/addressed tonight (ADR-008 through ADR-011, all `pytest tests/test_worker.py` 5/5 green,
none live-validated yet — that's the next session):**
- Adaptive interruption now explicit and platform-independent (was accidentally dev-mode-only).
- STT `code_switching` explicit `False` (was implicit-and-moot; now defensive against future
  language-list growth); D19 re-confirmed current, no Gladia change found for Urdu.
- Persona rewritten with worked code-switching-ratio examples, bounded disfluency, emotional
  stability guardrail — cited against LiveKit's prompting guide and code-switching-generation
  research, not guessed.
- Endpointing confirmed already correct per LiveKit's own guidance for our turn-detector; no blind
  change applied. Filler-on-tool-call correctly identified as blocked by a real tool-calling wiring
  bug (see ADR-011 and the PROGRESS.md trap), not built.
- Uplift phrase-replacement config: 16 entries reused verbatim from the old repo's human-verified
  D42 config, 8 new entries proposed and flagged for human confirmation before going live (item 3;
  see PROGRESS.md — NOT yet executed, pending sign-off, since it's a real write to a live Uplift
  API even though ADR-006 established it's zero-TTS-budget).

**Structurally capped by the current free-tier stack — no prompt or persona change can fix these:**
- **Uplift Orator has NO SSML, rate, pitch, or emotion parameter at all** (D42, reconfirmed
  tonight). Pacing is 100% punctuation-based. This is an API/architecture ceiling, not a quota
  ceiling — per H9 (docs/41-HUMAN-TASKS.md), even Uplift's Enterprise tier should NOT be assumed to
  add this; it needs to be asked about explicitly, not assumed away by paying more.
- Gladia STT finalization lag (~550-650ms, D21) is a vendor-side latency floor on the tier we use.
  Soniox is measured ~400ms faster AND 6x cheaper (ADR-002) but is blocked on a 402 (unfunded).
- The LiveKit Adaptive Interruption Detector (ADR-008) is a LiveKit Cloud-hosted inference call,
  not a local/free component — it fired live tonight with zero cost tracking in
  `usage_ledger.json`. Whether/how this is metered is UNVERIFIED — open item, not investigated
  further this pass.

**Not a free-tier ceiling — a real bug, fixable without money, not fixed tonight:** the tool-calling
wiring gap (ADR-011, PROGRESS.md trap) means `search_products`/`get_store_policy` do not actually
run; the LLM emits pseudocode and/or hallucinates results instead. This is the single most
functionally important finding from tonight's call and should be the FIRST thing addressed in the
next work session, ahead of any further quality polish — a beautifully-paced agent that invents
inventory data is a worse product than a plainly-paced one that doesn't.

**What would need a paid tier to close further:** Soniox STT (funding unblocks an already-written
integration, ADR-002); Gemini paid tier or the cerebras→groq→gemini failover chain (P3-T06 finding,
free-tier RPM caps after ~6 rapid calls); a TTS vendor other than Uplift, if true prosody/emotion
control is ever required — this is an ADR-001-level vendor decision, not a Phase-3 quality-pass
scope, and Uplift's own Enterprise tier should not be assumed to solve it without asking (H9).

**The line to hold:** "sounds as good as it can within these constraints" is falsifiable and
achievable. "Sounds like a paid competitor with prosody control we don't have" is not achievable on
this stack at any dev-tier budget, and treating it as a bug to keep chasing would be a category
error, not a quality gap.

---
## ADR-013 Tool-calling rework (P3-T09) and remaining voice polish DEFERRED to end-of-build   [ACCEPTED]
Date: 2026-07-17 | Decided by: the human (recorded here per that instruction)

**Decision — scope and sequencing, not a technical design.** P3-T09 (wiring `tools.py` onto
LiveKit's function-calling API — see `docs/23-PHASE-3-WORKER.md` P3-T09) and all remaining
voice/persona/prosody polish (the 8 unconfirmed Uplift phrase-replacement transliterations from
tonight, any further persona/prompt iteration) are **explicitly deferred to a dedicated pass at the
END of the build**, after the SDK and remaining phases (4 onward) are done. **Added to this deferred
scope the same night, after being found:** the `detection_delay=1103ms` interruption-latency finding
(ADR-014 addendum 1(c)) — resolving it needs several real Uplift-spending conversation samples, so
it's bundled here rather than chased in isolation. This supersedes the
"top priority, fix before further polish" framing recorded earlier the same night in
`state/PROGRESS.md` and `docs/23-PHASE-3-WORKER.md` — that framing was reasonable when written
(right after the bug was found live) but is now stale; both files have been corrected in place to
point here rather than silently left contradicting this entry.

**Why (as given).** Not stated as a technical reason — this is a sequencing/priority call by the
human. Recorded plainly so a future session doesn't silently re-litigate or re-derive a different
priority order from the code alone.

**tools.py's eventual rework — the shape, decided now so it isn't assumed differently later when
the deferred pass starts.** The tool suite will be **fixed, platform-owned tool functions — NOT
tenant-configurable custom tools** (i.e., not "each tenant defines their own tools/catalog," which
`docs/23-PHASE-3-WORKER.md`'s P3-T09 draft had left as an open option). It will query **this
project's real schema** (`tenants`, `agents`, `sessions`, `quota_state`, `usage_events`, `voices` —
see `supabase/SCHEMA.md`) **with proper per-tenant RLS**, replacing the old demo's
`shop_info`/`products`/`customers`/`reservations`/`support_tickets`/`callbacks` tables entirely —
those were the single-tenant TechZone Pipecat demo's tables and do not belong in the multi-tenant
product. This is a real schema-migration task (new tables/migrations, RLS policies, `tools.py`
rewritten against them), not a quick wiring fix — scoped for the deferred pass, per the sequencing
decision above.

**Consequences.** No code changes from this entry — it is a scope/sequencing record only.
`docs/23-PHASE-3-WORKER.md` P3-T09 stands as the technical prep (verified against installed
`livekit.agents` source: `Agent(tools=[...])`, `@function_tool(raw_schema=...)`, return-based
results, `RunContext`) for whenever the deferred pass begins, now with the schema/ownership
question closed rather than left as "ask." Do NOT start building any part of this — not the
function-calling wiring, not the schema migration, not further persona/phrase-replacement
iteration — until the deferred pass is explicitly begun.

**Evidence.** This ADR entry is the evidence — a direct human instruction, recorded verbatim in
intent per `AGENT_SYSTEM.md`'s "state in files, never conversation" rule. Cross-referenced in
`state/PROGRESS.md`'s tool-calling trap and `docs/23-PHASE-3-WORKER.md` P3-T09.

---
## ADR-014 P3-T08: 6 concurrent connections all succeeded — the documented "5 concurrent, hard
## cap" was NOT observed   [ACCEPTED — recorded as-measured, not explained]
Date: 2026-07-17 | P3-T08, live test, human pre-approved | Real result, not the expected one —
reported honestly rather than forced to match `docs/30-GUIDE-FREE-TIER.md`'s assumption.

**Context.** `docs/30-GUIDE-FREE-TIER.md` §4 and `docs/23-PHASE-3-WORKER.md` GATE 3 both state
LiveKit Build free tier caps at **5 concurrent**, with calls FAILING past it, and P3-T08's done-when
is explicitly "5 succeed, 6th fails cleanly with a typed error." A prior session (`state/HANDOFF.md`,
Session 5) found a headless `livekit.rtc` (Python) client HANGS on this Windows environment, so a
new driver was needed: `scripts/concurrency_test.py` + `scripts/concurrency_test_client.html` use
Playwright + real Chromium + the actual `livekit-client` 2.x JS SDK (already a declared Phase-4
dependency, `sdk/package.json`) to make 6 real WebRTC room connections, no media tracks published
(the concurrency cap is documented as enforced at the participant/session level, not at
track-publish time). A dedicated tenant was provisioned per run with `max_concurrent=20` so the
control plane's OWN per-tenant quota (`quota_state.concurrent_now`, `control_plane/mint.py`
L121-128) — already elevated from earlier tonight's undecremented Gate-3 test mints — could not
confound the result; only LiveKit's own cap was being exercised.

**What was actually observed, live, 2026-07-17 14:49-14:50 UTC+5.** All 6 connections reported
`connected` (none reported `failed`). The worker log independently confirms this: 6 real job
requests dispatched, 6 job runners initialized, Gladia STT sessions connected for at least 4 of the
6, adaptive interruption sessions created for all visible ones. No `429`, no rejection, no
LiveKit-side cap of any kind fired. The sessions then tore down naturally ~30s later when the test
browser pages closed (no audio was ever published, so the worker's `wait_for_participant()`-based
entrypoint raised `RuntimeError: room disconnected while waiting for participant` on room close —
expected given the test's design, not a new bug).

**What this does NOT prove.** The test connections were short-lived (~30s) and did not publish
audio; it's possible LiveKit Build's cap is measured differently (sustained duration, published
tracks, agent-minutes burn rate, or a threshold above 6) than "raw simultaneous room joins," and a
longer or larger test might still find a real ceiling. The test also only checked each page's FIRST
terminal status — a delayed rejection a few seconds after "connected" would not have been caught by
this run's polling loop (a real methodology gap, noted rather than hidden). This entry does NOT
claim "there is no cap" — it claims "the specific claim in our docs (5 concurrent, hard fail) was
not reproduced at n=6 under this test's conditions," which is a narrower, honest statement.

**Decision — do not guess why, record the discrepancy and stop.** Per CLAUDE.md's anti-hallucination
rule ("never invent a number... cannot verify it, write it in BLOCKERS.md, do not invent it"), no
explanation is asserted here for WHY the documented cap didn't trigger — that would be guessing.
GATE 3's "5 concurrent OK, 6th fails cleanly" checklist item is marked with the REAL result (all 6
succeeded) rather than force-fit to the expected one. Whether to re-test at a larger N, check the
LiveKit Cloud dashboard/plan details directly, or accept the documented "5 concurrent" figure as
stale is a decision for the human, not assumed here.

**Consequences.** `docs/30-GUIDE-FREE-TIER.md`'s "5 concurrent" LiveKit Build figure should be
treated as UNVERIFIED-BY-US going forward until re-checked, not as ground truth. `livekit_agent_min`
in `usage_ledger.json` was NOT updated by this test — it stayed at 0, the same instrumentation gap
already flagged (nothing in `worker/main.py` increments it on session end). Actual LiveKit
agent-minute spend for this test is an ESTIMATE, not measured: 6 sessions × ~30s wall-clock ≈
3 agent-minutes if billed continuously, or up to 6 agent-minutes if LiveKit rounds each session up
to a whole minute — reported as a bounded estimate, not a ledger fact, per the same anti-hallucination
rule. `scripts/concurrency_test.py` and `scripts/concurrency_test_client.html` are committed and
reusable for a future, larger-N or longer-duration re-test if the human wants one.

**Addendum 2026-07-17 (human review) — Uplift spend, real hypothesis, and interruption-latency
comparison, none of which were in the original entry.**

**(a) Uplift spend was genuinely ZERO, not "unmeasured" — verified, not estimated.**
`.env.local` had `UPLIFT_MODE=live` active for the entire test (never reverted after the Gate-3
call). But `worker/main.py`'s entrypoint (`ctx.connect()` → `wait_for_participant()` →
`build_session()` → `session.start(agent, room=...)`) never calls `session.generate_reply()` or any
other auto-greet — the agent only speaks in response to a real STT transcript. None of the 6 test
clients published any audio track (deliberate, to avoid fake-mic-device setup in headless
Chromium), so Gladia STT received zero audio frames and never produced a transcript; the LLM/TTS
path was never entered. **Uplift TTS spend for this test was 0 seconds — confirmed by tracing the
code path, not inferred from the unchanged ledger value.** `livekit_agent_min`'s 3-6 minute figure
above remains an estimate (a different, far less constrained resource — 1000/mo budget, not
Uplift's 600s-total-forever). **Consequence, stated plainly:** this test exercised ONLY room-join/
job-dispatch concurrency — it did not exercise STT, LLM, TTS, or adaptive-interruption inference
load, so it does not fully validate the free-tier concurrency concern for a real, speaking call.

**(b) Working hypothesis for why all 6 succeeded (previously left unstated on purpose — now
answered).** Reconstructed precise timing from the worker log: first job dispatched 14:49:43.818;
the other 5 arrived in a 7ms burst at 14:49:45.068-14:49:45.075; all 6 job runners initialized by
14:49:45.366; teardown did not begin until ~14:50:15. **All 6 sessions were simultaneously live for
a sustained ~30-second window — this rules out "peak load never actually hit 6."** The overlap was
real. Leading hypothesis, given (a): LiveKit Build's concurrency accounting is likely gated on
**active media flow (published/subscribed audio), not raw room presence** — none of the 6 sessions
ever exchanged a single audio frame in either direction, and it's plausible that only
actively-streaming sessions count against the "5 concurrent" limit. Secondary, non-exclusive
possibility: the documented figure is stale for the current Build tier; not independently checked.
**Cheapest next test (not built, not run — flagged as the concrete next step):** modify
`concurrency_test_client.html` to publish a synthetic tone via `MediaStreamAudioDestinationNode`
(Web Audio API, no real mic/permissions needed) instead of zero tracks. This exercises genuine
published/subscribed media at zero Uplift risk (a tone won't transcribe as speech, so the agent
still won't be triggered to reply) and would directly test the media-flow-gating hypothesis.

**(c) detection_delay=1.103s checked against LiveKit's own published numbers, not the unverified
"86% precision / 100% recall" figures from earlier pasted research.** Fetched
`livekit.com/blog/adaptive-interruption-handling` directly: LiveKit states a **median of ~216ms of
audio** needed before the model decides, with inference completing in **≤30ms** — a published
typical total of roughly **~250ms**. Our one measured sample: `prediction_duration=38ms` (closely
matches their ≤30ms inference claim), but `detection_delay=1103ms` — **roughly 4-5x their published
median.** Reads as slow on this single sample, not within normal range. Partial, grounded (not
complete) explanation: `livekit/agents/inference/interruption.py`'s own source sets
`AUDIO_PREFIX_DURATION = 1.0` (a full second of pre-roll context included in the detector's default
analysis window) — if LiveKit's 216ms figure is measured post-overlap-onset only (excluding
prefix), that config difference could account for part of the gap. **n=1 — not enough samples to
know if 1.1s is typical for this setup or a one-off (cold-start, network RTT to the "India West"
inference region from this dev machine, etc.).** Needs several more real interruption events,
captured live, before treating 1.1s as a stable number rather than a fluke.

**Status: OPEN, explicitly carried into the deferred end-of-build voice-quality pass (ADR-013) —
not attempted or re-tested before then.** Resolving this needs several real Uplift-spending
samples (genuine two-way conversation turns, not the zero-audio/synthetic-tone probes used for
P3-T08), so it is deliberately bundled with the rest of the deferred voice-quality work (P3-T09,
the 8 unconfirmed phrase-replacement entries, further prompt iteration) rather than chased in
isolation now. Recorded here so the deferred pass starts with this already scoped in, not
re-discovered from scratch.

**Evidence.** Live worker log, 2026-07-17 14:49:43–14:50:18 (job dispatch, job runner init, Gladia
connections, adaptive interruption sessions, clean teardown — full transcript in the session
record); `scripts/concurrency_test.py` output (`connected=6 failed=0 other=0`); `control_plane/
mint.py` L121-128 (the control-plane's own quota check, deliberately avoided via
`max_concurrent=20`); `docs/30-GUIDE-FREE-TIER.md` §4 (the documented, unreproduced claim);
`state/HANDOFF.md` Session 5 (the prior headless-`livekit.rtc`-hangs finding that motivated the
Playwright-based driver).

**Addendum 2 2026-07-17 (same day) — synthetic-tone re-test, a real methodology gap found and
fixed, and a corrected full-pipeline result.**

**(d) The synthetic-tone re-test proposed in Addendum 1(b) was run — and initially FALSIFIED the
media-flow-gating hypothesis, before a deeper methodology gap was found underneath.**
`concurrency_test_client.html` now supports `publishTone=1`: a real, continuous audio track
published via Web Audio API (`MediaStreamAudioDestinationNode`, a 220Hz near-silent sine — no mic,
no permissions, zero transcription/Uplift risk per Addendum 1(a)'s reasoning). First run at n=6:
**all 6 connected AND published real media — still `connected=6 failed=0`.** This falsifies the
leading hypothesis from Addendum 1(b): real published/subscribed media alone does not trigger the
documented cap either.

**(e) But that first tone run — and both original runs — likely never exercised a genuinely ACTIVE
agent session at all.** Investigating why the ledger showed 0 after that run (see ADR-016 addendum)
surfaced the real issue: `worker/main.py`'s entrypoint calls `ctx.wait_for_participant()` **before**
`session.start()`, and the test script closed each page almost immediately after observing
`"connected"` client-side. The worker log showed the SAME crash on every affected session:
`RuntimeError: room disconnected while waiting for participant` — `wait_for_participant()` was
still pending when the room's disconnect (from the fast page-close) cancelled it, so the entrypoint
never reached `build_session()`, `session.start()`, or (for the ADR-016 fix) the shutdown-callback
registration. **This means every prior concurrency result in this ADR (original 6-way, and the
first tone-published 6-way) most likely measured ONLY room-join concurrency — the LiveKit signaling
layer accepting a connection — not full-agent-session concurrency (STT connected, adaptive
interruption running, an actual dispatched `AgentSession`).** That is a materially weaker claim
than "5 concurrent agent sessions," and is flagged here explicitly rather than left implied by the
earlier "connected=6" framing.

**(f) Corrected re-test: sessions held open long enough for the full pipeline to complete.** Added
`HOLD_OPEN_S = 15` to `concurrency_test.py` — after all pages report `"connected"`, the script now
waits 15s before closing any of them. Verified live this DOES fix it: `wait_for_participant()`
resolved, `build_session()` completed (confirmed via this project's own
`"interruption_detection configured=adaptive"` log line — ADR-008 — firing for all 6),
`session.start()` ran, Gladia STT connected, the adaptive interruption detector initialized, and all
6 sessions closed CLEANLY on disconnect (`"session closed", "reason": "participant_disconnected",
"error": null`) — no crashes, unlike every prior run. **Real, corrected result: still `connected=6
failed=0`, this time under a genuinely full-pipeline, sustained (~15s), 6-way concurrent load. No
cap fired.** This is the most faithful test run tonight of what `docs/30-GUIDE-FREE-TIER.md`'s "5
concurrent" claim is actually about, and it still did not reproduce the claim.

**(g) Real measured usage delta, corrected for a race condition found in the same test (full
account: ADR-016 addendum).** The corrected 6-way run's 6 confirmed job-exits should have added 6
minutes to `livekit_agent_min`; the ledger only recorded +3 due to an unsynchronized
`increment()` racing itself under genuine concurrent-thread load (Windows `JobExecutorType.THREAD`
runs each job's shutdown callback on its own thread in the same process). Fixed with a
`threading.Lock`, verified non-live with a 300-call concurrent-thread stress test, and the ledger
was manually corrected (+3) to the true value. **Combined with the earlier single-session
verification (+1), the real, measured, race-corrected total from tonight's instrumentation testing
is `livekit_agent_min = 7`** — a real ledger fact, not an estimate, replacing every wall-clock
guess in this ADR's original body and Addendum 1.

**Updated consequence.** `docs/30-GUIDE-FREE-TIER.md`'s "5 concurrent" LiveKit Build claim has now
been tested THREE ways tonight (no media, synthetic media, and full-pipeline sustained load with
real media) and never reproduced once. It should be treated as actively contradicted by evidence
under these test conditions, not merely "unverified" — `docs/30-GUIDE-FREE-TIER.md` updated
accordingly (see the diff alongside this entry). Whether the true LiveKit Build cap is higher than
6, scoped differently (e.g., per-org billing tier upgrade, not a hard technical limit), or the
figure was simply wrong when originally written is still not determined — that would need either a
much larger-N test or checking the LiveKit Cloud dashboard/account plan directly, neither done here.

**Evidence.** Live worker logs, both re-test runs, 2026-07-17 15:52-16:00 (job dispatch, the
`wait_for_participant()` crash traceback, `interruption_detection configured=adaptive` ×6, Gladia
connection, clean `session closed`/`job exiting` ×6); `scripts/concurrency_test.py` /
`concurrency_test_client.html` (current versions, committed); `state/usage_ledger.json` (`7`,
verified not estimated); ADR-016 addendum (the race-condition fix and its own verification).

---
## ADR-015 Phase 4 client SDK: real implementation, GATE 4 machine lines closed   [ACCEPTED]
Date: 2026-07-17 | P4-T01 through P4-T05, non-live | `sdk/src/index.ts`

**Context.** Phase 3's Gate-3 confirmed the session/token contract
(`{token, wsUrl, roomName}` — `control_plane.mint.mint_session`), which the Phase-4 scaffold
(committed earlier, `sdk/src/index.ts` throwing "not implemented — Phase 4" everywhere) was
explicitly waiting on before real work could start. All non-live Phase-4 tasks done in one pass per
the new standing operating pattern.

**Decision — implementation shape, verified against installed `livekit-client` 2.20.1 source, not
guessed:**
- **P4-T01/T02 (transport + session lifecycle).** `connect({agentId})` POSTs
  `options.sessionEndpoint` with `{publishableKey, agentId}`, expects
  `{token, wsUrl, roomName}` back (this SDK's own public contract — the host's server is expected
  to relay our control plane's `POST /v1/session` response verbatim, since we don't control their
  endpoint's shape and this is the natural pass-through). Connects via `new Room(); room.connect
  (wsUrl, token)` (`livekit-client` L16405-16408). **Beyond the literal API sketch in
  `docs/24-PHASE-4-CLIENT-SDK.md`:** `connect()` also calls
  `room.localParticipant.setMicrophoneEnabled(true)` and fails the whole `connect()` call if it
  throws — a voice agent SDK that never publishes the caller's microphone doesn't do what the
  product is for, so this was added on that reasoning rather than left out because the doc's
  4-line sketch didn't spell it out. If this is unwanted (e.g., a push-to-talk product built on top
  of this SDK), it's a one-line change to make opt-in — flagged, not silently assumed permanent.
- **P4-T03 (typed events).** `on(event, cb)` backs a plain listener-set map. `'transcript'` ←
  `RoomEvent.TranscriptionReceived` (segments → `{text, final}, `livekit-client` L30465-30467).
  `'speaking'` ← `RoomEvent.ActiveSpeakersChanged` (boolean: any active speaker, L12238-12245).
  `'ended'` ← `RoomEvent.Disconnected` (L12130, passes the disconnect reason through).
  `'error'` ← `RoomEvent.MediaDevicesError` for POST-connect device failures (mic unplugged
  mid-call, permission revoked — L12360-12364) — a genuinely new wiring decision, since the doc's
  API sketch lists `'error'` as subscribable but doesn't say what fires it; initial-connect
  failures instead reject the `connect()` promise (a `try`/`await` failure), which is the more
  idiomatic split (setup errors reject, runtime errors emit).
- **P4-T04 (error taxonomy).** HTTP `429` from `sessionEndpoint` → `quota_exceeded`; `404` →
  `agent_not_found`; anything else non-2xx, a network/fetch failure, an incomplete JSON response,
  or a LiveKit connect failure → `session_failed`. Raw error text/exceptions are never attached to
  the thrown `UvaError` for any of the internal-failure paths (network, JSON parse, LiveKit
  connect) — only `MediaDevicesError`'s message is passed through, deliberately, since that's the
  end user's own local browser/device error, not something about our infrastructure, and is
  actionable for the host app to display ("please allow microphone access").
- **P4-T05 (build + bundle scan).** `npm run build` = `tsc` (unbundled ESM output; `livekit-client`
  stays an external import for the host's own bundler to resolve — the scaffold's original build
  script choice, kept as-is, a normal pattern for published npm libraries). `dist/index.js`:
  **5765 bytes raw, 2162 bytes gzipped**. `dist/index.d.ts`: 1485 bytes.

**GATE 4 result — full account in `docs/24-PHASE-4-CLIENT-SDK.md`.** `make bundle-check` → EXIT 0.
`grep -rE '(API_KEY|SECRET|SERVICE_ROLE|Bearer )' dist/` → zero matches (exit code 1). `npm ls` →
only `livekit-client` + `typescript`(dev), zero provider SDKs. "Works from a foreign origin" is
verified by code inspection (no same-origin assumption anywhere in the code — `sessionEndpoint`
and `wsUrl` are both runtime-supplied, no cookies sent, nothing reads `window.location`), not by an
actual live two-origin test — flagged as inspected, not empirically run. **HUMAN GATE — per
`docs/24`'s own line, "you personally grep `dist/`" — is NOT satisfied by the automated grep above
and is not claimed to be; it is the human's own remaining step.**

**Consequences.** No live/paid API call was made anywhere in Phase 4 — `sessionEndpoint` was never
actually called against a real host server (none exists yet), so `connect()`'s live path is
type-checked and code-reviewed but not exercised end-to-end. That end-to-end exercise naturally
happens once a real host integration exists (Phase 5+ or an external integrator), not invented here
as a fake test harness.

**Evidence.** `sdk/node_modules/livekit-client/dist/src/room/participant/LocalParticipant.d.ts`
L95-100 (`setMicrophoneEnabled`); `livekit-client.esm.mjs` L12103, L12130, L12238-12245,
L12360-12364, L30465-30467 (the `RoomEvent` definitions cited above); `control_plane/app.py` and
`control_plane/mint.py` (the response shape this SDK's contract mirrors); literal `make
bundle-check`, secret-grep, and `npm ls` output pasted to the human alongside this gate.

---
## ADR-016 `livekit_agent_min` instrumentation gap closed — real session duration now recorded   [ACCEPTED]
Date: 2026-07-17 | Closes the "estimate, not measured" caveat from ADR-014 going forward.

**Context.** ADR-014 flagged that `livekit_agent_min` in `state/usage_ledger.json` stayed at 0
despite real LiveKit usage across the whole session, because nothing in `worker/main.py` recorded
real session duration — every reported figure was a wall-clock estimate, not a ledger fact. On the
one resource this project treats as effectively unrecoverable in spirit (LiveKit Build's 1000
agent-min/mo hard cap — less severe than Uplift's 10-minutes-forever, but still a real budget), an
estimate is not good enough going forward.

**Decision.** `worker/main.py::entrypoint()` now records `_session_started_at = time.monotonic()`
right before `session.start()`, and registers `ctx.add_shutdown_callback(_record_agent_minutes)` —
verified against installed source (`livekit/agents/job.py` L525-535: `JobContext.
add_shutdown_callback`, "called when the job is shutting down," accepting an optional `reason: str`
argument) — the accurate end-of-session signal, since `session.start()` does not block until the
conversation actually ends (confirmed live all session: job teardown happens on room disconnect,
independent of when `entrypoint()`'s own function body returns). On shutdown, elapsed wall-clock
time is converted to whole minutes, **rounded up** (`max(1, math.ceil(elapsed_sec / 60))`), and
added to `livekit_agent_min` via a new `scripts/usage_guard.py::increment(key, amount)` helper
(simple read-modify-write against `state/usage_ledger.json`; not safe against concurrent writers —
acceptable since only one worker process runs against this file in dev, not a production
data-integrity mechanism).

**The rounding convention is an ASSUMPTION, stated plainly, not a verified LiveKit billing rule.**
Whole-minute-rounded-up is a common cloud-metering pattern (and matches the framing already used in
ADR-014's estimate), but LiveKit's actual billing granularity for Build-tier agent-minutes was never
independently confirmed against their docs. If it turns out to differ (e.g., per-second billing),
this instrumentation will over- or under-count relative to LiveKit's real invoice — flagged now so
that gap doesn't get silently assumed away later.

**Consequences.** Every future live worker session — Gate-3-style human-listen calls, concurrency
re-tests, anything — now writes a real, measured delta to `livekit_agent_min`, not an estimate.
`pytest tests/test_worker.py` reconfirmed 5/5 green (this code path is only exercised by a real
`JobContext`, which the test suite doesn't construct — the same class of gap noted for `prewarm` in
ADR-007: correctness here is verified by source-reading + live exercise, not by the unit gate).

**Evidence.** `livekit/agents/job.py` L525-535 (`add_shutdown_callback`); live exercise via the
synthetic-tone concurrency re-test that follows this entry (first real measured delta, not
estimated — see the next ADR entry for the actual recorded number).

**Addendum 2026-07-17 (same day) — a real race condition, caught by the concurrency test itself,
found and fixed.** First live exercise: a single held-open session correctly recorded `+1`.
Second live exercise: the corrected 6-way concurrency re-test (see ADR-014 addendum 2) confirmed
**6** clean job-exits in the worker log, but the ledger only recorded **+3**. Root cause:
`increment()`'s read-modify-write (`u = load(); u[key] += amount; write`) was not synchronized.
LiveKit's default `JobExecutorType.THREAD` on Windows (ADR-007) runs each job's shutdown callback
on its own OS thread **within the same worker process** — 6 callbacks fired within ~3 seconds of
each other, and unsynchronized concurrent writes lost updates (a classic lost-update race, textbook
case, not a novel bug). **Fixed:** wrapped `increment()`'s critical section in a module-level
`threading.Lock()` — this fixes the actual observed failure mode (concurrent threads in one
process) but does NOT make the file safe against separate OS processes writing concurrently (e.g.,
a worker process and a simultaneously-run `usage_guard.py --report`) — that would need a real file
lock, not implemented, since the observed bug was in-process. **Verified the fix, non-live:** a
local stress test (6 Python threads × 50 concurrent `increment()` calls each = 300 total,
snapshotting and restoring the real ledger around the test) landed exactly on the expected total
every time — `before=4 after=304 expected=304 MATCH=True`. **Ledger manually corrected** for the
3 minutes lost to the pre-fix race (6 confirmed job-exits, all real, all should count): `+3` applied
directly, bringing the ledger to the true value (1 + 6 = 7), rather than leaving a known-wrong
number on record. This is the kind of bug free-tier budget tracking exists to catch — logged
plainly, not smoothed over, per the same discipline as every other finding tonight.

---
## ADR-017 Voice picker uses 3-4 owned artworks, not Uplift character artwork — H9 #5 no longer blocks Phase 5   [ACCEPTED]
Date: 2026-07-17 | Decided by: the human (recorded here per that instruction, per the same
"state in files, never conversation" discipline as every other decision tonight)

**Decision.** The Phase-5 voice picker will use **3-4 owned artworks** rather than Uplift's
character artwork. `docs/41-HUMAN-TASKS.md` H9 #5 ("May we use your character artwork in a
commercial voice picker? (Blocks P5.)") and the Phase-5 human-gate row ("Confirm H9 #5 licence
answer before shipping any Uplift artwork") are both updated to reflect this — struck through, not
silently deleted, with the reasoning left in place so a future reader sees what changed and why,
not just a blank space.

**Why (as given).** Not stated as a technical or legal reason — a product/asset decision by the
human. Recorded plainly, same as ADR-013's sequencing decision, so it isn't re-derived or
re-litigated differently later by an agent working from the code alone.

**Consequences.** H9's other four questions (concurrency limit, 429 trigger, minute-1,501 behavior
Pro tier, Enterprise rate above 200h/month) remain live and still block Phase 8 — unaffected by
this decision, not touched here. Phase 5, when it starts, should source/prepare the 3-4 owned
artworks as part of its own scope — not specified further here, since that's Phase-5 implementation
work, not a decision to make now.

**Evidence.** This ADR entry and the corresponding edits to `docs/41-HUMAN-TASKS.md` are the
record — a direct human instruction in this session.

---
## ADR-018 Phase 5 non-live work: real voice catalogue, DB-level enable check, picker UI scaffold   [ACCEPTED]
Date: 2026-07-17 | P5-T01, P5-T04, P5-T05, non-live | `supabase/migrations/0005_*`, `0006_*`,
`voice-picker/`

**P5-T01 — voice catalogue source and confidence, stated plainly.** Uplift does not document a
programmatic "list voices" API endpoint (checked: no such path exists in their API reference as of
2026-07-17). The only source is their docs page `docs.upliftai.org/orator_voices`. Extracted via
**three independent WebFetch calls** (different prompts, one asking for a different column
schema) that agreed exactly on the total count (82) and every field checked across overlapping
rows — treated as adequately corroborated for a docs-sourced (not raw-API) dataset, but flagged at
that confidence level, not overclaimed as API-verified. `gender` is derived mechanically from the
internal "File" codename's `_m_`/`_f_` pattern (consistent across all 82 entries), except
`khwajasara` — left `NULL` rather than mechanically labeled, since the source page itself
described this voice as androgynous/gender-unspecified across every extraction attempt, not a
one-off artifact. `supabase/migrations/0005_voices_catalogue.sql` seeds these 82 as the current
picker catalogue; `v_meklc281` (this project's own demo voice, seeded in `0003`) and Uplift's other
"Legacy" voices are a separate, smaller, differently-ID'd set for existing integrations — **not**
merged into the new catalogue; whether they should ever appear in the picker is an open question,
not decided here. Applied directly (not via `make db-reset`, which would wipe unrelated tenant
data) — `voices` now has 83 rows, verified.

**P5-T05 — DB-level enforcement, not application code.** A FK alone can't express "and the
referenced voice must be enabled" (Postgres CHECK constraints can't do cross-table lookups). Added
a `BEFORE INSERT OR UPDATE OF voice_id` trigger on `agents` (`0006_agents_voice_enabled_check.sql`)
that raises `check_violation` if the target voice isn't enabled. Chosen over application-level
validation because no agent-creation application code exists yet (that's Phase 6 admin-portal
territory) — a DB-level trigger means no future write path can bypass it, including ones not yet
written. Tested live against the real dev DB, both directions: disabling a real voice and
attempting an insert correctly raised `CheckViolation`; re-enabling and inserting succeeded; test
tenant/agent rows cleaned up (cascade delete). Not a fixture/mock test — the actual trigger, the
actual table, verified by trying to break it.

**P5-T04 — UI scaffold, two things deliberately left undecided rather than guessed.**
`voice-picker/index.html` queries the real `voices` table directly via `@supabase/supabase-js` +
the public anon key — safe by the RLS policy `voices_read_all [SELECT] USING (enabled)`
(`supabase/RLS.md`), the same trust model every Supabase client app relies on; no custom backend
needed just to list voices. Verified live (Playwright, against the real free dev DB — not a
provider call): renders all 83 real voice cards, every play button correctly disabled since
`preview_url` is `NULL` everywhere (P5-T02 hasn't run). Two things NOT decided here, flagged rather
than silently assumed: (1) **where this UI is actually hosted/embedded** — a new top-level
`voice-picker/` directory was created as a minimal, framework-agnostic scaffold, but whether it
belongs inside Phase 6's admin portal, as a standalone tool, or something else was not decided;
(2) **the artwork-to-voice mapping** (ADR-017: 3-4 owned artworks, 82 voices) — cards show a
deterministic generated color-monogram placeholder instead of guessing which artwork maps to which
voice, since that's a real design decision, not an engineering one.

**Consequences.** GATE 5's actual checklist ("all voices render," "preview plays," "zero calls to
Uplift," "signed URLs expire") still needs P5-T02 (live Uplift recording, human-approved, not yet
run) and P5-T03 (CDN upload) before it can close — this entry only closes the non-live prep work.
`pytest tests/test_worker.py` reconfirmed 5/5 green throughout (Phase-5 changes don't touch the
worker).

**Evidence.** `docs.upliftai.org/orator_voices` (3 independent fetches, 2026-07-17);
`supabase/RLS.md` (the `voices_read_all` policy); live trigger test (both directions, this
session); live Playwright render test against the real dev DB (83/83 cards, 83/83 correctly
disabled).

---
## ADR-019 P5-T02 recording crash: washroom-singer cap breach, lost partial spend, script fix   [ACCEPTED]
Date: 2026-07-17 | P5-T02, `scripts/record_voice_previews.py`, `state/usage_ledger.json`

**What happened.** Human ran `UPLIFT_MODE=record python scripts/record_voice_previews.py` (live,
human-approved). It recorded 80/82 voices, then crashed on `washroom-singer`: that voice's
synthesis of the identical short greeting line exceeded the script's `PER_VOICE_MAX_SECONDS = 6.0`
per-line cap, which every other voice cleared in 2.6-5.1s. `wholesale-trader` (next alphabetically)
was never attempted — not because it was itself slow, but because the abort killed the whole
script rather than skipping one voice. Confirmed on disk: exactly 80 `.wav` files in
`voice-picker/previews/`, missing exactly `washroom-singer` and `wholesale-trader`.

**Ledger: true value, lost spend, and a reasoned correction.** Read `state/usage_ledger.json`
directly (not estimated, not a stale in-session figure): `uplift_tts_sec=305` at the moment of the
crash. The old `synth_one()` raised `SystemExit` *inside* the accumulation loop, before its own
`return bytes(pcm), sr` line — so the partial `pcm` bytearray (real, already-billed Uplift audio)
was discarded on the way out: never written to a file (confirmed: no partial `washroom-singer.wav`
exists on disk), never passed to `increment()`, and the `SystemExit` message itself carries no
numeric duration. This spend is genuinely unrecoverable from any log or file this script produced.
Per the same standard as ADR-016's race-condition correction, a stated, reasoned estimate was
applied instead of leaving the gap silent: **+8s**, applied via `usage_guard.increment` —
`uplift_tts_sec` 305 -> **313** (verified by re-reading the file after). Reasoning: (a) a **6.0s
confirmed floor** — the abort only fires once `len(pcm) / (2*sr)` has already crossed the cap, so
at least that much audio was generated and received; (b) a **+2s reasoned pad** for the overshoot
between crossing 6.0s and the check actually firing, grounded in reading the installed plugin
(`.../livekit/plugins/upliftai/tts.py`, `ChunkedStream._run` lines 396-412): Uplift delivers audio
as discrete WebSocket `"audio"` messages, each base64-decoded and pushed as one `audio_data` chunk
onto an `asyncio.Queue`, consumed and appended to `pcm` one chunk at a time — i.e. genuinely
incremental streaming, not one giant blob, so the overshoot at abort time is bounded by roughly one
chunk, not unbounded. The exact per-message chunk size is **not** documented or verified (would
require a live call to pin down, not done), so 2s is a deliberately generous, explicitly-labeled
pad, not a measured figure. **Residual, unresolved uncertainty, stated plainly, not papered over:**
whether Uplift's server-side synthesis job continues running (and billing) after the client stops
reading is unknown from the client library alone; this correction assumes billing tracks bytes
actually delivered to the client (consistent with this project's own ledger convention, which
meters received PCM bytes everywhere else), and could still be an undercount if Uplift's real
billing works differently. If the human checks Uplift's own dashboard and finds a different figure,
that number wins over this reasoned estimate.

**Root cause: verified, not guessed.** Re-fetched `docs.upliftai.org/orator_voices` (2026-07-17,
same source ADR-018 used) for `washroom-singer` specifically: description *"A gloriously tone-deaf
shower singer — every note off-key, yet utterly unable to stop belting,"* Group "Only in Pakistan,"
internal File codename `ai_naat_p4_m_za`. "Naat" is Islamic devotional poetry traditionally
performed in a melismatic, drawn-out, sung/chanted style, categorically different from ordinary
speech — unlike, e.g., `khateeb` (religious orator, File `ai_maulvi_p1_m_mna`, spoken not sung).
This is a **genuinely slower vocal delivery style baked into the voice model itself**, not a bug
and not specific to this script's text/config: all 81 other voices ran the identical code path,
identical `phrase_replacement_config_id`, identical text, and none crashed; `wholesale-trader`'s
absence is explained entirely by the crash-killed-the-run bug (item below), not by its own speed —
it was never attempted. Conclusion: **voice character, not a bug** — though the fix below still
treats a cap breach as an expected, handleable case rather than assuming it can't happen again.

**Fix: don't lose the spend, don't kill the run.** `synth_one()` now raises a local `CapExceeded`
exception carrying the partial `pcm`/`sr` instead of `SystemExit` inside the `try` block, so the
partial data survives the abort. The per-voice loop in `main()` catches `CapExceeded`, logs the
actual partial duration reached (`increment("uplift_tts_sec", round(partial_duration))` — partial
synthesis still costs real budget, silence about it is worse than the abort itself), prints a clear
skip message, and `continue`s to the next voice instead of letting the exception kill the whole
script — 80 good recordings should never be put at risk by one bad line. No preview file is written
for a capped voice (a clip truncated mid-note isn't a usable preview). **Not re-run yet** — per
standing process, any live-pipeline re-run needs explicit sign-off; the two remaining voices
(`washroom-singer`, `wholesale-trader`) are queued for a human-approved re-run, and `washroom-singer`
specifically also needs an explicit decision on its per-voice cap (whether to raise
`PER_VOICE_MAX_SECONDS` for it, trim its line, or accept/replace the voice) — deliberately left
undecided here, not silently bumped, per direct instruction.

**Evidence.** `state/usage_ledger.json` (305 before, 313 after, both read directly);
`voice-picker/previews/` directory listing (80 files, diffed against the 82-voice catalogue minus
`v_meklc281`); installed `livekit/plugins/upliftai/tts.py` (`ChunkedStream._run`,
`WebSocketClient._on_message`/`synthesize`); `docs.upliftai.org/orator_voices` (re-fetched
2026-07-17, `washroom-singer` and `khateeb` entries).

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

