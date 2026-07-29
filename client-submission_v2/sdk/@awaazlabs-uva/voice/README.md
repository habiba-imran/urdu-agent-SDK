# @awaazlabs-uva/voice

Browser SDK for AwaazLabs-UVA voice sessions. This package is safe to ship in a browser bundle:
it contains no tenant HMAC secret, provider key, database credential, or backend-only upstream URL.

## Install

From the client's frontend project:

```bash
npm install /path/to/client-submission_v2/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz livekit-client@^2.0.0
```

## Basic Usage

```ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const voice = new AwaazLabsUvaVoice({
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
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
});

voice.on('error', (error) => {
  console.error(error.code, error.message);
});

await voice.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
```

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

| Event | Payload |
|---|---|
| `connected` | none |
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
