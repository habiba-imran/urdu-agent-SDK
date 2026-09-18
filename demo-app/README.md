# UVA Demo App (Wave 1)

Reference **host backend + browser client** for the Wave 1 deliverable:

> A host can `npm install @awaazlabs-uva/voice` (and `@awaazlabs-uva/agents` for the host backend), complete a **browser** call, and get snappy first audio.

| Package | Used by | Role |
| --- | --- | --- |
| `@awaazlabs-uva/voice` | `frontend/` | Browser SDK — publishable key + session endpoints only |
| `@awaazlabs-uva/agents` | `backend/` | Server SDK — HMAC agent list / capabilities / pipeline PATCH |

Telephony (`@awaazlabs-uva/telephony`) is **Wave 2** — not part of this demo.

## Layout

```text
demo-app/
  backend/     Express host (session mint/refresh + agents helpers)
  frontend/    Vite Wave 1 smoke UI
  scripts/     bootstrap-packages.mjs — npm install voice + agents
```

## Prerequisites

1. Control plane on `UVA_CONTROL_PLANE_URL` (default `http://localhost:8000`)
2. Tenant portal API on `UVA_API_BASE_URL` (provider picker / pipeline PATCH)
3. LiveKit worker running for a real spoken call
4. Credentials in `backend/.env` and `frontend/.env` (from `.env.example`)

## Install packages (npm)

From `demo-app/`:

```bash
npm run bootstrap      # prefer registry; else pack monorepo → npm install tarballs
npm run install:all   # express/vite + lockfile sync
```

`bootstrap` installs through **npm** (never a raw `file:../../sdk` source link):

1. If `@awaazlabs-uva/voice` / `@awaazlabs-uva/agents` are on the public registry → installs `^` versions from npmjs
2. If not published yet → `npm pack` from `sdk/` + `sdk-server/`, then `npm install` the tarballs into `.packs/` (checked in so a fresh clone can `npm install` immediately)

After a real `voice-v*` / `agents-v*` release, re-run `npm run bootstrap` to switch onto registry versions.

### What a real host does

```bash
# browser app
npm install @awaazlabs-uva/voice

# host backend
npm install @awaazlabs-uva/agents
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

1. Wait for **Language / STT / LLM / TTS** dropdowns (needs portal `UVA_API_BASE_URL`).
2. Pick a valid combo (enabled capabilities for that language).
3. **Connect** — backend PATCHes the agent pipeline, then the voice SDK mints + joins.
4. Watch **First agent audio** timing (Wave 1 cold-start smoke).
5. Optional: **Mute mic**, **Unlock audio** (autoplay block), **Timeout smoke** (`/api/demo/hang` + `fetchTimeoutMs` → `timeout` error).

Urdu typically: Gladia + Gemini + Uplift.  
English typically: Gladia/Deepgram + Gemini/Groq + Cartesia/ElevenLabs/Rime.

**Provider flips:** changing Language / STT / LLM / TTS applies the pipeline in the background; Connect skips the portal PATCH when the combo is already on the agent.

## Wave 1 SDK surface exercised here

- `new AwaazLabsUvaVoice({ publishableKey, sessionEndpoint, refreshEndpoint, fetchTimeoutMs })`
- `connect` / `disconnect` / `startAudio` / `setMicMuted`
- Events: `connected`, `transcript` (replace-by-`id`), `agent_speaking`, `audio_blocked`, `turn_latency`, `error` (taxonomy codes)
- Host backend: session mint/refresh + `@awaazlabs-uva/agents` for capabilities / `updateAgent`

## Credentials

Do **not** commit real `.env` files. Copy `.env.example` in `backend/` and `frontend/`.
