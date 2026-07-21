# Basic Web Client

This is the Phase 0 example consumer app for `@uva/voice`.

## What it demonstrates

- browser-side `@uva/voice` usage
- config loaded from environment variables
- connect and disconnect controls
- transcript rendering
- caller and agent speaking state
- metrics and error output

## Current blocker

This app expects a **host-owned** session endpoint that speaks the SDK contract. That official
starter backend is planned for Phase 3, so this example is currently a frontend scaffold plus a
real integration target for that next phase.

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
