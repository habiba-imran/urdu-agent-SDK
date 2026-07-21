# Host Backend Node Starter

Reference host-owned backend for `@uva/voice`.

This example is the missing middle layer between:

- the browser SDK
- the host platform's HMAC secret
- the UVA control plane

It is intentionally small and single-tenant so a client team can understand the integration path
without inheriting unrelated product code.

## What it does

- exposes `POST /api/voice/session`
- exposes `POST /api/voice/session/refresh`
- validates the browser-facing `publishableKey`
- signs control-plane session requests with the tenant HMAC secret
- forwards token refresh to the control plane
- rewrites `refreshUrl` back to the host backend

## Environment

Copy `.env.example` to `.env` and set:

- `UVA_CONTROL_PLANE_URL`
- `UVA_TENANT_ID`
- `UVA_HMAC_SECRET`
- `UVA_PUBLISHABLE_KEY`
- `HOST_ALLOWED_ORIGINS`
- optional `HOST_PUBLIC_BASE_URL`
- optional `PORT`

## Run

```bash
npm install
npm run dev
```

The service listens on `http://localhost:3000` by default.

## Pair with the browser example

Use these browser example env values:

```env
VITE_UVA_PUBLISHABLE_KEY=<same as UVA_PUBLISHABLE_KEY>
VITE_UVA_SESSION_ENDPOINT=http://localhost:3000/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=http://localhost:3000/api/voice/session/refresh
VITE_UVA_AGENT_ID=<real agent id>
```

Then run `examples/basic-web-client/` and the browser example can connect through this starter.
