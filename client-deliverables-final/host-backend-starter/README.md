# Host backend starter

Minimal Node/Express backend that implements the browser voice session contract:

- `POST /api/voice/session`
- `POST /api/voice/session/refresh`

It signs requests to the AwaazLabs control plane with your tenant HMAC secret and returns only browser-safe fields (`token`, `wsUrl`, `roomName`, `refreshUrl`, `expiresIn`).

## Setup

```bash
cd host-backend-starter
cp .env.example .env
# Fill tenant secrets now. Leave URLs as placeholders until services are deployed.
npm install
npm run dev
```

Default listen port: `3000`.

Point your frontend at:

- `http://localhost:3000/api/voice/session`
- `http://localhost:3000/api/voice/session/refresh`

## Required env

| Variable | When |
|----------|------|
| `UVA_TENANT_ID` | Now (from provisioning) |
| `UVA_HMAC_SECRET` | Now (from provisioning) |
| `UVA_PUBLISHABLE_KEY` | Now (from provisioning) |
| `UVA_CONTROL_PLANE_URL` | When session service is deployed |
| `HOST_ALLOWED_ORIGINS` | Now (your frontend origins) |
| `HOST_PUBLIC_BASE_URL` | Optional; used to rewrite `refreshUrl` |

Agents / telephony SDKs are **not** required in this starter. Add `@awaazlabs-uva/agents` and `@awaazlabs-uva/telephony` in your own backend when you need those APIs; they use `UVA_API_BASE_URL` / `UVA_TELEPHONY_API_URL` (also provided when portal services are deployed).

## Security

- Never expose `UVA_HMAC_SECRET` to the browser.
- Never point the browser at `UVA_CONTROL_PLANE_URL` directly.
- Keep this starter (or its signing code) on your backend only.
