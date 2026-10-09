# Fast-track Chat D — Phases 8, 9 and 10 minimum P0

PHASE / SUBPHASE: Original Phases 8–10, explicitly requested minimum P0 only.
STATUS: CODE_COMPLETE_ACTIVATION_BLOCKED.
IMPLEMENTATION GATE: PASS.
ACTIVATION GATE: BLOCKED for new audible behavior across all language/channel/provider lanes.
NEXT SAFE PHASE / SUBPHASE: STOP. No provider/model tuning or P1/P2 work started.

## Verification

| Check | Final evidence |
| --- | --- |
| New parameterized Python suite | 53 passed; all included in the final focused run |
| Directly affected regressions | 224 passed before final compatibility corrections; final focused run supersedes this snapshot |
| Final focused regression, 27 files | **421 passed, 0 failed, 0 skipped**, one existing Starlette warning |
| Browser SDK | **33 passed**, typecheck and build passed |
| Scoped Ruff | PASS; existing invalid-noqa warning in main.py retained |
| Integrity | 714 captured files; only intended existing paths changed; no unexpected changes, removed captured files, new whitespace or invalid UTF-8 |
| Required graph refresh | Attempted; existing `uv trampoline failed to canonicalize script path` error |

Evidence: ignored `tmp/humanization-batch-d-20261009/` contains before-file copies, SHA-256 capture, targeted/affected/compatibility/final JUnit and integrity JSON. Preserve it before cleaning tmp. No full repository CI run or deployment was performed.

## Before and after

Before: TurnCoordinator observed lifecycle only; heard status was unknown, language/channel profiles were placeholders, browser connection exposed no positive playback-ready state, openings used an active boolean, and framework retry defaults could wait 30 seconds.

After: the same coordinator makes CONTINUE/YIELD/RECOVER_FALSE decisions. Short listener feedback requires a current agent overlap, known short duration and compatible conversation state. Critical English and obvious Urdu/mixed takeovers yield, including one-word wait/stop/no. No universal minimum-word filter or acoustic classifier was added. Candidate mode uses native pause/resume instead of bare-VAD force flushing.

False interruption recovery resumes an existing framework pause, restarts a short clause at a safe boundary, or replans without tool replay. Cancelled generations remain invalid. Recovery does not automatically apologize, and repeated recovery in the same semantic epoch is suppressed.

HeardState records genuine synchronized output text where available, otherwise complete contiguous chunks at an actual output playout boundary. Elapsed synthesis time alone cannot create heard text or word timing. WebRTC requires a positive browser readiness report before accepting local output evidence. This estimates likely receipt; playback permission and server output completion are not proof that a person heard speech. Unknown interrupted suffixes are removed from a copied model context; original audit/history and committed tool effects remain intact. Installed LiveKit ChatContext.copy shares messages, so interrupted messages are individually cloned before reconciliation.

LanguageProfile realizes English, Pakistani Urdu and Urdu-English mixed behavior through the same semantic runtime. It preserves literal entities, respectful register and mixed phrase boundaries. SHORT_RECEIPT, TOOL_ACK_CHECK, REPAIR_CONFIRM and FALSE_INTERRUPT_RECOVERY have session-local cooldown state. Uplift remains a renderer/provider adapter with unchanged model/output format. Single-language Gladia limitations remain; output policy cannot supply missing STT coverage.

ChannelProfile selects WEBRTC/TELEPHONY. Differences are acoustic only: conservative nonverbals, bounded local audio handoff and slower supported structured-data delivery. Available connection quality remains in the SDK timing snapshot. Telephony direction/route/provider/codec use explicit metadata only; missing values are UNKNOWN, RTT/jitter/loss remain unavailable, and TTS sample rate never becomes a SIP codec.

The SDK adds audio_ready/isAudioReady and a small readiness report/request exchange while preserving audio_blocked and startAudio. Manual media-element playback failures also report blocked state. Worker opening states distinguish playback not ready, disclosure pending/playing, greeting pending/playing and interactive. Mandatory disclosure remains separate and uninterruptible, precedes either greeting or first-speaker=user waiting, and cannot grant consent on a missing/failed handle. Optional readiness gating is default-off for older SDK compatibility.

Ordinary cached/live/generated greetings use the common delivery path for each selected renderer; mandatory disclosure uses neutral delivery. Static PCM hits retain their latency advantage. Cache identity includes language/channel/static-delivery versions. PCM is cloned per waiter, cache operations are locked, in-flight tasks are scoped by event loop, shielded synthesis has its own finite lifetime, and an opening timeout cannot start duplicate live synthesis.

Provider failures produce deterministic terminal session/UI/error outcomes without switching providers or claiming fallback speech. Defaults: provider connection 5 seconds/no retry; STT stays capped at 5 seconds/no retry even under legacy overrides. LLM/TTS useful-progress gaps are bounded at 6 seconds independently of plugin retry settings; empty output also fails. Tool operations have a 6-second total budget, preserving OUTCOME_UNKNOWN for uncertain dispatched writes. Idle STT microphone silence is not treated as provider failure.

Intentional end keeps summary/business effects independent of shutdown, waits for the public tool-step final playout, drains required output and skips the framework's 2-second final user-transcript wait only when no caller is speaking. Full audit/usage persistence and existing lifecycle DB behavior remain covered by regressions. A stalled summary dependency follows the bounded tool outcome rather than an unbounded close wait. Providers/owned synthesis streams close in finally blocks; shared cache fills settle within their own budget.

## Feature switches and defaults

- UVA_OVERLAP_POLICY=overlap_v1: candidate overlap, native false-resume and language realization. Default baseline/OFF.
- UVA_OPENING_POLICY=opening_v1: caller playback-ready opening gate, including SIP active evidence. Default baseline/OFF; old clients retain the legacy opening path.
- Existing UVA_TTS_RENDERER_<PROVIDER>=delivery_v1 and UVA_TTS_STREAMING_<PROVIDER>=streaming_v1 remain independent and OFF for all four providers.
- Shared profile versions: language_v1/channel_v1; candidate cache static-delivery version opening_v1. No model, voice, format or LiveKit upgrade.
- Core safety/correctness ON: unknown-heard context reconciliation, disclosure failure guard, bounded failure/empty-output handling, cache flight cleanup and intentional-close handling. Additive readiness diagnostics ON.

Current inherited environment and .env.local were checked for these ten feature settings: all baseline. No persistent flag, dependency, lockfile, credential, route or database/schema change was made.

## Required P0 coverage

| Requirement | Evidence |
| --- | --- |
| CONTINUE / YIELD; one-word takeover | Parameterized coordinator and public STT-hook tests |
| Contextual backchannels | Timing, agent-speaking, transcript extension and confirmation/repair cases |
| False recovery | Strategy fixtures plus public callback execution and nonstreaming replan |
| Heard bounds / unheard suffix | Real output integration, contiguous chunk/synchronized text fixtures and immutable audit/context test |
| English / Urdu / mixed / cooldown | Three profiles, same business grounding and session-isolated phrase cooldown |
| WEBRTC / TELEPHONY | Channel intent and unknown-codec fixtures |
| Connected versus ready | Python readiness exchange and browser startAudio/blocked/late-worker tests |
| Disclosure / greeting / first speaker | Locked disclosure ordering with both first-speaker modes and existing disclosure regressions |
| Greeting/cache policy | Four-provider identity invalidation, common compile path, single-flight timeout and per-waiter PCM isolation |
| Provider failures | LLM/TTS timeout injection, empty TTS, STT error event, truthful unavailable/unknown tool outcomes |
| Committed writes / close | Before/after-close effects, final step playout, full lifecycle/persistence regressions |
| Active providers compatible | Installed synthetic framework paths for Cartesia, Rime, ElevenLabs and Uplift, including streaming/cancellation |

## Files and scope

Read: AGENTS.md, complete implementation-status ledger, requested invariants/Phases 8–10/final execution-gate rules, current coordinator/runtime/agent/state/evidence/understanding/TurnPlan/history/delivery/streaming/spoken modules, latency, retries, opening/disclosure/cache, tools/session close, telephony runtime, SDK playback and affected tests. Installed LiveKit 1.6.5 AgentSession/Agent/activity/events/output/history sources were inspected for actual public behavior. The full research master was not read.

Changed existing files: SDK index; CI manifest and retry compatibility tests; greeting cache, latency, main, retry policy, disclosure, session opening, telephony diagnostics, tools; humanization coordinator/agent/runtime/state/history/streaming/TurnPlan/turn/orchestrator/spoken and delivery profiles/context/cache; status ledger. Exact changed paths are recorded in the integrity JSON.

New files: tests/test_humanization_batch_d.py, sdk/src/playback.test.ts and this report. No new production module or competing turn state machine.

Runtime items still unverified: live provider packets/errors/retries, real browser autoplay/headset/speaker behavior and caller recordings, PSTN routes/codec/media/readiness, deployed configuration and DB persistence, native Pakistani Urdu/mixed phrase/prosody listening, real alignment/receipt/cancellation/flush, long calls, concurrency and cost. Synthetic framework evidence does not establish these. Existing lane baselines remain absent.

Advanced interruption/classification, mid-user agent backchannels, exact unaligned word timing, empathy/laughter/filler tricks, codec/noise/region/jitter experiments, provider routing/fallback and model/LiveKit upgrades remain deferred. STOP after Chat D.
