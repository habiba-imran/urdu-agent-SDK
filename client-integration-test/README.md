# Independent client integration test

This folder is a standalone client: copy the folder outside the platform repository and run it there. It imports published npm SDK packages, calls public platform endpoints through its own host backend, and does not import worker, dashboard, database, or SDK source files. The historical `packages/` archives are not used by the current installation.

## SDK distribution

- Browser: published `@awaazlabs-uva/voice@1.1.1` from npm, including playback readiness, provider-failure events and humanization metrics.
- Backend: published `@awaazlabs-uva/agents@0.1.1` and `@awaazlabs-uva/telephony@0.1.1`, pinned in lockfiles. Both clients explicitly use `signatureVersion: 'raw-body-v1'`; deploy the compatible tenant portal before running this backend.
- `npm run verify` checks installed versions, registry artifact/integrity metadata, readiness support and independence from SDK source files. Historical snapshot manifests remain in `packages/` for comparison.
- Voice `1.1.1` was published on 2026-10-12. GitHub pushes alone do not install package updates in existing applications.

## Setup (PowerShell, Node 20+)

From this folder:

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
# Fill your test tenant's URLs/credentials and agent ID. Never put secrets in frontend/.env.
npm run install:all
npm run verify
```

Do not overwrite existing `.env` files when updating this app. `install:all` uses `npm ci` and the checked-in lockfiles. `verify` runs synthetic host-contract tests, DOM interaction tests, TypeScript, the production frontend build, and installed-package checks; it does not place calls. On PowerShell installations that block `npm.ps1`, use `npm.cmd` in place of `npm`.

The backend requires `UVA_TENANT_ID`, `UVA_HMAC_SECRET`, `UVA_PUBLISHABLE_KEY`, and `UVA_CONTROL_PLANE_URL`. Set `UVA_API_BASE_URL` for the agent/provider picker. Telephony additionally requires the appropriate API URL, backend-only Telnyx credentials, and an existing test route/number.

## Verify the backend SDK integration against staging

Set both machine API URLs to `https://uva-tenant-portal-staging.onrender.com`
in the existing ignored `backend/.env`, using a staging tenant's credentials.
Do not copy secrets into source or overwrite an existing environment file.
From `backend/`, run `npm run verify:staging`. The runner checks installed
0.1.1 packages and exercises the actual backend provider-capabilities, agents
and call-record routes, plus the telephony managed-number POST. It binds only
to loopback, prints no tenant records or credentials, and refuses other portal
URLs. It does not mint sessions, place calls, purchase numbers or modify agents.
This proves local backend-to-staging integration; it is not a hosted deployment
check. See `docs/BACKEND_SDK_STAGING_ROLLOUT.md` in the platform repository for
the deployment inventory, evidence and rollback order.

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

Choose a **dedicated test agent** from the agent picker. Its saved prompt appears beside the session controls. Edit the prompt, first speaker, and optional opening line, then use **Save prompt**; **Reset changes**, **Reload**, and **Copy prompt** act on that editor. Unsaved edits block connecting. Saved instructions apply to new sessions, including future phone calls using that agent. Prompt and greeting limits follow the platform (24,000 and 500 characters).

Choose language, STT/LLM/TTS providers, STT/LLM models, and voice from the live platform capabilities. **Apply pipeline** validates and saves the selection. **Start conversation** saves local pipeline edits before minting; unchanged selections skip that network step and use the agent's current server configuration. Refresh agents to reload changes made in another editor. Browsing the controls and loading the page do not update the agent. English uses the existing English providers; Pakistani Urdu and Urdu-English mixed tests use the existing Urdu route. There is no separate mixed-language API enum. Gladia's existing single-language limitation remains.

The page checks the deployed control plane and tenant API before loading the picker and enabling **Start conversation**. Initial backend preparation may take tens of seconds when the services are asleep; its status is visible above the controls. This checks backend health, not worker registration or provider readiness. After a minute of inactivity the next connect rechecks backend health. No session is minted and no agent dispatched during page preparation.

Connection settings contain the public key, editable agent ID, session/refresh endpoints, and timeout. When the frontend key is empty, the demo loads the backend's public key. Controls show loading states and lock conflicting edits during a session. Transcript controls copy or download the conversation. Diagnostics retain SDK errors, per-turn timing, playback readiness, and copy/clear actions. The expandable Telephony panel disables repeat actions while requests are pending.

Use **Start conversation**, grant microphone access, and click **Unlock audio** if blocked. **Mute mic** toggles the microphone and **End session** disconnects. The page reports room connection and playback readiness separately. Metrics are worker/SDK diagnostics; active-speaker signals and TTS TTFB do not prove caller-acoustic FUAW.

Read [TESTING.md](TESTING.md) for the humanization interaction matrix and [PLATFORM_TESTING.md](PLATFORM_TESTING.md) for platform-owned candidate settings. New audible candidates remain off until explicitly enabled on an isolated test worker.

See [the latency fix verification](LATENCY_FIX_VERIFICATION_2026-10-20.md) for current changes, run commands and received-audio measurements. The [earlier end-to-end audit](END_TO_END_VERIFICATION_2026-10-20.md) records the pre-fix failures. Warm startup improved, but remains about 9–10 seconds in the automated receiver; browser playback and listening quality remain unverified.

## Phone testing

The Telephony panel uses the backend-only telephony SDK. Check connection/readiness and assigned numbers before testing an existing inbound/outbound route. Number purchase and outbound calls incur provider charges; this app performs them only when you use those controls. Verify status and end reason in the dashboard Sessions/Telephony views. GitHub publication does not apply database migrations or provision phone routes.

Managed cards show the assigned agent and routing status. Numbers already in the managed list cannot be imported again. Assignment uses the SDK's automatic routing operation once; errors include the saved assignment/routing state when it can be verified. The panel refreshes state after an assignment error and enables outbound only when the selected number, agent, routing, tenant readiness, and E.164 destination pass its checks. Provisioning requests allow three minutes in the browser and two minutes per upstream SDK request. A timeout may leave a completed server action; refresh before retrying a mutation. Outbound calls are never retried automatically.

See [the telephony routing diagnosis](TELEPHONY_ROUTING_DIAGNOSIS_2026-10-20.md) for the active cross-tenant phone-number conflict found during the demo test. The deployed API's routing guard source fix requires deployment; local UI changes do not transfer an existing phone route.

See [the preserved inbound route verification](INBOUND_VERIFICATION_2026-10-20.md) for the carrier/dispatch checks, idle worker database fix, and isolated real-provider audio failure. The preserved route's Gemini reply timed out; inbound PSTN acceptance has not passed.

## Maintainer: optional historical SDK snapshots

Current clients install Voice from npm. The commands below create a candidate
snapshot for separate experiments; do not replace the registry pin or current
lockfile during this release rollout.

From the platform repository root, after SDK source changes:

```powershell
python scripts/package_client_voice.py
npm install --prefix client-integration-test/frontend
```

Commit the refreshed archive, manifest and frontend lockfile together. The packer builds the SDK and assigns a test-only prerelease version to a temporary package; it does not change the registry release or publish to npm. End clients never run this maintainer step.
