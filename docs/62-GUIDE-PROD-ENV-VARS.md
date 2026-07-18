# 62-GUIDE-PROD-ENV-VARS.md — every env var each deployed service actually reads

P9. Complements `docs/61-GUIDE-DEV-TO-PROD.md` (which covers the *switches* — `UPLIFT_MODE`,
`STT_PROVIDER`, LiveKit tier, Supabase project) rather than duplicating it — this doc is the
literal, exhaustive, per-service inventory, verified by grepping every `os.environ`/`os.getenv`/
`dotenv_values` call site in `control_plane/` and `admin/` (2026-07-18), not assumed from
`.env.example`.

## control_plane (docker/control-plane.Dockerfile)

| Var | Read by | Currently lives | Prod requirement |
|---|---|---|---|
| `SUPABASE_DB_URL` | `scripts/dbconn.py::conn_kwargs()` | `.env.local` (dev) | **Required.** Real process env var — fixed 2026-07-18 to check `os.environ` first (previously `.env.local`-file-only, silently broken in a container). Points at `uva-prod`, not `uva-dev`, in production (H1 — human-only switch). |
| `LIVEKIT_URL` | `control_plane/app.py` | `.env.local` (dev) | **Required.** Same fix applied. Prod LiveKit project's URL. |
| `LIVEKIT_API_KEY` | `control_plane/app.py` | `.env.local` (dev) | **Required.** Prod LiveKit API key. |
| `LIVEKIT_API_SECRET` | `control_plane/app.py` | `.env.local` (dev) | **Required, secret.** Prod LiveKit API secret. |
| `CP_TENANT_SECRETS` | `control_plane/secrets.py::EnvSecretProvider` | `.env.local` (dev) | **Required, secret.** JSON map `{"<tenant_id>": "<raw HMAC secret>"}`. Already `os.environ`-first — no fix needed. ADR-005 flagged this as an OPEN decision: dev reads a flat JSON env var; prod should likely move to a real secret store (Supabase Vault / a secrets manager / an encrypted column) rather than one large JSON blob in an env var — not decided, not built here, flagged again since Phase 9 is exactly the point this should get decided. |

## admin (docker/admin.Dockerfile)

| Var | Read by | Currently lives | Prod requirement |
|---|---|---|---|
| `SUPABASE_DB_URL` | `scripts/dbconn.py::conn_kwargs()` | `.env.local` (dev) | Same as control_plane's row above — shared code path. |
| `ADMIN_JWT_SECRET` | `admin/app.py::_ensure_admin_jwt_secret()` | `.env.local` (dev, auto-generated there if absent) | **Required, secret — MUST be set explicitly.** Already `os.environ`-first, but the auto-generate-and-write-to-`.env.local` fallback is dev-only-safe and actively wrong in a container: a read-only filesystem (common on managed platforms) makes the write fail; a writable-but-ephemeral one makes it succeed and then evaporate on the next redeploy, minting a fresh secret and invalidating every existing admin session each time. Generate once (`python -c "import secrets; print(secrets.token_hex(32))"`, matching what the fallback itself would generate) and set it as a real platform secret. |
| `ADMIN_PORTAL_ORIGINS` | `admin/app.py` | `.env.local` (dev, defaults to `http://localhost:5173` if unset) | **Required — the dev default is a placeholder, not prod-safe.** Comma-separated CORS allowlist for the real prod admin-portal frontend origin(s). GATE 6 line 4 ("admin portal not reachable from the SDK's origin") depends on this being correct, not just non-empty — never a tenant/host-platform origin. |

## Not env vars, but part of the same "where does prod get this" question

- **`RATE_LIMIT_PER_MIN`** (`control_plane/app.py`, `= 120`) — a hardcoded Python constant, not
  configurable via env var at all. Confirmed deliberate (ADR-023). Changing it for prod needs a
  code change + a new ADR, not a config flip — flagged again here so it isn't missed while
  reading only the env-var table.
- **Per-tenant `max_concurrent`/`max_minutes_month`** — DB row values (`tenants` table), not env
  vars. Whatever provisions real prod tenants must set sane values — dev's test tenants have used
  values like `20` or `100000` deliberately to bypass quota during testing; those are not
  prod-appropriate defaults for a real tenant.

## What does NOT need a service-level env var

- **`UPLIFTAI_API_KEY`, `GLADIA_API_KEY`, `GOOGLE_API_KEY`, `STT_PROVIDER`, `UPLIFT_MODE`** — all
  worker-only (`config.py`, `worker/factories.py`). Neither `control_plane` nor `admin` imports
  anything that reads these. Not part of either Dockerfile's env surface. See
  `docs/61-GUIDE-DEV-TO-PROD.md` for the worker's own switches (worker deployment itself is
  deferred to Phase 12 — `docs/63-GUIDE-WORKER-DEPLOYMENT-DEFERRAL.md`).
- **`SUPABASE_SERVICE_ROLE`** — read only by `scripts/upload_voice_previews.py` (a human-run,
  one-off Storage script) and, previously, `db.py` (removed, ADR-022). Not read by
  `control_plane/` or `admin/` at all — confirmed by this doc's own grep. Not part of either
  service's deployed env surface.

## Verification

Every row above is sourced from a real grep of `os.environ`/`os.getenv`/`dotenv_values` call
sites in `control_plane/*.py` and `admin/*.py`, cross-checked against the actual live-import
test in `docker/control-plane.Dockerfile`'s and `docker/admin.Dockerfile`'s verification (both
apps constructed successfully with ONLY the vars listed above set, no `.env.local` file present
— see the Dockerfile commit). Nothing in this table is inferred from `.env.example`, which is
known to have had at least one real bug this session (`UPLIFT_API_KEY` vs. the correct
`UPLIFTAI_API_KEY` — P8-T05, unrelated to these two services but a reminder not to trust that
file blindly).
