# @awaazlabs-uva/voice

<<<<<<< HEAD
Browser SDK for AwaazLabs-UVA voice sessions. This package is safe to ship in a browser bundle:
it contains no tenant HMAC secret, provider key, database credential, or backend-only upstream URL.

## Install

From the client's frontend project:

```bash
npm install /path/to/client-submission_v2/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz livekit-client@^2.0.0
```

## Basic Usage
=======
Browser SDK for AwaazLabs-UVA-Voice sessions.

## Install

From the client-submission root:

```bash
npm install ./sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz livekit-client@^2.0.0
```

## What You Need Before You Start

Every client integration needs four things:

- a deployed host-owned backend that implements the session contract
- a `publishableKey`
- an `agentId`
- a browser app that calls the host backend, not AwaazLabs-UVA upstream services directly

If you are starting from the client-submission bundle:

- package overview: [sdk/README.md](../../README.md)
- end-to-end integration guide: [docs/INTEGRATION_GUIDE.md](../../../docs/INTEGRATION_GUIDE.md)
- credentials reference: [docs/credentials-template.md](../../../docs/credentials-template.md)

## V1 public contract

```ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const agent = new AwaazLabsUvaVoice({
  publishableKey: 'pk_demo',
  sessionEndpoint: 'https://host.example.com/api/voice/session',
});

agent.on('transcript', (entry) => {
  console.log(entry.text, entry.final);
});

await agent.connect({ agentId: 'agent_123' });
await agent.disconnect();
```

Minimal browser example:
>>>>>>> origin/ukasha

```ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const voice = new AwaazLabsUvaVoice({
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
<<<<<<< HEAD
  sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT,
  refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT,
});

voice.on('transcript', (entry) => {
  if (entry.final) console.log('Final transcript:', entry.text);
});

voice.on('audio_blocked', (blocked) => {
  if (blocked) {
    // Show a button and call voice.startAudio() inside that button click.
  }
=======
  sessionEndpoint: 'http://localhost:3000/api/voice/session',
  refreshEndpoint: 'http://localhost:3000/api/voice/session/refresh',
});

voice.on('transcript', (entry) => {
  console.log(entry.text, entry.final ? 'final' : 'partial');
>>>>>>> origin/ukasha
});

voice.on('error', (error) => {
  console.error(error.code, error.message);
});

await voice.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
```

<<<<<<< HEAD
## Constructor Options

| Option | Required | Description |
|---|---:|---|
| `publishableKey` | Yes | Public tenant identifier |
| `sessionEndpoint` | Yes | Client backend route that creates a session |
| `refreshEndpoint` | No | Client backend route that refreshes a session token |

## Methods

- `connect({ agentId })`
- `disconnect()`
- `startAudio()`
- `on(event, listener)`
- `off(event, listener)`
- `AwaazLabsUvaVoice.listVoices(endpoint)`

## Events
=======
### Constructor

`new AwaazLabsUvaVoice(options)`

- `publishableKey: string`
- `sessionEndpoint: string`
- `refreshEndpoint?: string`

### Methods

- `connect({ agentId })`
- `disconnect()`
- `on(event, listener)`
- `off(event, listener)`

### Read-only properties

- `connectionState`
- `isConnected`

### Supported events
>>>>>>> origin/ukasha

| Event | Payload |
|---|---|
| `connected` | none |
<<<<<<< HEAD
| `disconnected` | optional reason |
| `ended` | optional reason |
| `transcript` | `{ text, final }` |
| `speaking` | boolean |
| `agent_speaking` | boolean |
| `metrics_updated` | metrics object |
| `audio_blocked` | boolean |
| `error` | `AwaazLabsUvaVoiceError` |

## Session Endpoint Contract

The SDK sends this request to the client's backend:

```json
{
  "publishableKey": "public-key",
  "agentId": "agent-uuid"
}
```

The backend must return:

```json
{
  "token": "short-lived-livekit-jwt",
  "wsUrl": "wss://livekit.example.com",
  "roomName": "room-name",
  "refreshUrl": "https://client-backend.example.com/api/voice/session/refresh",
  "expiresIn": 120
}
```

The browser must never call private AwaazLabs-UVA upstream services directly.

## Error Codes

| Code | Meaning |
|---|---|
| `quota_exceeded` | Tenant quota or concurrency limit hit |
| `agent_not_found` | Agent ID is missing or not visible to the tenant |
| `session_failed` | Backend, LiveKit, network, or session setup failed |

## Documentation

See `../../../docs/INTEGRATION_GUIDE.md` for full frontend/backend integration steps.
=======
| `disconnected` | LiveKit reason when available |
| `ended` | same reason forwarded for convenience |
| `transcript` | `{ text, final }` |
| `speaking` | `boolean` caller/room speaking state |
| `agent_speaking` | `boolean` non-local active speaker state |
| `metrics_updated` | metrics object when worker metadata/data channel emits it |
| `error` | `AwaazLabsUvaVoiceError` |

### Public error taxonomy

- `quota_exceeded`
- `agent_not_found`
- `session_failed`

`429` maps to `quota_exceeded`, `404` maps to `agent_not_found`, and every other non-success path
maps to `session_failed`. The SDK does not expose backend internals or raw provider failures as part
of its public contract.

## Session endpoint contract

The browser SDK never talks directly to AwaazLabs-UVA upstream services. It calls the host
platform's own backend:

- Request body: `{ publishableKey, agentId }`
- Success response: `{ token, wsUrl, roomName, refreshUrl?, expiresIn? }`

The refresh path uses `refreshUrl` when present, otherwise:

- `refreshEndpoint` from the constructor, or
- `<sessionEndpoint>/refresh`

See [docs/INTEGRATION_GUIDE.md](../../../docs/INTEGRATION_GUIDE.md) for the exact host-backend
specification.

## Local integration path

The shortest client-submission path is:

1. install this package into your frontend from `sdk/@awaazlabs-uva/voice/`
2. implement the host-owned backend routes from `docs/INTEGRATION_GUIDE.md`
3. set the frontend env to point at your host backend session routes
4. use a real `agentId`, `publishableKey`, `tenantId`, and tenant HMAC secret
5. connect from your browser app

Detailed setup steps are in [docs/INTEGRATION_GUIDE.md](../../../docs/INTEGRATION_GUIDE.md).

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
| `agent_not_found` | wrong `agentId`, wrong tenant, or agent no longer exists |
| `session_failed` immediately | host backend misconfigured, bad session upstream config, or refresh/session route mismatch |
| browser reaches AwaazLabs-UVA upstream directly | integration bug — the browser should call the host backend only |

## Client-submission guide

See [docs/INTEGRATION_GUIDE.md](../../../docs/INTEGRATION_GUIDE.md) for frontend, backend, agent
management, and verification steps.
>>>>>>> origin/ukasha
