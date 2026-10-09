# Humanization fast-track Batch A verification

Date: 2026-10-09 (Asia/Karachi).

PHASE / SUBPHASE: Fast-track Batch A; original Phase 4 and Phase 5 important P0 portions only.
STATUS: CODE_COMPLETE_ACTIVATION_BLOCKED.
IMPLEMENTATION GATE: PASS for the requested P0 batch.
ACTIVATION GATE: BLOCKED for new audible clarification/bridges; no caller-side or native listening evidence.
DEFAULT ENABLEMENT: core evidence/state observation, deterministic write guards, tool truth/error contracts ON; new clarification prompting and spoken bridge scheduler OFF.
NEXT SAFE PHASE / SUBPHASE: Stop here. A later batch needs a separate explicit request. Original Phase 6 and DeliveryIntent/TTS work are not started.

## Preflight and source evidence

Configured cwd `C:\Users\habib\Desktop\SDK\sdk-agent` does not exist on this host. Verified checkout is `C:\Users\habiba\Desktop\SDK\sdk-agent`; approved shell access used that path. Branch `main`, HEAD `c37fd73fd7bce0766496d7068c49d400f1c36e17`, unchanged. No commit, dependency upgrade, deployment, backend data mutation or live call.

Read the entire implementation status ledger, plan opening/universal rules, original Phases 4/5, and final execution/gate rules. `docs/HUMANIZATION_RESEARCH_MASTER.md` remains absent, confirmed by the current repository inventory. Its requested sections could not be read. Implementation uses the explicit user P0 requirements, current plan and executable source; no research-master or prior-chat claim is assumed.

FILES READ:

- `AGENTS.md`, the status ledger, scoped implementation plan sections and CI manifest.
- `worker/humanization/{state,events,runtime,agent,turn_plan,context_projection,policy,turn}.py`.
- `worker/tools.py`, `worker/write_tool_gate.py`, relevant `worker/main.py` event/bootstrap paths and `worker/telemetry.py` provider snapshot construction.
- `worker/providers/stt/deepgram.py`, `worker/providers/stt/gladia.py`, existing tool-prompt instructions in `worker/cartesia_spoken_output.py` and `worker/humanization/spoken.py`.
- Installed LiveKit public Agent/STT/session hooks, generation/tool-output conversion and Deepgram/Gladia plugin source. Actual versions: agents/Deepgram/Gladia 1.6.5, RTC 1.1.13.
- Relevant write/injection, runtime, Phase 3, observability, installed-framework, lifecycle, secret-guard, latency and provider regression suites. `tests/test_latency.py` and its helpers inspected after its collection failure.

FILES CHANGED:

- `worker/humanization/{state,events,runtime,agent}.py`.
- `worker/tools.py`, `worker/write_tool_gate.py`.
- `tests/ci_unit_manifest.txt`, `tests/test_tools_lifecycle_db.py`, `tests/test_wave5_residuals.py`.
- `docs/HUMANIZATION_IMPLEMENTATION_STATUS.md`.

NEW FILES:

- `worker/humanization/{evidence,understanding,coordinator,orchestrator}.py`.
- `tests/test_humanization_batch_a.py`.
- `tests/fixtures/humanization/repair.batch-a.json`.
- This report.

Before-edit copies, SHA-256 capture and JUnit artifacts are under ignored `tmp/humanization-batch-a-20261009/`. Integrity verification accepts only the listed existing files; all unrelated captured files retain their hashes. Original edited-file line endings preserved. Existing deleted deliverables/plan and dirty portal, telephony, SDK, frontend, latency and earlier-phase files preserved.

## Behavior and authority

BEHAVIOR BEFORE: grounding/TurnPlan existed as observer/shadow foundation, active transcripts were not parsed into critical state, gateway failures returned raw exception text, uncertain writes had telemetry labels without a safe business result contract, and waiting relied on prompts.

BEHAVIOR AFTER:

1. Public STT node yields original events unchanged while normalizing provider/model, final/interim text, language and available word timings. Nova alternative confidence is real; word confidence stays null because the installed plugins drop it. Gladia overall confidence stays null because the plugin substitutes 1.0 when absent. Flux confidence stays null; no experimental tuning. Timing comes from valid exposed words rather than zero/default timestamps. Actual plugin end-of-speech is endpoint evidence, never a semantic commit.
2. Committed input drives a deterministic InputUnderstanding parser for dates/weekdays, explicit times, digit phone numbers, literal emails, labelled person/doctor names, booking IDs and reference codes. Existing and replacement appointment dates have separate roles. Eleven English, Roman Urdu, Pakistani Urdu and mixed repair fixtures cover explicit supersession. Ambiguous/negated values remain unresolved. Real low Nova confidence (<0.65) is segment-scoped and requests repair; no aggregate confidence is invented. This local conservative floor is not endpoint tuning.
3. Explicit corrections supersede earlier active evidence, including confirmed values. Weaker inferred values cannot replace confirmed facts. The validated fields of a separately confirmed proposal become CONFIRMED; backend commitment remains a separate outcome.
4. The existing write gate additionally refuses missing/unresolved or mismatched current evidence, and refuses omission of unresolved optional target details. Required missing facts create a CLARIFY TurnPlan. Calendar weekdays cannot silently become arbitrary ISO dates: writes require matching current backend-offered slots or literal caller date/time evidence. Verified host/PSTN caller phone remains trusted and the ownership gate still applies. Negative/corrective/ambiguous replies invalidate the old proposal; a later yes cannot resurrect it.
5. TurnCoordinator tracks LISTENING, USER_SPEAKING, TURN_CANDIDATE, TURN_COMMITTED, AGENT_SPEAKING and INTERRUPTION_CANDIDATE from public framework/STT evidence. Only the framework commit boundary commits a turn. Media/VAD/endpoint thresholds, provider options, preemption settings and adaptive interruption are unchanged. Unchanged preemptive/final input copies can share a request identity within one epoch.
6. ToolExecutionPlan classifies fast/variable reads, proposals, commits, escalation records and session finalization. Gateway and lifecycle execution use provider-independent ToolResult outcomes: SUCCESS, NO_RESULT, VALIDATION_ERROR, CONFLICT, DEPENDENCY_TIMEOUT, DEPENDENCY_UNAVAILABLE, RATE_LIMITED, OUTCOME_UNKNOWN and CANCELLED. HTTP exception text is not passed to the model. Configuration failures have a structural diagnostic code and a safe speech summary.
7. Propose → separate explicit caller affirmation → deterministic ownership/schema/budget/confirmation gate → one POST is retained. A synchronous dispatch reservation stops concurrent duplicate confirmation POSTs. Read/write/protocol loss after possible dispatch yields OUTCOME_UNKNOWN where appropriate. Known pre-delivery connection/pool failures remain distinguishable. Unknown/in-flight writes block fresh write proposals until reconciliation; neither idempotency-key presence alone nor 429/5xx causes an automatic write retry.
8. Read results bind tool_call_id to the input identity and current revision. Changed input or closed session suppresses stale results using installed LiveKit StopResponse, which removes the tool output/continuation. Stale reads can finish internally, but cannot populate current offered slots or the spoken response. Session-local semantic state retains their actual internal outcome.
9. The delayed English read bridge scheduler starts concurrently with the operation, cancels for fast completion, suppresses stale/user-speaking acknowledgements and queues interruptible audio without awaiting playout before HTTP. It is OFF by default. Existing baseline prompt waiting behavior remains; live filler reduction is not claimed.
10. Canonical business effects and unknown heard status are separate from speech generations. A committed booking survives interrupted confirmation; its result and the gate's replay cache remain available. Subsequent LLM calls receive a disposable business-effect projection without rewriting audit/canonical chat history. Escalation returns escalation_recorded/liveTransfer=false and a follow-up-only summary; its tool contract explicitly says it does not transfer callers.
11. Framework tool_execution_updated remains the sole duration owner. Orchestration adds no second elapsed-time accumulation.

FEATURE FLAGS / POLICY VERSIONS: policy remains baseline; natural_v1 continues resolving to natural_v1_shadow. Session-local `clarification_enabled=False` and `tools.bridges_enabled=False` remain disabled; no environment switch or policy promotion enables them. English bridge callback exists only as a future internal realization path; Urdu/mixed bridge callback is absent. No new progress narration, TTS markup, renderer or DeliveryIntent.

## Verification

TESTS RUN / TEST RESULT:

- Final focused safety/runtime/framework suites: **136 passed, 0 skipped/failed**, `final-focused.xml`.
- Full offline CI manifest on final source: **404 passed, 1 skipped, 0 failed**, five existing warnings, `final-offline.xml`. New Batch A suite contains **47 tests**; mocked lifecycle tests are now included in the manifest.
- Additional applicable latency/provider/context/lifecycle suites: **78 passed, 0 skipped/failed**, one existing warning, `affected.xml`.
- Scoped Ruff: PASS. Scoped whitespace: PASS with `cr-at-eol`, respecting the existing committed CRLF test file. Plain diff --check flags its added CR characters; there is no added trailing space.
- Real installed AgentSession with synthetic providers/sink verifies stale completion produces zero audio/LLM tool output, a fresh lookup still produces audio, and framework tool timing is recorded once. These are offline framework tests, not live provider or acoustic proof.
- `tests/test_latency.py`: collection unavailable (`ModuleNotFoundError: config`). It is a legacy live-provider harness outside the worker offline manifest; its expected root config is absent. No compatibility shim/provider call was added. Applicable worker latency suites passed separately.
- `graphify update .`: attempted as required; fails existing `uv trampoline failed to canonicalize script path`. No graph existed at preflight.

The single full-suite skip is the existing offline SSRF `https://127.1/hook` case. Existing warnings are FastAPI/Starlette testclient deprecation and short synthetic JWT HMAC keys. Initial integration failures were corrected; final focused/full evidence supersedes exploratory XML runs.

Required tests 1–14 are covered by the new Batch A suite plus retained write/injection/observability regressions: Friday→Monday, ambiguous writes, weak inference, unconfirmed execution, duplicate concurrent/retry writes, post-dispatch unknown outcome, stale speech suppression, fast/slow waiting, once-only timing, escalation truth, completion despite interrupted speech, multilingual repair and baseline semantic lifecycle.

## Limits and gates

KNOWN LIMITATIONS:

- Deterministic small parser, literal/labelled entities and limited Urdu fixtures; no full Urdu corpus, spelled-number decoder, broad natural-date resolver or learned NLU. Unsupported/ambiguous capture fails closed and may need a more explicit repeat. Weekday-only booking needs current offered slots. Reschedule with an existing date needs separately grounded old/new roles.
- Dispatch tombstones, effects and offered slots are session-local. Automatic reconciliation, durable cross-process outcome recovery and safe retry proof are not added. Unknown writes remain blocked; backend reconciliation is required.
- Heard result stays unknown (`result_heard=None`). No playout/heard-state reconstruction or Phase 8 overlap behavior is claimed.
- Baseline prompt waiting instructions and prior Phase 3 prompt/persona/compaction activation gaps remain. New scheduler timing/listening benefits and generative compliance are unverified.
- Full original Phase 4/5 advanced policy classes, refined linguistic coverage and elaborate progress/long-running-tool behavior are not claimed complete; the user's fast-track P0 reductions are the scope.

UNVERIFIED LIVE ITEMS: Deepgram/Gladia network operation and deployed configuration; real backend booking/escalation outcomes and reconciliation; WebRTC/PSTN recordings; caller-heard confirmation and interruption timing; English/Urdu/mixed native listening; live bridge/prompt behavior; long-call, deployment, load/concurrency and billing evidence. No production enablement or paid smoke test occurred.

IMPLEMENTATION GATE: PASS for Fast-track Batch A P0 only.
ACTIVATION GATE: BLOCKED for new audible candidates.
DEFAULT ENABLEMENT: core safety/foundation ON; new clarification realization and spoken tool bridges OFF.
STOP: Batch A completed. No original Phase 6+ work.
