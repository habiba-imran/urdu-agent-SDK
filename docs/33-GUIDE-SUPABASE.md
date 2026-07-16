# 33-GUIDE-SUPABASE.md
Read when touching schema, migrations, RLS, or the MCP.

## 1. MCP config — mandatory, not advisory
```bash
claude mcp add supabase -e SUPABASE_ACCESS_TOKEN=$TOKEN -- \
  npx -y @supabase/mcp-server-supabase@latest \
  --read-only --project-ref=$DEV_REF --features=database,docs
```
| ✅ | ❌ |
|---|---|
| `--read-only` | write mode on real data |
| `--project-ref=<DEV>` | production, ever |
| `--features=database,docs` | all groups (every extra group = more reachable capability) |
| token in `-e` | token in args (**args land in git history**) |
| manual approval ON | auto-accept |
| scoped role | `service_role` (**bypasses RLS by design**) |

## 2. Why — the documented attack
General Analysis (~800pts HN): agent with `service_role` reads a poisoned support-ticket row →
follows the embedded instruction → SELECTs `integration_tokens` → writes them back into the thread
where the attacker reads them. RLS was enabled the whole time and did nothing, because service keys
bypass it by design.

🔴 **Read-only is necessary but NOT sufficient.** Willison's point: it closes the write-back leg,
but a read-only agent reading a poisoned row can still leak secrets **through its own output text**.
The durable fix is that production is never in reach. That is why H1 says two projects.

## 3. Migrations are code
`supabase/migrations/NNNN_name.sql`. Never click-ops. Never hand-edit `SCHEMA.md`/`RLS.md` —
`db-inspector` regenerates them.
🔴 **`make db-reset` must rebuild from zero.** Supabase free projects **pause after 7 days idle**.
Your dev DB will vanish over a weekend. Test the rebuild in Phase 1, not when it happens.

## 4. RLS
Every table. No exceptions. `rls_check.py` gates it.
The app path (Phase 3 worker) uses a scoped role with `tenant_id` in the JWT — RLS governs it.

🔴 **UPDATED per docs/40-ADR.md ADR-005 (2026-07-16): the agent IS now authorized to use
`service_role`** — reversing the original "migrations only, human-run, never read by the agent" rule.
But the authorization is NARROW: use `service_role` ONLY in the server-side control plane / token
mint, which authenticates tenants by HMAC (not a JWT) and must cross the tenant boundary before any
JWT exists. Everywhere RLS can already govern (tenant-scoped app reads), use the scoped
`authenticated` role — NOT service_role. `service_role` only ever touches DEV (uva-dev/uva-prod
split); production stays out of the agent's reach. Read ADR-005 for the full scope and rationale.

## 5. `db-inspector` is the ONLY agent that touches the MCP
Read-only tools, dev only, regenerates the two mirror files. Nothing else gets MCP access.
