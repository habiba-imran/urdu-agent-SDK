# @awaazlabs-uva/voice

Browser SDK for AwaazLabs-UVA-Voice sessions.

## Install

From the client-submission root:

```bash
npm install ./sdk/@awaazlabs-uva/voice
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

voice.on('error', (error) => {
  console.error(error.code, error.message);
});

await voice.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
```

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

| Event | Payload |
|---|---|
| `connected` | none |
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
