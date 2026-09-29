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
npm run dev
```

Open `http://localhost:3000` → `/login`.
