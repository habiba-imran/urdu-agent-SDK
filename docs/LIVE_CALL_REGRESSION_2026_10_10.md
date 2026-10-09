# Targeted live-call regression investigation — 2026-10-10

Scope: the two supplied English WebRTC client logs, pipeline `en/deepgram/groq/cartesia`, client snapshot `@awaazlabs-uva/voice@1.1.1-humanization.0`. Startup optimization was explicitly excluded by the user. No LiveKit upgrade, provider/model change, bake-off, production rollout or unrelated refactor.

## Diagnosis and evidence limits

**Farewell/refusal:** before this fix, `worker/humanization/turn_plan.py` had no closing or AI identity act; `HumanizationRuntime.understand_turn` derived the ordinary plan without conversational signals. `worker/humanization/agent.py:78` delegated these ordinary responses to the configured LLM. `worker/tools.py:74` only saved a summary and closed after the model chose `end_conversation_summary`; it did not produce a farewell. Source searches found neither reported refusal nor the “team members” claim as an explicit worker fallback/guardrail. The only prompt refusal rule, `worker/cartesia_spoken_output.py:26`, concerns requests for system instructions. The supplied logs show streamed refusal words followed by disconnects, with no SDK errors.

This establishes a missing platform conversational guarantee in the inspected source. The visible refusals are consistent with generated model content, rather than a literal information-refusal fallback. It does **not** establish why the remote model selected these words, whether the deployed worker matches this checkout, or what tenant persona/context it received. The logs lack session/room IDs, call-time worker configuration, tool events, effective prompt and raw LLM result. The existing `docs/last_session_prompt.txt` is dated September 18 and is not evidence of these two calls. Do not attribute the exact refusal to secrecy, persona injection or context corruption without those missing artifacts.

**AI identity:** the platform prompt previously lacked explicit truthful identification, while `worker/humanization/spoken.py` discouraged “As an AI” as filler. The tenant persona has a separate framed system slot in `worker/main.py`; general TurnPlan prompt activation remains shadow. These are source-confirmed omissions/conflicts, not proof of the actual call-time persona. Direct identity responses are now platform-owned and cannot be replaced by the model claiming to be human.

**Markup:** the baseline Cartesia prompt requires `<emotion>` and allows `<break>/<spell>`. Before the fix, baseline `AwaazAgent.transcription_node` passed text to the framework unchanged, while completed history was cleaned later. Incomplete markup such as `<emotion` therefore crossed the partial-transcription boundary. `worker/humanization/agent.py:459` now uses the existing `StreamSafeNormalizer` on the independently teed transcription stream for baseline and candidates. Provider TTS feeds retain their delivery syntax; canonical UI/history do not contain it.

**Metrics:** `worker/latency.py:41` explicitly defaults `UVA_PUBLISH_TURN_LATENCY` OFF. Publication is gated independently of humanization. Existing SDK decoding and the client subscribe to `turn_latency` and `metrics_updated` correctly (`sdk/src/index.ts:786`, `client-integration-test/frontend/src/main.ts:700`). The new session-wiring log at `worker/latency.py:1185` reports publication status and the existing allowlisted effective provider/policy snapshot; `worker/main.py` now includes explicit baseline renderer/pronunciation/streaming identities. No secrets, personas or transcripts are added to this log. The test-worker opt-in is documented in `client-integration-test/PLATFORM_TESTING.md`.

## Corrective behavior

- Existing TurnPlan gains `CLOSE` and `IDENTIFY_AI` for conservative explicit farewell and direct identity inputs. English, Pakistani Urdu and common Roman Urdu farewells are supported. A whole-utterance match avoids hanging up on farewell words inside another request.
- Existing AwaazAgent produces a short plain farewell or truthful AI statement. Closing uses the existing native speech/tool pipeline and `end_conversation_summary`, its required playout wait, and `shutdown(drain=True)`. No new closing state machine or business tool authority is introduced.
- Special responses still pass through the common candidate renderer, streaming, generation and tool-observation boundaries. A closing-tool continuation produces no second farewell or refusal. Empty intentional platform continuations are not misclassified as provider failures.
- Existing write confirmation, committed/outcome-unknown truth, noncancellable tool ownership, recording-disclosure and provider-failure guards remain authoritative. The deterministic closing summary is a minimal lifecycle note; no model-generated business outcome is invented.

## Effective configuration

Verified current inherited environment plus `.env.local`, without printing secrets:

| Control | Current local effective value |
| --- | --- |
| Humanization policy requested/effective | `baseline` / `baseline` |
| Cartesia/Rime/ElevenLabs/Uplift renderer | All `baseline` |
| Cartesia/Rime/ElevenLabs/Uplift streaming | All `baseline` |
| Overlap | `baseline` |
| Opening | `baseline` |
| Room turn metrics | OFF (`UVA_PUBLISH_TURN_LATENCY` unset) |

No persistent settings were changed. Natural-v1 remains shadow if requested. Mandatory conversational truth/exit fixes run in baseline as well as candidates. The call logs' Cartesia markup is consistent with the legacy manual-SSML path; a packaged SDK label does not enable worker candidates. **The exact historical remote policy/settings remain UNKNOWN**, including per-agent provider options and native preemption/interruption overrides. Capture the new configuration log from the worker serving the next call to establish them.

For isolated test-worker diagnostics, set `$env:UVA_PUBLISH_TURN_LATENCY = '1'` in its launch terminal and restart that worker. The frontend cannot enable this server flag. Production defaults stay OFF.

## Validation

- Targeted suite: **43 passed**, `tests/test_live_call_regressions.py`; offline installed LiveKit AgentSession with synthetic audio/providers. Covers all three requested English farewells, Urdu/Roman Urdu closing, direct AI/human questions, refusal avoidance, no hang-up on a question mentioning goodbye, committed write truth, disclosure/final playout/close ordering, markup-free partial text and history, retained baseline TTS markup, explicit room telemetry on/off, and all four candidate renderers with streaming ON/OFF.
- Final focused suite: **523 passed**, one existing Starlette warning, 33 test modules. Includes the intended focused P0 selection, the new targeted suite and relevant prompt/publication suites. English/Urdu/mixed, WebRTC/telephony profiles, write confirmation/correction, tool outcomes, cancellation, provider options/failure, greeting/opening/disclosure and session close contracts pass.
- Browser SDK: **33 passed** in six files, including telemetry decoding/publication compatibility. SDK source and server SDK are unchanged; no TS build claim is needed for these worker/doc changes.
- Scoped Ruff and `git diff --check`: PASS.
- Required `graphify update .` attempted; existing `uv trampoline failed to canonicalize script path` prevents graph refresh. No graph existed at initial inspection.
- Local JUnit evidence: `tmp/live-call-regressions/targeted.xml` and `focused.xml`. Counts overlap and must not be added.

## Performance and live gaps

The supplied proxies include 8,119 ms after the first services request, 4,552 ms after a split design request, and 3,398/3,859 ms on farewells. Some STT utterances have back-to-back finals. These logs cannot allocate those delays between STT endpointing, interrupted/restarted generation, LLM, TTS or transport. Closing/identity now avoid a remote LLM request, but no live latency improvement is claimed. Startup timing was left untouched.

No post-fix live call, acoustic/provider listening, deployed worker verification, or caller-heard FUAW measurement was performed. **FUAW is unavailable**; provider TTFB and active-speaker proxies are not substitutes. The next test must use the updated worker and room telemetry opt-in, then verify English WebRTC farewell/AI/partials and retain matching worker logs. Urdu, candidate providers, telephony and real aligned-transcription/playout behavior still require live verification. Existing summary persistence/provider failure conditions retain their original bounded behavior and are not proof of a live successful close.

## Exact files changed

- `worker/cartesia_spoken_output.py` — authoritative closing/identity/business-truth prompt rules.
- `worker/humanization/spoken.py` — truthful identity exception to filler wording.
- `worker/humanization/turn_plan.py` — existing planner acts, strict conversational signals and localized short responses.
- `worker/humanization/runtime.py` — derive those acts from committed turns.
- `worker/humanization/agent.py` — deterministic acts through existing speech/lifecycle pipeline; stream-safe canonical transcription.
- `worker/main.py` — explicit baseline renderer/pronunciation/streaming snapshot fields.
- `worker/latency.py` — session-wiring publication/effective-configuration log.
- `tests/test_live_call_regressions.py` — regression evidence.
- `client-integration-test/PLATFORM_TESTING.md` — existing test-worker telemetry opt-in instructions.
- `docs/LIVE_CALL_REGRESSION_2026_10_10.md` — this report.
- `docs/HUMANIZATION_IMPLEMENTATION_STATUS.md` — targeted closeout entry.

The pre-existing dirty `state/usage_ledger.json` was preserved and is outside this fix. No GitHub push/deployment or production canary was performed for this targeted task. Stop after this fix; original Phases 12–15 remain intentionally deferred.
