# Speech persona: SDK implementation and activation

The saved profile lives in `agents.llm_options.humanization`, an existing JSONB
column. The shared portal/machine validator accepts only bounded enums and
booleans; no schema, RLS, credentials, provider/model registry or phone routing
changes are required. Provider-specific LLM sampling options remain unsupported.

Use Agents SDK `humanization` on create/update. This replaces the profile, not
individual nested fields. Omit it to preserve settings; use `enabled:false` to
disable. The defaults when enabled are warm, balanced formality/energy, normal
pace, subtle expression and adaptive pace enabled. Unknown fields fail before
the write. An empty profile is disabled. Existing agents without a profile retain
the legacy environment-controlled behavior.

## End-to-end flow

1. Client controls send preferences to the host backend, which signs an Agents
   SDK update. Tenant secrets remain on that backend.
2. The existing agent API saves the validated profile in its normal tenant-scoped
   update. Changing providers without supplying llmOptions preserves the profile.
3. Web tests, inbound calls and outbound calls all reach `worker.main.build_session`.
   It bypasses the configuration cache for each new session and reads the saved
   profile. Active calls keep their existing profile.
4. Enabled profiles select conversational guidance and the selected TTS provider's
   renderer/streaming policy per session, without modifying process environment.
5. Enum-derived persona guidance reaches the first trusted LLM preamble on both
   Gemini and Groq. Tenant character/business prose remains separately quoted DATA.
   Full persona text is retained on the conversational Groq path.
6. Delivery uses the stable persona plus current turn cues. Concern persists for
   one relevant follow-up; clarification/confirmation remain deliberate. Native
   pace can scale the configured base when adaptivePace is enabled. Actual questions
   receive curious Cartesia delivery, without random emotion rotation.
7. The recording disclosure keeps neutral delivery. The opening waits for existing
   browser/SIP playback readiness when the profile is enabled. Canonical transcripts
   stay free of provider markup. Profile/policy changes invalidate greeting audio.

## Provider coverage and limits

English: both Gladia/Deepgram STT, both Gemini/Groq LLM and all three
Cartesia/ElevenLabs/Rime TTS providers (12 combinations). Urdu: Gladia + Gemini +
Uplift. Tests also exercise WebRTC and the shared telephony channel for both call
directions. They do not establish live PSTN transport or subjective voice quality.

Cartesia maps affect to supported emotion tags and uses bounded native speed.
ElevenLabs uses supported native speed with existing voice settings preserved.
Rime Coda/Mist use only their audited speed semantics. Default Rime Arcana and
Uplift retain plain speech, punctuation, pronunciation and chosen-voice expression;
no unsupported emotion, pitch, energy, SSML or nonverbal controls are fabricated.
Intensity and energy inform LLM wording; they are not claimed as native TTS knobs.
The renderer version is bumped to prevent stale rendered-audio reuse.

## Client test app

The frontend continues to use published Voice 1.1.1. Its backend uses the packaged
Agents 0.1.2-humanization.0 preview with lockfile integrity; Telephony stays 0.1.1.
This is an installed artifact, not a source alias. It is not published to npm.

- In **Agent prompt**, enable **Humanized speech**, choose the speech persona,
  and save. Unsaved changes block Start conversation. Reload/reset/saving/failed
  save and live-session lock states include persona controls.
- The **Inbound call settings** panel saves the profile on the number's verified
  assigned agent and reads it back. It does not move or reconfigure the route.
- Outbound calls use the outbound agent's saved profile. Select that same agent
  in Agent prompt to edit it; saving another agent cannot change the call's persona.

Run `npm.cmd run verify --prefix client-integration-test` after installation.
Copy `packages/` as well when moving the independent client folder.

## Rollout boundary

The checked local client configuration currently targets hosted staging control
plane/tenant APIs. Local edits do not deploy those services. The updated tenant
API and a fresh worker process serving that same LiveKit dispatch must be running
before enabling profiles there. No database migration or browser SDK publication
is needed. Restart the client backend after installing the snapshot.

For activation, compare baseline and enabled profiles with greetings, questions,
concern, correction, read-backs, tool waits and closing. Cover each intended
provider/model/voice, English/Urdu and browser/PSTN lane. Listen to caller-side
recordings for continuity, expression, intelligibility, interruption and latency.
Synthetic tests prove contracts; they cannot establish audible naturalness.
