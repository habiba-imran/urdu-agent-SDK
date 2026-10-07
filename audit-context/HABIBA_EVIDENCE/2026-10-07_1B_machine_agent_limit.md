# Evidence — M5-F01 machine agent limit bypass

**Date:** 2026-10-07  
**Method:** static read

## Portal path (enforced)

`tenant_portal_api/app.py` `create_agent_route` (~L683–L699):

- Counts agents for `x_tenant_id`
- If `existing[0] >= MAX_AGENTS_PER_TENANT` → HTTP 400 `agent limit reached`
- `MAX_AGENTS_PER_TENANT` from `PORTAL_MAX_AGENTS_PER_TENANT` default `100` (L153)

## Machine path (not enforced)

`machine_create_agent_route` (~L1107–L1158):

- Requires HMAC via `require_machine_auth`
- Calls `queries.create_agent(...)` directly
- No `COUNT` / `MAX_AGENTS_PER_TENANT` check in this function
- Grep: `MAX_AGENTS_PER_TENANT` only at L153, L695, L993 (delete docstring) — not in machine create

## Verdict

FAIL — machine create bypasses per-tenant agent quota.
