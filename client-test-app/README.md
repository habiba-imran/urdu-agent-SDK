# UVA Client Test App

A standalone client integration test app for the AwaazLabs UVA SDK. Acts as a real client to test:
- Connecting your Telnyx account
- Searching and purchasing phone numbers
- Creating agents with different STT/LLM/TTS provider combinations
- Testing outbound call readiness
- Viewing call logs

## Prerequisites

- Node.js 20+
- The `tenant_portal_api` Python backend running at `http://localhost:8000`

## Quick Start

```bash
# 1. From this directory, install dependencies
cd client-test-app
npm install

# 2. Install the SDK tarballs from the handover folder
npm run install:sdks

# 3. Copy and edit the backend env file
cp backend/.env.example backend/.env
# Edit backend/.env — only UVA_API_BASE_URL is required to start.
# You can enter Tenant ID, HMAC Secret, and Telnyx Key from the UI.

# 4. Start the backend (port 3001)
npm run backend

# 5. In a new terminal, serve the frontend (port 3000)
npm run frontend

# Or run both together:
npm run dev
```

## Open the app

Navigate to: **http://localhost:3000**

## Usage Flow

1. **Setup tab** — Enter your API base URL, Tenant ID, HMAC Secret, and Telnyx API key. Click "Save Config" then "Connect Telnyx Account".
2. **Phone Numbers tab** — Search for available numbers by country + area code. Reserve or purchase. Sync your existing Telnyx-owned numbers.
3. **Agents tab** — List, create, and update agents. Use the provider dropdowns to test different STT/LLM/TTS combinations.
4. **Provider Test tab** — Assign a number to an agent, run the outbound readiness checklist, and make a test outbound call.
5. **Call Log tab** — Browse recent call records and their statuses.

## Architecture

```
client-test-app/
  backend/server.js     ← Express.js, uses @awaazlabs-uva/agents + @awaazlabs-uva/telephony SDKs
  frontend/index.html   ← Single-page app
  frontend/style.css    ← Premium dark-mode styling
  frontend/app.js       ← All frontend logic
  package.json
```

## Security Notes

- Backend secrets (Tenant ID, HMAC Secret, Telnyx API Key) are stored only in the backend process memory and in `backend/.env`.
- The frontend never receives or stores secrets — it only calls your local backend at port 3001.
- **Never commit `backend/.env`** — it is in `.gitignore`.
