# @uva/voice

Browser SDK for Urdu Voice Agent sessions.

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

## Example app

See [examples/basic-web-client](../examples/basic-web-client/README.md) for the Phase 0 consumer
scaffold.
