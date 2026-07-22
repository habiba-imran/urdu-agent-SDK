# Client Quickstart

This guide is the fastest supported path for a client team integrating the Urdu Voice Agent SDK.

For the full client handoff package, including what UVA provides, which values go where, and the
exact onboarding checklist, see `docs/CLIENT_HANDOFF_GUIDE.md`.

It assumes you are using the reference materials already present in this repo:

- browser app: `examples/basic-web-client/`
- host-owned backend: `examples/host-backend-node/`
- SDK package: `sdk/`

## What the client receives

A client integration needs these values from the UVA team:

- `publishableKey`
- `tenantId`
- raw tenant HMAC secret
- `agentId`
- control-plane base URL

The HMAC secret belongs on the client's backend only. Never put it in browser code.

## Architecture in one sentence

Browser SDK -> host backend -> UVA control plane -> LiveKit worker.

The browser never signs control-plane requests itself.

## Step 1: install the SDK

```bash
npm install @uva/voice
```

## Step 2: run the host backend starter

Use `examples/host-backend-node/`.

Copy:

```bash
cp .env.example .env
```

Set:

- `UVA_CONTROL_PLANE_URL`
- `UVA_TENANT_ID`
- `UVA_HMAC_SECRET`
- `UVA_PUBLISHABLE_KEY`
- `HOST_ALLOWED_ORIGINS`
- optional `HOST_PUBLIC_BASE_URL`
- optional `PORT`

Start it:

```bash
npm install
npm run dev
```

By default it listens on `http://localhost:3000`.

## Step 3: configure the browser example or your own app

If you are using `examples/basic-web-client/`, copy `.env.example` to `.env` and set:

- `VITE_UVA_PUBLISHABLE_KEY`
- `VITE_UVA_SESSION_ENDPOINT=http://localhost:3000/api/voice/session`
- `VITE_UVA_REFRESH_ENDPOINT=http://localhost:3000/api/voice/session/refresh`
- `VITE_UVA_AGENT_ID`

Run it:

```bash
npm install
npm run dev
```

## Step 4: minimal integration code

```ts
import { UrduVoiceAgent } from '@uva/voice';

const agent = new UrduVoiceAgent({
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
  sessionEndpoint: 'http://localhost:3000/api/voice/session',
  refreshEndpoint: 'http://localhost:3000/api/voice/session/refresh',
});

agent.on('connected', () => console.log('connected'));
agent.on('transcript', (entry) => console.log(entry));
agent.on('error', (error) => console.error(error.code, error.message));

await agent.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
```

## Step 5: verify the integration

Successful integration means:

- the browser calls the host backend, not the control plane directly
- `POST /api/voice/session` returns `token`, `wsUrl`, and `roomName`
- the browser connects to LiveKit
- voice transcript events appear
- refresh happens through `/api/voice/session/refresh`

## Common mistakes

- putting the raw HMAC secret in frontend code
- sending `agentId` directly to `/v1/session` from the browser
- forgetting to forward the browser `Origin` header from the host backend to the control plane
- using `agentId` instead of `agent_id` in the host-backend request body to the control plane
- setting different session and refresh routes than the SDK expects

## Browser-facing error meanings

| Error | What it usually means |
|---|---|
| `quota_exceeded` | tenant cap reached |
| `agent_not_found` | wrong `agentId` or wrong tenant |
| `session_failed` | host backend misconfiguration, signing issue, refresh issue, or upstream failure |

## Files to hand to a client team

For a real onboarding handoff, send:

- `sdk/README.md`
- `docs/CLIENT_QUICKSTART.md`
- `docs/HOST_BACKEND_CONTRACT.md`
- `examples/host-backend-node/`
- `examples/basic-web-client/`
