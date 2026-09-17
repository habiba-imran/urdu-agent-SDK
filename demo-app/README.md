# UVA Demo App

Local host-backend + browser client for Wave 1 SDK smoke (`@awaazlabs-uva/voice`).

Mirrors the client-submission architecture:

- **frontend** — browser-only voice SDK (`publishableKey` + session endpoints)
- **backend** — signs control-plane session mint/refresh; optionally lists agents via `@awaazlabs-uva/agents`

## Layout

```text
demo-app/
  backend/     Express host (session + refresh)
  frontend/    Vite black/white UI
```

## Prerequisites

1. Dev DB reachable (used by `scripts/create_new_client.py`)
2. Control plane on `UVA_CONTROL_PLANE_URL` (default `http://localhost:8000`)
3. LiveKit worker running if you want a real spoken call
4. Built local voice package: `cd sdk && npm run build`

## Credentials already provisioned for this folder

Created with `python scripts/create_new_client.py "demo-app Habiba Wave1"` plus a DB agent insert:

| Value | Where |
| --- | --- |
| Tenant / publishable key | `backend/.env`, `frontend/.env` |
| HMAC secret | `backend/.env` only |
| Agent ID | `frontend/.env` → `VITE_UVA_AGENT_ID` |

Do **not** commit real `.env` files (gitignored). `.env.example` stays empty of secrets.

## Install

```bash
cd demo-app
npm run build:sdk
npm run install:all
```

## Run

Terminal 1 — backend:

```bash
cd demo-app
npm run dev:backend
```

Terminal 2 — frontend:

```bash
cd demo-app
npm run dev:frontend
```

Open `http://localhost:5173`.

1. Wait for **Language / STT / LLM / TTS** dropdowns to load (needs portal `UVA_API_BASE_URL` on the backend).
2. Pick a valid combo (options are filtered to **enabled** capabilities for that language).
3. Click **Connect** — backend PATCHes the agent pipeline, then the voice SDK mints + joins.

Urdu typically: Gladia + Gemini + Uplift.  
English typically: Gladia/Deepgram + Gemini/Groq + Cartesia/ElevenLabs/Rime.

**Provider flips / greeting cache:** changing Language / STT / LLM / TTS applies the pipeline in the background; Connect skips the ~10s portal PATCH when the combo is already on the agent. After a provider change, wait for the debug log “Background pipeline applied” (or ~1–2s) before Connect. Greeting PCM cache is per worker process and keyed by provider + voice + text + channel.

**Local speed:** worker defaults to `UVA_SESSION_RECORD_AUDIO=0` (no RecorderIO on `session.start`). Set `=1` in `.env.local` if you need session recordings.

## Packages

| Package | Source |
| --- | --- |
| `@awaazlabs-uva/voice` | `file:../../sdk` (current Wave 1 code) |
| `@awaazlabs-uva/agents` | `file:../../sdk-server` (backend listAgents helper) |

Same integration model as `client-submission_v2` (voice in browser, agents/HMAC on backend).
