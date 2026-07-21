# @uva/voice

Browser SDK for Urdu Voice Agent sessions.

## Install

```bash
npm install @uva/voice
```

## What You Need Before You Start

Every client integration needs four things:

- a deployed host-owned backend that implements the session contract
- a `publishableKey`
- an `agentId`
- a browser app that calls the host backend, not the control plane directly

If you are starting from the reference materials in this repo:

- browser example: [examples/basic-web-client](../examples/basic-web-client/README.md)
- host backend starter: [examples/host-backend-node](../examples/host-backend-node/README.md)
- end-to-end guide: [docs/CLIENT_QUICKSTART.md](../docs/CLIENT_QUICKSTART.md)

## V1 public contract

```ts
import { UrduVoiceAgent } from '@uva/voice';

const agent = new UrduVoiceAgent({
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
import { UrduVoiceAgent } from '@uva/voice';

const voice = new UrduVoiceAgent({
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

`new UrduVoiceAgent(options)`

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
| `error` | `UvaError` |

### Public error taxonomy

- `quota_exceeded`
- `agent_not_found`
- `session_failed`

`429` maps to `quota_exceeded`, `404` maps to `agent_not_found`, and every other non-success path
maps to `session_failed`. The SDK does not expose backend internals or raw provider failures as part
of its public contract.

## Session endpoint contract

The browser SDK never talks directly to the control plane with secrets. It calls the host
platform's own backend:

- Request body: `{ publishableKey, agentId }`
- Success response: `{ token, wsUrl, roomName, refreshUrl?, expiresIn? }`

The refresh path uses `refreshUrl` when present, otherwise:

- `refreshEndpoint` from the constructor, or
- `<sessionEndpoint>/refresh`

See [docs/HOST_BACKEND_CONTRACT.md](../docs/HOST_BACKEND_CONTRACT.md) for the exact host-backend
specification.

## Local integration path

The shortest repo-supported path is:

1. start the host backend starter in `examples/host-backend-node/`
2. start the browser example in `examples/basic-web-client/`
3. set the browser example env to point at the host backend starter
4. use a real `agentId`, `publishableKey`, `tenantId`, and tenant HMAC secret
5. connect from the browser example

Detailed setup steps are in [docs/CLIENT_QUICKSTART.md](../docs/CLIENT_QUICKSTART.md).

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
- The SDK never directly calls provider APIs such as Uplift, Gladia, Gemini, or Supabase.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `quota_exceeded` | tenant concurrency or monthly quota cap reached |
| `agent_not_found` | wrong `agentId`, wrong tenant, or agent no longer exists |
| `session_failed` immediately | host backend misconfigured, bad signing, wrong control-plane URL, or refresh/session route mismatch |
| browser reaches control plane directly | integration bug — the browser should call the host backend only |

## Example app

See [examples/basic-web-client](../examples/basic-web-client/README.md) for the Phase 0 consumer
scaffold, and [examples/host-backend-node](../examples/host-backend-node/README.md) for the Phase 3
reference backend starter that signs control-plane requests safely.
