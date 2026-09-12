# Engineering Implementation Brief

Use this brief when planning an application integration with the AwaazLabs UVA SDKs. It is client-facing and mirrors the package boundaries in this handover.

English Cartesia and Rime TTS, plus greeting / first-speaker, are configured through `@awaazlabs-uva/agents`. Spoken humanization is hosted — do not put SSML or `spell()` in the tenant prompt.

## Non-negotiable boundaries

- Browser code may import only `@awaazlabs-uva/voice`.
- Backend code may import `@awaazlabs-uva/agents` and `@awaazlabs-uva/telephony`.
- The tenant HMAC secret, Telnyx API key, SIP secret, provider credentials, and database credentials must never appear in frontend code.
- The frontend must request voice sessions from the client's own backend session endpoint.

## Backend modules to build

1. Configuration loader for `UVA_API_BASE_URL`, `UVA_TELEPHONY_API_URL`, `UVA_TENANT_ID`, and `UVA_HMAC_SECRET`.
2. Agent service using `AwaazLabsUvaAgentsClient` for `createAgent`, `listAgents`, and `updateAgent` (including `ttsProvider`, `greeting`, and `firstSpeaker`).
3. Voice session routes that authenticate the user, choose an agent ID, and return a short-lived session payload for the browser SDK.
4. Telephony service using `TelephonyClient` for Telnyx connection, number sync/import, assignment, SIP/routing setup, readiness checks, and approved outbound calls.
5. Error mapping that preserves SDK status/code/message while returning product-appropriate messages to end users.

## Frontend modules to build

1. Voice catalog loader using `AwaazLabsUvaVoice.listVoices(endpointUrl)`.
2. Voice session component using `new AwaazLabsUvaVoice({ publishableKey, sessionEndpoint, refreshEndpoint })`.
3. Connect/disconnect controls using `connect({ agentId, voiceId })`, `disconnect()`, and `startAudio()` after a user gesture when audio is blocked.
4. Transcript, speaking, metrics, connected, disconnected, ended, and error event handlers.

## Telephony setup sequence

1. `getConnectionStatus()`
2. `connectTelnyxAccount({ apiKey, label: 'primary' })` or `rotateTelnyxAccountKey({ apiKey })`
3. `syncTelnyxOwnedNumbers()`
4. `listManagedPhoneNumbers({ limit })`
5. `assignAgentToNumber(numberId, agentId)`
6. `upsertTelnyxSipConnection({ sipFqdn, sipUsername, sipSecret })`
7. `verifyTelnyxSipConnection()`
8. `upsertTelnyxOutboundVoiceProfile({ allowedDestinations, concurrencyLimit, channelLimit, dailySpendingLimit })`
9. `verifyTelnyxOutboundVoiceProfile()`
10. `configureNumberRouting(numberId)`
11. `configureOutboundTrunk()`
12. `getOutboundReadiness()`
13. `createOutboundCall({ agentId, fromNumberId, toNumber, idempotencyKey })` only after readiness and user/operator approval

## Acceptance checklist

- Packages install from the provided tarballs.
- Frontend build contains no backend-only SDK imports.
- Backend environment contains all required tenant/provider values.
- Agent creation/list/update works from backend code.
- An English agent can be created with `ttsProvider: 'cartesia'` or `'rime'`, optional `greeting`, and `firstSpeaker: 'agent' | 'user'`.
- Switching TTS provider is an `updateAgent` of `ttsProvider` + `ttsVoiceId` from `getProviderCapabilities()`.
- Browser `connect()` uses `agentId` only for greeting/TTS; those fields are not passed from the frontend.
- Browser voice session can request a session from the client's backend and react to SDK events.
- Telnyx connection status and managed number sync work from backend code.
- Managed numbers can be assigned to agents.
- Inbound routing and outbound readiness setup complete without exposing secrets.
- Outbound calls are guarded by readiness, E.164 validation, and idempotency.
- Application logs redact secrets, provider credentials, and signed auth headers.
