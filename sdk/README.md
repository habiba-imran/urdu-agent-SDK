# @awaazlabs-uva/voice

Browser SDK for AwaazLabs-UVA-Voice sessions.

## Install

```bash
npm install @awaazlabs-uva/voice
```

## What You Need Before You Start

Every client integration needs four things:

- a deployed host-owned backend that implements the session contract
- a `publishableKey`
- an `agentId`
- a browser app that calls the host backend, not AwaazLabs-UVA upstream services directly

Reference material (links point at the source repository, so they also work from npm):

- working host backend + browser client: [demo-app](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/tree/main/demo-app)
- end-to-end guide: [docs/CLIENT_QUICKSTART.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/docs/CLIENT_QUICKSTART.md)
- host backend contract: [docs/HOST_BACKEND_CONTRACT.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/docs/HOST_BACKEND_CONTRACT.md)
- server-side agent management: [`@awaazlabs-uva/agents`](https://www.npmjs.com/package/@awaazlabs-uva/agents)

## V1 public contract

```ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const agent = new AwaazLabsUvaVoice({
  publishableKey: 'pk_demo',
  sessionEndpoint: 'https://host.example.com/api/voice/session',
});

agent.on('transcript', (entry) => {
  console.log(entry.speaker, entry.text, entry.final);
});

await agent.connect({ agentId: 'agent_123' });
await agent.disconnect();
```

Minimal browser example:

```ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const voice = new AwaazLabsUvaVoice({
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
  sessionEndpoint: 'http://localhost:3000/api/voice/session',
  refreshEndpoint: 'http://localhost:3000/api/voice/session/refresh',
});

voice.on('transcript', (entry) => {
  console.log(entry.text, entry.final ? 'final' : 'partial');
});

voice.on('audio_blocked', (blocked) => {
  // Browsers can block autoplay. Show a button and call voice.startAudio() from its click handler.
});

voice.on('error', (error) => {
  console.error(error.code, error.message);
});

await voice.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
```

The SDK is safe to import at module scope in server-rendered frameworks such as Next.js; it only
touches the DOM once a call is connected.

### Constructor

`new AwaazLabsUvaVoice(options)`

- `publishableKey: string`
- `sessionEndpoint: string`
- `refreshEndpoint?: string`
- `fetchTimeoutMs?: number` — max wait for the session, refresh and voice-catalogue requests
  (default `15000`). A request that exceeds it fails with the `timeout` error code.

### Methods

- `connect({ agentId })`
- `disconnect()`
- `startAudio()` — call from a user gesture after `audio_blocked` fires with `true`
- `setMicMuted(muted)`
- `on(event, listener)`
- `off(event, listener)`
- `AwaazLabsUvaVoice.listVoices(endpointUrl, timeoutMs?)` — static voice-catalogue helper

### Read-only properties

- `connectionState`
- `isConnected`
- `isMicMuted`

### Supported events

| Event | Payload |
|---|---|
| `connected` | none |
| `disconnected` | LiveKit reason when available |
| `ended` | same reason forwarded for convenience |
| `transcript` | `{ id, text, final, speaker }` — replace earlier entries with the same `id` |
| `speaking` | `boolean` caller/room speaking state |
| `agent_speaking` | `boolean` non-local active speaker state |
| `audio_blocked` | `boolean` — `true` when the browser blocked playback |
| `metrics_updated` | metrics object when worker metadata/data channel emits it |
| `turn_latency` | per-turn stage timing object emitted by the worker |
| `error` | `AwaazLabsUvaVoiceError` |

A listener that throws does not stop other listeners from receiving the event.

### Public error taxonomy

| Code | Meaning |
|---|---|
| `quota_exceeded` | tenant plan cap (concurrency or monthly minutes), or a `429` with no more specific body |
| `rate_limit` | platform rate limit (`429` with a "rate limited" body) — back off and retry |
| `provider_limit` | an upstream voice/LLM provider limit, distinct from your plan quota |
| `worker_not_ready` | the voice worker is not ready to take the call yet |
| `agent_not_found` | `404` — wrong `agentId`, wrong tenant, or the agent no longer exists |
| `timeout` | the host backend did not answer within `fetchTimeoutMs` |
| `token_refresh_failed` | the call's token could not be refreshed (rejected, or retries ran out before expiry) |
| `session_failed` | any other session failure |

The SDK does not expose backend internals or raw provider failures as part of its public contract.

## Session endpoint contract

The browser SDK never talks directly to AwaazLabs-UVA upstream services. It calls the host
platform's own backend:

- Request body: `{ publishableKey, agentId }`
- Success response: `{ token, wsUrl, roomName, refreshUrl?, expiresIn? }`

The refresh path uses `refreshUrl` when present, otherwise:

- `refreshEndpoint` from the constructor, or
- `<sessionEndpoint>/refresh`

A failed refresh is retried with backoff until the token is about to expire, so a single network
blip does not end the call. `token_refresh_failed` is only emitted once retries are exhausted or
the backend rejects the token (`401`/`403`).

See [docs/HOST_BACKEND_CONTRACT.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/docs/HOST_BACKEND_CONTRACT.md)
for the exact host-backend specification.

## Local integration path

The shortest repo-supported path uses
[demo-app](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/tree/main/demo-app):

1. build this package (`cd sdk && npm run build`)
2. start the host backend in `demo-app/backend/`
3. start the browser client in `demo-app/frontend/`
4. set both `.env` files with a real `agentId`, `publishableKey`, `tenantId`, and tenant HMAC
   secret (the secret goes in the backend `.env` only)
5. open the browser client and connect

Detailed setup steps are in
[docs/CLIENT_QUICKSTART.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/docs/CLIENT_QUICKSTART.md).

## Explicit omissions in v1

These are intentionally out of scope for the supported surface right now:

- no text-chat transport
- no browser-side secret creation or rotation
- no agent configuration APIs
- no built-in UI components
- no guarantee of custom metric schema beyond passthrough delivery

## Security rules

- Zero secrets in the bundle.
- `publishableKey` identifies, never authorizes.
- The SDK talks only to the host's session endpoint and then to LiveKit.
- The SDK never directly calls private provider, database, or administrative infrastructure.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `quota_exceeded` | tenant concurrency or monthly quota cap reached |
| `rate_limit` | too many session requests for this tenant in the last minute |
| `agent_not_found` | wrong `agentId`, wrong tenant, or agent no longer exists |
| `timeout` | host backend is down, hung, or slower than `fetchTimeoutMs` |
| `session_failed` immediately | host backend misconfigured, bad session upstream config, or refresh/session route mismatch |
| no agent audio | browser blocked autoplay — handle `audio_blocked` and call `startAudio()` from a click |
| browser reaches AwaazLabs-UVA upstream directly | integration bug — the browser should call the host backend only |

## Changelog

See [CHANGELOG.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/sdk/CHANGELOG.md).
