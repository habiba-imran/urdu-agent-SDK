# Humanization Phase 0 baseline

Captured 2026-10-08 against `main`, HEAD `c37fd73fd7bce0766496d7068c49d400f1c36e17`. Phase 0 implementation gate: **PASS**. Phase 0 activation gate: **NOT_APPLICABLE** because this phase changes no runtime or audible behavior. Comparable live baselines are unavailable; later audible activation is **BLOCKED** for English, Pakistani Urdu and mixed speech on WebRTC and PSTN. Phase 1 has not begun.

The complete `HUMANIZATION_IMPLEMENTATION_PLAN_CODEX.md` was read before implementation. This report applies its Phase 0A–0J requirements only. The plan's named design source, `docs/HUMANIZATION_RESEARCH_MASTER.md`, is absent from this checkout and could not be read. Phase 0 has no hard dependency and requires no audible design decision; the executable runtime still matches its architectural invariant. Restore/resolve that missing design source before subsequent design-dependent implementation.

## 0A — Repository and environment

HEAD equals the codebase-context reference. The tree was already dirty; the full initial short status and SHA-256 of every tracked/non-ignored untracked file are in the local `repository-runtime.json`. Existing deletions remain deleted. Existing worker, portal, dashboard, telephony, tests, migration and documentation edits were preserved. `source-integrity.json` verifies all pre-existing paths against that capture, including lockfiles and untracked work. No dependency, model, voice, environment, database or production source was changed.

Only four versioned additions belong to this execution: this report, `HUMANIZATION_IMPLEMENTATION_STATUS.md`, `tests/fixtures/humanization/README.md` and `tests/fixtures/humanization/corpus.v1.json`. Generated evidence and helper scripts remain under ignored `tmp/`.

| Runtime/distribution | Resolved version |
| --- | --- |
| Host Python | 3.12.10 |
| Node / npm | v24.12.0 / 11.6.2 |
| `livekit` (RTC distribution, not `livekit-rtc`) | 1.1.13 |
| `livekit-agents` | 1.6.5 |
| `livekit-api` / `livekit-protocol` | 1.2.0 / 1.1.22 |
| `livekit-plugins-cartesia`, `deepgram`, `elevenlabs`, `fishaudio`, `gladia`, `google`, `groq`, `openai`, `rime`, `silero`, `upliftai` | each 1.6.5 |
| `livekit-blingfire` / `livekit-local-inference` | 1.1.0 / 0.2.7 |

The repository `.venv` launcher is unhealthy: `pyvenv.cfg` refers to the old `C:\Users\habib\...Python312` installation. Checks used the existing Python 3.12.10 host executable at `C:\Users\habiba\AppData\Local\Programs\Python\Python312\python.exe`, with the existing `.venv/Lib/site-packages` and repository root inserted by a local runner. No installation or upgrade occurred. Installed metadata, constructor/hook signatures and selected installed-source hashes are frozen in the bundle. Node 24 differs from CI's Node 20; these are local checks, not reproduction on CI Node 20.

`graphify-out/graph.json` and `graphify-out/wiki/index.md` did not exist, so the conditional initial graph query/navigation did not apply. `graphify update .` was attempted after additions, but the installed executable failed with `error: uv trampoline failed to canonicalize script path` (exit 1). It created no graph. No launcher repair, graph bootstrap or install was attempted.

## 0B — Current executable path

1. **Session creation:** `worker/main.py` receives the LiveKit job, resolves tenant/agent/session identity from dispatch, room/session data and telephony attributes, loads cached agent configuration, resolves the external provider voice ID, and constructs providers through `worker/providers/registry.py`. Configuration/cache keys include relevant endpointing options; telephony keeps configured Urdu/Uplift and selectable English providers. Verified caller identity is distinct from trunk/service numbers. Database/dispatch operation was traced in source, not exercised live.
2. **Agent and prompt:** `build_agent()` constructs the standard LiveKit `Agent`. There is no platform subclass owning all four planned hooks. Instructions combine the base safety/tool rules, gateway discipline, universal dialogue guidance, LLM, Urdu and TTS overlays, and language directive. Persona is framed as untrusted data in chat context; Groq compaction has a 3,000-character ceiling. The base 2–3-sentence guidance and universal 1–2-sentence guidance coexist; resolving this belongs to later prompt work.
3. **Turns and interruptions:** `build_session()` uses `build_turn_profile()` and `AgentSession(turn_handling=...)`, local Silero VAD, provider connection options and `use_tts_aligned_transcript=False`. STT commits and framework interruption are the baseline. Optional force-flush handlers suppress flushing during the opening; local VAD remains default. Current receipt/takeover handling is heuristic, not the planned TurnCoordinator/overlap intent state machine.
4. **Tools and safety:** gateway tools call `_post_client_tool()`. Consequential tools still use the deterministic propose → later user turn → confirm → write gate. It validates tenant/agent ownership, proposed argument identity, confirmation identity and idempotency; pending proposals expire after 300 seconds, completed writes can replay safely, and the write budget is five. No path was weakened. Framework tool-lifecycle timing and wrapper timing both exist, so possible double counting remains a baseline observation for Phase 1. Gateway exceptions/timeouts currently return an error-shaped result without a distinct unknown-write-outcome model; this phase makes no repair or passing safety claim for that gap. `escalate_to_human` records a follow-up request; it does not transfer a call.
5. **Spoken output:** provider-specific sanitizers are passed through the public TTS text-transform boundary. Cartesia manual markup, Rime normalization and plain ElevenLabs/Uplift output remain provider-owned by the worker. No new pronunciation, renderer, chunking or expressivity behavior was added.
6. **Opening and closing:** static greeting PCM uses cache/single-flight synthesis with a five-second bound; session startup may prewarm STT before an interruptible greeting. Generated openings, user-first waiting and recording disclosure follow separate paths. Closing drains the session, sanitizes the best-effort transcript, ends session/telephony rows, releases quota and persists usage/summary/recording artifacts under existing policy. Failures are stage-labelled and best-effort; live close/persistence is unverified.
7. **History and client:** the history helper strips provider markup and truncates `session.history` to 48 items. Framework agent chat context is a separate surface; this does not prove a bounded active LLM context or complete long-call transcript. The browser SDK owns transport, microphone processing, audio attach/unlock and metrics forwarding. The server SDK owns backend API signing and agent operations. No humanization policy was moved into either SDK.

Current `e2eMs` is a diagnostic combination of stage proxies, emitted with TTS metric completion; it is not speech-end-to-first-useful-audible-word latency. Existing aggregation does not establish the plan's bounded outcome-specific p50/p95/p99. No measured caller latency is claimed.

### Files read

The mandatory minimum was read, including the current dirty versions:

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

Supplemental recon covered the plan and codebase context; `AGENTS.md`; `pytest.ini`, `tests/conftest.py`, `tests/ci_unit_manifest.txt`, `scripts/run_ci_unit.py`; requirements, package manifests, Makefile and CI workflow; LLM/provider resolution and validation/default call sites; Cartesia/Rime/ElevenLabs option resolvers; spoken sanitizers and output overlays; recording policy, transcript logging and prompt dump; current humanization/latency safety and opening tests; `client-integration-test/README.md`, `telephony/README.md`, `tests/test_e2e.py` and `tests/test_urdu_pstn_uplift_e2e.py`; and exact installed versus tagged upstream Agent/session/activity/turn/events/tool-executor/text-transform/ElevenLabs source. Recon preceded fixture/document implementation; production sources were never edited.

## 0C–0D — Fresh verification

Commands were derived from manifests, the context's exact 23-file list and the CI runner. Local logs, focused JUnit and machine-readable command/result summaries are in the bundle.

| Check | Result |
| --- | --- |
| Exact focused 23-file Python suite | **185 passed, 0 skipped, 0 failed**, 1 warning; 24.81 s |
| Repository offline CI unit manifest | **293 passed, 1 skipped, 0 failed**, 5 warnings; 76.70 s |
| Isolated investigation of broader-suite skip | 19 passed, 1 skipped; 0.22 s |
| Browser SDK build / lint / tests | PASS; 26 tests in four files |
| Server SDK lint / build / tests | PASS; 12 tests in four suites |
| Telephony SDK lint / build / phase8 smoke / phase9 contract | PASS |
| Dashboard lint / typecheck / Next build | PASS |
| Repository Ruff check | **Pre-existing baseline failure**, exit 1; 24 errors |
| Repository Ruff format check | **Pre-existing baseline failure**, exit 1; 130 would reformat, 163 already formatted |
| `git diff --check` | **Pre-existing baseline failure**, native Git exit 2; whitespace findings in unchanged `tenant_portal_api/app.py` |
| Whitespace/UTF-8 validation of the four new files | PASS |
| Corpus structure, IDs, coverage and safety-reference validation | PASS; 30 scenarios, 18 categories |
| Original-path/hash preservation and new-file scope | PASS; `source-integrity.json` |

Focused warning: FastAPI/Starlette `httpx` TestClient deprecation. Broader warnings add four short **test-only** JWT HMAC-key warnings. No dependency remediation was performed.

The broader skip is `test_internal_targets_are_refused_when_hosted[https://127.1/hook]` in `tests/test_wave2_ssrf.py`. `tests/conftest.py:197` converts a failed case after one offline-blocked connection/DNS attempt into a skip. That individual case is **unverified**, not a passing SSRF test. The isolated `-rs` run documents this reason. The focused suite has no skips. The repository CI runner forces offline mode, clears the DB URL, supplies a harmless test encryption key if needed and runs its manifest with `-m "not live"`; conftest can skip blocked network/credential-dependent cases. These checks do not prove providers, DB/RLS, browser audio or PSTN.

Ruff findings are frozen in `ruff-check.log`, including undefined `concurrent` in `control_plane/app.py`, unused imports/locals and a duplicate test definition; `worker/main.py` also has an invalid existing `noqa` warning. `git diff --check` also reports existing trailing whitespace in the pre-existing portal edit; the four new files pass their own whitespace/UTF-8 check. File-integrity verification proves the failing source tree was not introduced by Phase 0. No broad formatter or lint autofix ran. Overall repository lint remains red even though the Phase 0 implementation gate passes.

The dashboard's package build contains an install step. The existing CI-style direct `node_modules/.bin/next.cmd build` was used instead, with no install or lockfile change. Its `lint` and `typecheck` both run `tsc --noEmit`. No separate configured Python type checker was found. The full database-backed `make gate`, unmanifested/live suites and deployment checks were not run; an isolated DB and actual runtime test lane were not established.

The focused list is preserved in `focused-suite.txt`:

```text
test_humanization_phase1.py through test_humanization_phase7.py
test_humanization_gap_fixes_e2e.py
test_latency_phase1.py through test_latency_phase4.py
test_cartesia_tts_options.py
test_cartesia_spoken_sanitize.py
test_rime_tts_options.py
test_rime_spoken_sanitize.py
test_rime_spoken_output.py
test_prompt_compact.py
test_greeting_cache.py
test_session_opening.py
test_provider_retries.py
test_start_path_cache.py
test_fl6_turn_latency_publish.py
```

These existing test filenames refer to earlier humanization work. Running them does not implement any phase of the new plan.

## 0E — Secret-free configuration freeze

`provider-defaults.json` records fresh-process source resolution with behavior overrides unset. `provider-config.json` records process + `.env.local` precedence used by worker startup, without constructing networked providers. No tenant/agent row, production configuration or deployed session was read. Voices in resolver snapshots are synthetic placeholders; actual chosen voices/options must be captured per live run.

| Surface | Source baseline | Locally configured resolution / qualification |
| --- | --- | --- |
| English create/reference providers | Deepgram Nova-3 → Groq `openai/gpt-oss-20b` → Cartesia `sonic-3.5` | Actual agent rows can select supported alternatives |
| Urdu providers | Gladia `default` → Gemini `gemini-3.6-flash` → Uplift | Gemini legacy model IDs are remapped; server SDK legacy create field is not effective runtime model proof |
| Turn / endpoint min–max | STT / 0.12–1.2 s | Same resolved profiles |
| Interruption | VAD; minimum WebRTC 0.65 s / telephony 0.55 s | Adaptive remains opt-in; no native intent evidence |
| False interruption | timeout 0.6 s, resume false | Same |
| Uninterruptible input discard | WebRTC true / telephony false | Same |
| Force barge flush | WebRTC off / telephony on | Same; suppressed during opening |
| Preemptive LLM/TTS | Groq off, zero retries; other profiles on, WebRTC 3 / telephony 2 retries, max speech 12 s | Same |
| Deepgram mode / endpoint | Nova / 100 ms; Flux/eager opt-in | Nova / **200 ms** locally; eager thresholds unavailable (`null`) |
| Provider retry options | max_retry 1, interval 1 s, timeout 30 s | Same; Groq SDK max retries separately zero |
| VAD | speech 0.12 s, silence 0.32 s, prefix 0.32 s, activation 0.45 | Same |
| Cartesia | manual SSML, speed 0.95, PCM 16 kHz both channels | Expressive constructor gate false on installed source |
| Rime | Arcana, WebSocket, immediate segments, speed_alpha 1.1 | 16 kHz WebRTC / 8 kHz telephony; stale Coda commentary is not runtime truth |
| ElevenLabs | `eleven_flash_v2_5`, auto mode, plain text, SSML off, text normalization off | Voice settings stability .5 / similarity .75 / style .25 / speed 1 / speaker boost false; newer dialogue gate false |
| Uplift | Fixture; cache miss fails, no silent live fallback | **Live** locally; live/record PCM 22,050 Hz; phrase config resolved absent, file fallback opt-in only |
| History / greeting | 48 session-history items / interruptible | Same; separate active chat context caveat above |
| Transcript log / prompt dump / room latency publish | Off / off / off | Resolved privacy flags and override-presence booleans in snapshot |

Groq uses low reasoning with default completion cap 96 and timeout 30 s. Gemini uses default minimal thinking, temperature .35, completion cap 180 and timeout 30 s. Gladia's default single-language configuration disables code switching; mixed-language corpus entries are evaluation targets, not supported-quality claims. Turn detector default is off. Uplift phrase IDs and environment secret values are never copied into evidence.

The plan's generic baseline descriptions are therefore qualified by actual local endpointing/Uplift overrides, model remapping, distinct history surfaces and the absent design master. No incompatible architecture was found; all differences are frozen rather than repaired.

## 0F — Live evidence availability

Presence-only checks found configured LiveKit, STT/LLM/TTS and database credential variables. Presence does not establish valid credentials, healthy services or an isolated test tenant. `TELNYX_API_KEY` is absent from this local process; existing tenant-encrypted credentials/routes may still exist and were not queried. PSTN route availability is **unknown**, not asserted absent.

No listeners were found on the documented/local test ports 3000, 3001, 3100, 5173, 5174, 8000, 8001, 8002, 8080 or 8787. The manual client-integration app requires running platform services, tenant credentials/origin configuration, microphone and audio unlock. No active caller-side corpus/acoustic harness, confirmed isolated synthetic tenant, PSTN destination or native Urdu reviewer was established. Consequently **no English WebRTC, Urdu WebRTC or PSTN baseline call was captured**. Remote service/worker health is unverified. No number purchase, tenant route change or real customer call was made to manufacture this evidence.

The existing Urdu/PSTN “E2E” test checks in-process provider/prompt/sanitizer behavior. The legacy `test_e2e.py` synthesizes/transcribes Urdu against a different product-agent/tools/real-DB path; it is not this worker's WebRTC/PSTN baseline. Existing Uplift smoke WAVs lack comparable corpus/current-run provenance and are not reused as baseline media.

All runtime and acoustic metrics are `null` with reasons in `metrics.json`. Audio/transcript artifact lists are empty. Existing recording policy distinguishes recorder start from persistence; persistence requires granted consent and an allowed recorder. Transcript logging and prompt dumping are opt-in. Future baseline media must follow the existing recording/consent/retention policy and stay out of committed fixtures.

## 0G–0H — Fixed corpus and reproducible evidence

Corpus **1.0.0**, policy **baseline**, SHA-256:

```text
d9ab900428d857a5ffe85ac1420cb66af387943aa1968167d1dba89a2c78a6e4
```

Thirty stable IDs (`HUM-EN-001`–`018`, `HUM-UR-001`–`008`, `HUM-MIX-001`–`004`) cover all 18 categories. Authored semantic references include retained/superseded entities, required clarification, write counts, unknown-outcome constraints, stale-read suppression, one-word takeover, backchannels, disclosure/opening and long-call recipes. All names, dates, contacts, business facts and fake-tool outcomes are synthetic. Reference labels are provisional expectations, not observed baseline success or native-listener approval. Urdu/mixed wording and gender/register fit remain pending native review.

The corpus README freezes scoring meaning, hard safety failures, caller-acoustic versus diagnostic timing, paired environment/config capture, human review fields and corpus version/fingerprint rules. Long-call recipes require actual expansion, duration and execution before claiming long-call evidence. This is a corpus **structure**, not a new runtime, simulator or Phase 1 telemetry implementation.

Local bundle location (git-ignored):

```text
C:\Users\habiba\Desktop\SDK\sdk-agent\tmp\humanization-phase0-20261008\
```

It contains `repository-runtime.json`, `source-integrity.json`, default/config snapshots, credential-presence booleans, installed API signatures, `focused-suite.txt`, focused JUnit/log, all check logs, `test-results.json`, corpus validation/fingerprint and an exact corpus copy, `metrics.json`, `runtime-evidence.json`, upstream tagged sources/URLs/hashes/diffs, reproduction helper scripts and `manifest.json` with artifact hashes. Its local README contains replay commands. Preserve this directory before deleting ignored temporary files; committed reports and corpus do not substitute for the original logs and dirty-source hashes. Fresh reruns must use a new dated output location and current preflight, not overwrite this freeze.

## 0I — Early upstream reconnaissance, no upgrade

As inspected on 2026-10-08, the latest Python release was **1.8.5**, published October 6, commit `76de175`. It adds conversation/span correlation and tool-name/input tracing, fixes fallback usage accounting and ElevenLabs connection/timeouts. These notes identify future compatibility checks; they do not prove equivalent behavior locally. [Official 1.8.5 release](https://github.com/livekit/agents/releases/tag/livekit-agents%401.8.5)

The preceding 1.8.4 release lists ElevenLabs v4 support, read-only chat protection and streaming replacement fixes. [Official 1.8.4 release](https://github.com/livekit/agents/releases/tag/livekit-agents%401.8.4)

The bundle compares exact installed source with eight tagged 1.8.5 source files, without importing/installing upstream. Source/API deltas support these scoped findings:

| Topic | Finding and later-phase implication |
| --- | --- |
| Agent hooks | The four planned hooks retain their argument boundaries and delegation through `Agent.default`. New expressive and model surfaces exist. Build around public hooks and retest before Phase 12; do not subclass private activity machinery. [Tagged Agent source](https://github.com/livekit/agents/blob/livekit-agents%401.8.5/livekit-agents/livekit/agents/voice/agent.py) |
| Text transforms | Callable async transform entry remains. `replace()` changes to single-pass, longest-match replacement with key-prefix holdback across chunks, so timing/text results can differ. Preserve chunk/sanitizer contract tests. [Tagged transforms](https://github.com/livekit/agents/blob/livekit-agents%401.8.5/livekit-agents/livekit/agents/voice/transcription/text_transforms.py) |
| Adaptive interruption | Turn config schemas largely persist, but activity overlap handling and false-interruption timing change; upstream defers false classification while a turn decision is pending. Do not rely on private timers/VAD boundary state; one-word and receipt tests still need acoustic evidence. [Tagged activity source](https://github.com/livekit/agents/blob/livekit-agents%401.8.5/livekit-agents/livekit/agents/voice/agent_activity.py) |
| Tool events / async tools | `tool_execution_updated.update` discriminator types persist in both versions. Batch outputs change from optional entries to output objects with per-output `reply_required`; RunContext/run ownership and duplicate matching also change. Async progress/result/cancellation and application idempotency must be retested; framework duplicate handling cannot replace the write gate. [Tagged events](https://github.com/livekit/agents/blob/livekit-agents%401.8.5/livekit-agents/livekit/agents/voice/events.py), [tool executor](https://github.com/livekit/agents/blob/livekit-agents%401.8.5/livekit-agents/livekit/agents/voice/tool_executor.py) |
| Alignment / transcription | Upstream adds a user-transcription-timeout event and aligned-transcript fallback to spoken text when no timings arrive. Existing local alignment is explicitly disabled; speech timing, transcript completeness and playout continuity require contracts, not an upgrade assumption. [Tagged activity source](https://github.com/livekit/agents/blob/livekit-agents%401.8.5/livekit-agents/livekit/agents/voice/agent_activity.py) |
| ElevenLabs | Tagged plugin routes newer v3/v4 models through text-to-dialogue and exposes alignment configuration. Installed plain Flash path has no such capability. Constructor/signature gates may resolve differently after upgrade; do not implicitly activate expressive/model changes. [Tagged ElevenLabs source](https://github.com/livekit/agents/blob/livekit-agents%401.8.5/livekit-plugins/livekit-plugins-elevenlabs/livekit/plugins/elevenlabs/tts.py) |
| Metrics / tracing | `metrics_collected` remains but is deprecated upstream in favor of session usage and per-turn ChatMessage metrics; trace correlation/privacy surfaces grow. Preserve compatibility, single timing ownership and diagnostic/acoustic distinction. [Tagged session source](https://github.com/livekit/agents/blob/livekit-agents%401.8.5/livekit-agents/livekit/agents/voice/agent_session.py) |

This is early conflict reconnaissance, not an exhaustive upgrade audit or migration. Dependencies and lockfiles remain untouched. Actual upgrade work stays in Phase 12.

## 0J — Exit gate and required completion report

| Implementation gate requirement | Evidence / result |
| --- | --- |
| Repository state and exact versions captured | Runtime snapshot and source hashes — PASS |
| Focused tests restored; failures explained | 185 passed, no skips/failures; broader skip and pre-existing Ruff failures explained — PASS |
| Fixed corpus structure | Version 1.0.0; 30 IDs / 18 categories; validated — PASS |
| Baseline artifact location | Ignored local bundle and hash manifest — PASS |
| No production behavior change | Original-path integrity verification, only four new docs/fixture files — PASS |
| Source differences and architectural path traced | 0B/0E/0F, missing master/environment/history/model qualifications — PASS |
| Safety/write gate preserved | Source trace, existing focused + CI write-gate/injection tests, unchanged hashes — PASS |
| Early upgrade recon | Tagged source comparison and 0I — PASS |
| Implementation-status ledger | `HUMANIZATION_IMPLEMENTATION_STATUS.md` — PASS |

```text
PHASE / SUBPHASE: Phase 0A–0J — Repository Re-verification and Baseline Freeze
STATUS: PASS

FILES READ: Mandatory and supplemental inventory in 0B; complete implementation plan; installed/upstream source recon.
FILES CHANGED: No pre-existing/versioned production files changed.
NEW FILES: This report; docs/HUMANIZATION_IMPLEMENTATION_STATUS.md; tests/fixtures/humanization/README.md; tests/fixtures/humanization/corpus.v1.json. Generated bundle is ignored local evidence only.
TESTS RUN: Exact 23-file focused suite; broader offline CI manifest; isolated skip investigation; repository Ruff check/format; browser/server/telephony SDK checks; dashboard lint/typecheck/build; corpus and source-integrity verification.
TEST RESULT: Focused 185/0 skipped/0 failed; broader 293/1 skipped/0 failed; isolated 19/1 skipped; browser 26 and server 12 passed; other package/build/corpus/integrity checks passed. Pre-existing Ruff 24 errors/130 format findings and portal diff whitespace remain.

BEHAVIOR BEFORE: Standard worker-owned streaming Agent path and existing deterministic write gate; no frozen new-plan corpus/ledger.
BEHAVIOR AFTER: Same runtime/audible behavior; versioned synthetic corpus, evidence freeze and continuity ledger added.

FEATURE FLAGS / POLICY VERSIONS: Evidence policy baseline; corpus 1.0.0; no runtime policy identity or new feature flag implemented.
DEFAULT ENABLEMENT: OFF for new humanization candidates; existing behavior/flags untouched.
KNOWN LIMITATIONS: Missing research master; broken venv and graphify launchers; Node 24 rather than CI 20; pre-existing Ruff failures; one explained offline SSRF skip; local ignored bundle must be preserved; authored/native-unreviewed reference labels.
RUNTIME ITEMS STILL UNVERIFIED: Valid provider credentials/deployed settings, live English/Urdu WebRTC and PSTN, caller-acoustic latency/interruption, native Urdu/mixed quality, recording/DB close persistence, long-call/concurrency/cost and later activation gates.

IMPLEMENTATION GATE: PASS
ACTIVATION GATE: NOT_APPLICABLE for Phase 0; later audible lanes BLOCKED, candidates OFF until comparable live baselines exist.
NEXT SAFE PHASE / SUBPHASE: Phase 1, only on a separate explicit request with fresh preflight and the missing design source resolved as needed. Phase 1 has not begun.
```
