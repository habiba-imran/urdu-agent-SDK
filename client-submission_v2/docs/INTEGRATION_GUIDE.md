# AwaazLabs-UVA-Voice SDK — Integration Documentation

> **Finova Solutions** — Confidential Client Onboarding Package
> Version: 1.0 | Last Updated: July 2026

---

> [!IMPORTANT]
> **Read this first — understanding the delivery format**
>
> This package includes the SDK source code inside the `sdk/` folder.
> These are **private packages** (not yet published to a public npm registry),
> so you install them from the included `.tgz` package files.
> You do **not** run `npm install @awaazlabs-uva/voice` from a registry — you install
> from the package file inside the `sdk/@awaazlabs-uva/voice/` directory.
>
> **What secrets are in the SDK code itself?**
> - `sdk/@awaazlabs-uva/voice/` (`@awaazlabs-uva/voice`) — **zero secrets.** This is the browser SDK.
>   It contains no API keys, no Finova credentials, no LiveKit secrets.
>   It is safe to ship publicly and is assumed to be fully inspectable.
> - `sdk/@awaazlabs-uva/agents/` (`@awaazlabs-uva/agents`) — **no hardcoded Finova secrets.**
>   It is a server-side signing library that accepts *your* credentials as
>   constructor arguments at runtime (loaded from your own `.env` file).
>   The package code itself is inert without you providing those values.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Package Contents & Extraction](#2-package-contents--extraction)
3. [Installing the Browser SDK (`@awaazlabs-uva/voice`)](#3-installing-the-browser-sdk-uvavoice)
4. [Installing the Server SDK (`@awaazlabs-uva/agents`)](#4-installing-the-server-sdk-uvaagents)
5. [Environment Configuration](#5-environment-configuration)
6. [Backend Integration: Session Endpoint](#6-backend-integration-session-endpoint)
7. [Frontend Integration: Voice Session](#7-frontend-integration-voice-session)
8. [Agent Management: Creating & Listing Agents](#8-agent-management-creating--listing-agents)
9. [Running the Reference Test App](#9-running-the-reference-test-app)
10. [Event Reference](#10-event-reference)
11. [Error Reference](#11-error-reference)
12. [Security Checklist](#12-security-checklist)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Prerequisites

Before beginning, ensure your development environment meets the following requirements.

### System Requirements

| Requirement | Minimum Version | Notes |
|---|---|---|
| **Node.js** | `18.0.0` | Required for `@awaazlabs-uva/agents` and the Express backend |
| **npm** | `8.0.0` | Included with Node.js 18 |
| **Modern Browser** | Chrome 90+ / Firefox 88+ / Safari 14+ | For `@awaazlabs-uva/voice` WebRTC sessions |

### Knowledge Requirements

- Familiarity with **TypeScript** or **JavaScript (ES2020+)**
- Basic understanding of **Express.js** (or any Node.js HTTP framework)
- Familiarity with **React**, **Vue**, or vanilla JS for the frontend integration
- Understanding of **environment variables** and `.env` files

### Credentials Required

You will receive the following credentials from your Finova Solutions onboarding contact.
**Do not proceed without these values** — see [`credentials-template.md`](credentials-template.md) for the full list, descriptions, and how each value connects to your code.

| Credential | Goes in | Description |
|---|---|---|
| `UVA_TENANT_ID` | Backend `.env` only | Your tenant UUID |
| `UVA_HMAC_SECRET` | Backend `.env` only | HMAC signing key — **never expose to browser** |
| `UVA_PUBLISHABLE_KEY` | Backend + Frontend `.env` | Public identifier — safe in browser |
| Backend-only session upstream config | Backend `.env` only | Provided securely by Finova or the approved host-backend starter |
| `UVA_PORTAL_API_URL` | Backend `.env` only | Finova portal API base URL |

---

## 2. Package Contents & Extraction

### Folder Structure

The deliverable package (`client-submission/`) has the following structure:

```
client-submission/
│
├── sdk/                          ← The SDK packages — install these into your app
│   ├── README.md                 ← SDK architecture overview
│   ├── @awaazlabs-uva/voice/               ← Browser SDK (@awaazlabs-uva/voice) — ZERO secrets
│   │   ├── dist/                 ← Compiled JS + TypeScript declarations
│   │   ├── src/                  ← TypeScript source (reference only)
│   │   └── package.json
│   └── @awaazlabs-uva/agents/              ← Server SDK (@awaazlabs-uva/agents) — no hardcoded secrets
│       ├── dist/                 ← Compiled JS + TypeScript declarations
│       ├── src/                  ← TypeScript source (reference only)
│       └── package.json
│
└── docs/
    ├── INTEGRATION_GUIDE.md      ← This file
    ├── ai-integration-guide.md   ← Copy-paste prompt for AI coding assistants
    └── credentials-template.md   ← Credential placeholders (filled by Finova)
```

> [!NOTE]
> The `dist/` folder inside each SDK package is the compiled, ready-to-use output.
> You do **not** need to build anything. `npm install` will wire up the `dist/` files directly.
> The `src/` folder is included for reference and transparency only.

### Extraction Steps

If you received the package as a `.zip` archive:

**macOS / Linux:**
```bash
unzip client-submission.zip -d ./client-submission
cd client-submission
```

**Windows (PowerShell):**
```powershell
Expand-Archive -Path client-submission.zip -DestinationPath .\client-submission
cd .\client-submission
```

---

## 3. Installing the Browser SDK (`@awaazlabs-uva/voice`)

> [!NOTE]
> **Why `npm install` from a local `.tgz` file?**
> `@awaazlabs-uva/voice` is a **private package** — it is not published on the public npm registry.
> Finova delivers it directly as `client-submission/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz`.
> The install command below tells npm to treat that local package file exactly as it would
> a registry package, with `dist/` wired as the runtime entry point.
>
> **What does the package contain?** Zero Finova secrets. It is a WebRTC session
> management library that only ever calls *your own backend's* session endpoint.
> It is safe to bundle and ship publicly.

In your **frontend project's** root directory, run:

```bash
# Replace the path with the actual path to this package file on your machine
npm install /absolute/path/to/client-submission/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz

# Or using a relative path from your frontend project root:
npm install ../../client-submission/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz
```

This adds the following to your frontend `package.json`:

```json
{
  "dependencies": {
    "@awaazlabs-uva/voice": "file:../../client-submission/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz"
  }
}
```

You can then import it in your code exactly as you would any npm package:

```typescript
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';
```

### Required Peer Dependency

`@awaazlabs-uva/voice` requires `livekit-client` (the WebRTC transport layer). Install it alongside:

```bash
npm install livekit-client@^2.0.0
```

### Verify Installation

```bash
node -e "const {AwaazLabsUvaVoice} = require('@awaazlabs-uva/voice'); console.log('OK:', typeof AwaazLabsUvaVoice);"
# Expected output: OK: function
```

---

## 4. Installing the Server SDK (`@awaazlabs-uva/agents`)

> [!WARNING]
> **Install this package in your BACKEND only.**
> Never add `@awaazlabs-uva/agents` to a frontend/browser project's `package.json`.
> It is the signing library your backend uses with your `UVA_HMAC_SECRET` — if
> bundled into a browser build, your secret would be exposed in the client bundle.

> [!NOTE]
> **Why `npm install` from a local `.tgz` file?**
> Same reason as above — `@awaazlabs-uva/agents` is a private package delivered in this folder,
> not on the public npm registry. The package code itself contains **no hardcoded
> Finova credentials.** It is a pure signing/HTTP client that you initialise at
> runtime by passing in your own credentials from environment variables.

In your **Node.js backend project's** root directory:

```bash
# Replace the path with the actual path to this package file on your machine
npm install /absolute/path/to/client-submission/sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz

# Or using a relative path from your backend project root:
npm install ../../client-submission/sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
```

This adds the following to your backend `package.json`:

```json
{
  "dependencies": {
    "@awaazlabs-uva/agents": "file:../../client-submission/sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz"
  }
}
```

You can then import it in your backend code:

```typescript
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';
```

### Peer Dependencies

`@awaazlabs-uva/agents` has **no external peer dependencies** — it uses only Node.js built-in
modules (`node:crypto`, `node:util`). Node.js ≥ 18.0.0 is required.

### Verify Installation

```bash
node -e "import('@awaazlabs-uva/agents').then(m => console.log('OK:', typeof m.AwaazLabsUvaAgentsClient));"
# Expected output: OK: function
```

---

## 5. Environment Configuration

Your application uses environment variables to supply credentials and endpoint URLs to the SDK. **Never hardcode these values in source code.**

### Backend Environment (`.env` in your Node.js project)

Create a `.env` file in your backend project root:

```env
# ─── Server Port ─────────────────────────────────────────────
PORT=3100

# ─── AwaazLabs-UVA Session Upstream ──────────────────────────
# Backend-only AwaazLabs-UVA session upstream config (provided during onboarding)
UVA_SESSION_UPSTREAM_URL=[BACKEND_ONLY_SESSION_UPSTREAM_URL]

# ─── Finova Portal API ───────────────────────────────────────
# URL of the Finova-hosted tenant portal API (provided during onboarding)
UVA_PORTAL_API_URL=[YOUR_PORTAL_API_URL]

# ─── Tenant Credentials (SERVER-SIDE ONLY) ───────────────────
# Your tenant UUID — identifies your organisation
UVA_TENANT_ID=[YOUR_TENANT_ID]

# Your HMAC secret — backend only; never expose it to the browser
# THIS IS A SECRET. NEVER EXPOSE IT TO THE BROWSER.
UVA_HMAC_SECRET=[YOUR_HMAC_SECRET]

# ─── Publishable Key (safe for browser) ──────────────────────
# Passed through to your frontend; identifies your tenant publicly
UVA_PUBLISHABLE_KEY=[YOUR_PUBLISHABLE_KEY]

# ─── CORS & Public URL ───────────────────────────────────────
HOST_ALLOWED_ORIGINS=http://localhost:5174
HOST_PUBLIC_BASE_URL=http://localhost:3100
```

### Frontend Environment (`.env` in your Vite / CRA project)

Create a `.env` file in your frontend project root:

```env
# ─── Public Key (safe for the browser) ───────────────────────
VITE_UVA_PUBLISHABLE_KEY=[YOUR_PUBLISHABLE_KEY]

# ─── Backend Session Endpoints (your own backend — NOT Finova's) ─
VITE_UVA_SESSION_ENDPOINT=http://localhost:3100/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=http://localhost:3100/api/voice/session/refresh
VITE_UVA_VOICE_CATALOG_ENDPOINT=http://localhost:3100/api/voices

# ─── Agent ID ────────────────────────────────────────────────
# The UUID of the AI agent to connect to (create one via @awaazlabs-uva/agents first)
VITE_UVA_AGENT_ID=[YOUR_AGENT_ID]
```

> **Note for Next.js:** Replace `VITE_` prefixes with `NEXT_PUBLIC_` for public variables. Keep secret variables (like `UVA_HMAC_SECRET`) without any prefix — they will never be bundled into the client.

---

## 6. Backend Integration: Session Endpoint

Your backend must expose a **session minting endpoint**. The browser SDK posts to this endpoint to obtain a short-lived LiveKit token. **Your backend — not the browser — owns all upstream session-service credentials and signing.**

### Browser-Facing Express.js Shape

```typescript
import express from 'express';

const app = express();
app.use(express.json());

const {
  UVA_PUBLISHABLE_KEY,
} = process.env;

const sessionClient = createAwaazLabsSessionClientFromSecureBackendConfig();

// Session mint endpoint — called by the browser SDK
app.post('/api/voice/session', async (req, res) => {
  const { publishableKey, agentId } = req.body;

  if (!publishableKey || !agentId) {
    return res.status(400).json({ error: 'publishableKey and agentId are required' });
  }

  if (publishableKey !== UVA_PUBLISHABLE_KEY) {
    return res.status(401).json({ error: 'unknown publishable key' });
  }

  try {
    const session = await sessionClient.createSession({
      publishableKey,
      agentId,
      origin: req.get('origin'),
    });
    return res.json(session);
  } catch (error) {
    return res.status(mapSessionErrorToStatus(error)).json({ error: mapSessionErrorToCode(error) });
  }
});

app.listen(Number(process.env.PORT ?? 3100));
```

`createAwaazLabsSessionClientFromSecureBackendConfig()` represents the Finova-provided backend-only
session adapter or approved host-backend starter. Keep its upstream URL and signing implementation
out of frontend code, browser bundles, AI prompts, and public client docs.

### Session Response Shape

Your endpoint must return (or proxy) the following JSON to the browser:

```json
{
  "token": "<short-lived LiveKit JWT>",
  "wsUrl": "wss://livekit.example.com",
  "roomName": "room_abc123",
  "refreshUrl": "https://your-backend.com/api/voice/session/refresh",
  "expiresIn": 120
}
```

---

## 7. Frontend Integration: Voice Session

### React Example (TypeScript)

```tsx
import { useEffect, useRef, useState } from 'react';
import { AwaazLabsUvaVoice, AwaazLabsUvaVoiceError } from '@awaazlabs-uva/voice';

export function VoiceWidget() {
  const agentRef = useRef<AwaazLabsUvaVoice | null>(null);
  const [connected, setConnected] = useState(false);
  const [transcript, setTranscript] = useState<string[]>([]);
  const [audioBlocked, setAudioBlocked] = useState(false);

  useEffect(() => {
    agentRef.current = new AwaazLabsUvaVoice({
      publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
      sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT,
      refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT,
    });
  }, []);

  const handleConnect = async () => {
    const agent = agentRef.current!;
    agent.on('connected', () => setConnected(true));
    agent.on('disconnected', () => setConnected(false));
    agent.on('transcript', (e) => {
      if (e.final) setTranscript((prev) => [...prev, e.text]);
    });
    agent.on('error', (err: AwaazLabsUvaVoiceError) => console.error(err.code, err.message));
    agent.on('audio_blocked', (blocked) => setAudioBlocked(blocked));

    await agent.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
  };

  const handleDisconnect = () => agentRef.current?.disconnect();

  return (
    <div>
      {audioBlocked && (
        <button onClick={() => agentRef.current?.startAudio()}>
          🔊 Unlock Audio
        </button>
      )}
      <button onClick={connected ? handleDisconnect : handleConnect}>
        {connected ? 'Disconnect' : 'Connect'}
      </button>
      <ul>
        {transcript.map((t, i) => <li key={i}>{t}</li>)}
      </ul>
    </div>
  );
}
```

### Vanilla JS Example

```html
<script type="module">
  import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

  const agent = new AwaazLabsUvaVoice({
    publishableKey: 'YOUR_PUBLISHABLE_KEY',
    sessionEndpoint: 'http://localhost:3100/api/voice/session',
  });

  agent.on('transcript', (e) => {
    if (e.final) console.log('Transcript:', e.text);
  });

  agent.on('audio_blocked', (blocked) => {
    if (blocked) document.getElementById('unlock-btn').style.display = 'block';
  });

  document.getElementById('connect-btn').addEventListener('click', () => {
    agent.connect({ agentId: 'YOUR_AGENT_ID' });
  });

  document.getElementById('unlock-btn').addEventListener('click', () => {
    agent.startAudio(); // Must be called inside a user gesture
  });
</script>
```

---

## 8. Agent Management: Creating & Listing Agents

Use `@awaazlabs-uva/agents` in your **backend only** to programmatically manage AI agents.

```typescript
import { AwaazLabsUvaAgentsClient, AwaazLabsUvaAgentsError } from '@awaazlabs-uva/agents';

const agents = new AwaazLabsUvaAgentsClient({
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
  baseUrl: process.env.UVA_PORTAL_API_URL!,
});

// Create a new Urdu AI agent
const newAgent = await agents.createAgent({
  name: 'Customer Support Agent',
  prompt: 'آپ ایک مددگار اردو کسٹمر سروس نمائندے ہیں۔ مہربانی سے ہر سوال کا مفید جواب دیں۔',
  voiceId: 'helpdesk-agent', // Use your backend voice catalog endpoint for available IDs
  llmModel: 'gemini-2.5-flash', // Optional; defaults to gemini-2.5-flash
  // Optional (see @awaazlabs-uva/agents' README for the full list): agentLanguage, sttProvider,
  // sttModel, sttOptions, llmProvider, llmOptions, ttsProvider, ttsVoiceId, ttsOptions.
  // Omit all of them for the current default (ur + Gladia + Gemini + Uplift) — unchanged.
});

console.log('Created agent ID:', newAgent.id);
// → Pass newAgent.id to your frontend's VITE_UVA_AGENT_ID

// List all agents for this tenant
const allAgents = await agents.listAgents();

// Update an existing agent
await agents.updateAgent(newAgent.id, {
  prompt: 'Updated Urdu prompt here...',
  voiceId: 'new-voice-id',
});
```

### Listing Available Voices (Browser or Server)

```typescript
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const voices = await AwaazLabsUvaVoice.listVoices(import.meta.env.VITE_UVA_VOICE_CATALOG_ENDPOINT);
// Returns: [{ id, displayName, gender, previewUrl, artworkUrl, enabled }]
voices.filter(v => v.enabled).forEach(v => console.log(v.id, v.displayName));
```

---

## 9. Running the Reference Test App

The `test-app/` directory contains a ready-to-run reference implementation.

### Step 1: Configure Environment Variables

Fill in your credentials (see [Section 5](#5-environment-configuration)) in:
- `test-app/backend/.env`
- `test-app/frontend/.env`

### Step 2: Install and Start the Backend

```bash
cd test-app/backend
npm install
npm run dev
# Server starts on http://localhost:3100
```

### Step 3: Install and Start the Frontend

Open a **second terminal**:

```bash
cd test-app/frontend
npm install
npm run dev
# UI opens on http://localhost:5174
```

### Step 4: Test the Integration

1. Open `http://localhost:5174` in your browser
2. Under **Agent Management**, click **Create Agent** and configure an Urdu voice + system prompt
3. Click **Use as Agent ID** on the new agent
4. Click **Connect** to start a WebRTC session
5. Speak into your microphone — transcriptions appear in real time

---

## 10. Event Reference

### `@awaazlabs-uva/voice` — `AwaazLabsUvaVoice` Events

| Event | Payload Type | Description |
|---|---|---|
| `connected` | `void` | Session established and microphone active |
| `disconnected` | `string \| undefined` | Session ended (LiveKit reason code when available) |
| `ended` | `string \| undefined` | Same as `disconnected`; convenience alias |
| `transcript` | `{ text: string, final: boolean }` | Incremental and final transcription segments |
| `speaking` | `boolean` | Any room participant is actively speaking |
| `agent_speaking` | `boolean` | The AI agent specifically is speaking |
| `metrics_updated` | `MetricsEvent` | Latency/performance metrics emitted by the agent worker |
| `error` | `AwaazLabsUvaVoiceError` | SDK-level error with a typed `code` |
| `audio_blocked` | `boolean` | Browser blocked audio autoplay; show an unlock button |

---

## 11. Error Reference

### `@awaazlabs-uva/voice` — `AwaazLabsUvaVoiceError` Codes

| Code | HTTP Status | Cause |
|---|---|---|
| `quota_exceeded` | 429 | Tenant concurrency or monthly quota reached |
| `agent_not_found` | 404 | The `agentId` does not exist for this tenant |
| `session_failed` | Any other | Misconfigured backend, bad signing, network error |

### `@awaazlabs-uva/agents` — `AwaazLabsUvaAgentsError`

| Status | Cause |
|---|---|
| `401` | Bad HMAC signature, replayed nonce, or expired timestamp |
| `403` | Tenant account is suspended |
| `404` | Agent ID not found (for `updateAgent`) |
| `429` | Rate limited |

---

## 12. Security Checklist

Before deploying to production, verify the following:

- [ ] `UVA_HMAC_SECRET` is only in your **backend** `.env` file — never in frontend code
- [ ] `UVA_TENANT_ID` is only in your **backend** `.env` file
- [ ] `UVA_PUBLISHABLE_KEY` is the **only** AwaazLabs-UVA credential in your frontend `.env`
- [ ] `.env` files are listed in `.gitignore` — never committed to version control
- [ ] Your session endpoint validates `publishableKey` against expected value before minting
- [ ] `VITE_UVA_VOICE_CATALOG_ENDPOINT` points to your backend, never to AwaazLabs-UVA infrastructure
- [ ] CORS is restricted to your known frontend origin (`HOST_ALLOWED_ORIGINS`)
- [ ] `@awaazlabs-uva/agents` is NOT listed in your frontend `package.json`
- [ ] Your bundler is not accidentally including `@awaazlabs-uva/agents` in the client build

---

## 13. Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `quota_exceeded` immediately | Monthly or concurrent quota hit | Contact Finova support to check quota |
| `agent_not_found` | Wrong `agentId` or wrong tenant | Verify agent was created under this tenant ID |
| `session_failed` immediately | Misconfigured backend or session adapter | Check backend-only session upstream configuration and logs |
| Audio plays on agent connect but then stops | Browser autoplay policy | Listen for `audio_blocked` event and call `agent.startAudio()` in a click handler |
| Browser reaches AwaazLabs-UVA upstream directly | Frontend calling wrong URL | The browser SDK must call **your backend** session endpoint, never AwaazLabs-UVA upstream services directly |
| `401 Unauthorized` from portal API | Bad HMAC secret or clock drift > 5 min | Verify `UVA_HMAC_SECRET` and ensure server clock is synced |
| TypeScript errors on import | Missing `dist/` folder | Run `npm run build` inside the SDK package directory |
| `ERR_REQUIRE_ESM` | Importing `@awaazlabs-uva/agents` with CommonJS `require()` | Use `import()` syntax; `@awaazlabs-uva/agents` is ESM-only |

---

*For support, contact your Finova Solutions account manager.*
