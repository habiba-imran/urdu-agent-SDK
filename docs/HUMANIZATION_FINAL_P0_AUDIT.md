# Final fast-track P0 humanization audit — 2026-10-09

VERDICT: **P0_IMPLEMENTATION_READY_ACTIVATION_BLOCKED**

IMPLEMENTATION GATE = PASS\
ACTIVATION GATE = BLOCKED\
DEFAULT ENABLEMENT = OFF for new audible candidates

This verdict covers the explicitly requested minimum fast-track P0 architecture, after the small corrective fixes below. It does not claim the full original Phase 11 acoustic/load/listening gates or original Phase 16 production readiness. No production canary, deployment, promotion, provider/model change, framework upgrade or credential/route change occurred.

## Scope and source identity

- Actual checkout: `C:\Users\habiba\Desktop\SDK\sdk-agent`; supplied `habib` path does not exist on this host.
- Branch `main`, HEAD `c37fd73fd7bce0766496d7068c49d400f1c36e17`; uncommitted source is the audited implementation. Existing unrelated dirty portal, telephony and deleted-deliverable work was preserved.
- Read the complete implementation-status ledger; only universal invariants, original Phases 11/16 and final execution rules from the plan. The research master was not read. Existing batch evidence supplemented current source and tests; historical results were not treated as fresh passes.
- Python 3.12.10; LiveKit agents and all eight provider plugins 1.6.5; RTC 1.1.13. No dependency or lockfile edits.
- Frozen corpus version 1.0.0, SHA-256 `d9ab900428d857a5ffe85ac1420cb66af387943aa1968167d1dba89a2c78a6e4`. Native Urdu labels remain provisional. The complete 30-scenario recipe corpus is not an executed acoustic/conversation evaluation; executed deterministic coverage is reported below.
- Ignored local evidence: `tmp/humanization-final-p0-20261009/`. Keep this bundle with the prior phase/batch bundles.

## Concrete failures corrected

1. **Backend outcome truth:** an HTTP 200 body containing only `outcome: OUTCOME_UNKNOWN` was slimmed to `success: true`, then normalized as committed success. Explicit failure/unknown outcomes now survive the gateway and override conflicting success flags or success narration. Unknown write outcomes retain their tombstone and cannot cause a second POST or fresh proposal. Unrecognized declared write outcomes fail closed to unknown. Declared `NO_RESULT` cannot become a committed write. Outcome telemetry also distinguishes unknown from ordinary failure.
2. **Entity correction order:** `Monday, not Friday` selected Friday because the parser always chose the last entity. Local negation now excludes the rejected entity before selecting current evidence, including supported date/time/phone/email/name/doctor/identifier forms. English, Roman Urdu, Urdu script and mixed fixtures retain the existing repair behavior. Unsupported/ambiguous values still require clarification.
3. **Corrected doctor arguments:** booking/rescheduling could omit a selected doctor or substitute an unrelated doctor after correction. These writes now require the current doctor to be retained in the existing service argument; old, omitted or unrelated doctor arguments fail closed. Reaffirming the same current doctor does not make that value unusable merely because an older observation of the same string is superseded. No doctor-ID schema, resolver or new backend interface was added.
4. **Telemetry version truth:** shadow sessions and independent candidates could be reported as baseline. Session construction now freezes effective policy/component/opening identities in its diagnostic snapshot; trace, room, rolling and close events use the effective session policy. Defaults remain baseline and audible flags remain off.

Changed existing source: `worker/humanization/orchestrator.py`, `worker/humanization/understanding.py`, `worker/tools.py`, `worker/main.py`, `worker/latency.py`. Added 35 parameterized regression cases in `tests/test_humanization_final_p0.py`, included in the existing CI manifest. No new architecture/harness was introduced.

## Code-to-architecture matrix

`IMPLEMENTED` describes code plus deterministic evidence. Candidate components may be implemented and default-off while live activation remains blocked.

| Requested component | Status | Current source/ownership and boundary |
| --- | --- | --- |
| Correlation IDs | IMPLEMENTED | `telemetry.py`, `latency.py`: session/user/assistant/generation/framework speech/tool IDs, monotonic ordering and bounded diagnostic traces; canonical tool duration is recorded once. |
| HumanizationRuntime | IMPLEMENTED | `humanization/runtime.py`: session-local authority, short locked state operations, independent tool/speech state and snapshots. |
| ConversationState | IMPLEMENTED | `state.py`: typed partitions, trusted snapshot replay and tenant/agent/session identity. |
| Event reducer | IMPLEMENTED | `events.py`: deduplication, grounding authority, terminal generation/tool tombstones and late business completion after close. |
| Centralized Agent/hook integration | IMPLEMENTED | `AwaazAgent` is constructed by `main.py`; public STT/LLM/TTS/transcription/turn hooks delegate to the installed framework. |
| Audit transcript vs active LLM context | IMPLEMENTED | `AuditTranscript` retains full plain turns; interrupted suffixes are reconciled on a copied model context. Legacy session-history cap does not cap active model input. |
| Policy resolver | IMPLEMENTED | `policy.py`: baseline default; `natural_v1` resolves to shadow with behavior off. Existing explicit configuration precedence preserved. |
| TurnPlan | IMPLEMENTED | `turn_plan.py`: local deterministic safety precedence and delivery mapping; normal full prompt policy remains shadow/off. |
| LLMContextProjection | IMPLEMENTED | `ContextProjection` in `context_projection.py`: confirmed-current facts, explicit overflow and disposable preview. General plan projection is shadow-only; recorded committed/unknown business effects are actively projected separately. |
| Critical InputUnderstanding | IMPLEMENTED | `understanding.py`, `evidence.py`: conservative final transcript evidence, segment confidence provenance and fail-closed write argument checks. Not a general multilingual semantic parser. |
| Correction/supersession | IMPLEMENTED | Explicit repair supersedes current evidence, invalidates proposals/offered slots and cannot authorize stale write arguments. Final audit adds reverse-order/local-negation cases. |
| TurnCoordinator | IMPLEMENTED | `coordinator.py`: semantic lifecycle, request revision and overlap decisions; acoustic endpoint/turn commit remains framework-owned. |
| ToolOrchestrator | IMPLEMENTED | `orchestrator.py`, `tools.py`: typed plans/results, six-second operation budget, independent business effects, optional concurrent bridges off. |
| OUTCOME_UNKNOWN | IMPLEMENTED | Dispatched uncertain writes remain unknown; no definite outcome narration, retry or duplicate dispatch. Declared backend outcomes now survive slimming. Durable restart reconciliation remains outside this session-local P0 implementation. |
| Stale-read suppression | IMPLEMENTED | Request revision checks before dispatch and before result continuation; installed `StopResponse` removes stale continuation; changed request cannot refresh offered slots. |
| DeliveryIntent | IMPLEMENTED | `delivery/intent.py`: semantic affect/pace/pause constraints with repair/confirmation precedence. |
| PronunciationPlan | IMPLEMENTED | `delivery/pronunciation.py`: offset validation, protected literal values, NORMAL/SPELL/ALIAS/DIGIT_GROUP/PHONEME contract; unsupported phonemes degrade safely. |
| ProviderCapabilities | IMPLEMENTED | `delivery/capabilities.py`: installed model/path/options/version contract; unsupported expressivity fails closed and live_verified remains false. |
| Cartesia renderer | IMPLEMENTED | Shared `renderers.py` compiler, supported Sonic controls isolated to audio; canonical text unchanged. Candidate off. |
| Rime renderer | IMPLEMENTED | Shared compiler; current Arcana path uses plain spelling/punctuation instead of guessed vendor controls. Candidate off. |
| ElevenLabs renderer | IMPLEMENTED | Shared compiler; current Flash 2.5 path retains model/voice/options and safely degrades unsupported controls. Candidate off. |
| Uplift renderer | IMPLEMENTED | Shared Urdu compiler; existing phrase configuration and PCM_22050_16 preserved; strict candidate fixture identity. Candidate off. |
| Canonical plain speech | IMPLEMENTED | `delivery/canonical.py`, Agent hooks and history hygiene: candidate text is normalized before framework history/UI/TTS branching; renderer markup is audio-only. Legacy rollback history is sanitized. |
| Stream-safe normalization | IMPLEMENTED | `StreamSafeNormalizer`: arbitrary transport fragmentation equivalence, syntax lookahead and fail-closed size limit. Candidate off. |
| Protected spans | IMPLEMENTED | `streaming.py`, pronunciation: identifiers/phones/emails/URLs/dates/times/currency and explicit spans are not split at unsafe boundaries. |
| SpeechPlan | IMPLEMENTED | Per framework speech ID/public step: canonical text, planned offsets, intent, pronunciation, provider context, cancellation/history/output references. |
| SpeechChunkPlanner | IMPLEMENTED | Provider-aware sentence/first-clause planning; one in-flight isolated synthesis, finite text limit and local handoff pacing. |
| Generation invalidation | IMPLEMENTED | Invalid plans reject text/chunks/frames, clear owned buffers and cancel only owned synthesis; business tasks remain independent. |
| OverlapCoordinator | IMPLEMENTED | Realized inside the existing TurnCoordinator and Agent STT/recovery hooks; no competing coordinator class. Candidate off. |
| HeardState | IMPLEMENTED | Synchronized text or completed contiguous output chunks only, WebRTC readiness gate, unknown interrupted suffix removed from copied context. Neither synthesis nor playback permission proves human hearing. |
| English profile | IMPLEMENTED | `LanguageProfile`: concise literal-preserving realization/function bank/cooldown; same semantic authority. Candidate realization off. |
| Pakistani Urdu profile | IMPLEMENTED | Urdu script, respectful/gender-neutral wording and literal entities; deterministic fixtures pass, native listening missing. |
| Urdu-English mixed profile | IMPLEMENTED | Mixed profile and fixtures; uses the existing Urdu route, not a new public selectable language. Single-language Gladia does not establish code-switch comprehension. |
| WEBRTC profile | IMPLEMENTED | `ChannelProfile`, SDK readiness messages, worker transport/opening binding. No caller-acoustic evidence. |
| TELEPHONY profile | IMPLEMENTED | Same semantic runtime; acoustic intent/lead differs; explicit SIP metadata only, unknown codec retained as unknown. No route/codec/media proof. |
| Playback readiness | IMPLEMENTED | SDK `audio_ready`/`isAudioReady`, `startAudio`/`audio_blocked`, late-worker request/report exchange; optional opening gate off. |
| Disclosure/greeting state | IMPLEMENTED | `session_opening.py`, `recording_disclosure.py`, `main.py`: disclosure precedes greeting or user-first waiting; failure cannot grant consent; disclosure remains uninterruptible. |
| Greeting/cache compatibility | IMPLEMENTED | Four-provider common candidate delivery; effective acoustic/policy/language/channel/tenant identity, loop-scoped single-flight, finite fills and cloned PCM. |
| Bounded provider failure | IMPLEMENTED | `provider_retries.py`: connection default 5s/no retry, STT hard cap; LLM/TTS 6s useful-progress budget, empty-output failure; terminal outcome without fictitious fallback. |
| Session-close safety | IMPLEMENTED | Required final tool-step playout precedes draining close; business effects/audit preserved, quiet intentional end skips excess transcript wait; existing persistence/quota regressions pass. |
| Telemetry/version/rollback controls | IMPLEMENTED | Secret-free structural snapshots, separate terminal outcomes/percentiles, candidate identities corrected, independent flags/rollback tests. Provider TTFB and diagnostic e2e never labeled FUAW; unplayed/cost precision unknown. |

Framework media endpointing/EOT, pause/resume, interruption buffer clearing, framework tool-task lifetime and room audio output are **REPLACED_BY_FRAMEWORK** responsibilities. The 1.6.5 task-local speech handle bridge is read-only and version-gated. A separate custom audio endpointing/playout state machine is **NOT_APPLICABLE** to this P0 implementation.

## Hard invariants and interaction correctness

| Invariant | Final result | Executed evidence |
| --- | --- | --- |
| No unconfirmed consequential write | PASS | Proposal/separate explicit affirmation/schema/ownership/budget gate and injection harness; no POST before confirmation. |
| No duplicate write from retry/recovery | PASS | Concurrent confirms reserve before await; completed/unknown replay and fresh-proposal refusal; recovery uses tool_choice=none. |
| No wrong write arguments after correction | PASS | Date/time/name/phone grounding, distinct existing/new reschedule date, reverse correction order and corrected doctor argument tests. |
| Known failure cannot become success | PASS | Failure normalization and final declared-outcome matrix overrides contradictory backend success text/flags. Live model narration compliance is unverified. |
| Unknown cannot become definite success/failure | PASS | Timeout/cancellation/declared unknown write retains unknown business effect and truthful summary; one POST/tombstone test. |
| No stale critical reuse | PASS | Superseded/unresolved values do not ground writes; strong evidence cannot be replaced by weak inference. |
| No stale read spoken after changed request | PASS | Revision checks and installed AgentSession stale continuation suppression. |
| No accepted zombie audio after invalidation | PASS | Four-provider installed synthetic framework interruption/late-output tests and invalid-plan acceptance checks. Live wire/flush timing is unverified. |
| No provider markup in canonical history | PASS | Whole/stream/static speech, canonical-history and installed framework tests across all four TTS paths. |
| No false live transfer | PASS | Record-only escalation docstring/result, liveTransfer=false and committed-effect instructions. |
| No cross-session/tenant state leakage | PASS | Per-session reducer/runtime/profile state and cache identity/PCM isolation tests; no new shared business state. Production concurrency remains unverified. |

All requested deterministic interaction cases pass: Friday→Monday; critical ambiguity; separate write confirmation; committed tool completion after interrupted speech; wait/stop/no takeover and supported Urdu equivalents; contextual short backchannels; false-interruption recovery without tool replay/apology; unknown/unheard suffix reconciliation; English/Urdu/mixed; WebRTC/telephony; disclosure/greeting/user-first opening; session close. Principal suites: Batch A–D, runtime/reducer/projection/TurnPlan/shadow tests, write/injection gates, provider/stream/cache/opening/close regressions and the final P0 suite.

No confirmed hard-invariant failure remains in the audited source and executed deterministic scope. These results do not measure acoustic takeover rates, production LLM compliance, actual human receipt or live tenant isolation.

## Current provider coverage

| Layer/provider | Current selectable source path | P0 participation / fresh evidence |
| --- | --- | --- |
| STT Deepgram | English registry + capability gate; Nova-3 default, existing opt-in Flux branch | Shared STT hook/evidence/coordinator; real constructor and synthetic event/provenance tests. No model added/promoted. |
| STT Gladia | English/Urdu registry + enabled capabilities | Same hook/authority; languages=[configured language], code_switching=False. Synthetic confidence fallback is not represented as real evidence. |
| LLM Groq | English registry + enabled capability gate | Existing model resolver, shared LLM hook, business-effect and canonicalization boundaries. Source default openai/gpt-oss-20b; existing aliases/options unchanged. |
| LLM Gemini | English/Urdu registry + enabled capability gate | Existing resolver/options, same shared hooks. Source default gemini-3.6-flash; installed constructor/options tests. Exact deployed effective model remains unverified. |
| TTS Cartesia | English registered/enabled | Current Sonic 3.5/default options through shared candidate compiler/stream hooks; constructor and installed synthetic pipeline/cancellation/history/cache tests. |
| TTS Rime | English registered/enabled | Current Arcana path and existing speaker/speed options through same boundaries; synthetic stream and rollback coverage. |
| TTS ElevenLabs | English registered/enabled | Current Flash 2.5 path; same architecture with unsupported-control degradation and four-provider tests. |
| TTS Uplift | Urdu registered/enabled | Current fixture/live adapter; same semantic/delivery/greeting boundaries and unchanged PCM/account phrase setup. |
| Soniox / Fish | NOT_APPLICABLE — inactive | Modules existing on disk do not make them selectable; absent from registry/capability choices. No integration/promotion claim. |

Registry/capability selectability is verified from current source, not from a deployed tenant catalogue. No new model, vendor ranking or bake-off was introduced. English and Urdu share the architecture; mixed realization does not remove current Gladia input limitations.

## Tests and practical checks

| Check | Final result |
| --- | --- |
| First intended focused suite, prior to audit fixes | 421 passed, zero failures/skips; this green run did not cover the newly reproduced bugs. |
| Final focused suite: prior 27 files + final P0 regressions | **456 passed, 0 failed, 0 skipped**; one existing Starlette warning. |
| Existing intended offline CI manifest | **638 passed, 1 skipped, 0 failed**; five existing warnings. |
| New final P0 cases | 35 passed, included in both final suites; counts overlap. |
| Final write/correction regression bundle | 107 passed; overlaps final suites. |
| Policy identity regression bundle | 86 passed, prior to the final doctor guard; final focused/CI runs supersede it. |
| Additional provider/latency/logging batch | 54 passed, 1 pre-existing mixed-import mock failure; no silent omission. |
| Legacy latency Phase 4 in an isolated process | **14 passed**; resolves the above Deepgram mock conflict. Prior imported real plugin bypassed that test's sys.modules fake; provider runtime was not altered to satisfy a mock. |
| Legacy latency Phase 2 in an isolated process | **9 passed**; its pre-existing Google mocks intentionally remain isolated. |
| Browser SDK | **33 passed**, lint/typecheck and build PASS. |
| Server SDK | **12 passed**, build and lint/typecheck PASS; no server SDK source edits. |
| Scoped Ruff | PASS; existing main.py invalid-noqa warning remains. |
| Graph refresh | Attempted after code edits; existing uv trampoline canonicalization error. No graph available. |

The one offline skip is `test_internal_targets_are_refused_when_hosted[https://127.1/hook]`: the offline DNS/socket guard blocks that nonstandard loopback spelling. It remains an explicitly unverified existing SSRF case. No paid provider sockets were allowed in pytest. Current focused provider tests used configured development fixtures; offline CI forced an empty process DB URL, and no schema/migration was changed. No full-repository Python discovery, global formatter, dashboard build or deployment was claimed.

## Live evidence and activation lanes

Credentials exist for LiveKit, STT/LLM and all four TTS vendors; inherited UPLIFT_MODE/LLM_MODE are live. Credential presence and old audio files are not fresh provider validation. The tested local service/preview ports, including documented 5174, have no listener. No isolated synthetic test tenant, caller-side harness/recording or verified test PSTN destination/route was established.

Existing Cartesia live-listen instructions describe a manually provisioned agent/worker/playground session, not an executable current candidate acoustic smoke. Existing Uplift standalone scripts use legacy Socket.IO/Pipecat, not the installed worker's current candidate renderer/stream pipeline. Running them would not verify this architecture. Other live security scripts are not voice-provider smoke tests. Remote worker health/account permissions/routes/deployed configuration were not verified.

**No paid live provider call, WebRTC call, PSTN call or native listening test was run.** Current provider constructors and installed synthetic framework paths passed; that is implementation evidence only. No unsupported new smoke harness was built.

| Affected lane | IMPLEMENTATION GATE | ACTIVATION GATE | DEFAULT ENABLEMENT |
| --- | --- | --- | --- |
| English WebRTC | PASS | BLOCKED | OFF |
| Pakistani Urdu WebRTC | PASS | BLOCKED | OFF |
| Urdu-English mixed WebRTC | PASS for shared profile/safety; current STT limitation retained | BLOCKED | OFF |
| English telephony | PASS | BLOCKED | OFF |
| Pakistani Urdu telephony | PASS | BLOCKED | OFF |
| Urdu-English mixed telephony | PASS for shared profile/safety; current STT limitation retained | BLOCKED | OFF |
| Cartesia / Rime / ElevenLabs / Uplift candidate rendering/streaming | PASS individually | BLOCKED individually | OFF individually |

Eleven effective settings (master policy, overlap, opening, four renderer and four streaming flags) were checked using inherited environment plus .env.local: all baseline. `natural_v1` remains shadow; clarification and spoken bridge candidates remain off. Mandatory truth/write/failure/cache/close guards and structural diagnostics are on. No persistent setting changed.

## Light performance/regression evidence

Reused `scripts/benchmark_humanization_telemetry.py`; no new research harness. The initial contended run peaked at **3.009 ms p95**, narrowly failing its 3 ms budget while test processes ran. This is preserved in `overhead.json`. An isolated repeat passed, and the final-source isolated run in `overhead-final.json` passed all existing budgets.

| Existing offline telemetry workload | Prior Phase 1 p95 ms | Final p95 ms |
| --- | --- | --- |
| 1 session, room serialization off | 1.379 | 1.615 |
| 1 session, room serialization on | 1.531 | 1.622 |
| 16 synthetic sessions, serialization off | 2.068 | 1.788 |
| 16 synthetic sessions, serialization on | 2.494 | 1.947 |

Final added observer cost: **0.407 microseconds/frame** over 100,000 synthetic frames, below 10 microseconds/frame; maximum payload **4,664 bytes**, below 14,000 bytes. This covers local telemetry/event/serialization/log-format work, not whole-runtime/provider/DB load or real room transport. Small host-sensitive p95 differences do not establish acoustic improvement/regression.

- **First-response timing:** live comparable baseline/candidate unavailable; original metrics artifact has zero runtime samples. Provider TTFB/server e2e are diagnostic proxies.
- **Chunk delay:** deterministic stream property/protected-boundary/backpressure tests pass; chunk_wait/local-gap instrumentation exists, but no paired live samples. Conservative EOS waits and fresh per-chunk provider shells can add startup/connection delay.
- **Interruptions:** deterministic invalidation, takeover, backchannel and recovery regressions pass; caller-observed audible stop unavailable.
- **Startup/opening:** cache single-flight/cold-hit/miss/readiness/disclosure/close contracts pass; no comparable audible cold/warm matrix.
- **Provider error rate:** bounded timeout/empty/error injection passes; no measured live baseline/candidate error rate.
- **Speculative/wasted synthesis:** structural synthesis/rejection counts exist; true unplayed audio, invoice cost and acoustic benefit unavailable. Provider TTFB is not FUAW.
- **Caller-acoustic FUAW is unavailable.** No timing values were substituted for it.

## Intentional deferrals and remaining risks

| Original work | Final classification |
| --- | --- |
| Phase 12 LiveKit upgrade | INTENTIONALLY DEFERRED |
| Phase 13 provider/model bake-offs | INTENTIONALLY DEFERRED |
| Phase 14 richer affect, automatic fallback, sophisticated pronunciation/adaptive interruption | INTENTIONALLY DEFERRED |
| Phase 15 P2/full duplex/learned or social experiments | INTENTIONALLY DEFERRED |
| Phase 16 production canary/promotion | NOT_APPLICABLE to this audit; explicitly not started |

Remaining activation requirements: current isolated live provider/WebRTC/PSTN smoke and recordings; matched baseline/candidate caller-acoustic timing and flush evidence; native Pakistani Urdu/mixed listening and STT comprehension; live model tool-truth/prompt compliance; exact deployed model/voice/options/codec/routes; long-call/state drift; full worker/DB/provider concurrency; persistence/reconciliation across crash/restart; measured reliability, variable cost and synthesis waste.

Prompt sentence-budget conflict, persona sharing the platform role and possible Groq compaction fact loss remain recorded barriers to promoting the general natural_v1/TurnPlan prompt policy. That policy stays shadow/off. Deterministic critical parsing is intentionally narrow; unrepresented doctor identities now fail closed through the existing service argument, and no general doctor-ID or natural-language entity resolver is claimed. Full state/audit/active model context can grow on long calls; the local telemetry benchmark is not a 10–20-minute multilingual runtime or production load trial. Mandatory safety tests do not guarantee a live model's narration or human comprehension.

Independent rollback paths remain and are tested. No deployment/canary or Phase 12–15 work was started. **STOP after this final audit.**
