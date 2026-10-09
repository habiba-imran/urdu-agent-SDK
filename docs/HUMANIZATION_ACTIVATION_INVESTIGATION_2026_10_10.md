# Live humanization activation and naturalness investigation — 2026-10-10

**Outcome: incorrect/stale local activation is proven; controlled live A/B is BLOCKED. No naturalness improvement or degradation has been scored.**

This is a focused investigation with one provenance instrumentation change and isolated test preparation. It does not start Phases 12–15, change provider models/voices/dependencies, restart a shared worker, or alter production defaults.

## Actual connection and running worker evidence

Initial branch `main`, HEAD `a3515768400c48be7a60e70dcd0df0a55ebd4993` (committed October 9, 19:55:52 PKT). The prior farewell/identity/transcription fixes remain uncommitted, alongside the pre-existing usage ledger edit. All those edits were preserved.

The independent browser's configured session endpoint is `http://localhost:3100`. The running backend proxies to `https://uva-control-plane-staging-dsyy.onrender.com` and `https://uva-tenant-portal-staging.onrender.com`. The browser joins LiveKit project `urdu-voice-agent-sdk-22to3tyc.livekit.cloud`; neither a cloud URL nor npm snapshot version identifies its media worker. See `client-integration-test/backend/src/config.js`, `createApp.js` and frontend `envDefaults`.

A local Python worker is running from this checkout: Python process **3392**, parent **8028**, `python -m worker.main dev`, started **2026-10-09 23:03:18 PKT**. Its real LiveKit health endpoint `/worker` identifies **`uva-staging-agent`**, SDK **1.6.5**; its environment points at the same LiveKit project. This is a shared staging dispatch name, not an isolated A/B worker. Read-only process-environment inspection exposed only explicitly allowed feature flags and the project hostname; credentials and tenant metadata were never output or persisted.

**The exact worker serving the two historical calls remains UNKNOWN.** They have no session/room/worker IDs or matching job logs. The LiveKit project currently has **zero active rooms**, so no active session/dispatch can be correlated. The local worker can serve cloud rooms dispatched to its name, but that does not prove it handled either historical call or rule out another remote worker. The client's wall-clock log formatter uses UTC (`main.ts:1155`); its pasted time-of-day lacks the calendar date. Do not compare those times as PKT or assume a call date.

**Freshness is not established.** The current local process predates changes to `cartesia_spoken_output.py`, `latency.py`, `main.py` and the Agent regression fixes. These prompt/latency modules are imported by `worker.main` at startup. Installed `.venv/Lib/site-packages/livekit/agents/cli/_legacy.py:1772` explicitly says Python `dev` mode no longer performs in-process hot reload. Consequently its startup-loaded prompt/telemetry code is stale. A lazily imported module could have a different load time; no blanket loaded-Agent hash is claimed. The latest fixes are not in Git HEAD and were not deployed/restarted by this investigation. Remote build/configuration remains unverified; GitHub CI/deploy hook definitions do not prove a running deployment.

## Real running configuration versus requested configuration

| Control | Captured current local process value/effective result | Historical call value |
| --- | --- | --- |
| Master policy | Unset → `baseline`, behavior disabled | UNKNOWN |
| Cartesia renderer / streaming | Both unset → baseline | UNKNOWN; logged markup is consistent with legacy manual SSML |
| Rime renderer / streaming | Both unset → baseline | UNKNOWN |
| ElevenLabs renderer / streaming | Both unset → baseline | UNKNOWN |
| Uplift renderer / streaming | Both unset → baseline | UNKNOWN |
| Overlap / opening | Both unset → baseline | UNKNOWN |
| Room stage metrics | `UVA_PUBLISH_TURN_LATENCY` unset → OFF | UNKNOWN; client received none |
| Uplift mode | `live` | No Uplift call supplied |
| Worker dispatch name | `uva-staging-agent` | UNKNOWN |

This is evidence from the **running local process**, not just `.env.local` or a new test shell. It does not substitute for a serving-session snapshot. `policy.py` accepts baseline/natural_v1_shadow/natural_v1; natural_v1 resolves to shadow with behavior off. Renderer flags accept exactly baseline/delivery_v1. Streaming accepts baseline/streaming_v1 and requires selected delivery_v1 plus agents/selected plugin **1.6.5**. Rime native streaming also requires its compatible WebSocket path; Uplift fixture mode is not live synthesis. No live flag was changed.

A read-only request through the running client's authenticated tenant backend found its configured **Demo App Agent** and confirms:

- English, Deepgram `nova-3`, Groq `openai/gpt-oss-20b`, Cartesia internal voice `cartesia-sonic-default`; all provider option maps empty; agent speaks first and has a static greeting.
- Persona exactly matches the existing minimal calm-demo/short-replies template (53 characters). No service facts, workflow details, or automatic empathy classifier are provided by that persona. Raw tenant prompt was not published.
- `recording_enabled=false`. Local env policy can separately permit capture; hosted persistence requires agent opt-in, job permission, required disclosure and granted consent. Those session-specific recording prerequisites have not been established or changed.
- Tenant API presently exposes all four intended TTS providers as enabled: Cartesia/Rime/ElevenLabs for English, Uplift for Urdu. Soniox/Fish are not in that selectable matrix.

These are current **configured agent** fields, not proof of the historical provider requests. Expected local TTS constructor defaults are Sonic-3.5, Arcana, Eleven Flash v2.5 and the existing Uplift path. Actual serving-session model, vendor voice translation, account support and per-worker overrides still require the session snapshot. No new model/voice was selected.

## What can actually change the audio

| Path/component | Active effect and limits in current source |
| --- | --- |
| ConversationState/InputUnderstanding | Per-session critical facts, repair and committed business truth. Normal user text does not automatically supply complaint/frustration/simple-answer signals. Not an affect engine. |
| TurnPlan | General plan/context projection remains shadow. Mandatory CLOSE/IDENTIFY_AI and critical truth/repair checks are separate existing exceptions. Ordinary turns commonly remain ANSWER/neutral empathy. |
| LLM prompt | Candidate renderer replaces provider-specific legacy delivery prompt with plain speech instructions; Agent adds affect/intensity/pace wording guidance. General question/response budget from the full projection is not activated. Tenant persona and universal “quick answer plus a short question” rules still influence repetitive phrasing. |
| Canonical text | Removes delivery syntax and protects literal facts; it does not rewrite generic dialogue or create natural intonation. Candidate renderer-only LLM text is buffered until tool boundary/EOS; streaming_v1 emits stable normalized fragments. |
| DeliveryIntent | Maps existing plan to warm/help, concerned/repair, reassuring/supportive and pace. Ordinary turns default warm/normal. Pause/emphasis plans are empty unless explicitly supplied; energy/intensity are not independently converted to vendor audio controls. |
| Cartesia renderer | Sonic-3 English can receive `<emotion>` and supported speed/pause/spelling controls. Ordinary warm maps to content. Baseline already requests emotion tags from the LLM, so candidate is not an automatic gain in expressive range. A standalone concern without a supplied complaint signal still maps to content in the local probe. |
| Rime renderer | Current Arcana capabilities deliberately do not enable emotion, speed or native spell direction without account proof. Ordinary speech remains plain; affect/pace degrade to wording/punctuation. Existing Arcana default speed_alpha=1.1 is retained. |
| ElevenLabs renderer | Current Flash path has speed/VoiceSettings support, no emotion/nonverbal tag realization here. Default ordinary pace leaves existing stability=.5, similarity=.75, style=.25, speed=1, speaker boost=false unchanged. Repair can reduce speed. |
| Uplift renderer | No local affect/speed/pause control. Canonical Urdu wording, literal pronunciation and optional existing account phrase replacement remain the mechanisms. Fixture audio is not live evidence. |
| SpeechChunkPlanner | Protected sentence boundaries and conservative first-clause rules; single short replies often wait for EOS. No acoustic boundary optimizer. This affects feed timing, not voice identity. |
| Provider connection continuity | `delivery/context.py:61,83` creates a new plugin/stream per planned chunk and closes it in finally. A continuity ID does not reuse a connection/provider context. Extra setup and intonation resets are a **proven mechanism**, but their audible harm/latency magnitude is an unmeasured hypothesis. |
| Playback/overlap | Native LiveKit owns output/cancellation. Optional overlap/opening candidates are baseline in the captured process. Output readiness or synthesized chunks do not prove hearing. |
| STT/turn timing | Current Groq turn profile explicitly disables preemptive generation/TTS. Supplied logs show split finals and long user-final→speaker proxies; they cannot establish stage attribution or acoustic lag. No STT/provider/model tuning was performed. |

Relevant sources: `worker/humanization/runtime.py:145`, `turn_plan.py:59,130`, `context_projection.py`, `agent.py:78,183,259,313`, `spoken.py:tts_overlay_for`, `delivery/intent.py`, `delivery/capabilities.py`, `delivery/renderers.py:80`, `delivery/context.py:61,83`, `streaming.py:21,180`, `humanization/turn.py:build_turn_profile`.

## Controlled baseline/candidate preparation and available evidence

[Independent A/B operator guide](../client-integration-test/HUMANIZATION_AB.md) supplies the exact isolated process-local recipe and seven fixed conversation steps: greeting, service question, follow-up, correction, concern, interruption, goodbye. The initial pair keeps master/overlap/opening/native STT/LLM/model/voice fixed and changes only the selected TTS renderer/streaming bundle. Other providers remain baseline. It does not activate general natural_v1 or create a research harness.

| Provider | Planned language/model/voice condition | A baseline | B delivery_v1 + streaming_v1 | Audio/listening verdict |
| --- | --- | --- | --- | --- |
| Cartesia | en / existing Sonic-3.5 default / current Cartesia default voice | Recipe verified; live pair not run | Resolvers/compile verified; not registered/activated | NOT ASSESSED |
| Rime | en / existing Arcana / fixed existing selectable Arcana voice | Recipe verified; live pair not run | Resolvers/compile verified; not registered/activated | NOT ASSESSED |
| ElevenLabs | en / existing Flash v2.5 / fixed existing selectable voice | Recipe verified; live pair not run | Resolvers/compile verified; not registered/activated | NOT ASSESSED |
| Uplift | Pakistani Urdu / existing Uplift / fixed existing selectable Urdu voice, existing live mode | Recipe verified; live pair not run | Resolvers/compile verified; not registered/activated | NOT ASSESSED |

Reused existing renderer, normalizer, planner and configuration classes for **28 offline compile probes** (seven synthetic utterances per provider), without model/provider calls. All four candidate streaming prerequisites resolve in the pinned local environment. Candidate prompts remove the legacy Cartesia emotion requirement. Ordinary constructor settings are unchanged for the four probes; Cartesia adds its renderer emotion tag, while Rime/ElevenLabs/Uplift ordinary provider text remains the canonical wording. Concern probes remain ANSWER/neutral empathy; no hypothetical complaint signal was silently supplied. Service answers create two planned chunks, while short follow-ups wait for the terminal remainder/short-reply path. These are structural findings, not executed conversations, baseline acoustic pairs or listening scores. The probe voice is explicitly a non-synthesized placeholder; actual voice identity was not simulated.

No new live A/B audio, recordings, provider calls, paid synthesis, turn metrics, caller-heard timing or listening scores were collected. Existing older fixture/smoke WAV files are not comparable pairs. Read-only LiveKit/API/process preflight is real infrastructure evidence; synthetic compilation/tests are separate. Human-like rhythm, pauses, intonation, expressivity, pronunciation, audible chunk gaps, interruption performance and voice identity remain **NOT ASSESSED**. **Caller-heard FUAW is unavailable.** Provider TTFB, server stage clocks and active-speaker proxies are not substitutes.

## Minimum missing infrastructure and stop boundary

The browser frontend and authenticated backend are available. What is still missing/unchecked is:

1. Explicit reservation of a dedicated test tenant/agent, plus a uniquely named dispatch path shared by its isolated control plane and a freshly started test worker. The discovered demo name does not prove exclusive isolation. Adding a unique worker name while the client still mints through shared staging is insufficient.
2. Matching worker/job/session artifacts from the call. No active room was available and historical IDs/logs were not provided. Do not restart or toggle the shared `uva-staging-agent` just because it is currently idle.
3. A human browser audio operator/listener (native Pakistani Urdu where appropriate) and approved recording/disclosure/consent configuration if preserving audio. This environment has no callable browser/audio automation tool, and the current agent's recording flag is off.

The user was asked for the reserved test-agent ID and worker launch/deployment/log location while investigation continued; no verified isolated target was established. Therefore live A/B stops before paid calls or unsafe activation, as explicitly requested.

## Minimal instrumentation change

`worker/telemetry.py:46` adds public job provenance: worker ID, job ID, dispatch name, process ID and `humanization_p0_20261010_activation_observation_v1`. `worker/main.py:1410` adds that allowlisted object to the existing per-session `providerSnapshot` before configuration logging/room telemetry. It serializes neither credentials nor job/tenant metadata. Missing context remains null. The marker identifies this instrumentation revision, not a cryptographic attestation of every module or an npm release.

Existing session wiring already logs effective configuration and publication status; `UVA_PUBLISH_TURN_LATENCY=1` is prepared **only for the isolated worker**. It remains off in the existing shared worker. SDK full metrics/debug JSON will retain the new worker object without a package/schema upgrade. Source changes here are limited to these two existing modules plus one provenance regression in `tests/test_humanization_observability.py`; documentation/test profiles are the remaining additions.

Validation: **118 passed** in one focused observability/framework/live-regression/final-P0 bundle; scoped Ruff PASS with an existing invalid-noqa warning in main.py. The required graph refresh was attempted but remains blocked by the existing `uv trampoline failed to canonicalize script path` tooling error. The 28 compile probes made no provider requests. No deployment or activation result is inferred from these checks. Secret-free local artifacts: `tmp/humanization-activation-20261010/running-worker-preflight.json`, `client-agent-preflight.json`, `profiles.json`, `offline-renderer-probes.json`, `instrumentation.xml`.

## Ranked next work

1. **Correct activation/freshness first — proven problem.** Use the reserved isolated route, restart from the current source, verify worker/job provenance and effective settings, then capture the matched Cartesia pair on the existing voice/model. The current local worker is baseline with stale startup-loaded modules. This is the highest-confidence explanation for no candidate effect in its calls.
2. **Make the existing conversational guidance reach ordinary turns — proven limitation, perceived benefit unmeasured.** A small bounded task should populate the existing concern/frustration signal and avoid mandatory/repeated follow-up wording, with a per-turn hint under current truth rules. Do not globally promote the full natural_v1 projection while its authority/compaction blockers remain. The renderer cannot express nuanced concern from a plan that stays neutral/warm, and the inspected persona supplies no service facts.
3. **Check/fix per-generation stream continuity — proven reinitialization, acoustic consequence unmeasured.** If the B recording/metrics show resets or gaps, reuse a compatible provider stream across that SpeechPlan's chunks while preserving invalidation, writes and playout boundaries. Scope the first corrective task to the existing Cartesia candidate, not a provider/model/framework upgrade. Renderer-only EOS buffering and conservative chunk boundaries must be measured separately from provider startup.

Provider/voice limitations remain a separate constraint: Arcana/Uplift lack verified controls here; Eleven Flash affect relies on wording. Unsupported intents can be functionally identical without implying a broken API or justifying a model migration. STT split finals and turn delays need the opted-in stage records before choosing a timing fix.

**Recommended next small task:** establish the unique isolated dispatch route and run one instrumented, human-listened Cartesia A/B with the current model/voice and seven steps. For the first speech-code implementation after that evidence, wire the existing concern signal/wording hint, or prioritize stream continuity only if the recording proves gaps. Do not start a new emotion engine or Phase 12–15. Production/shared-worker defaults remain unchanged. **STOP after this investigation and supported preflight.**
