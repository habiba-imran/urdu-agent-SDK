# Phase 1 — Dashboard Supabase Auth

## What shipped

- Dashboard login: **email + password** (Supabase Auth) — no tenant ID / HMAC on the login form
- `POST /portal/auth/supabase` — verifies Supabase `access_token`, resolves
  `auth_user_id → tenant_members → tenant_id`, issues the existing portal JWT (`sub` = tenant id)
- **First login** with no membership row: auto-creates `tenants` (+ HMAC credentials) and
  `tenant_members` with `role=owner`
- Existing `/portal/*` routes unchanged (still Bearer portal JWT)
- Migration: `supabase/migrations/0034_tenant_members.sql`
- Invite / member UI: Phase 2 (below)

## Local run

1. Apply migrations `0034` + `0035` on your Supabase DB.
2. Set portal env: `SUPABASE_JWT_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE`.
3. Set `dashboard/.env.local`:

```env
NEXT_PUBLIC_TENANT_PORTAL_API_URL=http://127.0.0.1:8002
NEXT_PUBLIC_CONTROL_PLANE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

4. Start portal + dashboard; create a user in Supabase Auth → Users; sign in on `/login`.

## Phase 2 — Members / invite

- `GET /portal/members` — list members for JWT tenant (`sub`)
- `POST /portal/members/invite` `{ "email" }` — **owner only**; creates/links Supabase Auth
  user via **service role** on the portal; inserts `tenant_members` (`role=member`,
  `status=invited`) on the inviter's tenant. Never accepts `tenant_id` from the client.
- Dashboard **Members** page (`/members`)
- Invited users must have a membership row **before** first login so Phase 1 bootstrap
  does not create a second tenant.

Portal env (in addition to Phase 1):

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE` (server only — never in `NEXT_PUBLIC_*`)

## Supabase configurations I need to do

(Copied into the agent reply as well — keep this list as the source of truth.)

### A. Database

1. Run migrations `0034_tenant_members.sql` and `0035_tenant_members_status.sql` against the **same** Postgres the portal uses (`SUPABASE_DB_URL`).

### B. Auth settings (invite-only for now)

1. Authentication → **Providers** → Email: enabled.
2. Authentication → **Providers** → Email → disable **Confirm email** for Phase 1 local testing **or** confirm the user after create (otherwise login fails until confirmed).
3. Authentication → **URL configuration**:
   - Site URL: `http://localhost:3000` (prod: your dashboard origin)
   - Redirect URLs: include `http://localhost:3000/**`
4. Authentication → **Policies / settings**: turn **off** public sign-ups if the toggle exists (“Allow new users to sign up”) so only users you create in the dashboard can authenticate. Phase 1 creates users manually under Authentication → Users.

### C. Create the first human user

1. Authentication → **Users** → **Add user** → Email + password (auto-confirm if offered).
2. Do **not** run `provision_demo_tenant.py` for this path — first dashboard login bootstraps the tenant.

### D. API keys / secrets for apps

1. Project Settings → **API**:
   - Copy **Project URL** → `NEXT_PUBLIC_SUPABASE_URL` (dashboard)
   - Copy **anon public** key → `NEXT_PUBLIC_SUPABASE_ANON_KEY` (dashboard)
   - Copy **JWT Secret** (Settings → API → JWT Secret, sometimes under Legacy) → `SUPABASE_JWT_SECRET` on **tenant portal** (Render + local `.env.local`). This is **not** the anon key.
2. Ensure portal `TENANT_PORTAL_ORIGINS` includes `http://localhost:3000` (and prod dashboard origin).
3. Staging Render tenant portal: add `SUPABASE_JWT_SECRET` and `SUPABASE_SERVICE_ROLE` (already has `SUPABASE_URL` if used for storage) → redeploy.

### E. Verify

1. `npm run dev` in `dashboard/` with env set.
2. Sign in with the Auth user email/password.
3. Credentials page should show publishable key (= tenant id) for the auto-created tenant.
4. Second login must keep the **same** tenant id.
