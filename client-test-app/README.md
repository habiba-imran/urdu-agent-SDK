# UVA Client Test App

Local test harness for the packages in `client-submission_v2`.

This app intentionally keeps the same boundary as the client handoff docs:

- Browser imports only `@awaazlabs-uva/voice`.
- Local Express backend imports `@awaazlabs-uva/agents` and `@awaazlabs-uva/telephony`.
- Tenant HMAC, Telnyx API keys, and SIP secrets stay out of the browser bundle.

## Prerequisites

- Node.js 20+
- A running tenant portal API URL
- A running control-plane session URL for browser voice sessions
- Tenant ID, tenant HMAC secret, and publishable key

## Setup

```powershell
Set-Location C:\Users\habib\Desktop\SDK\sdk-agent\client-test-app
npm install
npm run install:sdks
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
```

Edit `backend/.env`:

```env
UVA_API_BASE_URL=https://<tenant-api-service>
UVA_TELEPHONY_API_URL=https://<tenant-api-service>
UVA_SESSION_UPSTREAM_URL=https://<control-plane-service>
UVA_PUBLISHABLE_KEY=<publishable-key>
UVA_TENANT_ID=<tenant-id>
UVA_HMAC_SECRET=<tenant-hmac-secret>
PORT=3001
PUBLIC_BASE_URL=http://localhost:3001
ALLOWED_ORIGINS=http://localhost:3000
ALLOW_PAID_TELEPHONY_ACTIONS=0
```

Edit `frontend/.env`:

```env
VITE_TEST_BACKEND_URL=http://localhost:3001
VITE_UVA_PUBLISHABLE_KEY=<publishable-key>
VITE_UVA_SESSION_ENDPOINT=http://localhost:3001/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=http://localhost:3001/api/voice/session/refresh
```

## Run

Terminal 1:

```powershell
Set-Location C:\Users\habib\Desktop\SDK\sdk-agent\client-test-app
npm run backend
```

Terminal 2:

```powershell
Set-Location C:\Users\habib\Desktop\SDK\sdk-agent\client-test-app
npm run frontend
```

Open `http://localhost:3000`.

## Safe Test Order

1. Setup: confirm backend health, tenant config, and provider capabilities.
2. Agents: list existing agents or create an agent with a real voice ID from the hosted voice catalog.
3. Phone Numbers: connect Telnyx from the Setup tab, then sync/list owned or managed numbers.
4. Provider Test: assign a managed number to an agent, configure routing/SIP/profile/trunk, then check readiness.
5. Browser Voice: select an agent and connect through the browser SDK.
6. Call Log: list recent call records.

Reserve, purchase, and outbound-call routes are blocked unless `ALLOW_PAID_TELEPHONY_ACTIONS=1` is set in `backend/.env`. Leave it as `0` for normal SDK smoke testing.
