# Persona implementation audit - 2026-10-21

## Result

IMPLEMENTATION GATE: PASS for the scoped implementation and checks below.
ACTIVATION GATE: NOT VERIFIED. No real provider synthesis, browser audio,
PSTN call, human listening score, deployment or production activation was performed.
This report does not guarantee identical sound or zero defects across providers.

## Reviewed paths

- Agents SDK create/update -> signed `llm_options.humanization` -> shared
  portal/machine validation -> existing tenant-scoped query persistence.
- WebRTC and both telephony directions -> fresh `build_session` config load ->
  session-local policy/profile -> LLM preamble and delivery/streaming context.
- Gemini/OpenAI-compatible Groq request serialization, tenant DATA separation,
  full conversational persona retention and plain canonical history.
- Static/generated opening, neutral recording disclosure, actual question
  inflection, bounded contextual concern and native base-speed adaptation.
- Greeting-cache producer/consumer identity includes the profile. Renderer version
  changes invalidate old rendered audio. Inputs remain isolated from shared clients.
- Client prompt controls, inbound number's assigned-agent controls, outbound-agent
  instructions, save/reset/reload/dirty/live-session lock behavior and installed SDK.
- The client still sends only the public connection contract during mint; profile
  changes go through its backend Agents SDK, never tenant secrets in browser code.

## Verification

| Check | Result |
| --- | --- |
| Full affected Python regression | 682 passed, 7 skipped with external connections disabled |
| Final persona suite after cue refinement | 62 passed; overlaps the regression suite |
| Agents SDK | 17 passed, TypeScript build passed |
| Client backend after final audit fix | 39 passed |
| Client frontend interactions | 26 passed |
| Client TypeScript and production build | PASS; final responsive layout build also passed |
| Package provenance | PASS: exact pinned archive SHA-512, published Voice/Telephony registry provenance, compiled SDK equals installed SDK |
| Scoped Ruff | PASS; existing invalid-noqa warning remains in main.py |
| CRLF-aware tracked diff whitespace | PASS |
| Browser visual/audio verification | Unavailable: tool inventory returned no apps or browsers |
| Graphify refresh | Attempted in and outside sandbox; existing uv trampoline canonicalization error |

The focused suites include all 13 selectable language/provider combinations using
the installed framework with synthetic model/audio output, three entry-channel
session-builder paths, profile validation, opt-out, cache isolation, adaptive pace,
disclosure protection and profile preservation during provider changes. Their
success is not live provider or caller-heard evidence.

## Issues found and resolved during the audit

1. Dirty persona changes were blocked by submit logic but Start still appeared
   enabled. The visible button state and reset/input updates now agree with the guard.
2. Direct agent construction could lose the runtime's telephony channel. Its
   delivery context now inherits that channel; production builder coverage checks it.
3. Sparse/empty replacement profiles could be treated as unchanged by the client
   pipeline optimization. Comparison now uses normalized defaults and stored-profile
   presence, so an empty replacement reliably disables an enabled profile.
4. The prior total prompt-size test failed identically on unchanged HEAD: 6,428
   characters before and after this work. It now bounds the voice overlays separately
   from the mandatory platform safety/closing preamble; no safety text was removed.
5. Adaptive ElevenLabs pace is clamped to the installed plugin's documented range.
6. Profile settings, renderer version and installed preview integrity are covered
   so old greeting audio/package code cannot masquerade as the new implementation.

## Remaining operational requirements

The client's ignored backend configuration points at hosted staging. Deploy the
updated tenant API and run a fresh matching worker on that staging dispatch before
saving/enabling profiles there. Restart the local client backend after installing
the preview. No database migration, Voice SDK publication, phone routing change,
credential change, environment-file edit or shared-worker restart was made.

The 7 skipped regression cases remain environment/live-dependent checks; they are
not counted as successful verification. The existing Vite bundle-size warning also
remains. Unrelated pre-existing portal/membership/dashboard work was left intact.

## Acoustic limits

The implementation uses verified integration controls and natural wording; it does
not synthesize artificial pitch modulation or invent emotion controls for Uplift
or Arcana. The shared persona should be evaluated with the exact chosen voice,
model and transport. Native Urdu/mixed listening and caller-side recordings remain
required before making naturalness, prosody, latency or interruption claims.

Primary provider references consulted:
- [Cartesia voice controls](https://docs.cartesia.ai/build-with-cartesia/capability-guides/volume-speed-emotion)
- [ElevenLabs streaming protocol differences](https://elevenlabs.io/docs/eleven-api/guides/how-to/websockets/tts-vs-ttd-websockets)
- [Rime contextual expression](https://www.rime.ai/resources/introducing-arcana)
- [Uplift TTS API](https://docs.upliftai.org/orator)

See [SDK settings and activation](HUMANIZATION_PERSONA_SDK.md) for usage.
