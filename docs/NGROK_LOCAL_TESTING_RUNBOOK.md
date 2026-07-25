# ngrok Local Testing Runbook

This document explains how to temporarily test the Urdu Voice Agent SDK with:

- the `worker` running locally on our machine
- the `host backend` running locally on our machine
- `ngrok` exposing the local backend to the internet
- the client or another tester running the frontend on their own machine

This is a **temporary testing workaround**, not the final production deployment plan.

## Why we need this

The current blocker is the hosted worker environment.

Right now:

- the control plane is live
- the dashboard/backend flows are working
- the SDK/browser flow works locally
- but the Render worker can run out of memory and restart

Because of that, we need a temporary way for an external tester or client to test the SDK without
depending on the unstable hosted worker.

## The idea in one sentence

We keep the worker and backend on our local machine, and expose the local backend with `ngrok` so an
external frontend can connect through it.

## Important clarification

`ngrok` does **not** replace the worker.

What `ngrok` does:

- exposes our local HTTP backend to the public internet over HTTPS

What `ngrok` does **not** do:

- add memory to the worker
- fix Render memory issues
- host the worker itself

So the correct temporary setup is:

`External frontend -> ngrok URL -> our local host backend -> UVA control plane -> our local worker via LiveKit`

## Official ngrok behavior

According to ngrok's docs:

- `ngrok http <port>` exposes a local HTTP service on a public URL
- the ngrok agent creates an outbound TLS connection to ngrok's cloud
- no inbound port opening is required
- HTTPS is automatically provisioned on the public URL

Official references:

- ngrok quickstart: https://ngrok.com/docs/getting-started?os=windows
- ngrok CLI `http`: https://ngrok.com/docs/agent/cli
- how tunnels work: https://ngrok.com/docs/guides/share-localhost/tunnels

## What must run locally on our machine

For this workaround, we run these three things locally:

1. `worker`
2. `host backend`
3. `ngrok` tunnel for the host backend

Optional:

4. local browser example for our own verification

## Current integration values

Use these current demo/staging values:

| Value | Current value |
|---|---|
| `publishableKey` | `bb8fa755-4175-4a6f-8789-d315d8d6c449` |
| `tenantId` | `bb8fa755-4175-4a6f-8789-d315d8d6c449` |
| raw tenant `HMAC secret` | `7PzQCfjC01Ri3f6f88NCnB2qNSEgvNPQ9lGUnZ6Z8iw` |
| `agentId` | `aa3898ac-312d-43ea-8930-0b4776475a16` |
| control-plane base URL | `https://uva-control-plane-staging.onrender.com` |

## Before you start

Make sure:

- the worker can run locally on this machine
- the backend can run locally on this machine
- the machine stays on during testing
- the internet connection is stable
- the tester/client understands this is a temporary test setup

## Step 1: install and connect ngrok

### 1. Create an ngrok account

Create an account at:

- https://ngrok.com/

### 2. Install ngrok

Follow the official Windows quickstart:

- https://ngrok.com/docs/getting-started?os=windows

### 3. Add your auth token

Run:

```powershell
ngrok config add-authtoken YOUR_NGROK_AUTH_TOKEN
```

Replace `YOUR_NGROK_AUTH_TOKEN` with the value from your ngrok dashboard.

## Step 2: run the local worker

From repo root:

```powershell
cd C:\Users\habib\urdu-agent-SDK
py -m worker.main dev
```

What success looks like:

- the worker starts
- it registers successfully to LiveKit
- you do **not** see immediate crash/restart behavior

Important:

- the worker is not exposed with ngrok
- it connects outward to LiveKit by itself

## Step 3: create and run the local host backend

Use:

- `examples/host-backend-node/`

### Backend `.env`

Create:

`examples/host-backend-node/.env`

Use:

```env
PORT=3000
UVA_CONTROL_PLANE_URL=https://uva-control-plane-staging.onrender.com
UVA_TENANT_ID=bb8fa755-4175-4a6f-8789-d315d8d6c449
UVA_HMAC_SECRET=7PzQCfjC01Ri3f6f88NCnB2qNSEgvNPQ9lGUnZ6Z8iw
UVA_PUBLISHABLE_KEY=bb8fa755-4175-4a6f-8789-d315d8d6c449
HOST_ALLOWED_ORIGINS=http://localhost:5173
HOST_PUBLIC_BASE_URL=http://localhost:3000
```

### Run backend

```powershell
cd C:\Users\habib\urdu-agent-SDK\examples\host-backend-node
npm install
npm run dev
```

What success looks like:

- backend starts without errors
- backend listens on `http://localhost:3000`

## Step 4: expose the local backend with ngrok

Run:

```powershell
ngrok http 3000
```

ngrok will give you a public HTTPS URL that looks something like:

```text
https://abc123.ngrok-free.app
```

This URL forwards to:

```text
http://localhost:3000
```

Important:

- this public URL is what the external tester/client will use
- on the free tier, the URL may change when ngrok restarts

## Step 5: update backend public base URL if needed

If the backend needs to return a public refresh URL that works for external testers, update:

`HOST_PUBLIC_BASE_URL`

to the ngrok URL.

Example:

```env
HOST_PUBLIC_BASE_URL=https://abc123.ngrok-free.app
```

Then restart the backend:

```powershell
cd C:\Users\habib\urdu-agent-SDK\examples\host-backend-node
npm run dev
```

Recommended backend `.env` after ngrok is known:

```env
PORT=3000
UVA_CONTROL_PLANE_URL=https://uva-control-plane-staging.onrender.com
UVA_TENANT_ID=bb8fa755-4175-4a6f-8789-d315d8d6c449
UVA_HMAC_SECRET=7PzQCfjC01Ri3f6f88NCnB2qNSEgvNPQ9lGUnZ6Z8iw
UVA_PUBLISHABLE_KEY=bb8fa755-4175-4a6f-8789-d315d8d6c449
HOST_ALLOWED_ORIGINS=http://localhost:5173
HOST_PUBLIC_BASE_URL=https://abc123.ngrok-free.app
```

Replace `https://abc123.ngrok-free.app` with your real ngrok URL.

## Step 6: CORS / allowed origins

The backend must allow the frontend origin that will call it.

### Case A: tester/client runs the frontend locally

If they run the Vite app locally, the browser origin is usually:

```text
http://localhost:5173
```

Then this is enough:

```env
HOST_ALLOWED_ORIGINS=http://localhost:5173
```

### Case B: tester/client runs a deployed frontend

If they run a deployed frontend, add that frontend origin too.

Example:

```env
HOST_ALLOWED_ORIGINS=http://localhost:5173,https://client-frontend.example.com
```

## Step 7: how the client/tester configures their frontend

The tester/client does **not** need the HMAC secret.

They only need these frontend values:

```env
VITE_UVA_PUBLISHABLE_KEY=bb8fa755-4175-4a6f-8789-d315d8d6c449
VITE_UVA_SESSION_ENDPOINT=https://abc123.ngrok-free.app/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=https://abc123.ngrok-free.app/api/voice/session/refresh
VITE_UVA_AGENT_ID=aa3898ac-312d-43ea-8930-0b4776475a16
```

Replace `https://abc123.ngrok-free.app` with the real ngrok URL.

## Step 8: how the client/tester runs the frontend

Use:

- `examples/basic-web-client/`

Create:

`examples/basic-web-client/.env`

Then run:

```powershell
cd C:\Users\habib\urdu-agent-SDK\examples\basic-web-client
npm install
npm run dev
```

Expected local frontend URL:

```text
http://localhost:5173
```

## Step 9: end-to-end test flow

Use this order:

1. Start local worker.
2. Start local host backend.
3. Start ngrok on port `3000`.
4. Confirm the ngrok HTTPS URL is active.
5. Update backend `HOST_PUBLIC_BASE_URL` to the ngrok URL if not already done.
6. Restart backend if `.env` changed.
7. Give the client/tester the frontend env values that point to the ngrok URL.
8. Client/tester runs the frontend on their own machine.
9. Client/tester clicks connect.
10. Confirm the browser connects and transcript events appear.

## How to test that the tunnel itself is working

Before testing the SDK, open the ngrok backend URL in a browser or use:

```powershell
curl.exe https://abc123.ngrok-free.app/api/voice/session
```

If called with `GET`, this may return a method error, which is okay.

The important thing is:

- the ngrok URL resolves
- it reaches your local backend

## How to test the SDK end to end

The SDK test is successful if:

| Check | Expected result |
|---|---|
| frontend calls the ngrok session endpoint | yes |
| local backend receives the request | yes |
| backend signs request to control plane | yes |
| control plane returns session token | yes |
| browser connects to LiveKit | yes |
| local worker receives the job | yes |
| transcript appears in the browser | yes |
| refresh works through the ngrok refresh endpoint | yes |

## What to watch in logs

### Worker logs

Expected signs:

- worker starts successfully
- worker registers to LiveKit
- job request is received
- session starts
- transcript / conversation activity appears

### Host backend logs

Expected signs:

- request hits `/api/voice/session`
- backend forwards to control plane
- backend returns token + wsUrl + roomName

### Frontend logs

Expected signs:

- connected state
- transcript events
- no immediate `session_failed`

## Common problems

### Problem: client cannot connect

Check:

- ngrok is still running
- the ngrok URL did not change
- `VITE_UVA_SESSION_ENDPOINT` and `VITE_UVA_REFRESH_ENDPOINT` use the correct ngrok URL

### Problem: CORS error

Check:

- `HOST_ALLOWED_ORIGINS`
- frontend origin matches the allowed origin

### Problem: refresh fails

Check:

- `HOST_PUBLIC_BASE_URL` is the ngrok URL, not `http://localhost:3000`

### Problem: worker still fails

Check:

- local worker is actually running
- local machine has enough memory
- LiveKit registration succeeded

### Problem: client can reach backend but voice flow still fails

Check:

- control plane is reachable
- `tenantId`, `HMAC secret`, and `agentId` are correct
- local worker is connected to LiveKit

## Limitations of this workaround

This setup is fine for temporary testing, but it has limits:

- your laptop must stay on
- your local worker must stay running
- your local backend must stay running
- ngrok free URLs may change when restarted
- this is not a production deployment

## What changes later when Render is upgraded

When the hosted worker is fixed later:

- the client SDK contract does not need to change
- the browser still uses the same SDK flow
- the only thing that changes is where the backend/session path points

That means:

- this ngrok setup is temporary
- it does not force a redesign of the client deliverables

## Final summary

Use ngrok only as a temporary public entry point for the local backend.

The real testing setup is:

- worker local
- backend local
- ngrok exposing backend
- external frontend points to ngrok URL

If that flow works, the client can test the SDK on their own system even while the hosted worker is
not stable.
