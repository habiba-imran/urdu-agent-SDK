# Independent client integration test

This folder is a standalone client: copy the **entire folder**, including `packages/`, outside the platform repository and run it there. It imports installed SDK packages, calls public platform endpoints through its own host backend, and does not import worker, dashboard, database, or SDK source files.

## SDK distribution

- Browser: included `@awaazlabs-uva/voice@1.1.1-humanization.0` **unpublished test snapshot**, packed from current SDK source. Includes playback-readiness handshake, provider-failure events, and humanization metrics. This is not an npm release.
- Backend: published `@awaazlabs-uva/agents@0.1.0` and `@awaazlabs-uva/telephony@0.1.0`, pinned in lockfiles.
- `packages/voice-manifest.json` records archive SHA-256, npm integrity and SDK source hashes. `npm run verify` checks installed package identity and independence.
- Published voice `1.1.0` remains the baseline client release. Installing it again does not test the new readiness handshake. GitHub pushes do not publish npm packages.

## Setup (PowerShell, Node 20+)

From this folder:

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
# Fill your test tenant's URLs/credentials and agent ID. Never put secrets in frontend/.env.
npm run install:all
npm run verify
```

Do not overwrite existing `.env` files when updating this app. `install:all` uses `npm ci` and the checked-in lockfiles. `verify` runs synthetic host-contract tests, TypeScript, production frontend build, and installed-package/hash checks; it does not place calls.

The backend requires `UVA_TENANT_ID`, `UVA_HMAC_SECRET`, `UVA_PUBLISHABLE_KEY`, and `UVA_CONTROL_PLANE_URL`. Set `UVA_API_BASE_URL` for the agent/provider picker. Telephony additionally requires the appropriate API URL, backend-only Telnyx credentials, and an existing test route/number.

The platform control plane, tenant API, worker, LiveKit and chosen provider credentials must already be available. This client does not launch or configure them. Default local URLs: control plane `http://localhost:8000`, tenant API `http://localhost:8002`.

Allow `http://localhost:5174` in both the tenant's `allowed_origins` and the host's `HOST_ALLOWED_ORIGINS`. If you use `127.0.0.1`, allow that exact origin too. Use the same publishable key on backend and frontend.

## Run

Two terminals, from this folder:

```powershell
npm run dev:backend
```

```powershell
npm run dev:frontend
```

Open `http://localhost:5174`. Host health: `http://localhost:3100/healthz`.

Choose a **dedicated test agent**: changing language/providers in the picker updates that agent via the agents SDK. The picker uses platform capabilities; it does not hardcode new providers or models. English uses the existing English providers; Pakistani Urdu and Urdu-English mixed tests use the existing Urdu route. There is no separate mixed-language API enum. Gladia's existing single-language limitation remains.

Connect, grant microphone access, and click **Unlock audio** if blocked. The page reports room connection and playback readiness separately. Metrics are worker/SDK diagnostics; active-speaker signals and TTS TTFB do not prove caller-acoustic FUAW.

Read [TESTING.md](TESTING.md) for the humanization interaction matrix and [PLATFORM_TESTING.md](PLATFORM_TESTING.md) for platform-owned candidate settings. New audible candidates remain off until explicitly enabled on an isolated test worker.

## Phone testing

The Telephony panel uses the backend-only telephony SDK. Check connection/readiness and assigned numbers before testing an existing inbound/outbound route. Number purchase and outbound calls incur provider charges; this app performs them only when you use those controls. Verify status and end reason in the dashboard Sessions/Telephony views. GitHub publication does not apply database migrations or provision phone routes.

## Maintainer: refresh the included SDK snapshot

From the platform repository root, after SDK source changes:

```powershell
python scripts/package_client_voice.py
npm install --prefix client-integration-test/frontend
```

Commit the refreshed archive, manifest and frontend lockfile together. The packer builds the SDK and assigns a test-only prerelease version to a temporary package; it does not change the registry release or publish to npm. End clients never run this maintainer step.
