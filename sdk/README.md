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

If you are starting from the reference materials in this repo:

- browser example: [examples/web-client](../examples/web-client/README.md)
- host backend starter: [examples/host-backend](../examples/host-backend/README.md)
- end-to-end guide: [docs/CLIENT_QUICKSTART.md](../docs/CLIENT_QUICKSTART.md)

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
- `fetchTimeoutMs?: number` — max wait for session / refresh / voice-catalog `fetch` (default `15000`)

### Methods

- `connect({ agentId })`
- `disconnect()`
- `on(event, listener)`
- `off(event, listener)`
- `startAudio()` — call inside a user-gesture handler when `audio_blocked` fires with `true`

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
| `transcript` | `{ id, text, final, speaker }` |
| `speaking` | `boolean` caller/room speaking state |
| `agent_speaking` | `boolean` non-local active speaker state |
| `metrics_updated` | metrics object when worker metadata/data channel emits it |
| `turn_latency` | per-turn stage breakdown from the worker |
| `audio_blocked` | `boolean` — browser blocked/unblocked autoplay |
| `error` | `AwaazLabsUvaVoiceError` |

### Public error taxonomy

| Code | When |
|---|---|
| `quota_exceeded` | Plan concurrent / monthly cap, or an opaque `429` with no distinguishable body |
| `agent_not_found` | HTTP `404` from the session endpoint |
| `session_failed` | Generic connect / session failure |
| `rate_limit` | Platform rate limit signal in the response body (e.g. `"rate limited"`) |
| `worker_not_ready` | Host/control-plane signals worker not ready in the body |
| `provider_limit` | Upstream provider limit signal in the body |
| `timeout` | Client `AbortController` timeout (`fetchTimeoutMs`) |
| `token_refresh_failed` | LiveKit token refresh rejected (`401`/`403`) or retries exhausted until expiry |

`404` maps to `agent_not_found`. Distinguishing `rate_limit` / quota / `provider_limit` requires the
host to forward distinguishable body text (or `error` / `detail` / `code` fields) — empty `429`
bodies stay `quota_exceeded` for backward compatibility. The SDK does not expose raw provider
stack traces as part of its public contract.

## Session endpoint contract

The browser SDK never talks directly to AwaazLabs-UVA upstream services. It calls the host
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

1. start the host backend starter in `examples/host-backend/`
2. start the browser example in `examples/web-client/`
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
- The SDK never directly calls private provider, database, or administrative infrastructure.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `quota_exceeded` | tenant concurrency or monthly quota cap reached (or opaque `429`) |
| `rate_limit` | host/platform rate limit — back off and retry |
| `timeout` | host session/refresh endpoint did not respond within `fetchTimeoutMs` |
| `token_refresh_failed` | refresh rejected or network stayed down until LiveKit JWT expiry |
| `agent_not_found` | wrong `agentId`, wrong tenant, or agent no longer exists |
| `session_failed` immediately | host backend misconfigured, bad session upstream config, or refresh/session route mismatch |
| browser reaches AwaazLabs-UVA upstream directly | integration bug — the browser should call the host backend only |

## Example app

See [examples/web-client](../examples/web-client/README.md) for the Phase 0 consumer
scaffold, and [examples/host-backend](../examples/host-backend/README.md) for the Phase 3
reference backend starter that creates sessions through a backend-only upstream safely.
