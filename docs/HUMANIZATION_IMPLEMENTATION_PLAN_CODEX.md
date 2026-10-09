# Awaaz Humanization — Strict Codex Implementation Plan

**Prepared:** 2026-10-08\
**Independent end-to-end audit revision:** 2026-10-08\
**Purpose:** execution plan for implementing the final audited humanization research in `sdk-agent` phase by phase with Codex.\
**Primary design source:** `docs/HUMANIZATION_RESEARCH_MASTER.md` (final audited Phases 0–10).\
**Code snapshot reference:** `PROVIDER_HUMANIZATION_CODEBASE_CONTEXT.md`, prepared from branch `main`, Git HEAD `c37fd73fd7bce0766496d7068c49d400f1c36e17`, with a dirty working tree at inspection time.\
**Core requirement:** humanization is owned by Awaaz/platform code, not rebuilt by clients integrating the SDK.\
**Architecture rule:** deterministic/stateful shell around one streaming generative path. Do not add serial planner/humanizer LLM calls to normal turns.

## Final product goal

Every implementation decision in this plan must be judged against the same end state:

> **Awaaz should feel like a competent, socially aware human conversation rather than a conventional voice bot, while remaining safe, measurable, provider-flexible, English/Pakistani-Urdu capable, WebRTC/PSTN robust, and controlled by the Awaaz platform rather than each integrating client.**

The target experience includes all of the following simultaneously:

```text
low caller-perceived latency
natural turn-taking and pause tolerance
fast, correct interruption/barge-in
backchannel tolerance and recovery
accurate critical entities and corrections
thoughtful, concise dialogue
context-appropriate empathy/humor/expressivity
natural pronunciation and prosody
truthful tool waiting and write outcomes
playout-aware continuity
English + Pakistani Urdu + mixed speech
WebRTC + PSTN robustness
provider/model replaceability
reversible/versioned policy
business safety and tenant isolation
```

No single provider metric, TTS demo, latency number, or expressive effect is allowed to stand in for this whole goal.

## Independent-audit corrections incorporated

This version was re-audited from the plan, final research master, and source-grounded codebase context rather than from prior conversational conclusions. The audit identified and corrected these material gaps:

- added a missing **TurnCoordinator** implementation foundation;
- added explicit separation between **implementation completion** and **activation/production evidence**;
- added a centralized `AwaazAgent`/hook integration boundary so humanization does not fragment across callbacks;
- strengthened fixed-corpus/baseline capture before any audible change;
- added platform policy resolution/backward-compatibility semantics;
- added Groq persona-compaction/business-fact preservation tests;
- expanded privacy/PII, metric-validity and instrumentation-overhead requirements;
- expanded opening/greeting/warm-up/cache/provider-failure/session-close continuity;
- added concurrency, cold/warm, long-call and cost/usage gates before P0 is considered proven;
- added vertical-slice/reference-lane verification before broad provider migration;
- added candidate-provider lanes (Soniox/Fish/Urdu candidates) without promoting them to current production paths;
- added bounded affect/empathy/expressivity work to P1;
- added an implementation-status ledger for phase-to-phase Codex continuity.

---

# 0. How Codex must use this plan

This document is an **execution contract**, not a suggestion list.

For every phase:

1. Implement **only the requested phase/subphase**.
2. Re-read the actual code involved before editing.
3. Treat executable source and exact installed dependency source as runtime truth.
4. Use the research master as design intent, not as proof that a feature already exists.
5. Preserve unrelated dirty working-tree changes.
6. Never silently upgrade dependencies, provider models, voices, or framework versions.
7. Never mix a provider/model bake-off with an architecture refactor.
8. Never weaken the existing write confirmation/idempotency safety path for latency.
9. Never move humanization policy into client code.
10. Never add a second mandatory network/LLM call to the ordinary speech critical path.
11. Every audible behavior change must be reversible behind a semantic feature flag or policy version until verified.
12. Do not proceed to the next phase unless the current phase's **implementation gate** passes.
13. A phase may be code-complete while its **activation gate** remains blocked by missing live audio/provider/native-listener evidence; in that state the new behavior must remain disabled by default.
14. For large phases with independent lettered subphases, the user may request a single subphase (for example `Phase 6F`) and Codex must stop after that subphase's gate.

If the current repository differs from this plan:

- stop;
- document the difference;
- trace the actual call path;
- adapt the phase only if the architectural invariant remains valid;
- do **not** guess from filenames/comments.

## 0.1 Required pre-flight at the start of every Codex phase

Codex must begin by showing:

```text
git status --short
git branch --show-current
git rev-parse HEAD
```

Then it must:

- identify files it expects to edit;
- identify existing local changes in those files;
- state how it will avoid overwriting unrelated edits;
- inspect the exact implementations/call sites before writing code;
- inspect relevant tests before changing behavior.

Do not run broad formatters over unrelated files.

## 0.2 Required completion report for every phase

Every phase must end with a concise report containing:

```text
PHASE / SUBPHASE:
STATUS: PASS | CODE_COMPLETE_ACTIVATION_BLOCKED | BLOCKED | PARTIAL

FILES READ:
FILES CHANGED:
NEW FILES:
TESTS RUN:
TEST RESULT:

BEHAVIOR BEFORE:
BEHAVIOR AFTER:

FEATURE FLAGS / POLICY VERSIONS:
DEFAULT ENABLEMENT: ON | OFF | SHADOW
KNOWN LIMITATIONS:
RUNTIME ITEMS STILL UNVERIFIED:

IMPLEMENTATION GATE:
PASS | FAIL

ACTIVATION GATE:
PASS | BLOCKED | NOT_APPLICABLE

NEXT SAFE PHASE / SUBPHASE:
```

If the gate is `FAIL`, Codex must not begin the next phase.

## 0.3 Universal stop-ship invariants

These apply in **every phase**.

- An unconfirmed consequential write must never execute.
- A write timeout must not automatically mean failure if the backend outcome can be unknown.
- A duplicate consequential write must not be caused by retry/recovery logic.
- A superseded critical value must not be reused for a write.
- `escalate_to_human` must not be described as a live transfer unless a real transfer exists.
- Provider markup must never become canonical conversation history.
- A cancelled speech generation must not be allowed to produce accepted stale output after invalidation.
- Unsupported provider expressivity must fail closed to safe/plain delivery.
- Client/browser code must not become responsible for provider-specific humanization policy.
- Existing English and Urdu provider paths must remain functional unless the current phase explicitly migrates that exact path.
- Normal-turn humanization policy must be local/deterministic where possible; do not add an extra planner/humanizer LLM round trip.
- Structural telemetry must not require raw transcript/PII logging by default.
- New caches must not create cross-agent or cross-tenant content/voice leakage.

## 0.4 Two-gate rule: implementation versus activation

Every behavior-changing phase has two separate gates.

### Implementation gate

Answers:

> Is the code correct, reversible, tested, compatible and safe enough to continue engineering?

This can pass with the feature disabled.

### Activation gate

Answers:

> Is there enough runtime/acoustic/native-language evidence to enable this behavior for real callers?

Examples of activation evidence:

```text
live provider smoke
paired baseline/candidate audio
WebRTC/PSTN caller-side recording
native Pakistani Urdu review
tool failure simulation
load/concurrency evidence
```

If live infrastructure is unavailable:

```text
STATUS = CODE_COMPLETE_ACTIVATION_BLOCKED
DEFAULT ENABLEMENT = OFF
```

Codex may proceed to later implementation phases if the implementation gate passes, but production/canary enablement remains forbidden.

## 0.5 Audible-change baseline gate

Before enabling the **first audible change** for a given lane, the lane needs a preserved baseline.

A lane means a relevant combination such as:

```text
language
STT/LLM/TTS path
channel
cold/warm state
```

At minimum capture:

```text
configuration/provider snapshot
scenario/corpus version
current policy version
available latency trace
reference/received audio when infrastructure exists
```

If caller-side/live baseline evidence cannot be captured, the candidate behavior may be implemented and tested but must remain disabled for that lane.

## 0.6 Phase/subphase execution rule

Large phases intentionally contain independent subphases.

Examples:

```text
Phase 6F Cartesia renderer
Phase 6G Rime renderer
Phase 6H ElevenLabs renderer
Phase 6I Uplift renderer
```

Codex must not interpret "implement Phase 6F" as permission to continue through 6I.

The user's requested execution unit is the hard scope boundary.

## 0.7 Persistent implementation-status ledger

Phase 0 must create or initialize:

```text
docs/HUMANIZATION_IMPLEMENTATION_STATUS.md
```

Each completed phase/subphase must append/update:

```text
current git HEAD
phase/subphase status
implementation gate
activation gate
feature flag/default state
tests/evidence
known runtime gaps
next safe execution unit
```

This status file is operational continuity for Codex across separate prompts.

It must not replace tests or source truth.

---

# 1. Current source-grounded baseline Codex must preserve

The final audited research was grounded against the following repository facts. Codex must re-verify them in the live checkout before relying on them.

## 1.1 Current architecture

Relevant surfaces:

```text
sdk/
sdk-server/
tenant_portal_api/
control_plane/
worker/
```

The worker owns the main voice-agent behavior.

Current path conceptually:

```text
user audio
→ LiveKit / VAD / STT
→ turn handling
→ LLM
→ provider-specific text transform
→ TTS
→ LiveKit
→ browser or SIP/PSTN
```

`worker/main.py::build_agent()` currently uses the standard LiveKit `Agent`; the source-grounded audit found no custom Awaaz subclass overriding all of:

```text
stt_node
llm_node
tts_node
on_user_turn_completed
```

## 1.2 Current provider baseline

Repository/default reference path:

```text
English default:
Deepgram Nova-3
→ Groq openai/gpt-oss-20b
→ Cartesia

English selectable:
Deepgram / Gladia
→ Groq / Gemini
→ Cartesia / Rime / ElevenLabs

Urdu:
Gladia
→ Gemini
→ Uplift
```

Do not interpret this as proof of the deployed production configuration.

## 1.3 Current turn/interruption baseline

Source audit found effective defaults around:

```text
turn_detection = stt
endpointing min/max = 0.12 / 1.2 s
false_interruption_timeout = 0.6 s
resume_false_interruption = False

WebRTC interruption min duration = 0.65 s
Telephony interruption min duration = 0.55 s

UVA_INTERRUPTION_MODE default = vad
adaptive = opt-in

force barge-in flush:
WebRTC default off
Telephony default on
```

For non-Groq current profiles, preemptive LLM/TTS are enabled; Groq disables them.

These are inputs/configuration, not evidence of good caller experience.

## 1.4 Current TTS baseline

Codex must re-read these adapters before any renderer changes:

```text
worker/providers/tts/cartesia.py
worker/providers/tts/rime.py
worker/providers/tts/elevenlabs.py
worker/providers/tts/uplift.py
```

And text layers:

```text
worker/spoken_sanitize.py
worker/plain_spoken_sanitize.py
worker/cartesia_spoken_output.py
worker/cartesia_spoken_sanitize.py
worker/rime_spoken_output.py
worker/rime_spoken_sanitize.py
worker/elevenlabs_spoken_sanitize.py
worker/uplift_spoken_sanitize.py
```

Important source-grounded facts include:

```text
Cartesia:
model default sonic-3.5
manual_ssml baseline
16 kHz PCM both channels

Rime:
model default arcana
WebSocket
segment=immediate
16 kHz WebRTC / 8 kHz telephony

ElevenLabs:
eleven_flash_v2_5
auto_mode=True
plain style
current installed path does not provide the newer TTD/v4 integration assumed by current docs

Uplift:
UPLIFT_MODE defaults to fixture in inspected code
live/record use PCM_22050_16
```

Do not switch any of these simply because a newer provider model exists.

## 1.5 Current tool safety baseline

Current tools include:

```text
end_conversation_summary
escalate_to_human

gateway-dependent:
lookup_business_info
check_availability
book_appointment
reschedule_appointment
cancel_appointment
```

Current writes have a deterministic propose → user turn → confirm → write gate with idempotency/ownership tracking.

Preserve it.

## 1.6 Current test baseline

The source-grounded audit ran a focused 23-file Python suite:

```text
185 passed
0 skipped
0 failed
1 warning
```

This is a **reference baseline**, not a permanent hardcoded expected count. The repository may have changed.

The focused suite did **not** prove:

- live provider operation;
- browser microphone → provider → speaker E2E;
- PSTN quality;
- Urdu listening quality;
- production latency;
- full repository build/lint/typecheck.

Phase 0 will establish the fresh baseline before code changes.

---

# PHASE 0 — Repository Re-verification and Baseline Freeze

**Goal:** establish a trustworthy current baseline before changing behavior.

**Audible behavior change:** none.

**Hard dependency:** none.

## 0A. Repository state capture

Codex must:

1. Record branch, HEAD and `git status --short`.
2. Compare current HEAD with the codebase-context snapshot HEAD.
3. If HEAD changed, do not assume context line numbers or behavior are still current.
4. Identify all currently modified/untracked files.
5. Record the installed Python/Node versions and the currently resolved LiveKit package versions.
6. Record exact provider plugin versions.
7. Record whether the repository virtual environment is healthy.

### Required evidence artifact

Create a short machine-readable or Markdown baseline record under an existing suitable test/artifact directory or `/tmp`/local output if the repository does not persist test artifacts. Do **not** add generated noise to git unless the repo already has an artifact convention.

At minimum record:

```text
git HEAD
dirty files
python version
node version
livekit-agents version
livekit-rtc version
provider plugin versions
```

## 0B. Re-trace current runtime path

Read, at minimum:

```text
worker/main.py
worker/config.py
worker/latency.py
worker/humanization/turn.py
worker/humanization/spoken.py
worker/humanization/history.py
worker/tools.py
worker/write_tool_gate.py
worker/session_opening.py
worker/session_close.py
worker/telephony_runtime.py
worker/telephony_tts.py

worker/providers/registry.py
worker/providers/capabilities.py
worker/providers/types.py

worker/providers/stt/deepgram.py
worker/providers/stt/gladia.py

worker/providers/tts/cartesia.py
worker/providers/tts/rime.py
worker/providers/tts/elevenlabs.py
worker/providers/tts/uplift.py

sdk/src/index.ts
sdk-server/src/index.ts
```

Trace:

```text
session creation
agent creation
turn policy
interrupt path
LLM prompt composition
tool lifecycle
TTS transform
opening/greeting
session close
```

Do not edit during this subphase.

## 0C. Baseline test restoration

Re-run the existing focused suite from the codebase context if those tests still exist.

Also inspect:

```text
pytest.ini
tests/conftest.py
```

to confirm whether live/provider tests are excluded.

If the local environment is broken:

- diagnose;
- do not upgrade dependencies casually;
- use the repository's intended environment or a minimally equivalent clean environment;
- document any deviation.

## 0D. Full available static checks

Run whatever the repository currently supports, such as:

```text
pytest focused suite
pytest broader non-live suite if feasible
lint
typecheck
SDK build
server SDK build
```

Do not invent package-manager commands; inspect manifests/scripts first.

## 0E. Baseline runtime configuration snapshot

Without exposing secrets, record effective:

```text
default STT/LLM/TTS providers/models
turn/interruption defaults
preemptive settings
provider retry defaults
Uplift mode resolution
humanization-related environment defaults
```

## 0F. Baseline behavior capture

If credentials/test infrastructure exist, capture:

```text
one English WebRTC call
one Urdu WebRTC call
one PSTN call if route exists
```

Label missing live evidence explicitly.

Missing live evidence does not block non-audible implementation work, but it **does** block activation of later audible behavior for the affected lane.

## 0G. Freeze the evaluation corpus structure

Before changing audible behavior, create a versioned scenario corpus structure.

Minimum categories:

```text
ordinary short answer
multi-part answer
mid-thought pause
long hesitation
critical entity capture
self-correction
clarification
tool read
tool write
tool timeout/outcome unknown
backchannel
one-word takeover
false interruption/noise
English
Pakistani Urdu
Urdu-English mixed
opening/greeting
long-call repetition
```

Requirements:

- stable scenario IDs;
- synthetic/non-sensitive committed fixtures;
- human reference labels where appropriate;
- version number or corpus fingerprint;
- no production PII in committed fixtures.

Do not wait until Phase 11 to decide what "better" means.

## 0H. Save baseline artifacts

Create a reproducible baseline bundle or documented artifact location containing:

```text
git/runtime version snapshot
provider/config snapshot
policy = baseline
corpus version
test results
available metrics JSON
available baseline transcripts/audio under existing privacy policy
```

This is the comparison point for all later audible phases.

## 0I. Early LiveKit upgrade reconnaissance — no upgrade

Inspect the target/current upstream release only enough to identify likely conflicts with planned P0 work.

Record whether newer upstream materially changes:

```text
Agent hooks
text transforms
adaptive interruption
tool events/async tools
alignment/transcription
ElevenLabs support
metrics/tracing
```

Do **not** upgrade or change lockfiles in Phase 0.

Purpose:

> avoid building P0 around private 1.6.5 quirks that are already removed upstream.

Actual upgrade work remains isolated in Phase 12.

## 0J. Initialize implementation-status ledger

Create/update:

```text
docs/HUMANIZATION_IMPLEMENTATION_STATUS.md
```

with Phase 0 evidence and all missing activation evidence.

## Phase 0 verification gate

Implementation gate must pass before Phase 1:

- repository state captured;
- exact current versions captured;
- existing focused tests pass or every failure is explained as a pre-existing baseline failure;
- fixed corpus structure exists;
- baseline artifact bundle/location exists;
- no production behavior changed;
- source-path differences from the audited research are documented;
- current safety/write gate still exists;
- early upgrade-reconnaissance notes exist;
- implementation-status ledger exists.

**Do not proceed if:** baseline test failures are unexplained or the current code no longer matches the assumed architectural path.

**Activation note:** missing live WebRTC/PSTN/Urdu baseline evidence is allowed at this point, but later audible candidates for those lanes must remain disabled until comparable baseline evidence exists.

---

# PHASE 1 — Observability, Correlation IDs, Outcome Labels and Policy Identity

**Goal:** make later humanization changes measurable and attributable.

**Audible behavior change:** none.

**Depends on:** Phase 0 PASS.

Primary current files:

```text
worker/latency.py
worker/main.py
worker/tools.py
worker/session_close.py
worker/transcript_logging.py
worker/usage.py
sdk/src/index.ts
```

Possible new files:

```text
worker/humanization/events.py
worker/humanization/telemetry.py
```

Do not create extra modules if existing files provide a cleaner home.

## 1A. Correlation identity model

Introduce explicit identities for:

```text
session_id              existing framework/session identity if appropriate
user_turn_id
assistant_turn_id
generation_id
tool_call_id
speech_chunk_id         only where needed
```

Requirements:

- IDs must not be reused across distinct semantic operations.
- `tool_call_id` must remain independent from `generation_id`.
- An interrupted speech generation must not imply a tool was cancelled.
- IDs must be available in structured logs/metrics.
- Avoid exposing internal identifiers to caller-facing text.

## 1B. Outcome taxonomy

Add normalized outcome labels, at minimum:

```text
completed
interrupted
cancelled
cancelled_speculation
provider_error
tool_error
tool_timeout
tool_outcome_unknown
false_interruption
stale
```

Do not mix invalid/cancelled samples into completed latency percentiles.

## 1C. Fix tool timing ownership

The source audit found a possible double-count path:

```text
_post_client_tool() timing
+
framework tool_execution_updated timing
```

Codex must trace both paths in the current source and establish **one** canonical execution-duration owner.

Add an integration-style test proving one gateway tool contributes once.

## 1D. Stage-timing event hooks

Add timestamps using a monotonic clock for:

```text
user turn/speech state transition available today
turn committed
LLM request start
first useful LLM text observed
first speakable chunk ready      placeholder if chunker not implemented yet
TTS request start
TTS first audio metric/event
speech complete/interrupted
tool start/finish
```

Do not relabel framework proxies as acoustic truth.

Current `e2eMs` must remain clearly diagnostic.

## 1E. Percentile aggregation

Add bounded/statistically sane aggregation for at least:

```text
p50
p95
p99
```

by:

```text
outcome
provider/model
language
channel
```

Do not report `0` for unavailable measurements.

## 1F. Humanization policy identity

Introduce a session-level identity:

```text
humanization_policy_version
```

Start with a value representing current/baseline behavior.

Also record component version/fingerprint fields if practical:

```text
turn policy
delivery policy
streaming policy
language profile
channel profile
renderer version
```

These may initially be constants.

## 1G. Provider snapshot

Create a normalized `ProviderSnapshot` for the session:

```text
STT provider/model/effective options
LLM provider/requested + effective model/options
TTS provider/model/voice/effective options
installed plugin versions if available
language
channel
```

No secrets.

## 1H. SDK diagnostic compatibility

If `sdk/src/index.ts` consumes metrics:

- preserve existing event compatibility;
- add new fields additively;
- do not make clients parse new humanization logic;
- prevent double interpretation of `turn_latency` and `metrics_updated`.

## 1I. Privacy and structural telemetry

Humanization observability must work without globally enabling transcript logging.

Requirements:

- structural events may contain dialogue-act/outcome/category data without raw caller text;
- do not put tool auth secrets, raw headers or private backend payloads into traces;
- do not persist full `ConversationState` snapshots into INFO logs by default;
- sensitive entity values should be omitted/redacted in general telemetry;
- `UVA_LOG_TRANSCRIPTS` and prompt dumps remain explicit debug controls;
- evaluation with recordings/transcripts follows existing recording/transcript policy.

## 1J. Metric validity, sample counts and instrumentation overhead

For every percentile report include a sample count.

Requirements:

- do not report a confident p99 from tiny samples;
- keep completed/interrupted/error outcomes separate;
- benchmark instrumentation overhead under single and moderate concurrent sessions;
- avoid per-audio-frame expensive logging/serialization;
- use monotonic time for latency math;
- wall-clock time may be added only for cross-system/log correlation.

Add a monotonic sequence/event ordering field if multiple asynchronous callbacks can arrive out of order.

## 1K. Test Studio / integration diagnostic surface

Use the existing Test Studio or integration-test surface as an engineering view where practical.

Expose diagnostics such as:

```text
policy version
provider snapshot
turn/generation/tool IDs
outcome
stage timing
transport summary when later available
```

Do not expose secrets or make this required for normal SDK clients.

## 1L. Usage/cost attribution hooks

Preserve current `session.usage.model_usage` behavior but add enough correlation to distinguish where possible:

```text
normal turn usage
retry usage
speculative/wasted synthesis
prewarm/cache activity
```

Do not claim vendor invoice accuracy.

This data becomes important in Phase 13 provider comparisons.

## Phase 1 tests

Required unit/integration tests:

- ID uniqueness/correlation.
- Tool timing counted once.
- Cancelled turn excluded from completed latency distribution.
- Missing metrics remain null/unavailable.
- Provider snapshot contains requested/effective distinction where available.
- Policy version included in trace.
- Existing latency event consumers remain compatible.
- Structural telemetry does not require raw transcript content.
- Instrumentation overhead is measured and bounded.
- Existing focused suite still passes.

## Phase 1 exit gate

Implementation PASS only if:

```text
one user turn
→ one correlated trace
→ optional tool
→ one assistant generation
→ one outcome
```

can be followed without ambiguity.

Also require:

- tool timing is counted once;
- invalid/cancelled outcomes are separated;
- sample counts accompany percentiles;
- telemetry contains no accidental secrets/PII in deterministic tests.

**Do not proceed if:** tool timing remains double-counted, cancelled samples remain indistinguishable, IDs cannot reliably correlate a turn, or observability itself materially damages realtime behavior.

---

# PHASE 2 — HumanizationRuntime, Typed ConversationState and Event Reducer

**Goal:** create explicit platform-owned state without changing audible behavior.

**Audible behavior change:** none.

**Depends on:** Phase 1 PASS.

Likely files:

```text
worker/humanization/runtime.py
worker/humanization/state.py
worker/humanization/events.py
worker/humanization/policy.py
worker/main.py
```

Use existing modules where cleaner.

## 2A. Runtime object

Create one session-scoped `HumanizationRuntime`.

It should own/refer to:

```text
ConversationState
policy version
provider snapshot
language/channel identity
event reducer
```

It must not become a network service.

## 2B. Minimal typed state partitions

Implement P0 only:

```text
task_state
grounding_state
repair_state
interaction_state
tool_state
speech_state
recent_behavior_state
language_state
channel identity
```

Keep affect state minimal or deferred.

Do not build a giant emotion graph.

## 2C. Grounded values

For critical task fields, support statuses such as:

```text
heard
inferred
confirmed
superseded
unresolved
```

A stronger value must not be overwritten by a weaker inference.

## 2D. Event reducer

All P0 humanization state updates should go through one controlled reducer/transition path.

Avoid:

```text
callback A mutates state directly
callback B mutates same state differently
```

## 2E. Turn-boundary snapshots

Create serializable snapshots at meaningful boundaries:

```text
before user turn
after user turn commit
after tool result
after assistant turn
session close
```

Do not serialize provider clients or secrets.

## 2F. Integrate with session userdata/state

Use stable framework/public mechanisms where possible.

Do not patch private LiveKit internals if a public hook/state surface exists.

## 2F.1 Central Awaaz Agent/hook boundary

The source snapshot currently constructs the standard LiveKit `Agent`.

Introduce one centralized integration boundary—preferably an `AwaazAgent` subclass or a clearly defined hook bundle—using public installed-framework extension points.

Initial behavior must delegate to existing/default behavior.

Purpose:

```text
future stt_node logic
on_user_turn_completed
llm context projection
tts_node/chunking
transcription/heard-state
```

should not be scattered across unrelated callbacks in `worker/main.py`.

Requirements:

- verify exact installed hook signatures/source before overriding;
- call/delegate to framework defaults where behavior is not intentionally replaced;
- no audible behavior change in this subphase;
- public hooks preferred over private monkey-patching.

## 2G. No behavioral authority yet

For this phase:

- state observes existing behavior;
- state does not yet rewrite prompts or TTS;
- write gate remains the current source of write safety.

## 2H. Separate active LLM context from audit transcript

The source audit found an important ambiguity in `worker/humanization/history.py` and `worker/session_close.py`: truncating `session.history` does not prove the actual agent LLM context is bounded, and it can also remove earlier content from the shutdown transcript.

Codex must inspect the exact current LiveKit `AgentSession`/agent chat-context relationship and then establish explicit semantics for:

```text
audit transcript
active LLM context
typed ConversationState
```

Requirements:

- do not use audit-transcript truncation as a proxy for token control;
- do not lose the full session transcript merely to bound LLM context;
- do not duplicate full raw history into `ConversationState`;
- if LLM context bounding is changed, add a long-call regression proving the outbound model context is bounded as intended;
- preserve current session-close persistence unless the new separation is proven equivalent/better.

## 2I. Platform policy resolver and backwards compatibility

Create one internal resolver that produces the session's effective humanization policy.

Initial policy identities should support at least:

```text
baseline
natural_v1_shadow
natural_v1
```

Requirements:

- existing agents with no humanization field continue to resolve to an explicitly defined default;
- do not expose raw VAD/chunk/provider markup knobs through the public SDK;
- record requested/effective policy separately if an override mechanism exists;
- explicitly define precedence between the versioned policy and legacy environment flags already controlling interruption/retry/history/preemption behavior;
- do not silently ignore an existing environment override during migration;
- do not add a database column merely because the abstraction exists—first determine whether environment/platform resolution is sufficient;
- if persistence/schema/API changes are needed, make them explicit migrations with machine/portal/SDK backward-compatibility tests;
- if policy becomes part of cached `AgentConfig`, audit the existing session-bundle cache TTL/invalidation behavior so a policy update does not appear immediately in one path and remain stale in another;
- preserve legacy requested/effective LLM-model behavior, including the source-audited backend SDK legacy default path, unless intentionally migrated.

## 2J. Event ordering and concurrency safety

The runtime will receive asynchronous events from STT, tools, TTS, interruption and session lifecycle callbacks.

Requirements:

- reducer transitions must tolerate late/stale events using IDs/sequence;
- cancelled generation events cannot resurrect state;
- tool completion can arrive after speech cancellation;
- session shutdown cannot race a committed write into disappearance;
- tests must exercise out-of-order event delivery;
- avoid one global lock around realtime audio processing.

## 2K. Tenant/agent state isolation

ConversationState and policy state are session-local.

Add tests proving:

- two concurrent sessions do not share recent-behavior state;
- one agent's task facts cannot appear in another;
- new caches introduced later must key on enough identity to prevent cross-agent voice/content reuse;
- no assumption is made that current process-level provider credentials imply future BYO-key safety.

## Phase 2 tests

- Serialization round-trip.
- Reducer deterministic replay.
- Confirmed vs superseded critical values remain distinct.
- Tool state independent from speech state.
- Active generation state independent from tool-call state.
- Existing session behavior unchanged under feature flag off/baseline policy.
- Awaaz hook boundary delegates to baseline behavior.
- Out-of-order/late-event tests pass.
- Concurrent session state isolation passes.
- Active LLM context and audit transcript semantics are explicit.
- Existing focused suite passes.

## Phase 2 exit gate

Implementation PASS only if a multi-turn fixture can be replayed into the same final `ConversationState` and all state mutations flow through controlled transitions.

**Do not proceed if:** state is being mutated from multiple uncontrolled paths, task truth exists only inside chat history, event ordering can resurrect stale state, or the new hook layer changes baseline speech unintentionally.

---

# PHASE 3 — TurnPlan and LLMContextProjection in Shadow Mode

**Goal:** derive provider-neutral turn behavior locally, without yet changing speech.

**Audible behavior change:** none.

**Depends on:** Phase 2 PASS.

Primary areas:

```text
worker/humanization/turn.py
worker/humanization/spoken.py
worker/main.py
```

Possible new files:

```text
worker/humanization/turn_plan.py
worker/humanization/context_projection.py
worker/humanization/types.py
```

## 3A. TurnPlan schema

Implement provider-neutral fields such as:

```text
dialogue_act
response_budget
language_style
certainty
clarification_target
empathy_level
humor_permission
laughter_permission
filler_permission
question_policy
tool_policy
interruption_context
reason_codes
```

Do not include provider tags/options.

## 3B. Deterministic P0 derivation rules

At minimum support:

```text
critical uncertainty → CLARIFY
user correction → REPAIR_CONFIRM
confirmed write proposal → confirmation/write policy
complaint/frustration → humor/laughter forbidden
simple factual answer → short response budget
tool wait → tool-policy signal
```

## 3C. LLMContextProjection

Create a compact projection from authoritative state.

Include only what the LLM needs:

```text
confirmed task facts
unresolved facts
recent repair
current turn policy
language style
```

Exclude:

```text
raw jitter
internal IDs
provider capability dump
stale/superseded values except when needed to explain a repair
```

## 3D. Ephemeral injection

Use the current framework's safest supported turn hook/context mechanism.

Do not permanently append internal plan machinery to long-term chat history.

## 3E. Shadow mode

Compute and log:

```text
TurnPlan
context projection
```

but do not let them change output yet.

Compare with actual current behavior.

## 3F. Prompt authority and contradiction audit

Before TurnPlan is allowed to drive speech in later phases, reconcile the current prompt stack.

Codex must inspect:

```text
SYSTEM_INSTRUCTIONS_BASE
CLIENT_TOOLS_DISCIPLINE
UNIVERSAL_SPOKEN_RULES
Groq/Gemini overlays
Urdu language overlay
TTS delivery overlays
main.py language directive
tenant persona framing
```

The source audit already identified a response-length contradiction around "one or two" versus "two or three" sentences.

Requirements:

- define one platform authority hierarchy;
- preserve tenant persona/business facts as lower-authority style/data;
- do not let tenant persona override write/tool/platform invariants;
- mark TTS-provider delivery instructions for removal from the LLM path when that provider is migrated in Phase 6;
- do not create a larger prompt merely to restate TurnPlan;
- add tests for the final compact projection/instruction order.

Recommended authority order:

```text
platform safety/business invariants
→ current TurnPlan
→ language profile
→ tenant persona/business facts
→ provider rendering outside the LLM where possible
```

## 3G. Groq persona compaction and business-fact preservation

The source snapshot shows Groq persona compaction can hard-limit effective persona text around 3000 characters and potentially lose late facts.

Before TurnPlan activation:

- build representative long tenant-persona fixtures;
- identify business facts that must never depend on their position in a free-form persona;
- project critical structured business/task facts separately from stylistic persona text where practical;
- test that long prompts do not silently drop required services/hours/rules/identity facts;
- keep the audit transcript/persona source intact even if active model context is compacted.

Do not "fix" this by simply raising the character limit without token/latency evidence.

## 3H. Tenant prompt trust-boundary tests

Create adversarial tenant-persona fixtures that try to override:

```text
write confirmation
tool truth
platform safety
language/channel policy
provider markup rules
```

The platform authority hierarchy must win.

## 3I. TurnPlan activation prerequisites

TurnPlan remains `SHADOW` until:

- Phase 0 baseline exists for the target lane;
- Phase 3 deterministic tests pass;
- Phase 4 critical-repair integration is available for any rule that depends on entity certainty;
- policy flag can revert immediately to baseline.

A later subphase may activate a narrow reference lane first.

## Phase 3 tests

Deterministic fixtures asserting:

```text
repair → REPAIR_CONFIRM
uncertain critical entity → CLARIFY
complaint → laughter forbidden
simple answer → SHORT/MICRO budget
write flow → correct tool policy
```

English + Urdu/mixed examples where state inputs are available.

## Phase 3 exit gate

PASS only if:

- TurnPlan is deterministic for fixed state;
- no second planner LLM exists;
- plan is provider-neutral;
- shadow traces show no obvious safety contradictions.

---

# PHASE 4 — Provider-Neutral InputUnderstanding, Critical Repair and TurnCoordinator Foundation

**Goal:** make corrections/critical uncertainty explicit before generation/tool execution.

**Audible behavior change:** limited to clarification/repair only after verification and feature flag enablement.

**Depends on:** Phase 3 PASS.

Primary files:

```text
worker/providers/stt/deepgram.py
worker/providers/stt/gladia.py
worker/humanization/turn.py
worker/main.py
```

Likely new modules:

```text
worker/humanization/input/evidence.py
worker/humanization/input/understanding.py
worker/humanization/input/repair.py
worker/humanization/input/entities.py
```

## 4A. TranscriptEvidence contract

Normalize provider evidence:

```text
text
is_final
language
start/end if available
overall confidence if truly available
word evidence/alignment if truly available
provider endpoint signal
source provider/model
```

Do not invent unavailable confidence values.

## 4B. Deepgram adapter

Map current Deepgram Nova/Flux evidence into `TranscriptEvidence`.

Re-verify exact installed plugin behavior for:

```text
interims
finals
Flux preflight/eager signals
alignment
confidence
```

Keep provider details at the adapter boundary.

## 4C. Gladia adapter

Map Gladia events into the same contract.

Do not assume code switching or word confidence that the current path does not provide.

## 4D. Critical entity model

Start with fields relevant to current tools/business flows:

```text
date
time
phone
confirmation/reference code
name
email
appointment/booking identifier
```

Support:

```text
confirmed
unresolved
superseded
```

## 4E. Repair/correction rules

Handle patterns such as:

```text
"No, Friday."
"Actually Monday."
"Not Dr Ali — Dr Ahmed."
Urdu/mixed equivalents.
```

A correction must supersede the weaker prior value.

## 4F. Clarification gate

If a critical value is unresolved:

- prevent consequential write;
- TurnPlan should become clarification/repair;
- do not guess from LLM inference.

## 4G. Language fixtures

Add:

```text
English
Pakistani Urdu
Urdu-English mixed
```

fixtures.

Do not claim full Urdu conversational coverage from a small fixture set.

## 4H. Normalize turn events

Create provider/framework-neutral turn evidence for the HumanizationRuntime, using existing LiveKit/VAD/STT events rather than replacing the media stack.

Conceptual events:

```text
VOICE_START
VOICE_END
STT_INTERIM
STT_FINAL
EOT_CANDIDATE
EOT_CONFIRMED
TURN_RESUMED
```

Only emit a field/event when the installed source truly provides it.

## 4I. TurnCoordinator state machine

Introduce an Awaaz-owned `TurnCoordinator` that initially **delegates actual commit behavior to the current LiveKit baseline** while tracking explicit state.

Minimum conceptual states:

```text
LISTENING
USER_SPEAKING
TURN_CANDIDATE
TURN_COMMITTED
AGENT_SPEAKING
INTERRUPTION_CANDIDATE
```

Responsibilities:

```text
turn candidate identity
commit/cancel reason
speculation eligibility
current turn-policy class
timing/metrics
```

Do not reimplement low-level VAD.

## 4J. Turn-policy classes in shadow

Compute platform-owned semantic policies such as:

```text
rapid_exchange
free_form
structured_capture
reflective_sensitive
agent_playing_audio
```

Examples:

- yes/no confirmation → `rapid_exchange`;
- phone/email/code capture → `structured_capture`;
- sensitive/emotional content → `reflective_sensitive`.

The integrating client does not set raw endpointing thresholds.

## 4K. TurnPlan + TurnCoordinator narrow activation

After deterministic tests, allow an opt-in reference-lane experiment where TurnPlan/TurnCoordinator may influence only bounded behavior such as:

```text
response budget
clarification
structured-capture patience
```

Do not globally change endpointing thresholds in this phase.

Global endpointing/speculation tuning remains experimental until Phases 8/13.

## Phase 4 tests

- Correction supersession.
- Ambiguous critical values block write.
- Confirmed value survives later weak inference.
- Provider raw fields remain isolated to adapter layer.
- Mixed-language critical entities remain intact.
- Existing write gate behavior remains unchanged unless fed validated state.
- TurnCoordinator shadow state follows current framework commit/cancel events correctly.
- Structured-capture policy does not commit an explicitly incomplete fixture.
- Existing focused suite passes.

## Phase 4 exit gate

Implementation PASS only if:

- no consequential write can consume an unresolved/superseded critical value in tests;
- TurnCoordinator can represent turn lifecycle without changing baseline behavior when disabled;
- narrow activation is fully reversible.

Activation of changed turn timing for real callers remains blocked until the relevant audio corpus/runtime evidence exists.

---

# PHASE 5 — ToolOrchestrator, Tool Truth and Deterministic Waiting Behavior

**Goal:** move tool conversational behavior from prompt-only instructions into Awaaz runtime while preserving write safety.

**Audible behavior change:** yes, behind feature flag/policy version.

**Depends on:** Phase 4 PASS.

Primary files:

```text
worker/tools.py
worker/write_tool_gate.py
worker/latency.py
worker/main.py
worker/session_close.py
```

Potential new files:

```text
worker/humanization/tools/orchestrator.py
worker/humanization/tools/state.py
worker/humanization/tools/feedback.py
worker/humanization/tools/errors.py
```

## 5A. Tool categories

Classify current tools explicitly:

```text
FAST_READ
VARIABLE_READ
WRITE_PROPOSAL
WRITE_COMMIT
ESCALATION_RECORD
SESSION_FINALIZATION
```

Names can differ, semantics may not.

## 5B. ToolExecutionPlan

Create an internal plan carrying:

```text
effect class
may_cancel
may_retry
idempotency_required
expected latency class
ack policy
progress policy
interruption policy
result urgency
```

Client does not configure humanization fields.

## 5C. Canonical ToolResult

Normalize outcomes:

```text
success
no_result
validation_error
conflict
timeout
unavailable
cancelled
outcome_unknown
```

Keep:

```text
speech summary
structured business data
business effect
retry safety
idempotency key when applicable
```

## 5D. Preserve existing write gate

`worker/write_tool_gate.py` remains authoritative.

Do not bypass:

```text
propose
→ user turn
→ confirm
→ write
```

## 5E. OUTCOME_UNKNOWN

For consequential writes, distinguish:

```text
definite failure
```

from:

```text
request may have committed but response was lost
```

Automatic retry is forbidden unless idempotency/reconciliation proves it safe.

## 5F. Delayed bridge scheduler

For read tools:

```text
tool starts
→ result fast? speak result directly
→ result slow? short truthful bridge
```

Do not add filler to every fast tool.

Bridge must be interruptible.

The tool request should start **concurrently** with feedback scheduling. Do not:

```text
speak bridge
→ wait for bridge to finish
→ only then start HTTP
```

unless the business operation specifically requires that ordering.

For languages without a reviewed deterministic bridge phrase, keep that bridge behavior disabled or use an already-verified safe realization path.

## 5G. Stale read suppression

If the user changes:

```text
Friday → Monday
```

then the old read:

- may be cancelled if safe;
- otherwise may complete silently;
- must not hijack the active turn.

Use semantic request identity/tool-call state.

## 5H. Error normalization

Map backend/internal errors into user-actionable classes.

Do not speak raw HTTP codes.

## 5I. Escalation truth

Current `escalate_to_human` creates an escalation record.

Do not say "transferring you now" unless a real transfer is implemented.

## 5J. Tool result vs heard result

Persist:

```text
business effect completed
```

independently from:

```text
result speech heard
```

This is necessary for interrupted confirmations.

## 5K. Tool interruption matrix

Explicitly test:

```text
read not yet dispatched
read running and cancellable
read running but non-cancellable
write proposed but not confirmed
write confirmed but not dispatched
write dispatched/committing
write completed while result speech is interrupted
```

User speech interruption and business-operation cancellation are separate decisions.

## 5L. Rate-limit and dependency error semantics

Normalize at least:

```text
RATE_LIMITED
DEPENDENCY_TIMEOUT
DEPENDENCY_UNAVAILABLE
VALIDATION_ERROR
CONFLICT
OUTCOME_UNKNOWN
```

Do not silently retry writes because an upstream returned 429/5xx.

## 5M. Progress truth and repetition guard

If long tools later expose progress:

- only speak real progress;
- cap/reason repeated progress announcements;
- do not say "almost done" without evidence;
- completion updates must wait for a conversationally safe moment if the caller is speaking.

## Phase 5 tests

Hard tests:

- unconfirmed write never executes;
- duplicate write not caused by retry;
- timeout-after-dispatch can become `OUTCOME_UNKNOWN`;
- stale read never speaks after active intent replacement;
- escalation wording/state matches record creation;
- delayed bridge cancelled when result returns quickly;
- fast tool can skip bridge;
- tool execution duration counted once.

## Phase 5 runtime verification

Controlled scenarios:

```text
fast lookup
slow lookup
lookup correction
booking success
booking conflict
simulated write timeout after dispatch
user interruption after successful booking but before full spoken result
```

## Phase 5 exit gate

Implementation PASS only if all hard write/tool invariants are green and tool feedback can be disabled independently.

Activation of new spoken bridge/progress behavior additionally requires paired timing/listening evidence for the target language/channel. If that evidence is missing, keep feedback policy on the verified baseline while later code phases proceed.

---

# PHASE 6 — Provider-Neutral DeliveryIntent, PronunciationPlan and Renderer Contract

**Goal:** remove provider-specific humanization semantics from the LLM and compile Awaaz intent into each TTS provider safely.

**Audible behavior change:** yes, one provider path at a time.

**Depends on:** Phase 5 PASS.

Current areas:

```text
worker/humanization/spoken.py
worker/cartesia_spoken_output.py
worker/rime_spoken_output.py
worker/*spoken_sanitize.py
worker/providers/tts/*
```

Likely new:

```text
worker/humanization/delivery/intent.py
worker/humanization/delivery/pronunciation.py
worker/humanization/delivery/capabilities.py
worker/humanization/delivery/renderers/
```

## 6A. Canonical spoken text

Make plain spoken text the canonical LLM result.

Provider markup must not be canonical history.

Keep a compatibility flag for baseline behavior.

## 6B. DeliveryIntent

Implement provider-neutral fields such as:

```text
affect
intensity
pace
energy
emphasis spans
pause events
nonverbal event
speech mode
continuity identity
```

Keep initial taxonomy small.

## 6C. PronunciationPlan

Separate correctness from emotion.

Support, where needed:

```text
NORMAL
SPELL
ALIAS
PHONEME
DIGIT_GROUP
```

with protected spans.

## 6D. Capability registry

Create honest internal capability mapping from:

```text
provider
model
plugin version
endpoint path
configured options
```

Do not infer from model string only.

At minimum TTS capability fields should distinguish:

```text
streaming
alignment
emotion
speed
pause
nonverbal
pronunciation
continuation context
fast cancel
native output formats
```

The existing public `/provider-capabilities` surfaces remain a provider-selection contract unless intentionally expanded.

Do not expose an unverified humanization feature publicly merely because the provider's marketing/docs list it. Public capability expansion requires:

```text
provider support
+
installed plugin/path support
+
Awaaz wiring
+
live verification
```

## 6E. Renderer contract

Renderer input:

```text
canonical chunk
DeliveryIntent
PronunciationPlan
ChannelProfile
ProviderCapabilities
```

Renderer output:

```text
provider text/options
context/continuation data
flush hints
alignment mode
```

Unsupported feature:

```text
degrade safely
```

Never emit unsupported literal tags.

---

## 6F. Cartesia renderer migration — reference lane first

Cartesia is the first reference renderer because it is the audited English CREATE-default TTS path.

Read exact current:

```text
worker/providers/tts/cartesia.py
worker/providers/tts/cartesia_options.py
worker/cartesia_spoken_output.py
worker/cartesia_spoken_sanitize.py
```

Requirements:

- preserve current baseline behind flag;
- move emotion/spell/pause rendering into renderer;
- do not require LLM to open/close provider markup;
- canonical transcript remains plain;
- do not change model from current default in this subphase;
- do not enable current-framework expressive mode just because an option exists.

Verification:

- contract tests;
- markup never leaks;
- identical semantic text before/after renderer;
- current provider constructor tests pass;
- paired baseline/candidate audio if live credentials exist.

### 6F.1 Reference-lane vertical-slice gate

Before broad provider migration, prove the architecture on one narrow lane:

```text
English
current Deepgram baseline
current Groq/Gemini baseline as configured
Cartesia
WebRTC
```

Verify:

```text
ConversationState
TurnPlan
canonical text
DeliveryIntent
Cartesia renderer
tool truth
generation identity
baseline rollback
```

Do not claim streaming/chunking improvements yet; Phase 7 owns them.

If live audio evidence is unavailable, Cartesia renderer may be code-complete but stays disabled.

Gate before 6G.

---

## 6G. Rime renderer migration

Read exact current:

```text
worker/providers/tts/rime.py
worker/providers/tts/rime_options.py
worker/rime_spoken_output.py
worker/rime_spoken_sanitize.py
```

Requirements:

- do not delete Arcana merely from external assumptions;
- preserve model selection;
- renderer must respect current plain/no-SSML path unless exact model behavior is verified;
- pronunciation/spelling semantics move into provider adapter/renderer;
- do not silently switch segment mode/model.

Verification:

- Arcana/Coda/Mist option contract tests where paths exist;
- no unsupported stage cue leakage;
- current Rime option tests pass.

---

## 6H. ElevenLabs renderer migration

Read exact current plugin/source.

Requirements:

- baseline remains Flash 2.5/plain;
- current installed path must not pretend v4/TTD exists;
- plain renderer first;
- future audio-tag renderer may remain capability-gated;
- do not change `auto_mode` in this phase.

Verification:

- plain baseline unchanged under baseline flag;
- capability gate rejects unsupported expressive path;
- provider tags never enter canonical text.

---

## 6I. Uplift renderer migration

Requirements:

- preserve `UPLIFT_MODE` semantics;
- fixture is not treated as live acoustic proof;
- no English/Cartesia markup reaches Uplift;
- phrase replacement/pronunciation logic is represented through Awaaz plan where supported;
- do not switch PCM/μ-law format yet.

Verification:

- fixture tests;
- live path smoke only if configured;
- Urdu canonical text preserved;
- phrase replacement options validated.

---

## 6J. Renderer cross-provider contract suite

Given the same:

```text
canonical_text
DeliveryIntent
PronunciationPlan
```

assert for every renderer:

- semantic content preserved;
- unsupported features degrade;
- no raw provider tag leaks to transcript;
- same business facts;
- safe exception/fallback behavior.

## 6K. Remove migrated provider-delivery prompting from the LLM path

For each migrated provider only:

- remove or disable the old prompt instruction that asks the LLM to emit provider-specific markup/stage cues;
- keep the baseline prompt path behind the compatibility flag until A/B verification passes;
- ensure `LLMContextProjection` contains semantic delivery policy, not TTS syntax;
- verify that switching TTS providers no longer changes the social policy encoded in the main LLM prompt.

Do not remove provider-specific prompt rules for an unmigrated provider.

## 6L. Cache-key/version audit

Humanization changes can make cached audio stale.

Inspect:

```text
worker/greeting_cache.py
services/tts_cache.py
provider/client caches
any pre-synthesized tool-bridge cache added in Phase 5
```

Cache identity for rendered audio should include enough of:

```text
provider
model
voice
language
channel/profile
humanization policy version
renderer version
pronunciation version
effective relevant provider options
```

Requirements:

- do not reuse old PCM under a new delivery policy;
- do not silently explode cache cardinality;
- document restart/invalidation semantics for environment-derived settings not present in keys;
- add tests proving a behavior-version change misses/rekeys cached rendered audio.

## Phase 6 exit gate

Implementation PASS only when:

- the provider-neutral renderer contract is stable;
- the Cartesia reference lane passes deterministic verification;
- every currently supported TTS provider has either:
  - a migrated renderer path; or
  - an explicit compatibility adapter preserving old behavior;
- baseline paths remain available for rollback.

Activation is provider-by-provider. A provider without live/listening evidence remains default-off on the new renderer even if the phase implementation gate passes.

Do not remove baseline path yet.

---

# PHASE 7 — StreamSafeNormalizer, SpeechPlan, SpeechChunkPlanner and Generation Cancellation

**Goal:** produce low-latency speech from streaming LLM output without corrupting meaning or allowing zombie audio.

**Audible behavior change:** yes.

**Depends on:** Phase 6 PASS.

Primary areas:

```text
worker/spoken_sanitize.py
worker/plain_spoken_sanitize.py
provider sanitizers
worker/main.py
LiveKit tts_node path
provider TTS stream adapters
```

Likely new:

```text
worker/humanization/streaming/normalizer.py
worker/humanization/streaming/protected_spans.py
worker/humanization/streaming/chunk_planner.py
worker/humanization/streaming/speech_plan.py
worker/humanization/streaming/cancellation.py
```

## 7A. Stream invariance first

Before behavior changes, add property-based tests:

```text
whole text transform
==
same text streamed across arbitrary chunk boundaries
```

for:

```text
English
Urdu
mixed
emails
URLs
numbers
codes
markup-like text
malformed tags
emoji
multibyte Unicode
```

Do not proceed until whitespace/entity corruption is fixed.

## 7B. Protected spans

Chunker must avoid unsafe splits inside:

```text
phone
email
URL
date/time
money
ID/code
spelled name
pronunciation override
provider control construct
```

## 7C. SpeechPlan

Per assistant generation track:

```text
generation_id
canonical text
speakable chunks
delivery intent
pronunciation plan
provider context
played/heard ranges where available
cancelled state
```

## 7D. Conservative chunk planner

Start with:

```text
short complete response
sentence
safe stable first clause
final remainder
```

Do not implement learned chunking.

LLM transport chunk != speech chunk.

Implement/tune the first streaming candidate on the reference English/Cartesia lane before changing all providers.

## 7E. Generation invalidation

On true interruption/new generation:

- mark old `generation_id` invalid;
- clear planner buffer;
- reject late old-provider audio;
- prevent stale chunk acceptance.

Add tests that inject late events from cancelled generations.

## 7F. Provider context/flush policies

Implement provider-specific strategy behind the common planner.

### Cartesia

Test/use same-turn continuation context only after exact current API/plugin verification.

### Rime

Trace existing `segment=immediate` behavior.

Do not change segmentation until measured.

### ElevenLabs

Trace exact text granularity reaching `auto_mode=True`.

Do not tune schedule blindly.

### Uplift

Baseline should remain complete short sentence/appropriate chunk, not raw Gemini token fragments.

## 7G. Audio lead/backpressure

Track an estimate such as:

```text
generated_audio_ahead_ms
```

Prevent unlimited synthesis far ahead of playback.

Do not choose final lead target without runtime evidence.

## 7H. Chunk timing metrics

Add:

```text
first useful LLM text
→ first speakable chunk
```

as `chunk_wait_ms` or equivalent.

Also capture, where possible:

```text
inter-chunk audio gap
generated audio lead
wasted/cancelled synthesized duration
```

Do not conflate any of these with provider TTFB.

## 7I. Per-provider streaming activation

After reference-lane proof, verify provider-specific feed behavior separately:

```text
Cartesia
Rime
ElevenLabs
Uplift
```

Do not enable one global chunk policy merely because it works for Cartesia.

## Phase 7 tests

- Arbitrary stream split properties.
- Protected span integrity.
- Cancelled generation late chunk rejected.
- Chunk planner deterministic.
- Provider context lifecycle tests.
- Existing sanitizer tests still pass.
- No tag leakage.

## Phase 7 runtime verification

At minimum:

```text
micro reply
long reply
phone number
email
English
Urdu
mixed
interruption mid-response
```

## Phase 7 exit gate

Implementation PASS only if:

- stream correctness is proven;
- stale output cannot survive invalidation;
- provider-specific chunk policy is capability-gated;
- baseline streaming path remains available.

Activation of the new chunk planner for a provider requires live audio evidence showing that latency improves or remains acceptable **without** a material prosody/intelligibility/interruption regression.

---

# PHASE 8 — OverlapCoordinator, False-Interruption Recovery and HeardState

**Goal:** distinguish listening backchannels from true takeover and recover based on what was actually heard.

**Audible behavior change:** yes.

**Depends on:** Phase 7 PASS.

Primary areas:

```text
worker/humanization/turn.py
worker/main.py
worker/latency.py
provider STT adapters
provider TTS alignment paths
```

Likely new:

```text
worker/humanization/turn/overlap.py
worker/humanization/streaming/heard_state.py
```

## 8A. OverlapDecision

Build on the Phase 4 `TurnCoordinator`; do not create a second competing turn state machine.

P0 actions:

```text
CONTINUE
YIELD
RECOVER_FALSE
```

Reserve `ADAPT` for later P2 work.

Class evidence may include:

```text
VAD
adaptive detector if enabled/supported
STT partial/final
agent playback position
current dialogue act
language
channel
```

## 8B. Audit force-flush interaction before adaptive mode

Trace:

```text
wire_barge_in_flush()
session.interrupt(force=True)
native framework interruption
```

Test matrix:

```text
VAD + force flush
VAD without force flush
adaptive + force flush
adaptive without force flush
```

only where exact installed framework supports it.

Do not enable adaptive globally until this is understood.

## 8C. One-word takeover protection

Critical corpus:

```text
wait
stop
no
hold on
Urdu equivalents/mixed forms
```

Do not solve backchannels with a global `min_words=2`.

## 8D. Backchannel handling

Build controlled fixtures/audio for:

```text
mhm
yeah
right
okay
ji
haan
acha
hmm
```

The lexical item alone must not determine the action.

Until Phase 9's Urdu language profile is reviewed, do not promote Urdu lexical/backchannel rules to a global production default. Keep Urdu-specific behavior behind the policy flag.

## 8E. False interruption recovery

Implement explicit recovery strategies:

```text
resume
restart short clause
replan
```

based on speech/heard position.

Do not auto-apologize after every cough/noise event.

## 8F. HeardState

For aligned providers, track word/range evidence where truly supported.

For Uplift or unaligned paths:

```text
chunk/sentence-level heard state
```

is acceptable.

Never fabricate word timing.

## 8G. History reconciliation

After interrupted assistant speech:

- audit transcript may retain full generated text;
- active conversation context must not assume unheard suffix was received.

Verify exact installed LiveKit history behavior before modifying it.

## Phase 8 tests

- CONTINUE vs YIELD fixtures.
- One-word takeover zero misses in critical deterministic/audio corpus.
- False interruption recovery.
- Heard range does not exceed played evidence.
- Interrupted suffix not treated as heard.
- Tool business state persists independently.
- Existing interruption tests pass.

## Phase 8 runtime verification

English + Urdu/mixed:

```text
backchannel
correction
one-word stop
cough/noise
laughter only
laughter + speech
speaker echo
```

## Phase 8 exit gate

Implementation PASS requires:

- deterministic overlap-state transitions;
- cancellation/heard-state invariants;
- one-word takeover protection in the committed test corpus;
- baseline mode remains available.

Activation of new adaptive/backchannel behavior requires the relevant English/Urdu and WebRTC/PSTN audio corpus to show that true interruptions stop stale speech reliably **and** backchannel tolerance does not suppress critical takeover.

If that audio evidence is unavailable, ship the code default-off and continue.

---

# PHASE 9 — LanguageProfile: English, Pakistani Urdu and Code-Switch Behavior

**Goal:** use one semantic runtime with language-specific realization rather than forking the architecture.

**Audible behavior change:** yes.

**Depends on:** Phase 8 PASS.

Primary areas:

```text
worker/humanization/spoken.py
worker/providers/stt/gladia.py
worker/providers/stt/deepgram.py
worker/providers/tts/uplift.py
worker/uplift_spoken_sanitize.py
```

Likely new:

```text
worker/humanization/language.py
worker/humanization/languages/en.py
worker/humanization/languages/ur_pk.py
```

Use simpler structure if the codebase prefers.

## 9A. LanguageProfile contract

Include:

```text
locale
script policy
code-switch policy
repair cues
structured-data rules
acknowledgement functions
tool-bridge functions
formality rules
gender-sensitive phrasing rules
chunk/punctuation rules
```

## 9B. English profile

Move existing English conversational style rules into the provider-neutral language/policy layer where appropriate.

Do not duplicate provider renderer behavior.

## 9C. Pakistani Urdu profile

Use:

```text
ur_pk
```

semantics.

Preserve:

- natural Urdu script;
- natural Pakistani register;
- useful English brand/business terms when appropriate;
- concise spoken phrasing.

Do not hardcode a translated English backchannel list as semantics.

## 9D. Urdu-English mixed mode

Represent:

```text
ur_pk_mixed
```

or equivalent.

Ensure:

- critical English entities survive;
- mixed-language phrase boundaries remain intact;
- the STT limitation of single-language Gladia is not hidden by output behavior.

## 9E. Phrase-function banks

Store functions:

```text
SHORT_RECEIPT
TOOL_ACK_CHECK
REPAIR_CONFIRM
FALSE_INTERRUPT_RECOVERY
```

not random free-floating fillers.

Implement cooldowns via state.

## 9F. Gender/register review

Avoid voice/grammar mismatches in Urdu.

Do not rely only on machine translation.

## 9G. Uplift language integration

Keep Uplift as renderer/provider adapter, not the owner of Urdu dialogue policy.

Do not change output format in this phase.

## Phase 9 tests

- Urdu script fixtures.
- Mixed-language entities.
- Tool bridge function rendering.
- Repair cues.
- Phrase cooldown.
- No provider tags.
- Same task/tool state across English/Urdu paths.

## Phase 9 native activation gate

A native Pakistani Urdu reviewer/listening panel is required before broad rollout of any changed Urdu phrasing.

Implementation can proceed to Phase 10 with Urdu candidate behavior disabled if native review is unavailable.

Activation PASS requires a documented native review result.

---

# PHASE 10 — ChannelProfile, WebRTC/PSTN Transport, Opening and Session Resilience

**Goal:** make transport/channel part of Awaaz rendering/measurement without moving policy to the client.

**Audible behavior change:** initially diagnostics only; later bounded channel rendering.

**Depends on:** Phase 9 PASS.

Primary areas:

```text
sdk/src/index.ts
worker/telephony_runtime.py
worker/telephony_tts.py
worker/main.py
worker/latency.py
```

## 10A. Playback-ready state

Browser must distinguish:

```text
connected
```

from:

```text
audio playback ready
```

Use current LiveKit/browser public APIs.

Preserve existing `audio_blocked`/`startAudio()` contract.

Do not let server-side greeting metrics imply the user heard it.

## 10B. Browser transport diagnostics

Eval/diagnostic mode should capture compact summaries where available:

```text
actual capture settings
connection quality
RTT
jitter
packet loss
jitter buffer delay
concealment
playout approximation
```

Do not stream raw `getStats()` constantly.

For cumulative browser counters such as jitter-buffer delay/concealed samples:

- compute interval deltas/ratios rather than logging the lifetime cumulative value as "current latency";
- include sample count/window;
- preserve raw-unavailable as null, not zero.

Where practical, also record:

```text
capture sample rate/settings
remote audio codec mime/clock rate
worker/room region
```

for controlled diagnostics.

## 10C. TransportState

Normalize into a small internal state:

```text
channel
playback_ready
transport_health
codec class if known
```

Keep raw stats out of LLM context.

## 10D. Initial ChannelProfile

Start only:

```text
WEBRTC
TELEPHONY
```

Later split:

```text
PSTN_NARROWBAND
PSTN_WIDEBAND
```

when negotiated codec evidence is available.

## 10E. PSTN metadata

Where available record:

```text
call direction
SIP provider/route
LiveKit/SIP region
worker region
codec
codec/sample-rate class
```

If unknown, mark unknown.

Never infer codec from TTS sample rate.

For controlled experiments, document the conversion graph:

```text
TTS provider output format/rate
→ LiveKit/media conversion
→ SIP codec
→ caller
```

before attempting native μ-law/8 kHz optimizations.

## 10F. Channel-aware delivery controls

Allow bounded differences such as:

```text
structured-data pace
nonverbal conservatism
audio lead target
```

Semantic content must not change.

## 10G. Opening/greeting verification

Measure separately:

```text
connect/answer
→ playback/media ready
→ first disclosure audio
→ disclosure complete
→ greeting first audible word
→ first interactive turn
```

Do not break recording disclosure sequencing.

Business greeting and mandatory recording disclosure are separate opening states.

## 10H. Opening state machine

Represent at least:

```text
WAITING_FOR_CALLER
PLAYBACK_NOT_READY
DISCLOSURE_PENDING
DISCLOSURE_PLAYING
GREETING_PENDING
GREETING_PLAYING
INTERACTIVE
```

Exact names may differ.

Requirements:

- first-speaker=user remains supported;
- caller speech over an ordinary greeting can remain interruptible according to policy;
- mandatory disclosure behavior remains explicitly separate;
- server "speech completed" must not be treated as proof the browser/phone heard the content.

## 10H.1 Greeting/closing delivery convergence

Once Phase 6 renderers exist, ordinary greetings/closings should use the same provider-neutral delivery system rather than retain a special Cartesia-only social policy.

Requirements:

- greeting semantics remain trusted platform/business text;
- static cached greeting may use a fixed `DeliveryIntent` such as warm/medium energy;
- generated greeting uses the same TurnPlan/DeliveryIntent model as other speech;
- mandatory disclosure remains separate and conservative;
- do not remove current static greeting latency advantages merely for architectural purity;
- verify cached and generated speech sound like the same persona/voice.

## 10I. Greeting/cache correctness and single-flight audit

Inspect:

```text
worker/greeting_cache.py
services/tts_cache.py
provider_client_cache.py
session_opening.py
```

Verify:

- policy/renderer/pronunciation/channel changes invalidate rendered audio appropriately;
- the existing static-greeting timeout + `asyncio.shield` path cannot create harmful duplicate work/state;
- process-global cache plus thread-local provider clients is safe under concurrent sessions;
- cached frames are cloned/isolated;
- no cross-agent/tenant voice/content leakage.

## 10J. Warm-up/prewarm behavior

Trace current:

```text
STT prewarm
TTS prewarm/static greeting synthesis
LLM prewarm
VAD/plugin/DB warmup
```

Measure cold and warm separately.

Do not optimize startup by making hidden paid provider calls without usage attribution.

## 10K. Basic provider-failure conversational recovery — P0 resilience

The inspected retry budget can outlast a natural silence budget.

Before P0 verification, implement a bounded failure path for:

```text
STT unavailable
LLM request failure/timeout
TTS failure before useful audio
tool dependency unavailable
```

Requirements:

- no unexplained 30-second dead air merely because framework timeout is 30 seconds;
- distinguish provider retry from user-facing recovery;
- do not automatically switch providers in P0;
- if a spoken fallback is impossible because TTS itself is unavailable, surface a deterministic session/UI/error outcome instead of pretending speech occurred;
- preserve business/tool truth;
- record retry/failure telemetry.

Automatic provider routing/fallback remains Phase 14.

## 10L. Session-close continuity

Inspect `worker/session_close.py` and lifecycle callbacks.

Verify:

- final required playout is handled intentionally;
- a spoken closing/goodbye does not leave the call hanging open silently for several seconds;
- audit transcript/usage persistence is not lost by active-context truncation;
- committed writes are not silently cancelled by shutdown;
- pending read/background work follows explicit cancellation semantics;
- provider connections are released cleanly.

## 10M. Cold/warm/startup metrics

Record separately:

```text
cold process/provider
warm/reused provider
static cached greeting hit
static greeting miss
generated greeting
first-speaker=user
WebRTC autoplay blocked
PSTN
```

Do not mix setup latency into normal warmed turn latency without labels.

## Phase 10 tests

- SDK backwards compatibility.
- `audio_ready`/blocked flow.
- Stats parsing.
- Channel profile selection.
- Unknown codec safe fallback.
- Structured-data delivery policy differs only acoustically.
- Opening state transitions.
- Greeting cache invalidation/concurrency.
- Provider failure produces bounded deterministic outcome.
- Session-close committed-write preservation.
- Client still has no raw humanization knobs.

## Phase 10 live verification

At minimum where infrastructure exists:

```text
WebRTC headset
WebRTC speaker
PSTN
cold opening
warm opening
autoplay-blocked browser
provider failure injection
```

## Phase 10 exit gate

Implementation PASS only if:

- channel detection/diagnostics are trustworthy;
- semantic behavior is unchanged by channel profile;
- opening/disclosure/greeting states are explicit;
- provider failures cannot create indefinite unexplained silence in deterministic tests;
- session close preserves business truth.

Activation for each channel remains blocked until that channel's live/acoustic evidence exists.

---

# PHASE 11 — Full Evaluation Harness and Production-Quality Verification

**Goal:** prove the P0 implementation before provider/model tuning.

**Depends on:** Phases 0–10 PASS.

This is a verification phase, not a feature phase.

## 11A. Deterministic per-commit lane

Must include:

```text
existing focused suite
state/reducer tests
TurnPlan tests
critical repair tests
write/tool invariants
renderer contract tests
stream property tests
generation cancellation tests
channel/profile tests
```

## 11B. Text conversation simulations

Build scenario corpus covering:

```text
simple Q&A
corrections
clarifications
multi-turn task
tool success/failure
stale read
write confirmation
outcome unknown
escalation record
long-call repetition
English
Urdu
mixed
```

Check final state deterministically where possible.

## 11C. Live provider smoke lane

Credential-gated and isolated.

For each currently supported path:

```text
STT opens/streams
LLM streams/tool-calls
TTS returns audio
cancel path works
```

Do not run paid live calls in ordinary unit CI unless explicitly configured.

## 11D. WebRTC acoustic harness

Measure actual caller-side/receiver audio for:

```text
user acoustic speech end
→ first useful audible word

interruption onset
→ old speech inaudible
```

Also save transport stats.

## 11E. PSTN acoustic harness

Use actual returned phone audio if possible.

Record:

```text
route
codec if known
carrier/test number class
```

## 11F. English listening panel

Paired baseline vs candidate.

Whenever possible, rerun the **baseline policy through the same current harness/environment** as the candidate so provider/network drift does not make an old historical recording the only comparator.

Randomize/blind A/B ordering where practical.

Score:

```text
naturalness
prosody
interaction timing
interruptibility
recovery
pronunciation
scriptedness/repetition
trust
```

## 11G. Pakistani Urdu listening panel

Must include native Pakistani Urdu listeners.

Use the same paired/randomized comparison principle as English where practical.

Also score:

```text
code-switch naturalness
formality/register
gender/voice fit
local pronunciation
```

## 11H. Hard release invariants

Any occurrence blocks release:

```text
unconfirmed write
duplicate consequential write
false known-success/failure claim
stale critical value used
stale cancelled audio accepted
stale read result spoken as active
provider markup spoken/leaked
```

## 11I. Long-call/state-drift suite

Before P0 is called proven, run at least a controlled long-call corpus in each primary language style where practical.

Target scenarios:

```text
10–20 minute scripted/simulated conversation
repeated corrections
multiple read tools
one write
topic changes
interruptions
provider connection reuse
```

Look for:

```text
phrase repetition
state drift
tool duplication
history contradictions
context growth
connection decay
```

## 11J. Concurrency/load suite

Compare:

```text
single session
moderate expected concurrency
peak-like controlled concurrency
```

Monitor:

```text
event-loop delay
DB pool serialization
tool HTTP pool
provider connection pools
first-audio p95
inter-chunk gaps
error/retry rate
```

The single locked DB connection per worker process identified in the source snapshot is a specific item to measure.

## 11K. Cold/warm/opening suite

Include the Phase 10 startup matrix so a candidate does not improve normal turns while making first interaction worse.

## 11L. Cost/usage comparison

Track, where defensible:

```text
STT audio
LLM tokens
TTS synthesis
retry usage
wasted speculative synthesis
telephony
prewarm/cache activity
```

Do not claim invoice precision unless reconciled.

## 11M. Test Studio / engineering review surface

Use the existing Test Studio/integration test surface to review:

```text
policy/provider snapshot
turn trace
tool trace
transport summary
current feature flags
baseline vs candidate identifiers
```

This is an engineering aid, not a new client responsibility.

## 11N. Initial maturity targets

Use the audited research targets as **internal goals**, not universal facts.

Example targets may include:

```text
WebRTC FUAW:
p50 <= 700 ms
p95 <= 1200 ms

PSTN FUAW:
p50 <= 900 ms
p95 <= 1500 ms

WebRTC barge-in audible stop:
p50 <= 250 ms
p95 <= 500 ms

PSTN:
p50 <= 400 ms
p95 <= 750 ms
```

Do not block architecture correctness solely because a new lab baseline shows these targets need recalibration. Record the decision.

## 11O. Interaction/accuracy acceptance matrix

Carry the audited master targets into executable evaluation reports.

### True barge-in

Measure:

```text
user acoustic interruption onset
→ old agent audio inaudible
```

Initial internal maturity targets:

```text
WebRTC p50 <= 250 ms
WebRTC p95 <= 500 ms

PSTN p50 <= 400 ms
PSTN p95 <= 750 ms
```

Success also requires capturing the caller's new contribution and coherent recovery.

### One-word takeover

Committed critical set:

```text
wait
stop
no
approved Urdu equivalents
```

Hard gate:

```text
0 misses before activation
```

### Backchannel false yield

Initial target:

```text
<= 5%
stretch <= 3%
```

report separately by language/channel/item/position.

### Missed genuine takeover

Initial target:

```text
<= 2%
```

with any high-priority stop miss remaining a blocker.

### False-interruption recovery

Initial internal target:

```text
>= 98%
```

of correctly identified false/noise cases recover without state loss, excessive repetition, irrelevant apology or zombie audio.

### Correction adoption

Deterministic semantic-state suite:

```text
100%
```

Live controlled audio maturity:

```text
>= 98% clean
>= 95% degraded/noisy
```

### Critical final-state entities

Initial internal targets:

```text
>= 99% exact clean
>= 97% noisy/PSTN
```

for selected dates/times/codes/phone groups/slot/doctor identity.

Correct clarification is preferable to wrong commitment and should be scored separately.

## 11P. Tool continuity acceptance matrix

Hard gates:

```text
unconfirmed writes = 0
duplicate writes = 0
wrong write arguments = 0
known-failed tool spoken as success = 0
OUTCOME_UNKNOWN spoken as definite success/failure = 0
stale read spoken after replacement = 0
fabricated specific progress = 0
false live-transfer claim = 0
```

For delayed bridges after tuning, initial internal goals:

```text
unnecessary bridge rate <= 10%
needed-but-missing bridge rate <= 5%
```

A fast tool is not penalized for correctly skipping filler.

## 11Q. Listening / humanization acceptance matrix

For meaningful audible changes, use paired baseline-vs-candidate listening.

Initial internal gate:

```text
candidate preferred in >= 60% of decisive paired ratings
```

and no credible degradation in:

```text
trust
intelligibility
task clarity
```

Clean WebRTC naturalness maturity target:

```text
mean >= 4.0 / 5
```

This is a product target, not formal ITU MOS unless the standardized protocol is actually followed.

Also test:

```text
voice identity stability
cached vs generated speech continuity
pronunciation
structured-data intelligibility
repetition/scriptedness
emotion/nonverbal appropriateness
```

Initial structured-data listener capture targets:

```text
clean WebRTC >= 99%
PSTN/noise >= 97%
```

If a listener needs replay, first-attempt capture counts as failed.

## 11R. Repetition, nonverbal and transport guards

Initial repetition guard for instrumented phrase-bank realizations:

```text
same lexical realization <= 2 times in 10 agent turns
```

unless required confirmation/disclosure.

For scenarios marked humor/laughter-prohibited:

```text
inappropriate laughter/nonverbal joke behavior = 0
```

For candidate nonverbals later enabled in P1:

```text
>= 90% acceptable/appropriate ratings
< 2% strongly inappropriate ratings
```

Transport comparison should record:

```text
naturalness drop
intelligibility drop
FUAW change
barge-in-stop change
```

Initial transport regression guard:

```text
no >0.3 / 5 mean naturalness loss
```

versus baseline under the same transport condition without explicit trade-off justification.

## 11S. Reliability, speculation-waste and cost guards

Track:

```text
connect errors
timeouts
retries
provider disconnects
fallbacks
synthesized-but-unplayed audio
```

Provider reliability investigation/rollback trigger:

```text
> 2x baseline error rate
or
+0.5 percentage-point absolute error increase
```

with adequate sample size.

When speculative TTS is enabled later, initial waste guard:

```text
no >2x increase in unplayed synthesized audio
```

without approximately:

```text
>= 100 ms meaningful p95 FUAW improvement
```

or another documented user-quality gain.

Cost guard:

```text
>20% variable provider/model cost increase
```

requires documented quality/latency justification.

These are Awaaz internal decision rules, not universal standards.

## Phase 11 exit gate

P0 is considered implementation-complete only if:

```text
ConversationState
IDs
TurnPlan
TurnCoordinator
critical repair
tool truth
DeliveryIntent/renderers
stream-safe speech path
generation invalidation
overlap/heard state
language profile
channel profile
opening/session resilience
correct metrics
rollback/version controls
```

exist and the committed corpus passes.

Also require:

- long-call/state-drift suite complete;
- controlled concurrency/load evidence;
- cold/warm/opening comparison;
- interaction/accuracy matrix reported;
- tool continuity matrix reported;
- paired listening evidence for any audible candidate proposed for activation;
- no hard invariant failure;
- reliability/cost/waste regression recorded.

Features whose activation evidence is still missing may remain default-off, but Phase 16 cannot promote them to production without their activation gates.

---

# PHASE 12 — LiveKit Upgrade Compatibility Lane

**Goal:** evaluate newer LiveKit separately from core humanization behavior.

**This phase is intentionally isolated.**

It may be done after Phase 11, or earlier only if a blocking P0 feature cannot be implemented safely on the pinned version.

**Never merge this work invisibly into another phase.**

## 12A. Upgrade reconnaissance

Read:

```text
current pinned requirements
current installed dependency source
target LiveKit release notes
target plugin compatibility
migration notes
```

Record all relevant API differences.

## 12B. Compatibility branch

Create a dedicated branch/history.

Upgrade only the intended LiveKit packages.

Do not simultaneously change:

```text
TTS models
prompts
chunk policy
interruption policy
tool semantics
```

unless required for compatibility and clearly documented.

## 12C. Re-run entire deterministic suite

Must include:

```text
baseline focused suite
new P0 tests
SDK/server builds
English/Urdu text corpus
write/tool safety
stream/cancellation
```

## 12D. Re-verify exact newer capabilities

Do not assume docs.

Inspect target installed source for:

```text
adaptive interruption
aligned transcript behavior
async tools
tts_node
text transforms
Eleven v4 path
tool events
metrics
```

## 12E. Live audio regression

WebRTC + PSTN where available.

## Phase 12 exit gate

Upgrade merges only if:

- all hard invariants pass;
- no unexplained latency regression;
- no English/Urdu regression;
- exact version/capability snapshot is updated.

A newer framework feature may implement Awaaz mechanics, but it must not replace Awaaz business/humanization invariants.

---

# PHASE 13 — Provider/Model Bake-offs and P1 Tuning

**Goal:** optimize providers only after the architecture and measurement harness are stable.

**Depends on:** Phase 11 PASS; use upgraded framework only if Phase 12 also passed.

## 13A. Baseline freeze

Before each experiment save:

```text
policy version
provider snapshot
language
channel
cold/warm state
network condition
scenario corpus version
```

Change one major variable at a time.

## 13B. English STT experiments

Evaluate current relevant choices:

```text
Deepgram Nova
Deepgram Flux where supported
```

Do not make Flux non-English assumptions.

Measure:

```text
critical entity accuracy
partial/final stability
turn timing
backchannel behavior
```

Where exact installed/upgraded capabilities allow, isolate turn semantics with a controlled matrix such as:

```text
current Nova endpointing + current turn mode
Nova text + framework/audio turn detector
Flux EndOfTurn baseline
Flux eager/speculative EOT only after simple EOT works
dynamic endpointing only when exact framework source supports it
```

Do not change STT model and interruption policy in the same comparison.

## 13C. Urdu STT experiments

Evaluate Gladia baseline and any approved candidates separately.

Include, only as evidence-backed candidates:

```text
Gladia code-switch/custom-vocabulary options
Deepgram Urdu where current vendor/plugin path truly supports it
Soniox only after intentional dependency/registration work
```

Do not replace Gladia solely from English benchmark results.

Also compare the current short-silence behavior against an Awaaz-owned Urdu/mixed turn-completeness policy using the same Gladia provider before attributing improvements to a provider swap.

## 13D. LLM experiments

Compare approved Groq/Gemini configurations using the same:

```text
TurnPlan
tool policy
renderer
corpus
```

Include the currently relevant Groq model sizes/configurations only when they are actually exposed and available in the checkout/account; do not infer model availability from old research notes.

For Gemini specifically, audit the source-snapshot request shape that sends `temperature=0.35`:

```text
current request
vs
temperature removed / current-provider-recommended shape
```

before treating temperature as a humanization control.

Measure:

```text
correctness
tool behavior
first useful text
response naturalness
cost
```

## 13E. Cartesia experiments

Only now consider:

```text
model upgrade
continuation context
alignment
```

against current baseline.

## 13F. Rime experiments

Verify actual deployed/direct model path first.

Then compare approved:

```text
current Arcana/direct path
Coda
Mist v3
```

and segmentation policies.

## 13G. ElevenLabs experiments

First verify the exact current Flash path text granularity and `auto_mode=True` behavior after Awaaz's chunk planner.

Compare, where the installed/current API supports it:

```text
current auto_mode behavior
vs
explicit Awaaz-managed stable chunks / provider-recommended alternative
```

Then, if the installed/upgraded plugin supports current TTD/v4 path:

- integrate as a separate, gated experiment;
- do not replace Flash baseline silently.

## 13H. Uplift experiments

Evaluate:

```text
persistent live streaming
phrase replacements
PCM baseline
native telephony format only if exact adapter path supports it
```

with native Urdu listeners.

Also confirm the deployed environment is not silently using the repository's fixture-mode default when interpreting acoustic results.

## 13H.1 Unexposed/candidate TTS lane

Candidates such as:

```text
Fish Audio
Cartesia Urdu
ElevenLabs Urdu/current dialogue models
```

remain separate research/integration candidates.

They must not be added to normal provider selection merely because code/docs exist.

Any candidate needs:

```text
intentional registration
capability contract
provider smoke
language-native listening
cost/reliability comparison
rollback
```

## 13I. Preemptive-generation experiments

Compare:

```text
no speculation
LLM-only
LLM + TTS
```

where relevant.

Optimize caller-perceived latency, not provider metrics alone.

## 13J. Reliability/rate-limit experiment

For any adoption candidate, exercise where feasible:

```text
429/rate limit
connection reset
timeout
provider 5xx
reconnect
concurrent calls
```

Record recovery latency and caller-visible effect.

## 13K. Provider adoption rule

Use result labels:

```text
ADOPT
ADOPT_BEHIND_FLAG
RETEST
REJECT
INCONCLUSIVE
```

Do not call one provider globally "best" if channel/language results differ.

## Phase 13 exit gate

Any provider/model change requires:

- deterministic regressions green;
- live provider smoke;
- paired listening;
- caller-observed latency comparison;
- cost comparison;
- rollback flag.

---

# PHASE 14 — Advanced P1 Humanization

**Goal:** add higher-order naturalness only after the deterministic platform is stable.

Examples:

```text
adaptive interruption default if proven
persistent provider context optimization
better pronunciation lexicon
long-running async tool progress
transport-aware provider routing
stronger heard-state
```

Do **not** implement P2 social tricks here.

## 14A. Adaptive interruption promotion

Only if Phase 8/11 data shows improvement.

Keep:

```text
one-word takeover
backchannel
turn-boundary answer
Urdu
PSTN
```

gates.

## 14B. PronunciationLexicon

Platform-owned lexicon compiling to provider-specific controls.

Support business-specific names/terms without client-side provider syntax.

## 14C. Long-running tool orchestration

If framework/runtime supports:

```text
background progress
cancellation
```

integrate through ToolOrchestrator.

Writes remain governed by Awaaz safety.

## 14D. Provider continuity/alignment

Enable:

```text
word alignment
same-turn continuation contexts
```

where provider/plugin evidence proves support.

## 14E. Channel/provider routing

Only after evidence.

Example possible profiles:

```text
English WebRTC premium
English PSTN robust
Urdu WebRTC
Urdu PSTN
```

Routing remains internal.

## 14F. Advanced provider fallback / routing

Phase 10 already owns the basic bounded failure outcome.

P1 may add automatic provider fallback only after evidence.

Requirements:

- distinguish provider retry from user-facing recovery;
- do not automatically switch providers mid-turn without a controlled fallback policy;
- make fallback sticky for the appropriate scope rather than oscillating;
- keep `DeliveryIntent`, business state and tool truth stable across fallback;
- record fallback/retry as telemetry;
- ensure fallback voice/persona remains acceptable;
- never retry a consequential business write merely because the speech/LLM provider changed.

## 14G. Bounded AffectState and empathy trajectory

Add a small, inspectable state model only after core correctness is stable.

Candidate states:

```text
neutral
positive
amused
frustrated
worried
confused
urgent
```

Requirements:

- affect never becomes business authority;
- no mandatory second sentiment/emotion model call on every turn;
- conservative uncertainty/default-to-neutral behavior;
- state can influence empathy level, pace and delivery;
- complaints/urgent contexts suppress humor/laughter.

## 14H. Contextual humor/laughter/expressivity policy

Implement only with renderer/provider listening evidence.

Use:

```text
forbidden
reactive_only
light_allowed
```

or equivalent permissions.

Requirements:

- repetition/cooldown state;
- no random laughter before facts, writes, complaints or critical structured data;
- unsupported provider nonverbals degrade to wording/prosody;
- English and Urdu require separate listening validation.

## 14I. Optional bounded public style contract

Only if the product needs customer-selectable style, expose semantic choices such as:

```text
conversation_style = formal | neutral | casual
expressiveness = conservative | natural | lively
```

Requirements:

- compile these into Awaaz policy;
- do not expose raw provider/VAD/chunking knobs;
- platform safety/TurnPlan can override them contextually;
- old agents with no setting keep a stable default;
- public API/schema changes require SDK/server/portal compatibility tests.

This subphase is optional; the humanization runtime must work well without requiring customers to configure it.

## Phase 14 exit gate

P1 features need live audio evidence, not only unit tests.

---

# PHASE 15 — P2 Social/Full-Duplex Experiments

**Goal:** explore advanced social behavior after P0/P1 stability.

Not production-required.

Possible experiments:

```text
COLLABORATIVE ADAPT overlap
agent-generated mid-user backchannels
learned timing policy
dynamic richer affect inference
full-duplex model benchmark
long-term personalization
```

Rules:

- behind experimental flags;
- no impact on write truth;
- no required client code;
- do not add serial latency to standard turns;
- do not promote from demo quality alone.

## Phase 15 exit gate

Any P2 experiment is considered complete only when:

- it is isolated behind an experimental flag;
- disabling it returns to the verified P1 path;
- hard business/tool invariants remain unchanged;
- caller-observed latency impact is measured;
- English/Urdu/channel scope is explicitly stated;
- the result is labeled `ADOPT`, `ADOPT_BEHIND_FLAG`, `RETEST`, `REJECT`, or `INCONCLUSIVE`.

P2 experimentation is **not** a prerequisite for production readiness of the P0/P1 humanization runtime.

---

# PHASE 16 — Final System Audit, Canary and Rollout

**Goal:** audit the implementation as a whole before production-wide enablement.

**Depends on:** relevant implementation phases PASS.

## 16A. Code-to-plan audit

Codex/reviewer must compare final code against:

```text
HUMANIZATION_IMPLEMENTATION_PLAN_CODEX.md
HUMANIZATION_RESEARCH_MASTER.md
```

For every architecture component, mark:

```text
implemented
intentionally deferred
replaced by framework capability
not applicable
```

Any unexplained drift is a release blocker.

## 16B. Source-level invariant audit

Explicitly verify:

```text
write gate still authoritative
state authority hierarchy preserved
tool/speech state separated
provider markup isolated
generation invalidation enforced
stale read suppression
client ownership boundary preserved
```

## 16C. Full verification matrix

Run:

```text
deterministic suite
text simulations
live provider smoke
English WebRTC
Urdu WebRTC
PSTN
interruptions
tool failures
write timeout/unknown outcome
long-call
concurrency/load
```

as available.

## 16D. Canary rollout

Recommended sequence:

```text
internal/test
1%
5%
20%
50%
100%
```

Use stable per-session policy assignment.

Do not switch a live conversation between policy versions.

## 16E. Canary promotion evidence

Promote by sample/evidence, not time alone.

Starting guidance from the audited master:

```text
1%  >= 200 completed turns
5%  >= 1000
20% >= 3000
50% >= 5000
```

Adjust for product volume while preserving statistical caution.

## 16F. Immediate rollback triggers

Immediate stop/rollback for any confirmed:

```text
unconfirmed/duplicate write
false success/failure about consequential action
stale critical value used
stale cancelled speech emitted
severe Urdu comprehension/naturalness regression
severe PSTN intelligibility regression
security/privacy regression
```

## 16G. Quantitative rollback alerts

Use current baseline comparison.

Examples from audited research:

```text
FUAW p95 > baseline +15% or +150 ms
false-yield +3 percentage points
missed takeover +2 percentage points
critical final-state accuracy -1 point
provider error +0.5 point or 2x baseline
unexpected cost +20%
```

These are starting internal thresholds, not universal standards.

## 16H. Feature-flag and compatibility cleanup

After a stable rollout window—not immediately at first 100% enablement—review temporary migration flags.

Requirements:

- retain a proven rollback path through the agreed rollback window;
- remove obsolete one-off flags only after their baseline path is no longer needed;
- consolidate long-term behavior into versioned policy rather than dozens of environment toggles;
- remove dead provider-prompt/sanitizer compatibility code only after all affected provider lanes have passed activation gates;
- document any intentional legacy compatibility that remains.

## 16I. Final documentation update

Only after code/runtime truth is known:

- update codebase context;
- update master implementation status;
- update provider/version snapshot;
- update the implementation-status ledger to `ROLLED_OUT` or the appropriate final state;
- document deferred P1/P2 items.

Do not rewrite docs to claim live validation that did not occur.

## Phase 16 exit gate

The humanization implementation is production-ready only when:

```text
truth is preserved
caller-observed timing is measured
interaction behavior is verified
acoustics are listened to
English and Urdu gates pass
WebRTC/PSTN affected paths pass
rollback is proven
```

---

# 17. Strict dependency graph

```text
Phase 0  Baseline
   ↓
Phase 1  Observability / IDs
   ↓
Phase 2  HumanizationRuntime / State
   ↓
Phase 3  TurnPlan shadow
   ↓
Phase 4  InputUnderstanding / Repair / TurnCoordinator foundation
   ↓
Phase 5  ToolOrchestrator
   ↓
Phase 6  DeliveryIntent / Renderers
   ↓
Phase 7  Streaming / Generation cancellation
   ↓
Phase 8  Overlap / HeardState
   ↓
Phase 9  Language profiles
   ↓
Phase 10 Channel / Transport / Opening / Session resilience
   ↓
Phase 11 Full P0 Verification
   ↓
   ├────────────→ Phase 12 LiveKit upgrade lane (optional/separate)
   │
   └────────────→ Phase 13 Provider/model bake-offs
                         ↓
                    Phase 14 P1
                         ↓
                    Phase 15 P2 experiments

All production paths
   ↓
Phase 16 Final audit / canary / rollout
```

Important:

- Phase 12 is **not** allowed to silently merge into Phases 1–10.
- If a P0 phase is truly blocked by the pinned framework, perform the smallest required Phase 12 compatibility work first, then return to the blocked phase.
- Provider/model bake-offs are intentionally after P0 architecture verification.

---

# 18. What Codex is explicitly forbidden to do early

Before Phase 13, Codex must not casually:

```text
switch Cartesia model
replace Rime model
enable Eleven v4
change Uplift output format
change Deepgram STT mode globally
change Gemini/Groq defaults
raise/lower endpointing globally
turn adaptive interruption on globally
rewrite every provider at once
upgrade LiveKit inside a humanization PR
```

unless the active phase explicitly calls for that exact change.

Before Phase 15, do not implement:

```text
random agent laughter
agent mid-user "mhm" backchannels
learned humanization controller
multi-agent empathy/joke agents
```

as production defaults.

---

# 19. Required verification pattern inside every implementation phase

Every Codex implementation phase must have these five internal subphases even if not repeated above:

## A. RECON

- inspect current code;
- trace call path;
- inspect tests;
- identify dirty changes;
- confirm exact dependency behavior.

## B. IMPLEMENT

- smallest coherent change;
- preserve compatibility;
- add semantic flag/version where audible/risky.

## C. DETERMINISTIC VERIFY

- unit tests;
- property tests;
- state/invariant tests;
- existing regression suite.

## D. RUNTIME VERIFY

When the phase affects runtime audio/provider behavior:

- live/provider smoke if credentials exist;
- WebRTC/PSTN as relevant;
- paired baseline/candidate evidence.

If unavailable, mark runtime verification pending and keep feature disabled.

## E. PHASE AUDIT

Ask:

```text
Did this phase accidentally implement later phases?
Did it weaken a hard invariant?
Did it add serial network latency?
Did it move policy to the client?
Did it change a provider/model unintentionally?
Can it be rolled back?
Is implementation evidence being confused with activation evidence?
```

Then issue:

```text
IMPLEMENTATION GATE = PASS/FAIL
ACTIVATION GATE = PASS/BLOCKED/NOT_APPLICABLE
```

A blocked activation gate requires the candidate feature to remain off; it does not necessarily block later code-only phases.

---

# 20. Plan audit — dependency and coverage check

This implementation plan was audited against the final research architecture and the source-grounded codebase context.

## 20.1 P0 architecture coverage

Final research P0 requirement | Plan phase
--- | ---
Correct metrics / IDs | 1
ConversationState | 2
Central Agent/hook boundary | 2
Policy resolver / compatibility | 2
TurnPlan | 3
Prompt/business-fact authority | 3
Critical repair / InputUnderstanding | 4
TurnCoordinator foundation | 4
Write/tool truth | 5
DeliveryIntent / renderer boundary | 6
Stream-safe speech path | 7
Generation invalidation | 7
Overlap decision | 8
Heard-state | 8
Language-specific realization | 9
Channel awareness | 10
Opening/session resilience | 10
Basic provider failure outcome | 10
Full P0 verification | 11

No P0 component from the audited final architecture is intentionally omitted.

## 20.2 Provider coverage

Provider area | Covered in
--- | ---
Deepgram Nova | 4, 13
Deepgram Flux | 4, 13
Deepgram Urdu candidate | 13
Gladia | 4, 9, 13
Soniox candidate/unexposed | 13
Groq | 3, 13
Gemini | 3, 9, 13
Cartesia | 6, 7, 13
Rime | 6, 7, 13
ElevenLabs | 6, 7, 13
Uplift | 6, 7, 9, 13
Fish Audio candidate/unexposed | 13

## 20.3 Channel coverage

Channel | Covered in
--- | ---
Browser/WebRTC | 10, 11, 16
PSTN/SIP | 10, 11, 16
Opening/autoplay | 10
Codec/sample-rate experiments | 13
Transport-aware rendering | 10, 14

## 20.4 Safety/truth coverage

Concern | Covered in
--- | ---
Write confirmation/idempotency | 5
Outcome unknown | 5
Duplicate write | 5, 11, 16
Stale read | 5
Stale audio | 7
Unheard suffix | 8
Turn commit/endpointing ownership | 4, 8
Audit transcript vs active LLM context | 2
Prompt/business-fact authority | 3
Escalation truth | 5
Provider-rendered cache invalidation | 6, 10
Basic provider failure/dead-air handling | 10
Advanced provider fallback | 14
PII/structural telemetry | 1
Tenant/session isolation | 2, 10
Client ownership boundary | all phases
Provider capability mismatch | 6

## 20.5 Verification coverage

Verification layer | Covered in
--- | ---
Existing regression tests | 0 and every phase
Fixed corpus/baseline artifacts | 0
Unit/invariant tests | every implementation phase
Property streaming tests | 7
Text simulations | 11
Live provider smoke | 11
WebRTC acoustic | 11
PSTN acoustic | 11
Native Urdu listening | 9, 11
Cold/warm/opening | 10, 11
Concurrency/load | 11, 16
Long-call/state drift | 11, 16
Cost/usage | 1, 11, 13
Canary/rollback | 16

## 20.6 Ordering audit

The order is intentional:

1. freeze source/runtime/test/corpus baseline;
2. correct observability and IDs;
3. create explicit state and centralized framework-hook boundary;
4. derive policy in shadow and protect prompt/business-fact authority;
5. establish repair plus TurnCoordinator lifecycle;
6. establish tool truth;
7. move delivery semantics out of provider prompts;
8. change streaming/cancellation;
9. change overlap/recovery;
10. refine language realization;
11. refine channel/opening/session resilience;
12. verify the whole P0 system under long-call/load/cold-warm conditions;
13. isolate framework upgrade;
14. tune providers/models;
15. add P1 affect/continuity/fallback capabilities;
16. experiment with P2;
17. canary and final audit.

This prevents simultaneous changes from hiding regressions while still allowing a narrow reference lane to prove the architecture early.

---

# 20.7 Independent audit verdict

After the end-to-end independent review, the plan is considered implementation-ready **with the corrections in this revision**.

The audit specifically rejected these weaker designs:

```text
prompt-only humanization
provider-specific social policy
one universal endpointing threshold
one universal TTS chunk policy
tool truth stored only in chat text
provider TTFB treated as caller latency
live-evidence absence treated as permission to guess
runtime-verification absence treated as a reason to block all code progress
large multi-provider changes before a reference vertical slice
automatic provider fallback before basic failure semantics are trustworthy
```

The plan now deliberately supports two simultaneous goals:

```text
engineering can continue safely behind disabled/shadow flags
+
caller-facing activation cannot occur without the relevant evidence
```

That distinction is essential for a phase-by-phase Codex workflow.

---

# 21. Final Codex execution rule

When the user says:

```text
"Implement Phase N"
```

or:

```text
"Implement Phase N.X / N-letter"
```

Codex should:

1. read this plan's requested execution unit;
2. read the final master sections relevant to that unit;
3. read the latest `docs/HUMANIZATION_IMPLEMENTATION_STATUS.md`;
4. inspect the actual current code;
5. implement only the requested execution unit;
6. run that unit's deterministic/runtime verification;
7. update the implementation-status ledger;
8. produce the completion report;
9. stop.

Codex should **not** automatically start the next phase/subphase.

The goal is not to implement the most code per prompt.

The goal is to make every humanization change:

```text
correct
measurable
provider-independent
reversible
English/Urdu compatible
WebRTC/PSTN aware
safe for business actions
```

before moving forward.
