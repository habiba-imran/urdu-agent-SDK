# Host Backend Contract

> **Superseded (P2-C1 / client delivery).** Do not follow stale paths or env names in older
> revisions of this file.

## Where to go instead

1. **In-dashboard guide (canonical):** `/docs/backend-setup`, `/docs/how-integration-works`,
   `/docs/errors-and-troubleshooting`.
2. **Repo pack:** `client-deliverables-final/02-HOST_BACKEND_CONTRACT.md` and
   `client-deliverables-final/host-backend-starter/` (uses `UVA_CONTROL_PLANE_URL`).
3. **npm:** `@awaazlabs-uva/voice` talks only to **your** host session endpoint.

## Contract (summary)

Browser → `POST /api/voice/session` on **your** host with `{ publishableKey, agentId }` →
your host HMAC-signs `POST {UVA_CONTROL_PLANE_URL}/v1/session` → return
`{ token, wsUrl, roomName, refreshUrl, expiresIn? }` where `refreshUrl` points at **your**
`/api/voice/session/refresh` (rewrite any control-plane relative URL).

Preserve upstream HTTP status and short error bodies so the voice SDK can map
`agent_not_found`, `quota_exceeded`, `rate_limit`, etc.

Env (backend only): `UVA_TENANT_ID`, `UVA_HMAC_SECRET`, `UVA_PUBLISHABLE_KEY`,
`UVA_CONTROL_PLANE_URL`, `HOST_ALLOWED_ORIGINS`, optional `HOST_PUBLIC_BASE_URL`.
