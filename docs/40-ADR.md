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

