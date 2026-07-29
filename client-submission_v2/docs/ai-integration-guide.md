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
