# Client integration test (fresh start)

Simulates a **new client** integrating from `client-deliverables-final/` only:

- Installs `@awaazlabs-uva/voice`, `@awaazlabs-uva/agents`, `@awaazlabs-uva/telephony` from **public npm** (no monorepo `file:` packs)
- Host backend follows `host-backend-starter/` (session mint + refresh + HMAC)
- Browser uses the voice SDK against **this** host, not the control plane directly

## Ports (avoid clashing with `demo-app`)

| Service | Port |
|---------|------|
| Host backend | `3100` |
| Frontend | `5174` |

## Setup

```bash
cd client-integration-test
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# Fill secrets + URLs in backend/.env and frontend/.env

npm run install:all
```

## Run

Terminal 1 — ensure control plane / portal / worker are already up (same as your local platform).

Terminal 2:

```bash
npm run dev:backend
```

Terminal 3:

```bash
npm run dev:frontend
```

Open http://localhost:5174

## What to verify

The frontend is the **same Wave 1 UI as `demo-app/frontend`** (metrics, timings, pipeline picker, audio unlock), plus a **Telephony** panel.

Packages are from **public npm** only (`voice`, `agents`, `telephony`).

1. Open http://localhost:5174  
2. Browser voice: wait for pickers → Connect → Unlock audio if needed  
3. Telephony (Telnyx key in `backend/.env` only):
   - **Connect / refresh Telnyx**
   - **Sync account numbers** → see managed + owned lists
   - **Search / Purchase** to buy a number
   - Select a managed number → **Assign to agent + configure inbound routing**
   - Inbound: dial that E.164 from a real phone
   - Outbound: **Prepare outbound** → enter destination → **Place outbound call**

### Can’t hear the agent?

Usually Chrome autoplay — click **Unlock audio**. Slow `session_mint_ms` is control-plane/DB, not the npm package.

## Prerequisites (local platform)

Your AwaazLabs services must already be running (same as `demo-app`):

- Control plane → `UVA_CONTROL_PLANE_URL` (e.g. `http://localhost:8000`)
- Tenant portal API → `UVA_API_BASE_URL` (e.g. `http://localhost:8002`)
- Voice worker / LiveKit for actual audio

Also ensure the tenant `allowed_origins` includes `http://localhost:5174` (control plane origin check).

## Independence checks

```bash
# Packages resolve from registry.npmjs.org — not file: monorepo packs
rg "registry.npmjs.org/@awaazlabs-uva" backend/package-lock.json frontend/package-lock.json
```
