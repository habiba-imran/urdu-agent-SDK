# Basic Web Client

This is the browser-side Phase 3 example consumer app for `@awaazlabs-uva/voice`.

## What it demonstrates

- browser-side `@awaazlabs-uva/voice` usage
- config loaded from environment variables
- connect and disconnect controls
- transcript rendering
- caller and agent speaking state
- metrics and error output

## Pairing backend

This app is meant to be run with [examples/host-backend](../host-backend/README.md), the
reference host-owned backend starter that delegates to the backend-only session service and relays
refresh safely.

## Environment

Copy `.env.example` to `.env` and set:

- `VITE_UVA_PUBLISHABLE_KEY`
- `VITE_UVA_SESSION_ENDPOINT`
- `VITE_UVA_REFRESH_ENDPOINT`
- `VITE_UVA_AGENT_ID`

## Run

```bash
npm install
npm run dev
```

For a full local pairing:

1. Start `examples/host-backend/`
2. Point `VITE_UVA_SESSION_ENDPOINT` at `http://localhost:3000/api/voice/session`
3. Point `VITE_UVA_REFRESH_ENDPOINT` at `http://localhost:3000/api/voice/session/refresh`
