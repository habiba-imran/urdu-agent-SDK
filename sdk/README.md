# @awaazlabs-uva/voice

Browser SDK for AwaazLabs UVA voice sessions. **Zero secrets** — talks only to **your** host session endpoint, then LiveKit.

Published as `@awaazlabs-uva/voice@1.1.0`. Pin this version in lockfiles. In-console guide: tenant dashboard → `/docs` (canonical for clients).

## Install

```bash
npm install @awaazlabs-uva/voice@1.1.0
```

Companion packages (backend only — never in a browser bundle):

```bash
npm install @awaazlabs-uva/agents@0.1.0 @awaazlabs-uva/telephony@0.1.0
```

## What you need

- Your host backend implementing the [session contract](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/docs/HOST_BACKEND_CONTRACT.md)
- A `publishableKey` and `agentId` (from the dashboard or `@awaazlabs-uva/agents`)
- A browser app that calls **your** session endpoint — never the control plane with an HMAC

Where to read next:

- **In-dashboard `/docs`** (Quickstart, Backend setup, Frontend setup, Errors) — client source of truth
- Repo redirect: [docs/CLIENT_QUICKSTART.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/docs/CLIENT_QUICKSTART.md)
- Optional starter: [`client-deliverables-final/host-backend-starter/`](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/tree/main/client-deliverables-final/host-backend-starter)
- Agent CRUD: [`@awaazlabs-uva/agents`](https://www.npmjs.com/package/@awaazlabs-uva/agents)
- PSTN: [`@awaazlabs-uva/telephony`](https://www.npmjs.com/package/@awaazlabs-uva/telephony)

## Minimal example

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
  // Show a button; call voice.startAudio() from its click handler when blocked === true.
});

voice.on('error', (error) => {
  console.error(error.code, error.message);
});

await voice.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
await voice.disconnect();
```

Safe to import at module scope in Next.js — DOM access happens on connect.

### Constructor

`new AwaazLabsUvaVoice(options)`

- `publishableKey: string`
- `sessionEndpoint: string`
- `refreshEndpoint?: string`
- `fetchTimeoutMs?: number` — session / refresh / voices fetch timeout (default `15000`); overruns throw `timeout`

### Methods

- `connect({ agentId })`
- `disconnect()`
- `startAudio()` — from a user gesture after `audio_blocked`
- `setMicMuted(muted)`
- `on(event, listener)` / `off(event, listener)`
- `AwaazLabsUvaVoice.listVoices(endpointUrl, timeoutMs?)` — static voice catalogue helper

### Read-only properties

- `connectionState` · `isConnected` · `isMicMuted`

### Supported events

| Event | Payload |
|---|---|
| `connected` | none |
| `disconnected` | LiveKit reason when available |
| `ended` | same reason (convenience) |
| `transcript` | `{ id, text, final, speaker }` — replace earlier entries with the same `id` |
| `speaking` | `boolean` caller/room speaking |
| `agent_speaking` | `boolean` agent active speaker |
| `audio_blocked` | `boolean` — `true` when the browser blocked playback |
| `metrics_updated` | metrics object when the runtime emits it (may be absent if publishing is off) |
| `turn_latency` | per-turn timing when the runtime emits it |
| `error` | `AwaazLabsUvaVoiceError` |
| `connect_timing` | mint vs LiveKit-join ms (diagnostics) |

A throwing listener does not stop other listeners.

### Public error taxonomy

| Code | Meaning |
|---|---|
| `quota_exceeded` | Plan concurrency or monthly minutes, or opaque `429` |
| `rate_limit` | Platform rate limit (`429` with a rate-limit body) — back off |
| `provider_limit` | Upstream voice/LLM provider limit (not your plan quota) |
| `worker_not_ready` | Voice worker not ready yet — retry shortly |
| `agent_not_found` | HTTP `404` — wrong `agentId` / tenant |
| `timeout` | Host did not answer within `fetchTimeoutMs` |
| `token_refresh_failed` | Refresh rejected or retries exhausted |
| `session_failed` | Any other session failure |

## Session endpoint contract

Request body: `{ publishableKey, agentId }`

Success: `{ token, wsUrl, roomName, refreshUrl?, expiresIn? }`

Refresh uses `refreshUrl` when present, else `refreshEndpoint`, else `<sessionEndpoint>/refresh`.

Full host contract: [docs/HOST_BACKEND_CONTRACT.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/docs/HOST_BACKEND_CONTRACT.md).

## Explicit omissions

- No text-chat transport · no browser secrets · no agent CRUD · no UI components
- Metrics schemas are passthrough — not a stable public schema beyond delivery

## Security

- Zero secrets in the bundle
- `publishableKey` identifies; it does not authorize minting alone
- Never call control-plane HMAC routes from the browser

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `quota_exceeded` | Concurrent or monthly cap |
| `rate_limit` | Too many session requests |
| `agent_not_found` | Wrong `agentId` / tenant |
| `timeout` | Host slow or down |
| `session_failed` | Host misconfig or upstream mint failure |
| No agent audio | Handle `audio_blocked` → `startAudio()` |

## Changelog

See [CHANGELOG.md](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/blob/main/sdk/CHANGELOG.md).
