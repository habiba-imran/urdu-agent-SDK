# Client Quickstart

> **Superseded (P2-C1).** This file previously pointed at deleted demo-app and
> examples trees. Do not follow those paths.

## Where to go instead

1. **In-dashboard guide (canonical for clients):** open the tenant dashboard → `/docs`
   (Quickstart, Backend setup, Going live, Security).
2. **Repo starter pack:** `client-deliverables-final/` — especially
   `client-deliverables-final/host-backend-starter/` and
   `client-deliverables-final/01-INTEGRATION_GUIDE.md`.
3. **Public SDKs** (pin these — match `package.json` / `/docs`):
   - `@awaazlabs-uva/voice@1.1.0` (browser)
   - `@awaazlabs-uva/agents@0.1.0` (backend)
   - `@awaazlabs-uva/telephony@0.1.0` (backend)

## Architecture in one sentence

Browser SDK → **your** host backend (HMAC) → AwaazLabs-UVA session service → LiveKit worker.

The browser never signs requests or calls AwaazLabs-UVA upstream with the tenant secret.
