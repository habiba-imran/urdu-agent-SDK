# 01 — Integration Guide

## 1. Packages and where they run

| Package | Runtime | Responsibility |
|---------|---------|----------------|
| `@awaazlabs-uva/voice` | **Browser only** | Short-lived LiveKit/WebRTC voice session |
| `@awaazlabs-uva/agents` | **Your backend only** | Create/list/update agents (HMAC-signed) |
| `@awaazlabs-uva/telephony` | **Your backend only** | Telnyx connect, numbers, routing, outbound calls (HMAC-signed) |

Never import `agents` or `telephony` in frontend bundles — they need the tenant HMAC secret.

## 2. Install (npm)

Frontend:

```bash
npm install @awaazlabs-uva/voice@1.1.0
```

Backend:

```bash
npm install @awaazlabs-uva/agents@0.1.0
npm install @awaazlabs-uva/telephony@0.1.0
```

`livekit-client` is pulled in automatically with the voice package.

For browser voice sessions you also need a **host backend**. Use the included starter:

```bash
cd host-backend-starter
cp .env.example .env
# fill tenant secrets now; fill UVA_CONTROL_PLANE_URL when deployed
npm install
npm run dev
```

## 3. Backend environment

```bash
# From AwaazLabs provisioning (fill now)
UVA_TENANT_ID=<TENANT_UUID>
UVA_HMAC_SECRET=<TENANT_HMAC_SECRET>
UVA_PUBLISHABLE_KEY=<PUBLISHABLE_KEY>

# From AwaazLabs when services are deployed (fill later)
UVA_API_BASE_URL=<TENANT_PORTAL_API_BASE_URL>
UVA_TELEPHONY_API_URL=<TENANT_PORTAL_API_BASE_URL>   # often same as above
UVA_CONTROL_PLANE_URL=<SESSION_UPSTREAM_URL>

# Your Telnyx key — required for phone / PSTN
TELNYX_API_KEY=<YOUR_TELNYX_API_V2_KEY>

# Optional Telnyx SIP / outbound (after connect)
TELNYX_SIP_FQDN=
TELNYX_SIP_USERNAME=
TELNYX_SIP_SECRET=
TELNYX_OUTBOUND_ALLOWED_DESTINATIONS=US

# Your host
HOST_ALLOWED_ORIGINS=http://localhost:5173,https://your-app.example.com
HOST_PUBLIC_BASE_URL=https://your-api.example.com
PORT=3000
```

**Important:** Telephony uses **Telnyx**, not Twilio. See `04-TELEPHONY_AND_PROVIDER_KEYS.md`.

## 4. Frontend environment

```bash
VITE_UVA_PUBLISHABLE_KEY=<PUBLISHABLE_KEY>
VITE_UVA_SESSION_ENDPOINT=http://localhost:3000/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=http://localhost:3000/api/voice/session/refresh
VITE_UVA_AGENT_ID=<AGENT_UUID>
```

Only these belong in the browser. Never put `UVA_HMAC_SECRET` or `TELNYX_API_KEY` in frontend env.

## 5. Create and manage agents (backend)

Requires `UVA_API_BASE_URL` (portal) when that service is deployed.

```ts
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';

const agents = new AwaazLabsUvaAgentsClient({
  baseUrl: process.env.UVA_API_BASE_URL!,
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
});

const agent = await agents.createAgent({
  name: 'Support Agent',
  prompt: 'Answer customer questions in a concise and helpful way.',
  voiceId: 'voice_id_from_catalog',
  llmModel: 'gemini-2.5-flash',
  agentLanguage: 'en',
  ttsProvider: 'cartesia',
  ttsVoiceId: 'voice_id_from_catalog',
  firstSpeaker: 'agent',
  greeting: 'Hi, thanks for calling. How can I help you today?',
});

// Use agent.id in the browser as VITE_UVA_AGENT_ID
console.log('agentId', agent.id);

const allAgents = await agents.listAgents();

await agents.updateAgent(agent.id, {
  ttsProvider: 'rime',
  ttsVoiceId: 'voice_id_from_catalog',
});
```

### Greeting and who speaks first

Set on the **agent** (via agents SDK), not on browser `connect()`:

| Field | Values | Effect |
|-------|--------|--------|
| `firstSpeaker` | `'agent'` \| `'user'` | Agent greets immediately, or waits for caller |
| `greeting` | string, max 500 chars | Opening line when agent speaks first |

### Provider capabilities

```ts
const capabilities = await agents.getProviderCapabilities();
const cartesiaVoices = capabilities.languages.en?.tts?.cartesia?.voices ?? [];
const urduTtsProviders = Object.keys(capabilities.languages.ur?.tts ?? {});
```

If a provider is missing for a language, treat it as unavailable.

English TTS: **Cartesia** and **Rime**. Omit `ttsProvider` to keep the hosted default (typically Urdu + Uplift). Do not put SSML, markdown speech scripts, or filler-word markup in `prompt` / `greeting`.

## 6. Host backend session endpoints

Full contract + signing: **`02-HOST_BACKEND_CONTRACT.md`**.

Runnable implementation: **`host-backend-starter/`**.

Minimum routes:

- `POST /api/voice/session` → `{ token, wsUrl, roomName, refreshUrl?, expiresIn? }`
- `POST /api/voice/session/refresh` → refreshed token payload

The starter:

1. Validates `publishableKey`
2. HMAC-signs the control-plane mint request
3. Calls `{UVA_CONTROL_PLANE_URL}/v1/session`
4. Returns only browser-safe fields
5. Rewrites `refreshUrl` to your `/api/voice/session/refresh`

You can run the starter as-is or copy its `signing.js` + route handlers into your own API.

## 7. Browser voice sessions

```ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const voice = new AwaazLabsUvaVoice({
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
  sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT,
  refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT,
});

voice.on('connected', () => console.log('connected'));
voice.on('transcript', (entry) => {
  console.log(entry.speaker, entry.text, entry.final);
});
voice.on('audio_blocked', (blocked) => {
  if (blocked) {
    // Show a button; on click call voice.startAudio()
  }
});
voice.on('error', (error) => {
  console.error(error.code, error.message);
});

await voice.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
await voice.disconnect();
```

### Minimal browser test page

```html
<!doctype html>
<html>
  <body>
    <button id="start">Start call</button>
    <button id="unmute-audio" hidden>Enable audio</button>
    <pre id="log"></pre>
    <script type="module">
      import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

      const log = (msg) => {
        document.getElementById('log').textContent += msg + '\n';
      };

      const voice = new AwaazLabsUvaVoice({
        publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
        sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT,
        refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT,
      });

      voice.on('transcript', (e) => log(`${e.speaker}: ${e.text}`));
      voice.on('audio_blocked', (blocked) => {
        document.getElementById('unmute-audio').hidden = !blocked;
      });
      voice.on('error', (e) => log(`ERROR ${e.code}: ${e.message}`));

      document.getElementById('start').onclick = async () => {
        await voice.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
        log('connected');
      };
      document.getElementById('unmute-audio').onclick = async () => {
        await voice.startAudio();
      };
    </script>
  </body>
</html>
```

Point session/refresh env vars at **your** host backend (the starter), not the control-plane URL.

### Voice SDK surface (v1)

**Constructor:** `publishableKey`, `sessionEndpoint`, optional `refreshEndpoint`, optional `fetchTimeoutMs` (default 15000).

**Methods:** `connect({ agentId })`, `disconnect()`, `startAudio()`, `setMicMuted(muted)`, `on` / `off`.

**Events:** `connected`, `disconnected`, `ended`, `transcript`, `speaking`, `agent_speaking`, `audio_blocked`, `metrics_updated`, `turn_latency`, `error`.

**Out of scope for v1:** text chat transport, browser secret management, agent config APIs in the browser package, built-in UI components.

## 8. Telephony (phone) — backend only

Requires **your own Telnyx API key** and portal URL when deployed. See `04-TELEPHONY_AND_PROVIDER_KEYS.md`.

```ts
import { randomUUID } from 'node:crypto';
import { TelephonyClient } from '@awaazlabs-uva/telephony';

const telephony = new TelephonyClient({
  baseUrl: process.env.UVA_TELEPHONY_API_URL!,
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
});

await telephony.connectTelnyxAccount({
  apiKey: process.env.TELNYX_API_KEY!,
  label: 'primary',
});

await telephony.syncTelnyxOwnedNumbers();
const numberId = /* managed number id */;
const agentId = /* agent id */;
await telephony.assignAgentToNumber(numberId, agentId);
await telephony.configureNumberRouting(numberId);
await telephony.configureOutboundTrunk();

const readiness = await telephony.getOutboundReadiness();
if (!readiness.ready) {
  console.error('outbound not ready', readiness.reasons);
  throw new Error('outbound_not_ready');
}

const call = await telephony.createOutboundCall({
  agentId,
  fromNumberId: numberId,
  toNumber: '+15551234567',
  idempotencyKey: randomUUID(),
});
```

### Inbound (high level)

1. Connect Telnyx → sync/import/purchase numbers  
2. Assign number → agent  
3. Configure routing  
4. Inbound call reaches the assigned agent  

### Outbound (high level)

1. `getOutboundReadiness()` must be ready  
2. `createOutboundCall({ agentId, fromNumberId, toNumber, idempotencyKey })`  
3. One unique idempotency key per intended call; after timeouts check `getCallStatus` before retrying with a new key  

`toNumber` must be E.164.

## 9. Verify integration

Browser path is working when:

1. Browser calls **your** session endpoint  
2. Session returns `token`, `wsUrl`, `roomName`  
3. LiveKit connects  
4. Transcripts appear  
5. Refresh goes through your refresh route  

Phone path is working when Telnyx is connected, a number is assigned to an agent, readiness is green, and a test call reaches the worker.
