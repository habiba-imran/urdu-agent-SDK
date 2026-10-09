# Phase 1 verification and completion report

Execution started 2026-10-08 and completed 2026-10-09 (Asia/Karachi). Scope: **Phase 1A–1L only** of `HUMANIZATION_IMPLEMENTATION_PLAN_CODEX.md`, which was read in full. Older test filenames containing `phase2` through `phase7` are existing regression tests, not implementation of those phases.

**STATUS: PASS. IMPLEMENTATION GATE: PASS. ACTIVATION GATE: NOT_APPLICABLE** for this non-audible instrumentation phase. Phase 2 has not started. No deployment, provider call, package installation, dependency upgrade, voice/model migration, business-write change or audible candidate activation occurred.

## Preflight and preserved work

- Branch `main`, HEAD `c37fd73fd7bce0766496d7068c49d400f1c36e17`; same Phase 0 baseline.
- The tree already contained portal/telephony edits, deleted client deliverables, the replacement plan, Phase 0 documents/corpus and untracked telephony files. These were preserved.
- Existing changes in `worker/main.py` were inbound room/session resolution and call-status tracking. Phase 1 adds only the provider snapshot, diagnostic userdata, existing greeting-cache activity observation and telemetry wiring around them.
- Existing telephony additions in `tests/ci_unit_manifest.txt` remain; two telemetry test files were appended.
- Originals of `main.py`, `latency.py`, `tools.py` and the manifest were copied into the ignored evidence directory before editing.
- Final hash comparison against Phase 0's 681 captured paths: exactly the eight intended existing source/test files changed; **673 unchanged, zero unexpected changes, zero dependency/lockfile changes**. `worker/usage.py`, `worker/session_close.py`, `worker/telephony_runtime.py` and all unrelated dirty source remain unchanged from that snapshot. The ledger is a separate authorized Phase 0 document update.
- No graph JSON/wiki existed, so the conditional initial graph query did not apply. `graphify update .` was attempted after code changes; it fails with the existing `uv trampoline failed to canonicalize script path` environment error. No graph freshness is claimed.
- `docs/HUMANIZATION_RESEARCH_MASTER.md` remains absent. Phase 1's explicit observability requirements and inspected source were sufficient for this non-audible work; no missing research content was invented. Resolve that source gap before design-dependent work.

## Subphase evidence

| Subphase | Result | Implementation and verification |
| --- | --- | --- |
| 1A identities | PASS | Existing dispatch session ID where supplied, otherwise a labeled generated observability ID. Independent UUID user/assistant/generation/tool identities; framework speech/call IDs retained as correlation fields. One speech report contains distinct generations for tool continuations. Public event/task scope plus `RunContext` owns correlation. Unowned/late metrics never attach to the current turn. Concurrent tasks, user resumption, duplicate commits, overlapping speech stages and cross-session tool IDs tested. No chunk identity is invented before chunk planning. |
| 1B outcomes | PASS | All ten required labels supported. Terminal handle and provider cancellation/error evidence govern generation outcomes. Completed percentiles exclude all nine invalid outcomes. Speculation cancellation and actual tool outcome remain independent. Recoverable provider errors record retry activity without poisoning a successfully completed generation. |
| 1C tool timing | PASS | `tool_execution_updated` start/end is the sole duration owner. The HTTP wrapper annotates dependency outcomes with exact call/speech ownership and never records duration. Duplicate end events are ignored. Gateway integration asserts a 50 ms execution contributes once; nested tool duration is separately displayed and not added to the E2E proxy. Installed-framework integration also runs the real gateway function once between two LLM steps. |
| 1D stages | PASS | Monotonic user speech transitions, commit, LLM node start/first nonempty content, TTS node start/first output frame, speech terminal and tool start/end observations. Sequence numbers accompany structural events. Public hook wrappers preserve yielded objects, errors, cancellation and generator closure. No prompt/STT rewriting, chunk planner or state reducer. Missing stages remain null. |
| 1E distributions | PASS | At most 32 outcome/lane buckets, 256 samples per metric. Partitioned by STT/LLM/TTS provider and effective model, language, channel and operation. Completed normal-turn legacy aggregate remains available; greeting/platform speech is separate. Null/negative/nonfinite measurements are excluded. |
| 1F policy | PASS | Session/log/turn policy `baseline`; turn, delivery, streaming, language, channel and renderer component versions are constant `baseline`. No behavior-policy activation logic. |
| 1G snapshot | PASS | Requested/effective model distinction, normalized adapter options, voice, language/channel and installed plugin versions. Exact installed safe scalar option fields can correct resolver values for cached clients. Unknown vendor models remain null. Four active constructor lanes exercised offline: Deepgram/Groq with Cartesia, Rime and ElevenLabs; Gladia/Gemini/Uplift. `deployed_verified=false` explicitly distinguishes constructor configuration from deployed proof. |
| 1H SDK | PASS | New fields are optional and additive. Legacy `turn_latency` forwarding to `metrics_updated` remains compatible. Dual subscribers can filter aggregate events by `type`; integration frontend does so. Three new SDK tests cover legacy, additive/null and invalid/unrelated data contracts. |
| 1I privacy | PASS | New structural telemetry does not serialize caller text, tool arguments/results, auth, headers, URLs, prompts or whole private option/state dictionaries. Transcript logging explicitly disabled in telemetry tests. Secret/email/private-text sentinels tested, including arbitrary configured emotion/model strings. Only known installed emotion categories are exposed; unknown strings become null. Existing transcript/prompt-debug/recording controls are untouched. |
| 1J validity/overhead | PASS | Every percentile includes its own sample count, rolling window and descriptive confidence label. p95 requires 20 samples, p99 requires 100; these are display minima, not confidence guarantees. Ordered events use a session sequence and monotonic clock. First audio observation logs once, not per frame. Single/16-session CPU and serialization benchmark passes the explicit budgets below. |
| 1K engineering view | PASS | Existing integration debug event lines expose policy, identities, outcome, sequence and proxy type; its existing JSON pane/copy dump exposes provider snapshot, tools, generations and stage details. Cancelled/error turns remain inspectable and are excluded from its completed latency samples. Frontend typecheck/build pass; browser rendering/interaction has not been verified. |
| 1L usage | PASS | Existing `session.usage.model_usage` billing path untouched. Correlated provider token/audio metrics aggregate separately for normal turns, platform speech and cancelled/interrupted generations. Cache/prewarm/recoverable retry activity has independent structural records. Duplicate request metrics do not double usage. Summary accumulation is incremental, not a full historical rescan. Retry-specific tokens and unplayed audio remain null; `invoiceAccurate=false`. |

## Timing and outcome semantics

`stages` and `monotonicAt` use process-local monotonic **seconds**. Latency fields use **milliseconds**. These absolute timestamps are for ordering within the worker; do not subtract them from another machine's clock.

`llm_request_start` and `tts_request_start` mean entry to the existing default nodes. `first_useful_llm_text` currently means the first nonempty content delta; it is a structural text observation, not semantic or audible verification. `tts_first_audio` is the first output frame from the default TTS node. Provider TTFB metrics remain a separate diagnostic observation. Neither is caller playout. `first_speakable_chunk_ready` remains null until the requested later chunk-planning work exists.

`e2eMs` retains the legacy diagnostic component proxy, explicitly labeled `server_diagnostic_proxy` with `acousticVerified=false`. It combines the available EOU/STT, LLM TTFT and TTS TTFB diagnostics; missing values remain null when no component exists. It does not claim first useful audible word latency. Tool execution totals are separately diagnostic because tool/model/audio stages can overlap.

The production tracker waits for the public speech terminal callback before admitting a completed sample. A tool finishing after speech interruption emits its independent tool-finish outcome; the already published speech report is not rewritten as successful. Metrics arriving after a terminal report are stale and cannot resurrect it. Missing ownership remains explicitly unowned rather than guessed. Direct legacy metrics-only tracker use keeps its existing event contract; production wiring always enables terminal lifecycle tracking.

## Tests and checks

| Check | Final result |
| --- | --- |
| Original exact 23-file focused suite plus the two new Python suites | **224 passed, zero skipped/failed**, one existing Starlette deprecation warning; 36.47 s |
| New Python observability coverage within that run | **39 tests**, including real installed `AgentSession` with synthetic LLM/TTS, actual gateway wrapper, output sink and terminal callback; no network/room required |
| Repository offline CI manifest | **332 passed, 1 skipped, zero failed**, five existing warnings; 95.04 s |
| Browser SDK | `npm run lint`, `npm run build`, `npm test`: **PASS**, 29 tests across five files |
| Integration frontend | `npx --no-install tsc --noEmit`, `npm run build`: **PASS**; existing 608.15 kB Vite chunk-size warning |
| Focused Ruff | Latency/telemetry/tools, benchmark and new Python tests: **PASS** |
| Repository Ruff | **24 existing errors**, same error descriptions as Phase 0; no autofix/formatter or unrelated cleanup |
| Scoped whitespace | **PASS** with `cr-at-eol` permitted to preserve the existing CRLF test file; no whitespace edits to unrelated files |
| Source/dependency integrity | **PASS**, 673 captured paths unchanged, eight intended source/test changes, no lockfile/dependency changes |
| Graph refresh | **Environment failure**, uv trampoline path error; no graph was present |

The existing skip is `test_internal_targets_are_refused_when_hosted[https://127.1/hook]`: the offline guard blocks one DNS/connection attempt. That individual SSRF case remains unverified. The focused run has no skips. Repository-wide Ruff findings are not represented as a passing global lint check. Phase 0's broader package/dashboard/format evidence remains its historical baseline; those unchanged surfaces were not rerun as Phase 1 audio/runtime proof.

### Reproduction and local evidence

Evidence lives in ignored `tmp/humanization-phase1-20261008/`: focused/CI logs and JUnit, SDK lint/build/test logs, integration typecheck/build logs, focused/repository Ruff output, overhead JSON/log, source-integrity JSON and before-edit copies. Preserve this bundle before cleaning `tmp/`.

The `.venv` launcher still references the former Windows user. Verification uses host Python 3.12.10 with the already installed `.venv/Lib/site-packages`, through the preserved Phase 0 runner; no installation occurred. LiveKit agents/plugins remain 1.6.5, RTC 1.1.13. Node v24.12.0 remains different from CI Node 20.

From the repository root in PowerShell:

```powershell
$env:CI_UNIT_FORCE_OFFLINE='1'
$paths=Get-Content tmp/humanization-phase0-20261008/focused-suite.txt
python tmp/humanization-phase0-20261008/run_python.py pytest @paths tests/test_humanization_observability.py tests/test_humanization_observability_framework.py -q -rs

$env:SUPABASE_DB_URL=''
$env:TENANT_SECRET_ENCRYPTION_KEY='ci-unit-test-encryption-key'
$paths=Get-Content tests/ci_unit_manifest.txt | Where-Object { $_.Trim() -and -not $_.StartsWith('#') }
python tmp/humanization-phase0-20261008/run_python.py pytest @paths -q -rs

python tmp/humanization-phase0-20261008/run_python.py scripts/benchmark_humanization_telemetry.py --output tmp/humanization-phase1-20261008/overhead.json
```

### Instrumentation benchmark

The final synthetic benchmark uses a representative English provider snapshot, two observed LLM passes, observed TTS, a framework tool lifecycle, structural log formatting and optional room-payload serialization. Each session runs 300 turns. Disabled trials perform the same synthetic node passes. Logging writes to a no-I/O sink; room publication records serialized byte size. A separate 100,000-frame stream isolates first-frame observer overhead.

Budgets established for this workload: **3 ms p95 CPU handling per tool turn**, **10 µs added per frame**, **under 14,000 bytes per synthetic room payload**. Earlier minimal one-generation trials were superseded by this fuller workload; the report below is the final run, not an acoustic comparison.

| Concurrent sessions | Room serialization | Instrumented p95 handling |
| --- | --- | --- |
| 1 | OFF | 1.379 ms |
| 1 | ON | 1.531 ms |
| 16 | OFF | 2.068 ms |
| 16 | ON | 2.494 ms |

Maximum serialized payload: **4,639 bytes**. Added frame observer time: **0.334 µs/frame** (baseline 28.062 ms, observed 61.446 ms across 100,000 frames). All budgets pass. Percentiles are descriptive measurements of this machine/workload, not production load guarantees. Deployment log sink, real network publication, backpressure and real provider/acoustic E2E overhead are still unverified.

## Files read, changed and added

Read in full: the entire implementation plan; Phase 0 baseline/status; repository `AGENTS.md`; latency/tool implementations and relevant tests; provider cache/registry/types; active Deepgram/Gladia, Groq/Gemini, Cartesia/Rime/ElevenLabs/Uplift adapters and option resolvers; humanization package/turn configuration; transcript logging/usage; SDK metrics handling and integration diagnostics. Read relevant call paths in `worker/main.py` and usage/close persistence in `worker/session_close.py`, test runner/conftest/manifest and package manifests. Inspected exact installed public Agent/AgentSession/SpeechHandle/events, generation pipeline, tool executor, metrics and plugin option/model source. The original focused test paths are listed in Phase 0's `focused-suite.txt`. The missing research master and absent graph were verified as absent, not read.

Changed existing files:

- `worker/latency.py`: identities, terminal outcomes, stage observers, canonical lifecycle timing, bounded distributions and correlated diagnostic usage.
- `worker/tools.py`: diagnostic userdata; exact-call outcome annotations replacing duplicate wrapper duration.
- `worker/main.py`: session snapshot and observer wiring; observe existing startup/cache activity.
- `sdk/src/index.ts`: additive optional diagnostic types and legacy forwarding guidance.
- `client-integration-test/frontend/src/main.ts`: aggregate/turn filtering and structural debug fields.
- `tests/test_latency_phase2.py`, `tests/test_latency_phase3.py`: updated hook expectations, canonical tool timing/annotation regression assertions.
- `tests/ci_unit_manifest.txt`: include the two new suites, preserve existing entries.
- `docs/HUMANIZATION_IMPLEMENTATION_STATUS.md`: append Phase 1 completion and gates.

New files:

- `worker/telemetry.py`: policy/constants, safe provider snapshot, trace schema and bounded percentile primitives. Root location avoids the existing `humanization.__init__ -> turn -> latency` import cycle.
- `tests/test_humanization_observability.py`: deterministic identity/outcome/timing/privacy/cancellation/concurrency/provider-option contracts.
- `tests/test_humanization_observability_framework.py`: offline installed-framework user/tool/LLM/TTS terminal integration.
- `sdk/src/metrics.test.ts`: diagnostic compatibility tests.
- `scripts/benchmark_humanization_telemetry.py`: reproducible offline instrumentation benchmark.
- This verification report. Ignored local artifacts are evidence, not production modules.

## Required completion fields

**PHASE / SUBPHASE:** 1A–1L. **STATUS:** PASS. Files read/changed/new and tests/results are recorded above.

**BEHAVIOR BEFORE:** speech ID plus partial latency metrics; HTTP gateway and framework both contributed tool duration; no normalized terminal outcome or independent operation identities; median diagnostics without tail counts; legacy clients could process forwarded turns twice.

**BEHAVIOR AFTER:** the existing speech/provider/tool path remains authoritative. Structural traces correlate user, assistant, individual generations and independent tools; only terminal completed normal turns enter the completed aggregates; tool execution is measured once; options/policy/outcomes/counts and unavailable fields are explicit. Integration dual subscriptions count each turn once. Existing billing and write gates remain intact.

**FEATURE FLAGS / POLICY VERSIONS:** `humanization_policy_version=baseline`, all component versions `baseline`. No new audible flag. Existing `UVA_PUBLISH_TURN_LATENCY` controls room diagnostics, **default OFF**, without changing an explicit existing setting. Structural server diagnostics are **ON** through existing logging. `UVA_LOG_TRANSCRIPTS`/prompt debug controls are untouched. Later audible candidates remain **OFF/BLOCKED**.

**KNOWN LIMITATIONS / RUNTIME ITEMS STILL UNVERIFIED:** caller-side audio/first useful audible word, real provider/deployed model/voice/options, browser diagnostic interaction/audio, PSTN, deployed logging/publish/load overhead, billing/invoice agreement and actual retry/unplayed synthesis cost. Prewarm/cache records are activities, not claims of successful paid prewarming. Late or unowned metrics may lack attribution; exact billing stays with existing session usage. No universal log sanitization of unrelated existing framework/debug paths is claimed. Rolling windows/maps are bounded diagnostics, not a durable whole-call audit store. No live recording/listening baseline was created; the prior missing research source and infrastructure gaps persist.

**IMPLEMENTATION GATE: PASS. ACTIVATION GATE: NOT_APPLICABLE** for Phase 1. Later audible gates remain blocked pending their own evidence. **NEXT SAFE PHASE / SUBPHASE:** Phase 2 only upon a separate explicit request and fresh preflight. **SCOPE STOP: Phase 2 NOT STARTED.**
