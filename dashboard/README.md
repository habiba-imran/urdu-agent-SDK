# Urdu VaaS Tenant Dashboard

Next.js console for tenant self-service (credentials, agents, sessions, etc.).

## Auth (Phase 1)

Email + password via **Supabase Auth**. After login the dashboard exchanges the Supabase
session for a tenant portal JWT. Tenant ID / HMAC are **not** used as the human login.

See `docs/PHASE1-DASHBOARD-SUPABASE-AUTH.md` for setup.

## Quickstart

```bash
cp .env.example .env.local
# fill NEXT_PUBLIC_SUPABASE_* and portal/control-plane URLs
npm install
# Build the local browser SDK before first dev run:
npm --prefix ../sdk install
npm --prefix ../sdk run build
npm run dev
```

Open `http://localhost:3000` â†’ `/login`.

## Current testing surface

`/docs/humanization-testing` contains the client build/readiness and interaction matrix. `/test-studio` consumes the current repository voice SDK, shows room connection separately from browser playback readiness, and keeps the audio-unlock gesture. The production build already builds `../sdk`; for development build it first as above.

Use `client-integration-test/` for the independent client path: it ships a pinned, unpublished voice package snapshot and calls its own host backend. Test Studio alone is not proof of that integration. Candidate worker controls stay off by default; see the client's `PLATFORM_TESTING.md` for isolated operator comparisons. Git publication does not publish npm, apply migrations, configure service origins, deploy workers, or verify live audio.

Checks: `npm run typecheck`, `npm run build`. Existing backend/auth/telephony changes require their own runtime/deployment validation.
