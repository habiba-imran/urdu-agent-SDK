# Humanization client testing

## Which client build to test

The published browser SDK `@awaazlabs-uva/voice@1.1.0` supports the baseline integration. The independent `client-integration-test/` folder includes an **unpublished** `1.1.1-humanization.0` package snapshot with the current playback-readiness handshake and telemetry. Copy its whole folder, including `packages/`, and install using its lockfiles. Dashboard Test Studio builds against the current repository SDK.

A GitHub push does not update npm, start a worker, apply migrations, or activate candidate policies. The browser never chooses internal humanization versions in the mint body.

## Before making calls

- Use an isolated test tenant and dedicated test agent. Pipeline changes update the chosen agent, including future phone calls using it.
- Match the publishable key, host endpoints and exact allowed origins. Keep HMAC and provider/Telnyx credentials on the backend/platform.
- Confirm the control plane, tenant API, worker, LiveKit and selected provider are available. Check the capability endpoint for selectable providers.
- Keep baseline settings for the first pass. An operator may enable candidates on an isolated test worker; record effective component versions and restart it before comparing runs.
- In the browser, distinguish room connection from playback readiness. Click `startAudio()` through an Unlock/Enable audio button when blocked. Playback ready proves browser readiness, not that the caller heard a particular word.

## Language and channel matrix

| Lane | How to test |
| --- | --- |
| English WebRTC | English test agent, normal browser call through your own host |
| Pakistani Urdu WebRTC | Urdu test agent, native Urdu speech and listening |
| Urdu-English mixed WebRTC | Existing Urdu agent route; alternate Urdu/English entities, names and terms |
| English telephony | Existing English test phone route, inbound or explicitly initiated outbound |
| Pakistani Urdu telephony | Existing Urdu test phone route with native listening |
| Urdu-English mixed telephony | Existing Urdu route, mixed turns over the phone |

There is no separate public mixed-language enum. Gladia's current single-language configuration is a known limitation. Current STT paths are Deepgram/Gladia; LLM paths Groq/Gemini; TTS paths Cartesia/Rime/ElevenLabs for English and Uplift for Urdu. Fish/Soniox are not selectable. Use the current capabilities and voice catalog rather than guessed model or voice IDs.

## Interaction checks

| Scenario | Required result |
| --- | --- |
| Friday → Monday; Monday, not Friday | Final proposal and confirmed write use Monday; Friday is superseded |
| Ambiguous critical date, phone, email, name or doctor | Clarification before a consequential write; no guessed value |
| Write confirmation | Proposal first, explicit confirmation before commit; correction requires the current arguments |
| Tool finishes while speech is interrupted | Result remains business truth; speech interruption does not repeat or undo the write |
| Wait, stop, no; Urdu equivalents | Yield appropriately; do not treat stop as a harmless backchannel |
| Short backchannel | Avoid unnecessary takeover when context supports continuing |
| False interruption | Resume/recover without duplicating tools or inventing an apology |
| Interrupted assistant suffix | Unheard suffix is not treated as heard or as caller confirmation |
| Known failure or OUTCOME_UNKNOWN | No spoken success for failure; unknown remains uncertain, never a definite result |
| Opening/disclosure | Required disclosure and greeting follow configuration; no duplicate greeting; test blocked playback and user-first opening |
| Session close | Required final speech completes where applicable; no accepted late audio after close |
| Separate tenants/sessions | No critical values, effects, transcript or selected agent bleed between sessions |

Use a synthetic sandbox backend for write/unknown/retry fault cases. Do not deliberately trigger real bookings, purchases or transfers as a fault-injection substitute. Test greetings cold/warm and each intended TTS provider with real listening. A live transfer must only be described as connected when the actual route proves it.

## Record evidence accurately

Record agent ID, session/call ID, language, channel, provider/model/voice, effective policy/component versions, timestamps, outcome, and the expected/observed interaction. Retain permitted recordings and compare matched baseline/candidate runs. Copy the independent client's diagnostics and inspect dashboard Sessions for status/transcript and Telephony for call outcomes. For write arguments and OUTCOME_UNKNOWN, also inspect the sandbox backend's actual side effects; transcript alone is insufficient.

`turn_latency` also reaches `metrics_updated` for compatibility. Process per-turn events only in `turn_latency`; process aggregates only when `metrics.type === 'metrics_updated'`. Keep interrupted/cancelled/provider-error outcomes out of completed-turn latency summaries.

Worker e2e, LLM TTFT, TTS TTFB and browser active-speaker signals are timing proxies. They are **not caller-acoustic FUAW**. FUAW remains unavailable without a caller-side acoustic measurement. Track startup, chunk gaps, interruptions, errors and synthesis waste only when the corresponding evidence exists.

## Current gate

P0 implementation is verified; activation remains blocked pending real provider/audio, browser/phone and native Urdu/mixed evidence. Candidate audible policies default off. A baseline call passing does not activate or prove the candidate path. LiveKit upgrades, model/provider bake-offs, advanced P1 and P2/full duplex remain intentionally deferred. This checklist is for testing, not a production canary rollout.
