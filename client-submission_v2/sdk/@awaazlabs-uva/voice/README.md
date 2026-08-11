# @awaazlabs-uva/voice

Browser TypeScript SDK for AwaazLabs UVA voice sessions over LiveKit/WebRTC.

## Install

```bash
npm install ./client-submission_v2/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz
```

## Runtime

Use this package only in browser/frontend code. It needs a publishable key and your own backend session endpoints. It must not receive tenant HMAC secrets, Telnyx keys, SIP secrets, or provider credentials.

```bash
PUBLIC_UVA_PUBLISHABLE_KEY=<PUBLIC_TENANT_KEY>
PUBLIC_UVA_SESSION_ENDPOINT=<YOUR_BACKEND_SESSION_ENDPOINT>
PUBLIC_UVA_REFRESH_ENDPOINT=<YOUR_BACKEND_SESSION_REFRESH_ENDPOINT>
PUBLIC_UVA_VOICE_CATALOG_ENDPOINT=<YOUR_BACKEND_VOICE_CATALOG_ENDPOINT>
```

## Usage

```ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const voices = await AwaazLabsUvaVoice.listVoices(
  import.meta.env.PUBLIC_UVA_VOICE_CATALOG_ENDPOINT,
);

const agent = new AwaazLabsUvaVoice({
  publishableKey: import.meta.env.PUBLIC_UVA_PUBLISHABLE_KEY,
  sessionEndpoint: import.meta.env.PUBLIC_UVA_SESSION_ENDPOINT,
  refreshEndpoint: import.meta.env.PUBLIC_UVA_REFRESH_ENDPOINT,
});

agent.on('connected', () => {
  console.log('connected');
});

agent.on('transcript', (event) => {
  console.log(event.final ? 'final' : 'partial', event.text);
});

agent.on('audio_blocked', async (blocked) => {
  if (blocked) {
    // Show a user-initiated button, then call agent.startAudio() in that click handler.
  }
});

await agent.connect({
  agentId: '<AGENT_ID>',
  voiceId: voices[0]?.id,
});
```

Your backend session endpoint remains the source of truth for the actual session payload. `agentId` is the required browser input. `voiceId` is an optional compatibility field in the browser API shape and should not be treated as a replacement for backend session-side selection logic.

## API

```ts
AwaazLabsUvaVoice.listVoices(endpointUrl)

new AwaazLabsUvaVoice({ publishableKey, sessionEndpoint, refreshEndpoint? })

agent.connect({ agentId, voiceId? })
agent.disconnect()
agent.startAudio()
agent.on(eventName, callback)
agent.off(eventName, callback)
```

Events: `transcript`, `speaking`, `error`, `ended`, `connected`, `disconnected`, `agent_speaking`, `metrics_updated`, and `audio_blocked`.

Error codes: `quota_exceeded`, `agent_not_found`, and `session_failed`.
