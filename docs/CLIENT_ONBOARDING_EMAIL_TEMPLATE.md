# Client Onboarding Email Template

Use this when manually onboarding a client. Prefer pointing them at the **tenant
dashboard `/docs`** once they have console access.

## Subject

AwaazLabs-UVA-Voice SDK onboarding package

## Email body

Hi <client-name>,

Your AwaazLabs-UVA-Voice integration package is ready.

Here is what your engineering team needs:

- `publishableKey`: `<publishable-key>`
- `tenantId`: `<tenant-id>`
- `agentId`: `<agent-id>`
- backend-only session upstream URL: `<session-upstream-url>`
- HMAC secret: `<send separately through a secure channel>`

Important security note:

- the HMAC secret must live on your backend only
- do not place it in frontend or mobile client code

Recommended integration path:

1. Open the tenant dashboard → **Docs** (Quickstart + Backend setup), **or** start from
   `client-deliverables-final/host-backend-starter/`
2. Wire the browser SDK (`@awaazlabs-uva/voice`) to your host backend routes
3. Verify session mint, connect, transcript, refresh, and reconnect

Package contents (current):

- Dashboard `/docs` (canonical client guide)
- `client-deliverables-final/` (+ `host-backend-starter/`)
- `docs/HOST_BACKEND_CONTRACT.md`
- Public npm: `@awaazlabs-uva/voice`, `@awaazlabs-uva/agents`

Expected backend routes:

- `POST /api/voice/session`
- `POST /api/voice/session/refresh`

If your team wants a guided technical handoff, we can walk through the quickstart together and run a
staging connection test live.

Best,

<your-name>
