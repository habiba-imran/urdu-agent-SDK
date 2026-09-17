# Client Quickstart

This guide is the fastest supported path for a client team integrating the AwaazLabs-UVA-Voice SDK.

For the full client handoff package, including what AwaazLabs-UVA provides, which values go where, and the
exact onboarding checklist, see `docs/CLIENT_HANDOFF_GUIDE.md`.

It assumes you are using the reference materials already present in this repo:

- browser app: `demo-app/frontend/`
- host-owned backend: `demo-app/backend/`
- browser SDK package: `sdk/` (`@awaazlabs-uva/voice`)
- server SDK package: `sdk-server/` (`@awaazlabs-uva/agents`, optional — agent management from your backend)

## What the client receives

A client integration needs these values from the AwaazLabs-UVA team:

- `publishableKey`
- `tenantId`
- raw tenant HMAC secret
- `agentId`
- backend-only session upstream configuration

The HMAC secret belongs on the client's backend only. Never put it in browser code.

## Architecture in one sentence

Browser SDK -> host backend -> AwaazLabs-UVA session service -> LiveKit worker.

The browser never signs requests or calls AwaazLabs-UVA upstream services itself.

## Step 1: install the SDK

```bash
npm install @awaazlabs-uva/voice
```

## Step 2: run the host backend

Use `demo-app/backend/`. It depends on the local `sdk-server/` package, so from `demo-app/` run
`npm run build:sdk` and `npm run install:all` once first.

Copy:

```bash
cp .env.example .env
```

Set:

- `UVA_CONTROL_PLANE_URL` — the session upstream, supplied through the secure onboarding channel
- `UVA_API_BASE_URL` — tenant API base URL (only needed for the optional agent listing)
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

If you are using `demo-app/frontend/`, copy `.env.example` to `.env` and set:

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
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const agent = new AwaazLabsUvaVoice({
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

- the browser calls the host backend, not AwaazLabs-UVA upstream services directly
- `POST /api/voice/session` returns `token`, `wsUrl`, and `roomName`
- the browser connects to LiveKit
- voice transcript events appear
- refresh happens through `/api/voice/session/refresh`

## Common mistakes

- putting the raw HMAC secret in frontend code
- calling the AwaazLabs-UVA session service directly from the browser
- forgetting to forward the browser `Origin` header from the host backend to the session upstream
- exposing backend-only upstream URLs or signing details in frontend docs/code
- setting different session and refresh routes than the SDK expects

## Browser-facing error meanings

| Error | What it usually means |
|---|---|
| `quota_exceeded` | tenant cap reached |
| `rate_limit` | too many session requests for this tenant in the last minute — back off |
| `provider_limit` | upstream voice/LLM provider limit, not your plan quota |
| `worker_not_ready` | voice worker not ready to take the call yet |
| `agent_not_found` | wrong `agentId` or wrong tenant |
| `timeout` | host backend did not answer within `fetchTimeoutMs` (default 15s) |
| `token_refresh_failed` | refresh rejected, or retries ran out before the token expired |
| `session_failed` | host backend misconfiguration or upstream failure |

The full taxonomy is in `sdk/README.md`.

## Files to hand to a client team

For a real onboarding handoff, send:

- `sdk/README.md`
- `docs/CLIENT_QUICKSTART.md`
- `docs/HOST_BACKEND_CONTRACT.md`
- `demo-app/` (reference host backend + browser client)
