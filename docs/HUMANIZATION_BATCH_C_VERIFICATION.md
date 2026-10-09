# Fast-track Chat C — original Phase 7 P0

Date: 2026-10-09. Branch `main`, HEAD `c37fd73fd7bce0766496d7068c49d400f1c36e17` unchanged.
Actual checkout: `C:\Users\habiba\Desktop\SDK\sdk-agent`; configured `habib` path is absent.

STATUS: **CODE_COMPLETE_ACTIVATION_BLOCKED**.
IMPLEMENTATION GATE: **PASS** for the requested P0 scope.
ACTIVATION GATE: **BLOCKED** for every provider/language/channel lane.
DEFAULT ENABLEMENT: **OFF**. Both renderer and streaming settings were verified as `baseline` for all four providers in the inherited environment / `.env.local`. No persistent environment configuration was changed.

## Behavior and rollback

Before: Batch B joined the complete LLM utterance for canonicalization, then joined the complete TTS input before synthesis. The original framework/provider path remained available when renderers were disabled.

After, only on the explicit candidate: streamed canonical text reaches history/UI before provider rendering; a conservative planner feeds one isolated synthesis chunk at a time. Provider text is never fed back into canonical history. Static `session.say()` text is also normalized on its transcription branch before framework history/UI commit. The candidate uses the existing provider adapters, models, voices and audio formats.

Each provider has an independent `UVA_TTS_STREAMING_<PROVIDER>=streaming_v1` switch. It requires that provider's existing `UVA_TTS_RENDERER_<PROVIDER>=delivery_v1` switch. Missing or `baseline` streaming settings retain Batch B complete-utterance synthesis; renderer `baseline` retains the original framework/provider path. `natural_v1` does not enable either switch. Unknown policies or unaudited framework/plugin versions fail closed. No switch was activated for real callers.

## P0 implementation

- `StreamSafeNormalizer` only transforms stable source prefixes. It preserves inter-fragment whitespace and keeps unresolved tags, brackets, links and spelling constructs pending; it also checks malformed syntax exposed by cleanup. Whole-text canonicalization retains its previous default semantics. No forced flush of partial syntax.
- Protected spans cover phones, emails, URLs, numeric/textual dates, times, money/decimals, codes/IDs, spaced/dotted/hyphenated spelling, explicit pronunciation overrides and complete/partial provider controls. Renderer pronunciation offsets are shifted for the exact canonical chunk.
- Planner selects a complete short response at EOS, a stable first clause when supported, complete sentences, and the final remainder. It waits for punctuation with lookahead and never splits solely by length or LLM token arrival. Cartesia permits a first clause; Rime and ElevenLabs prefer sentences; Uplift permits a suitable first Urdu comma/semicolon clause and otherwise sentences. No shared character-size policy.
- `SpeechPlan` tracks speech ID plus public step number (matching LiveKit generation trace identity), canonical text, planned chunk offsets, DeliveryIntent, PronunciationPlan, model/path/language/channel context, cancellation and structural timing/output counters. Public `chat_items` IDs are captured as handle-level history references; completed framework playout retains those references separately. These are not word ranges or acoustic heard evidence; heard reference remains unknown. Active plans are retained until handle completion; recent session-local plans are bounded.
- Invalidation checks the bound handle before every text/chunk/audio acceptance. A public interruption waiter clears normalizer/planner buffers and cancels only the synthesis task. Isolated provider streams/plugins close in explicit `finally` blocks. Old provider frames remain bound to the old plan and are rejected after invalidation. Framework cancellation/output-buffer clearing remains authoritative. Tool IDs, argument JSON, usage, tool revisions and business-effect authority remain separate and unchanged.
- Backpressure is deliberately basic: one synthesis chunk in flight; accepted audio is paced against elapsed local time with a provisional 2,000 ms handoff allowance. The stock framework has an unbounded audio channel, so sequential text feeding alone would not bound that channel. This estimate does not measure caller playback, sink queue depth or speculative audio before playback authorization. One provider request can internally buffer audio; its remote buffer is not measured. Runaway text fails closed at 32,768 characters rather than splitting an entity.
- Structural terminal logs include `streaming_policy_version`, `generation_id`, first-useful-text-to-chunk wait, local inter-chunk frame gap, lead estimate, observed synthesized/rejected duration and synthesized duration belonging to cancelled generations. The latter is potential waste, not exact unplayed duration. Provider-internal unconsumed audio, true wasted duration and caller-heard latency remain unknown. No transcript/provider text is logged; existing room latency fields are not relabeled as caller-heard timing.

## Provider paths verified

| Provider | Offline evidence | Preserved feed/configuration |
| --- | --- | --- |
| Cartesia | Actual installed constructor and streaming entry, synthetic incremental AgentSession and interruption/closure | Sonic 3.5, current adapter/tokenizer, existing native streaming; no continuation experiment |
| Rime | Actual installed constructor and streaming entry, synthetic incremental AgentSession and interruption/closure | Arcana/current voice, WebSocket, `segment=immediate`; no segmentation change |
| ElevenLabs | Actual installed constructor and streaming entry, synthetic incremental AgentSession and interruption/closure | Flash 2.5, `auto_mode=True`, current voice/settings; no chunk schedule or v4/TTD migration |
| Uplift | Actual installed live constructor/streaming entry with synthetic emission; existing fixture adapter regression; Urdu/mixed synthetic AgentSession and interruption/closure | Planned Urdu/mixed phrases/sentences; downstream existing tokenizer; `PCM_22050_16` and phrase configuration preserved |

Streaming-entry tests replace provider network/emission with synthetic audio while exercising installed TTS/SynthesizeStream construction, input acceptance, stream lifetime and close behavior. They do not prove wire packets, paid synthesis, acoustic output or service-side cancellation. Existing source was traced for Cartesia's tokenizer/continuation loop, Rime's segmentation/send/flush, ElevenLabs' auto-mode tokenizer/flush, and Uplift's collect-then-synthesize segments.

## Tests run

- Initial normalization/protection properties: **35 passed**, after resolving partial control syntax.
- Initial new tests plus directly affected Batch B contracts: **121 passed**, zero skips/failures.
- Final targeted `tests/test_humanization_batch_c.py`: **60 passed**, zero skips/failures. Includes arbitrary single/random/character boundaries on 17 English/Urdu/mixed/entity/syntax cases, a seeded 4,000-case malformed-composition property, deterministic planner, protected spans, explicit pronunciation offsets, provider gates/rollback, installed stream entries, incremental pre-EOS framework feeding, canonical history, tool identity/usage, interruption/late output, business-task isolation and handoff pacing.
- **One focused regression suite: 319 passed**, zero skips/failures. Exact paths below. This includes the final targeted cases; counts are not additive.
- Post-audit directly affected new/Batch B suites: **146 passed**, zero skips/failures, after closing the static-speech transcription/history gap. This includes all 60 new tests and verifies static history/playout references for each provider. Counts overlap with the focused suite.
- Scoped Ruff: **PASS**. UTF-8, original line endings and scoped trailing-whitespace checks: **PASS**.
- Integrity snapshot: all 711 captured existing files preserved except five intended paths. Prior unrelated dirty changes/deletions preserved; no dependency/lockfile edits.
- Required `graphify update .` attempted once: existing `uv trampoline failed to canonicalize script path` error; graph refresh unavailable.

Focused regression command:

```powershell
python -m pytest tests/test_humanization_batch_a.py tests/test_humanization_batch_b.py tests/test_humanization_batch_c.py tests/test_humanization_gap_fixes_e2e.py tests/test_humanization_phase4.py tests/test_humanization_phase5.py tests/test_humanization_phase6.py tests/test_humanization_phase7.py tests/test_humanization_observability_framework.py tests/test_humanization_phase2_framework.py tests/test_cartesia_tts.py tests/test_cartesia_tts_options.py tests/test_rime_tts.py tests/test_rime_tts_options.py tests/test_elevenlabs_tts.py tests/test_write_tool_gate.py tests/test_injection_write_gate.py tests/test_greeting_cache.py tests/test_latency_phase3.py -q --junitxml=tmp/humanization-batch-c-20261009/focused-regression.xml
```

Evidence: ignored `tmp/humanization-batch-c-20261009/`, including before-edit copies, preflight hashes, JUnit and final integrity report. Paid provider sockets remain blocked by the existing offline test harness. No full repository suite was run for this batch.

## Files and limits

Existing files changed: `worker/humanization/agent.py`, `worker/humanization/delivery/canonical.py`, `worker/humanization/delivery/context.py`, `tests/ci_unit_manifest.txt`, `docs/HUMANIZATION_IMPLEMENTATION_STATUS.md`.
New files: `worker/humanization/streaming.py`, `tests/test_humanization_batch_c.py`, this report.

Files read: complete implementation-status ledger and AGENTS.md; requested universal invariants, original Phase 7 and final execution/gate sections; current Awaaz hooks, runtime/state cancellation interfaces, canonical/delivery policy/capabilities/pronunciation/render/context, spoken dispatch/plain/Cartesia sanitizers, provider adapters and relevant options, current main TTS extras, directly relevant tests/framework helpers, CI manifest, and exact installed LiveKit Agent default TTS node, speech-handle/activity/generation and four provider TTS sources. No full research-master read or broad repository exploration.

The one task-local handle lookup uses installed `_SpeechHandleContextVar`: public `session.current_speech` represents playback and can identify the wrong handle for queued/preemptive nodes. This small read-only bridge is pinned to audited agents/plugins 1.6.5 and fails closed on unknown versions. Public interruption waiting/completion and ordinary provider close own all other lifecycle operations. No dependency upgrade or framework patch.

Chunk synthesis currently owns a fresh plugin shell per chunk, as Batch B did per utterance. Connection overhead, long text without punctuation, malformed syntax held until EOS, lead threshold and real prosody need live evaluation. This intentionally avoids advanced continuation, learned chunking, provider bake-offs and deeper provider optimization.

UNVERIFIED LIVE/AUDIO ITEMS: paid provider wire/acoustic behavior and deployed configuration; paired baseline/candidate English/Urdu/mixed recordings; caller-side WebRTC/PSTN first useful audio and barge-in stop; native Urdu/mixed intelligibility/prosody; real playback lead and wasted duration; long calls, concurrency, cold/warm connection cost, remote cancellation/flush guarantees, deployment and billing impact. No live call, carrier route change or deployment occurred. Missing evidence blocks audible activation even though implementation passes.

Scope audit: no business-write authority changes, second LLM/network planner, client policy, adaptive interruption, new HeardState inference, transport/codec experiment, voice/model migration or Phase 8 work.

NEXT SAFE EXECUTION UNIT: stop after original Phase 7 P0. Further implementation or live activation needs its separately requested scope/evidence. **Phase 8 NOT STARTED.**
