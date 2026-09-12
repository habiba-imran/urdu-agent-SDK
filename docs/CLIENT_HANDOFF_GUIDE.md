# Client Handoff Guide

This is the client-facing handoff document for integrating the AwaazLabs-UVA-Voice SDK.

It is written in simple language and is meant to answer these questions quickly:

- What are we getting from the AwaazLabs-UVA team?
- Which values do we need?
- Which values go in frontend code and which go in backend code?
- Which folders/files should we use?
- Which commands should we run?
- How do we know the integration is working?

## Start Here

If you only read one section first, read this one.

To get the SDK working on your system, do these steps in order:

1. Get the handoff package from the AwaazLabs-UVA team.
2. Open `examples/host-backend/`.
3. Create `.env` in that folder and paste the backend values from this document.
4. Run the backend with `npm install` and `npm run dev`.
5. Open `examples/web-client/`.
6. Create `.env` in that folder and paste the frontend values from this document.
7. Run the frontend with `npm install` and `npm run dev`.
8. Open the browser app.
9. Click connect.
10. Confirm that the browser connects and transcript events appear.

If all of that works, the integration is set up correctly.

## What the client receives from AwaazLabs-UVA

The client receives:

| Item | What it is | Why the client needs it |
|---|---|---|
| `publishableKey` | Browser-safe public identifier | Used by the browser SDK and backend validation |
| `tenantId` | Tenant UUID | Used by the backend-only session integration |
| raw tenant `HMAC secret` | Private signing secret | Used by the backend to generate the HMAC signature |
| `agentId` | Voice agent UUID | Used when the browser calls `connect({ agentId })` |
| backend-only session upstream URL | AwaazLabs-UVA session service URL | Used only by the client backend to mint sessions |
| SDK package | Browser SDK | Used in the client frontend |
| host backend starter | Example backend | Fastest supported backend integration path |
| browser example | Example frontend | Fastest supported frontend integration path |
| contract docs | Integration docs | Explains exact request/response format |

## Current AwaazLabs-UVA handoff values

The real integration values must be delivered through a secure channel. Do not paste live secrets,
tenant IDs, agent IDs, or upstream service URLs into this document.

| Value name | Current value | Used in | Provided by |
|---|---|---|---|
| `publishableKey` | `[YOUR_PUBLISHABLE_KEY_OR_TENANT_ID]` | frontend + backend | AwaazLabs-UVA |
| `tenantId` | `[YOUR_PUBLISHABLE_KEY_OR_TENANT_ID]` | backend only | AwaazLabs-UVA |
| raw tenant `HMAC secret` | `[YOUR_HMAC_SECRET]` | backend only | AwaazLabs-UVA |
| `agentId` | `[YOUR_AGENT_ID]` | frontend | AwaazLabs-UVA |
| backend-only session upstream URL | `[BACKEND_ONLY_SESSION_UPSTREAM_URL]` | backend only | AwaazLabs-UVA |

Important:

- These are placeholders only.
- Use the current demo/staging or production values delivered through the secure onboarding channel.
- The raw tenant `HMAC secret` must stay on the backend only.

## Very important security rule

The raw tenant `HMAC secret`:

- must go in backend environment variables only
- must never go in frontend code
- must never go in browser env files
- must never be committed to Git
- must never be exposed in public JavaScript

## Simple architecture

The browser does **not** talk to AwaazLabs-UVA upstream services directly.

The correct flow is:

`Browser app -> Client backend -> AwaazLabs-UVA session service -> LiveKit worker`

What this means:

- the browser uses `@awaazlabs-uva/voice`
- the browser asks the client's own backend for a session
- the client's backend signs the request using the tenant HMAC secret
- the AwaazLabs-UVA session service returns a LiveKit token
- the browser connects using that token

## Which files AwaazLabs-UVA sends to the client

The handoff package should include these files/folders:

| Path | What it is |
|---|---|
| `sdk/README.md` | Browser SDK guide |
| `docs/CLIENT_HANDOFF_GUIDE.md` | Main onboarding/handoff document |
| `docs/CLIENT_QUICKSTART.md` | Short setup guide |
| `docs/HOST_BACKEND_CONTRACT.md` | Exact API contract |
| `examples/host-backend/` | Reference backend starter |
| `examples/web-client/` | Reference frontend/browser app |

## Exactly what AwaazLabs-UVA must provide with this document

The AwaazLabs-UVA team should send the client these items together:

| Type | What AwaazLabs-UVA sends |
|---|---|
| Document | `docs/CLIENT_HANDOFF_GUIDE.md` |
| Document | `docs/CLIENT_QUICKSTART.md` |
| Document | `docs/HOST_BACKEND_CONTRACT.md` |
| Document | `sdk/README.md` |
| Code | `examples/host-backend/` |
| Code | `examples/web-client/` |
| Value | `publishableKey` |
| Value | `tenantId` |
| Value | raw tenant `HMAC secret` |
| Value | `agentId` |
| Value | backend-only session upstream URL |

What this means in simple words:

- the docs explain the integration
- the example backend gives them a working server-side starting point
- the example frontend gives them a working browser-side starting point
- the five integration values are the actual credentials/config they must plug in

## Which value goes where

This is the most important table for the client team.

| Value | Frontend? | Backend? | Notes |
|---|---|---|---|
| `publishableKey` | Yes | Yes | Safe for browser use |
| `tenantId` | No | Yes | Backend only |
| raw tenant `HMAC secret` | No | Yes | Secret, backend only |
| `agentId` | Yes | No | Used by browser `connect()` |
| backend-only session upstream URL | No | Yes | Backend only |

## What the client needs to build

The client needs two things:

### 1. Browser app

This app:

- uses `@awaazlabs-uva/voice`
- calls the client's backend session route
- connects to the selected voice agent

Reference folder:

`examples/web-client/`

### 2. Host-owned backend

This backend:

- receives browser session requests
- validates the `publishableKey`
- calls the AwaazLabs-UVA session service using backend-only credentials
- returns the session token to the browser
- handles refresh safely

Reference folder:

`examples/host-backend/`

## Backend setup

Use:

`examples/host-backend/`

### Step 1: create backend env file

Inside the backend folder:

```bash
cp .env.example .env
```

If you are on Windows and not using `cp`, just create a new file named `.env` and copy the values
below into it.

Then set:

```env
PORT=3000
UVA_SESSION_UPSTREAM_URL=[BACKEND_ONLY_SESSION_UPSTREAM_URL]
UVA_TENANT_ID=[YOUR_PUBLISHABLE_KEY_OR_TENANT_ID]
UVA_HMAC_SECRET=[YOUR_HMAC_SECRET]
UVA_PUBLISHABLE_KEY=[YOUR_PUBLISHABLE_KEY_OR_TENANT_ID]
HOST_ALLOWED_ORIGINS=http://localhost:5173
HOST_PUBLIC_BASE_URL=http://localhost:3000
```

### What each backend env var means

| Env var | Meaning |
|---|---|
| `PORT` | Local port for the backend |
| `UVA_SESSION_UPSTREAM_URL` | Backend-only AwaazLabs-UVA session upstream URL |
| `UVA_TENANT_ID` | Tenant UUID used in signing |
| `UVA_HMAC_SECRET` | Private HMAC signing secret |
| `UVA_PUBLISHABLE_KEY` | Browser-safe tenant identifier |
| `HOST_ALLOWED_ORIGINS` | Browser origins allowed to call this backend |
| `HOST_PUBLIC_BASE_URL` | Public base URL of the backend |

### Step 2: run backend

From `examples/host-backend/`:

```bash
npm install
npm run dev
```

Expected local backend URL:

```text
http://localhost:3000
```

What success looks like:

- the backend starts without errors
- it listens on port `3000`
- it is ready to receive browser session requests

## Frontend setup

Use:

`examples/web-client/`

### Step 1: create frontend env file

Inside the frontend folder:

```bash
cp .env.example .env
```

If you are on Windows and not using `cp`, just create a new file named `.env` and copy the values
below into it.

Then set:

```env
VITE_UVA_PUBLISHABLE_KEY=[YOUR_PUBLISHABLE_KEY_OR_TENANT_ID]
VITE_UVA_SESSION_ENDPOINT=http://localhost:3000/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=http://localhost:3000/api/voice/session/refresh
VITE_UVA_AGENT_ID=[YOUR_AGENT_ID]
```

### What each frontend env var means

| Env var | Meaning |
|---|---|
| `VITE_UVA_PUBLISHABLE_KEY` | Browser-safe tenant identifier |
| `VITE_UVA_SESSION_ENDPOINT` | Client backend route for new sessions |
| `VITE_UVA_REFRESH_ENDPOINT` | Client backend route for refresh |
| `VITE_UVA_AGENT_ID` | Voice agent to connect to |

### Step 2: run frontend

From `examples/web-client/`:

```bash
npm install
npm run dev
```

Expected local frontend URL:

```text
http://localhost:5173
```

What success looks like:

- the frontend starts without errors
- the browser opens the sample client app
- the app can call the backend session route

## Minimal SDK example

```ts
import { AwaazLabsUvaVoice } from '@awaazlabs-uva/voice';

const agent = new AwaazLabsUvaVoice({
  publishableKey: import.meta.env.VITE_UVA_PUBLISHABLE_KEY,
  sessionEndpoint: import.meta.env.VITE_UVA_SESSION_ENDPOINT,
  refreshEndpoint: import.meta.env.VITE_UVA_REFRESH_ENDPOINT,
});

agent.on('connected', () => console.log('connected'));
agent.on('transcript', (entry) => console.log(entry));
agent.on('error', (error) => console.error(error.code, error.message));

await agent.connect({ agentId: import.meta.env.VITE_UVA_AGENT_ID });
```

This is the key idea:

- the browser only needs `publishableKey`, `agentId`, and the backend session URLs
- the browser does **not** need the tenant secret

## What the client backend must do

The client backend must:

- expose `POST /api/voice/session`
- expose `POST /api/voice/session/refresh`
- validate the incoming `publishableKey`
- call the AwaazLabs-UVA session service only from the backend
- keep the upstream URL, signing details, tenant ID, and HMAC secret out of frontend code and docs
- return the minted session token back to the browser

Exact contract:

- see `docs/HOST_BACKEND_CONTRACT.md`

In simple words:

- the backend is the secure middle layer
- it protects the tenant secret
- it talks to the AwaazLabs-UVA session service on behalf of the browser

## What the client should never do

| Do not do this | Why |
|---|---|
| Put the raw tenant HMAC secret in frontend code | Security risk |
| Call AwaazLabs-UVA upstream services directly from the browser | Wrong integration model |
| Send `agentId` directly from the browser to the AwaazLabs-UVA session service | Browser must go through host backend |
| Expose backend-only upstream URLs or signing details in frontend docs/code | Infrastructure disclosure risk |
| Hardcode a stale session token in frontend code | Token expiry will break the app |

## How to verify the integration

The setup is working if:

| Check | Expected result |
|---|---|
| Browser calls the client backend | Yes |
| `POST /api/voice/session` succeeds | Yes |
| Backend creates session through backend-only upstream | Yes |
| Control plane returns `token`, `wsUrl`, `roomName` | Yes |
| Browser connects to LiveKit | Yes |
| Transcript events appear | Yes |
| Refresh works through `/api/voice/session/refresh` | Yes |

## Simple test flow for the client

After starting both apps, the client should do this:

1. Open the browser app.
2. Make sure the app is pointing to the local backend.
3. Click connect.
4. Wait for the connected state.
5. Speak into the microphone.
6. Confirm transcript events appear.
7. Leave the app connected long enough to confirm refresh still works.

If those steps pass, the integration is working.

## Common errors

| Error | Usually means |
|---|---|
| `quota_exceeded` | Tenant concurrency or monthly quota reached |
| `agent_not_found` | Wrong `agentId`, wrong tenant, or agent not attached to this tenant |
| `session_failed` | Bad backend configuration, wrong refresh route, malformed backend response, or upstream issue |

## Short client checklist

The client should do these steps in order:

1. Get the handoff package from AwaazLabs-UVA.
2. Put the backend values into `examples/host-backend/.env`.
3. Run the backend.
4. Put the frontend values into `examples/web-client/.env`.
5. Run the frontend.
6. Open the browser app.
7. Connect to the agent.
8. Confirm transcript and refresh are working.

## One-page summary

The client needs:

- the SDK
- the sample backend
- the sample frontend
- the five AwaazLabs-UVA-provided integration values

The client does **not** need:

- direct browser access to AwaazLabs-UVA upstream services
- the tenant secret in frontend code
- any manual session token pasted into the browser

## Short AwaazLabs-UVA checklist before sending

Before sending this package to a client, AwaazLabs-UVA should confirm:

| Check | Status should be |
|---|---|
| `publishableKey` ready | Yes |
| `tenantId` ready | Yes |
| raw tenant `HMAC secret` ready | Yes |
| `agentId` ready | Yes |
| backend-only session upstream configured | Yes |
| backend example works locally | Yes |
| frontend example works locally | Yes |
| secret is intended for this client/demo handoff | Yes |

## Final note

This document currently includes the active **demo/staging** integration values.  
If AwaazLabs-UVA later creates a separate production tenant for the client, this document must be updated
with the new production values before final delivery.
