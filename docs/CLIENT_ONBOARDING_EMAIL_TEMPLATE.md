# Client Onboarding Email Template

Use this when manually onboarding a client before a full self-serve portal exists.

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

1. start from the host backend starter
2. wire the browser SDK to your host backend routes
3. verify session mint, connect, transcript, refresh, and reconnect

Package contents:

- `sdk/README.md`
- `docs/CLIENT_QUICKSTART.md`
- `docs/HOST_BACKEND_CONTRACT.md`
- `examples/host-backend/`
- `examples/web-client/`

Expected backend routes:

- `POST /api/voice/session`
- `POST /api/voice/session/refresh`

If your team wants a guided technical handoff, we can walk through the quickstart together and run a
staging connection test live.

Best,

<your-name>
