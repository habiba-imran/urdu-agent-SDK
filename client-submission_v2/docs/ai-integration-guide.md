<<<<<<< HEAD
# AI Coding Agent Integration Prompt

Use this document when the client wants a coding agent to implement the SDK in their own
application. Fill the placeholders first, then paste the prompt into the coding agent.

## Values To Fill Before Pasting

```text
CLIENT_SUBMISSION_PATH = [ABSOLUTE_OR_RELATIVE_PATH_TO_CLIENT_SUBMISSION_V2]
FRONTEND_STACK         = [React/Vite, Next.js, Vue, or other]
BACKEND_STACK          = [Express, Fastify, NestJS, Next.js API routes, or other]
FRONTEND_PROJECT_PATH  = [PATH_TO_CLIENT_FRONTEND]
BACKEND_PROJECT_PATH   = [PATH_TO_CLIENT_BACKEND]

PUBLISHABLE_KEY        = [PUBLISHABLE_KEY]
TENANT_ID              = [TENANT_ID]
HMAC_SECRET            = [HMAC_SECRET]
SESSION_UPSTREAM_URL   = [BACKEND_ONLY_SESSION_UPSTREAM_URL]
SESSION_REFRESH_URL    = [OPTIONAL_BACKEND_ONLY_REFRESH_UPSTREAM_URL]
VOICE_CATALOG_URL      = [VOICE_CATALOG_URL]
PORTAL_API_URL         = [PORTAL_API_URL]
AGENT_ID               = [AGENT_ID_OR_BLANK_TO_CREATE_ONE]
```

## Copy Prompt From Here

```text
You are an expert TypeScript/JavaScript engineer. Integrate the private AwaazLabs-UVA SDK into my
application. Follow the package docs in:

[CLIENT_SUBMISSION_PATH]/docs/INTEGRATION_GUIDE.md
[CLIENT_SUBMISSION_PATH]/docs/credentials-template.md

My app:
- Frontend stack: [FRONTEND_STACK]
- Backend stack: [BACKEND_STACK]
- Frontend path: [FRONTEND_PROJECT_PATH]
- Backend path: [BACKEND_PROJECT_PATH]

Credentials and configuration:
- PUBLISHABLE_KEY: [PUBLISHABLE_KEY]
- TENANT_ID: [TENANT_ID] (backend only)
- HMAC_SECRET: [HMAC_SECRET] (backend only, never expose to browser)
- SESSION_UPSTREAM_URL: [BACKEND_ONLY_SESSION_UPSTREAM_URL] (backend only)
- SESSION_REFRESH_URL: [OPTIONAL_BACKEND_ONLY_REFRESH_UPSTREAM_URL] (backend only, optional)
- VOICE_CATALOG_URL: [VOICE_CATALOG_URL] (backend only)
- PORTAL_API_URL: [PORTAL_API_URL] (backend only)
- AGENT_ID: [AGENT_ID_OR_BLANK_TO_CREATE_ONE]

Install packages:
1. In the frontend project, install:
   npm install [CLIENT_SUBMISSION_PATH]/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz livekit-client@^2.0.0

2. In the backend project, install:
   npm install [CLIENT_SUBMISSION_PATH]/sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz

Backend requirements:
- Create or update backend `.env`.
- Keep these backend-only values out of frontend code: TENANT_ID, HMAC_SECRET, SESSION_UPSTREAM_URL,
  SESSION_REFRESH_URL, VOICE_CATALOG_URL, PORTAL_API_URL.
- Implement:
  - GET /api/health
  - POST /api/voice/session
  - POST /api/voice/session/refresh
  - GET /api/voices
  - GET /api/agents
  - POST /api/agents
  - PATCH /api/agents/:agentId
- POST /api/voice/session must validate `publishableKey`, accept `agentId`, and proxy to the
  backend-only session upstream. Do not invent raw HMAC/session minting logic.
- Agent routes must use `AwaazLabsUvaAgentsClient` from `@awaazlabs-uva/agents`.
- CORS must allow my frontend origin exactly.

Frontend requirements:
- Create or update frontend `.env`.
- Instantiate `AwaazLabsUvaVoice` with publishableKey, sessionEndpoint, and refreshEndpoint.
- Build a voice widget with connect, disconnect, transcript list, connection state, error display,
  agent speaking indicator, and audio unlock handling.
- Listen for `audio_blocked` and call `startAudio()` inside a user click handler.
- If AGENT_ID is blank, add a backend-backed agent creation flow first, then use the returned
  agent id for voice connection.
- Fetch voices from my backend `/api/voices`; the browser must not call AwaazLabs-UVA upstream
  services directly.

Security requirements:
- Do not import `@awaazlabs-uva/agents` anywhere in frontend/browser code.
- Do not expose HMAC_SECRET, TENANT_ID, portal API URL, or backend-only upstream URLs to the browser.
- Add `.env` files to `.gitignore`.
- After implementation, verify the browser request to `/api/voice/session` sends only
  `{ publishableKey, agentId }`.

After coding, provide:
1. Files changed.
2. Exact commands to run.
3. Manual values still required.
4. Test checklist proving:
   - backend health works,
   - voices list works,
   - agent creation/listing works,
   - voice session connects,
   - transcript appears,
   - audio unlock works if browser blocks audio,
   - no backend secrets are present in browser bundle or browser network calls.
```

## Notes For The Human Developer

- Review generated backend session code carefully. It must proxy/delegate through the provided
  backend-only upstream configuration.
- If using Next.js, public frontend variables should use `NEXT_PUBLIC_UVA_*` instead of `VITE_UVA_*`.
- If the coding agent adds `@awaazlabs-uva/agents` to a frontend `package.json`, reject that change.
- If transcript works but audio does not, inspect provider/worker logs and browser autoplay state.
=======
# AI Coding Agent Integration Prompt Guide

> **AwaazLabs-UVA-Voice SDK** — Powered by Finova Solutions
> Copy the prompt below and paste it directly into your AI coding assistant
> (Cursor, GitHub Copilot Chat, Claude, ChatGPT, Gemini, etc.)

---

## How to Use This Guide

1. **Fill in the bracketed placeholders** in the prompt below with your actual values from `credentials-template.md`
2. **Copy the entire prompt block** between the triple-dashed lines
3. **Paste it into your AI assistant's chat interface** and send it
4. The AI will generate the integration code, explain what it built, and tell you what manual steps remain

---

---

## ✂️ COPY FROM HERE

---

# AwaazLabs-UVA-Voice SDK — Full Integration Prompt

You are an expert TypeScript/JavaScript developer. I need you to integrate the **AwaazLabs-UVA-Voice SDK** (`@awaazlabs-uva/voice` and `@awaazlabs-uva/agents`) into my application. Follow every instruction precisely and produce production-quality code.

---

## My Application Stack

> *(Edit these lines to match your project before pasting)*

- **Frontend:** [React with Vite / Next.js / Vue 3 / Vanilla JS — choose one]
- **Backend:** [Express.js / Fastify / Next.js API Routes / NestJS — choose one]
- **Language:** TypeScript (preferred) or JavaScript
- **Package manager:** npm

---

## My Credentials & Configuration

> *(Replace all bracketed values with your actual values from `credentials-template.md`)*

```
PUBLISHABLE_KEY    = [YOUR_PUBLISHABLE_KEY]
TENANT_ID          = [YOUR_TENANT_ID]
HMAC_SECRET        = [YOUR_HMAC_SECRET]             ← backend only
SESSION_UPSTREAM   = [BACKEND_ONLY_SESSION_UPSTREAM_URL]  ← backend only
PORTAL_API_URL     = [YOUR_PORTAL_API_URL]          ← backend only
AGENT_ID           = [YOUR_AGENT_ID]                ← optional; I may want to create one
BACKEND_PORT       = 3100
FRONTEND_PORT      = 5174
```

---

## Task: Integrate the AwaazLabs-UVA-Voice SDK

### STEP 1 — Environment Files

Create the following environment files. **Do not put any secrets in the frontend `.env`.**

**`backend/.env`:**
```
PORT=3100
UVA_SESSION_UPSTREAM_URL=[BACKEND_ONLY_SESSION_UPSTREAM_URL]
UVA_PORTAL_API_URL=[YOUR_PORTAL_API_URL]
UVA_TENANT_ID=[YOUR_TENANT_ID]
UVA_HMAC_SECRET=[YOUR_HMAC_SECRET]
UVA_PUBLISHABLE_KEY=[YOUR_PUBLISHABLE_KEY]
HOST_ALLOWED_ORIGINS=http://localhost:5174
HOST_PUBLIC_BASE_URL=http://localhost:3100
```

**`frontend/.env`:**
```
VITE_UVA_PUBLISHABLE_KEY=[YOUR_PUBLISHABLE_KEY]
VITE_UVA_SESSION_ENDPOINT=http://localhost:3100/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=http://localhost:3100/api/voice/session/refresh
VITE_UVA_VOICE_CATALOG_ENDPOINT=http://localhost:3100/api/voices
VITE_UVA_AGENT_ID=[YOUR_AGENT_ID]
```

Also add both `.env` files to `.gitignore`.

---

### STEP 2 — Backend: Install `@awaazlabs-uva/agents` and Implement Required Endpoints

**Install the server SDK** from the local `sdk/` folder (path relative to `backend/`):

> Note: `@awaazlabs-uva/agents` is a **private package** delivered inside `sdk/@awaazlabs-uva/agents/` —
> it is NOT on the public npm registry. Install it from the included `.tgz` package file.
> The package code itself contains no hardcoded Finova secrets — it is a signing
> library that your backend initialises at runtime with credentials from `.env`.

```bash
npm install ../sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
```

**Implement these three backend routes:**

#### Route A: `POST /api/voice/session` — Session Mint Endpoint

This is the most critical route. The browser SDK (`@awaazlabs-uva/voice`) posts to this endpoint to get a LiveKit token. **This route must delegate to the Finova-provided backend-only session adapter or approved host-backend starter. Do not generate raw HMAC signing code from this prompt.**

Implementation requirements:
- Read `publishableKey` and `agentId` from the request body
- Validate `publishableKey` against the expected backend value
- Call the backend-only AwaazLabs-UVA session adapter/starter with `{ publishableKey, agentId, origin }`
- Proxy the response JSON `{ token, wsUrl, roomName, refreshUrl?, expiresIn? }` back to the browser
- Handle `429` (quota), `404` (agent not found), and other errors with appropriate HTTP status codes

#### Route B: `POST /api/voice/session/refresh` — Token Refresh

- Accept `Authorization: Bearer <existing_token>` header from the browser SDK
- Forward a refresh request through the same backend-only session adapter/starter
- Return the new `{ token, wsUrl, roomName, refreshUrl?, expiresIn? }`

#### Route C: `GET /api/agents` and `POST /api/agents` — Agent Management

Use `AwaazLabsUvaAgentsClient` from `@awaazlabs-uva/agents`:

```typescript
import { AwaazLabsUvaAgentsClient } from '@awaazlabs-uva/agents';

const agentsClient = new AwaazLabsUvaAgentsClient({
  tenantId: process.env.UVA_TENANT_ID!,
  tenantSecret: process.env.UVA_HMAC_SECRET!,
  baseUrl: process.env.UVA_PORTAL_API_URL!,
});
```

- `GET /api/agents` → call `agentsClient.listAgents()` and return the array
- `POST /api/agents` → accept `{ name, prompt, voiceId, llmModel? }` and call `agentsClient.createAgent(params)`
- `PATCH /api/agents/:agentId` → call `agentsClient.updateAgent(agentId, params)`

Add CORS middleware so `http://localhost:5174` can reach the backend.

---

### STEP 3 — Frontend: Install `@awaazlabs-uva/voice` and Build the Voice UI

**Install the browser SDK** from the local `sdk/` folder (path relative to `frontend/`):

> Note: `@awaazlabs-uva/voice` is a **private package** delivered inside `sdk/@awaazlabs-uva/voice/` —
> it is NOT on the public npm registry. Install it from the included `.tgz` package file.
> This package holds **zero secrets** — it is safe to bundle and ship publicly.

```bash
npm install ../sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz livekit-client@^2.0.0
```

**Build a `VoiceWidget` component** with the following behavior:

1. **Initialise** `AwaazLabsUvaVoice` with `publishableKey`, `sessionEndpoint`, and `refreshEndpoint` from the frontend `.env`
2. **Connect button**: calls `agent.connect({ agentId })` on click
3. **Disconnect button**: calls `agent.disconnect()` on click
4. **Transcript display**: listens for `transcript` events and shows final segments in a scrollable list
5. **Agent speaking indicator**: listens for `agent_speaking` to show a visual pulse/indicator
6. **Audio unlock button**: listens for the `audio_blocked` event; if `true`, display a prominent "Unlock Audio 🔊" button that calls `agent.startAudio()` inside the click handler (this is required by browser autoplay policy)
7. **Error display**: listens for `error` events and shows a user-friendly message based on `error.code`:
   - `quota_exceeded` → "Usage limit reached. Please try again later."
   - `agent_not_found` → "Agent not found. Please check the Agent ID."
   - `session_failed` → "Connection failed. Please check your setup."
8. **Connection state**: show one of `idle | connecting | connected | disconnecting` in the UI

**Also build an `AgentManager` component** that:
- Fetches and lists existing agents from `GET /api/agents`
- Has a form to create a new agent (`name`, `prompt`, `voiceId` dropdown populated from `AwaazLabsUvaVoice.listVoices(voiceCatalogEndpoint)`)
- On creation, sets the new agent ID as the active agent for `VoiceWidget`

---

### STEP 4 — Voice Picker (Optional)

Call the static method `AwaazLabsUvaVoice.listVoices(import.meta.env.VITE_UVA_VOICE_CATALOG_ENDPOINT)` to fetch the available Urdu voices from your own backend and populate a `<select>` dropdown in the `AgentManager` form. Filter to only `enabled: true` voices. The browser must never call an AwaazLabs-UVA infrastructure URL directly for this list.

---

## Output Requirements

After generating all code, you MUST provide:

### 1. Summary of What Was Built

Write a clear, bulleted summary covering:
- Every file created or modified
- What each backend route does
- What each frontend component does
- How the SDK packages are wired together

### 2. Manual Steps Required by the Developer

List every action the developer must perform manually, including:
- [ ] Filling in credentials in `.env` files from `credentials-template.md`
- [ ] Running `npm install` in both backend and frontend
- [ ] Creating an initial agent (if `AGENT_ID` was left blank)
- [ ] Any framework-specific setup (e.g., configuring Vite proxy, Next.js API routes, etc.)
- [ ] Verifying CORS settings match actual deployment URLs in production

### 3. Core Features of the Integration

Highlight:
- Zero-secret browser bundle — `@awaazlabs-uva/voice` holds no credentials
- Backend-only authenticated session minting — every session token is minted through your server boundary
- Automatic token refresh — sessions self-renew without user intervention
- Real-time Urdu transcription via LiveKit WebRTC
- Browser autoplay policy handling — `audio_blocked` event + `startAudio()` pattern
- Full agent lifecycle management via `@awaazlabs-uva/agents`

### 4. Step-by-Step Testing Procedure

Provide the following test checklist for the developer to verify the integration:

```
TESTING CHECKLIST
─────────────────────────────────────────────────────────────
□ STEP 1: Start the backend
  Run: cd backend && npm run dev
  Verify: Server starts on http://localhost:3100
  Test: curl http://localhost:3100/api/agents
  Expected: Returns a JSON array (may be empty)

□ STEP 2: Start the frontend
  Run: cd frontend && npm run dev
  Verify: UI opens on http://localhost:5174

□ STEP 3: Create an Agent
  Action: Open the UI → Agent Manager → fill in name, prompt, voice → click Create
  Expected: New agent appears in the agent list with a UUID

□ STEP 4: Select the Agent
  Action: Click "Use as Agent ID" or equivalent on the new agent
  Expected: The agent ID is set in the voice widget

□ STEP 5: Connect a Voice Session
  Action: Click "Connect" in the Voice Widget
  Expected: Status changes to "connecting" then "connected"
  Expected: Microphone permission prompt appears (accept it)

□ STEP 6: Speak and See Transcription
  Action: Speak a sentence in Urdu or English
  Expected: Transcript entries appear in real time (partial, then final)

□ STEP 7: Verify Agent Responds
  Expected: The "Agent Speaking" indicator activates
  Expected: You hear the agent's Urdu voice response

□ STEP 8: Test Audio Unlock (if needed)
  If audio is blocked: An "Unlock Audio" button appears
  Action: Click the button
  Expected: Agent audio begins playing

□ STEP 9: Disconnect
  Action: Click "Disconnect"
  Expected: Status returns to "idle"; connection closed cleanly

□ STEP 10: Verify No Secrets in Browser
  Action: Open browser DevTools → Network → find the /api/voice/session request
  Verify: The browser ONLY sends { publishableKey, agentId } to your backend
  Verify: UVA_HMAC_SECRET and UVA_TENANT_ID are NOT present in any browser request
─────────────────────────────────────────────────────────────
```

---

## Security Rules to Follow

- `UVA_HMAC_SECRET` and `UVA_TENANT_ID` must ONLY exist in backend environment variables
- `@awaazlabs-uva/agents` must ONLY be imported in backend code
- The browser must NEVER call AwaazLabs-UVA upstream services directly
- `publishableKey` is the only AwaazLabs-UVA credential that may appear in frontend code
- All `.env` files must be in `.gitignore`

---

*Begin the integration now. Generate all files completely — no placeholders, no `// TODO` comments. Every function must be fully implemented.*

---

## ✂️ END OF COPY BLOCK

---

## Notes for the Developer

### After the AI Generates the Code

1. **Review the output** before running it — especially the backend session route. It must delegate to the Finova-provided backend-only session adapter or approved starter and must not expose upstream URLs or signing details to the browser.

2. **Fill in credentials** from `credentials-template.md` into the generated `.env` files before running anything.

3. **If the AI missed something**, ask it a follow-up:
   > "You missed implementing [X]. Add it now following the same patterns you used for the rest of the integration."

4. **Framework differences** — If you use Next.js instead of Vite:
   - Replace `VITE_` env prefixes with `NEXT_PUBLIC_` in the frontend
   - Move the backend routes to `app/api/` (App Router) or `pages/api/` (Pages Router)
   - Adjust the prompt's "Frontend" and "Backend" sections accordingly before pasting

5. **Iterating on the Agent Prompt** — The Urdu system prompt you pass to `createAgent()` is the personality and instruction set for your AI. Iterate on it via `updateAgent()` without recreating the agent.
>>>>>>> origin/ukasha
