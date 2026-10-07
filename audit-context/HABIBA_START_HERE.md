# Habiba — start here

**Status (2026-10-07):** `HABIBA_BACKEND_FINAL` **PASS** + backlog remediations landed. Ehsan may start.

## Apply before hosted deploy

1. Set `TENANT_SECRET_ENCRYPTION_KEY` on CP + portal (startup **refuses** without it when hosted).
2. Run `python scripts/encrypt_tenant_secrets.py --finalize` after key is set.
3. Apply migrations **0037** (revoke telephony PostgREST writes) and **0038** (`telephony_webhook_claims`).
4. Set GitHub `PURGE_APPLY=true` when ready to delete expired media (dry-run now **fails** if pending rows exist).

## What was fixed (code)

| ID | Fix |
|---|---|
| M5-F01 / M11-F01 | Machine agent cap · portal create 403 |
| M1-F01 / M1-F02 | Hosted encryption key required · no env fallback on DB error |
| M4-F01 / M4-F02 / M4-F03 | Webhook hosted verify · durable claims inbox · LiveKit HTTP timeout |
| M7-F01 / M7-F02 | Sentry scrub · purge dry-run fails if pending |
| M11-F02 | Migration drops authenticated telephony write policies |

## Still deferred (ops / capacity)

- **M5-F02** — RLS vs postgres role (accepted → 2026-12-31)
- **M8-F01** — paste Render plan limits when you have dashboard access
- **M2-F01** — document global capacity = sum of tenant `max_concurrent`

## Ehsan

See [`HANDOFF_TO_EHSAN.md`](./HANDOFF_TO_EHSAN.md) — hide create-agent UI, verify client HMAC, worker quota release.
